from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.arca.comprobante import armar_comprobante, armar_comprobante_nota_credito
from app.arca.servicio import emitir_factura, emitir_nota_credito
from app.auditoria import registrar as registrar_auditoria
from app.config import get_settings
from app.configuracion import obtener_configuracion
from app.db import SesionLocal, get_db
from app.deps import get_usuario_actual, requerir_admin, validar_rango_de_fechas
from app.dinero import formatear_ar, redondear
from app.fechas import rango_utc
from app.models import Anulacion, Configuracion, Rubro, Tarjeta, Usuario, Venta
from app.schemas import (
    ComprobanteOut,
    EstadoArca,
    MedioPago,
    Pagina,
    VentaAnularIn,
    VentaCrear,
    VentaFiscalOut,
    VentaOut,
    VentaRegistradaOut,
)

router = APIRouter(prefix="/ventas", tags=["ventas"])


def _emitir_en_segundo_plano(venta_id: int) -> None:
    """Corre después de responderle al vendedor: abre su propia sesión, la del
    pedido ya se cerró para cuando esto se ejecuta."""
    with SesionLocal() as db:
        venta = db.get(Venta, venta_id)
        if venta is not None:
            emitir_factura(db, venta)


def _emitir_nota_credito_en_segundo_plano(anulacion_id: int) -> None:
    with SesionLocal() as db:
        anulacion = db.get(Anulacion, anulacion_id)
        if anulacion is not None and anulacion.estado in ("pendiente", "fallo"):
            venta = db.get(Venta, anulacion.venta_id)
            if venta is not None:
                emitir_nota_credito(db, venta, anulacion)


def _venta_ya_creada(existente: Venta, datos: VentaCrear, usuario: Usuario, response: Response) -> Venta:
    """El mismo id_cliente con los mismos datos es un reintento: se devuelve la venta original.
    Si los datos difieren es un error del frontend, y no se puede devolver una venta ajena
    como si fuera la que el vendedor acaba de cobrar."""
    if (
        existente.subtotal != datos.subtotal
        or existente.medio_pago != datos.medio_pago
        or existente.vendedor_id != usuario.id
        or existente.tarjeta_id != datos.tarjeta_id
        or existente.rubro_id != datos.rubro_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese id_cliente ya se usó en otra venta con datos distintos.",
        )
    response.status_code = status.HTTP_200_OK
    return existente


def _calcular_montos(
    subtotal: Decimal, medio_pago: str, tarjeta: Tarjeta | None, configuracion: Configuracion
) -> tuple[Decimal, str | None, str | None, Decimal | None, str | None]:
    """El único ajuste es el recargo automático del medio de pago (efectivo
    nunca lo tiene; en tarjeta depende de cuál se haya elegido). Lo que
    devuelve queda congelado en la venta: un cambio posterior en la
    configuración o en la tarjeta nunca altera una venta ya cobrada."""
    if medio_pago == "tarjeta":
        porcentaje = tarjeta.recargo_porcentaje
        etiqueta = tarjeta.nombre
    elif medio_pago == "transferencia":
        porcentaje = configuracion.recargo_transferencia_porcentaje
        etiqueta = "transferencia"
    else:
        porcentaje = Decimal("0")
        etiqueta = None

    if porcentaje <= 0:
        return subtotal, None, None, None, None

    monto = redondear(subtotal * porcentaje / Decimal("100"))
    detalle = f"Recargo por {etiqueta} {porcentaje}% (+{formatear_ar(monto)})"
    return subtotal + monto, "recargo", "medio_pago", monto, detalle


def _respuesta_venta(venta: Venta, usuario: Usuario) -> VentaOut | VentaRegistradaOut:
    """El estado fiscal (y todo dato fiscal) es información administrativa: el
    vendedor solo se entera de que la venta quedó registrada, nunca de esto.
    `response_model=None` en la ruta es a propósito, para que este chequeo de
    rol sea lo único que decide qué campos viajan."""
    if usuario.rol == "admin":
        return VentaOut.model_validate(venta)
    return VentaRegistradaOut.model_validate(venta)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=None)
def crear_venta(
    datos: VentaCrear,
    response: Response,
    background_tasks: BackgroundTasks,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
) -> VentaOut | VentaRegistradaOut:
    existente = db.scalar(select(Venta).where(Venta.id_cliente == datos.id_cliente))
    if existente is not None:
        venta = _venta_ya_creada(existente, datos, usuario, response)
        if venta.estado_arca == "pendiente":
            background_tasks.add_task(_emitir_en_segundo_plano, venta.id)
        return _respuesta_venta(venta, usuario)

    tarjeta = None
    if datos.medio_pago == "tarjeta":
        if datos.tarjeta_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Elegí con qué tarjeta se cobró.")
        tarjeta = db.get(Tarjeta, datos.tarjeta_id)
        if tarjeta is None or not tarjeta.activa:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="La tarjeta elegida no está disponible."
            )
    elif datos.tarjeta_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tarjeta_id solo se usa cuando el medio de pago es tarjeta.",
        )

    rubro = db.get(Rubro, datos.rubro_id)
    if rubro is None or not rubro.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El rubro elegido no está disponible.")

    configuracion = obtener_configuracion(db)
    se_factura = getattr(configuracion, f"facturar_{datos.medio_pago}")

    total, ajuste_tipo, ajuste_origen, ajuste_monto, ajuste_detalle = _calcular_montos(
        datos.subtotal, datos.medio_pago, tarjeta, configuracion
    )

    venta = Venta(
        id_cliente=datos.id_cliente,
        subtotal=datos.subtotal,
        ajuste_tipo=ajuste_tipo,
        ajuste_origen=ajuste_origen,
        ajuste_monto=ajuste_monto,
        ajuste_detalle=ajuste_detalle,
        total=total,
        medio_pago=datos.medio_pago,
        tarjeta_id=tarjeta.id if tarjeta else None,
        tarjeta_nombre=tarjeta.nombre if tarjeta else None,
        tarjeta_recargo_porcentaje=tarjeta.recargo_porcentaje if tarjeta else None,
        tarjeta_tipo=tarjeta.tipo if tarjeta else None,
        vendedor_id=usuario.id,
        estado_arca="pendiente" if se_factura else "no_aplica",
        # Congelados al cobrar: si el rubro cambia de nombre, de descripción o
        # de alícuota después, no tiene que alterar esta venta.
        rubro_id=rubro.id,
        rubro_nombre=rubro.nombre,
        descripcion_factura=rubro.descripcion_factura,
        alicuota_iva=rubro.alicuota,
    )
    db.add(venta)
    try:
        db.commit()
    except IntegrityError:
        # Dos pedidos con el mismo id_cliente llegaron a la vez: gana el primero.
        db.rollback()
        existente = db.scalar(select(Venta).where(Venta.id_cliente == datos.id_cliente))
        if existente is None:
            raise
        return _respuesta_venta(_venta_ya_creada(existente, datos, usuario, response), usuario)

    # La respuesta al vendedor no espera a ARCA: la factura se emite después.
    if venta.estado_arca == "pendiente":
        background_tasks.add_task(_emitir_en_segundo_plano, venta.id)
    return _respuesta_venta(venta, usuario)


@router.get("", response_model=Pagina[VentaOut], dependencies=[Depends(requerir_admin)])
def listar_ventas(
    desde: date | None = None,
    hasta: date | None = None,
    medio_pago: MedioPago | None = None,
    estado_arca: EstadoArca | None = None,
    vendedor_id: int | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    validar_rango_de_fechas(desde, hasta)
    inicio, fin = rango_utc(desde, hasta)

    condiciones = []
    if inicio is not None:
        condiciones.append(Venta.fecha_hora >= inicio)
    if fin is not None:
        condiciones.append(Venta.fecha_hora < fin)
    if medio_pago is not None:
        condiciones.append(Venta.medio_pago == medio_pago)
    if estado_arca is not None:
        condiciones.append(Venta.estado_arca == estado_arca)
    if vendedor_id is not None:
        condiciones.append(Venta.vendedor_id == vendedor_id)

    total = db.scalar(select(func.count()).select_from(Venta).where(*condiciones))
    ventas = db.scalars(
        select(Venta)
        .where(*condiciones)
        .order_by(Venta.fecha_hora.desc(), Venta.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()
    return {"items": ventas, "total": total, "pagina": pagina, "por_pagina": por_pagina}


@router.get("/{venta_id}", response_model=VentaOut, dependencies=[Depends(requerir_admin)])
def ver_venta(venta_id: int, db: Session = Depends(get_db)):
    venta = db.get(Venta, venta_id)
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    return venta


@router.get("/{venta_id}/comprobante", response_model=ComprobanteOut)
def ver_comprobante(
    venta_id: int,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    venta = db.get(Venta, venta_id)
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    if usuario.rol != "admin" and venta.vendedor_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para ver el comprobante de esta venta.",
        )
    if venta.estado_arca != "facturada":
        # Mensaje neutro a propósito, sin importar si está pendiente o si falló:
        # el motivo del error (si lo hay) es información administrativa, no
        # algo que se le muestre a quien pide el comprobante.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El comprobante todavía no está disponible."
        )
    return armar_comprobante(db, venta, obtener_configuracion(db), get_settings().arca_cuit)


@router.get("/{venta_id}/nota-credito/comprobante", response_model=ComprobanteOut)
def ver_comprobante_nota_credito(
    venta_id: int,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    venta = db.get(Venta, venta_id)
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    if usuario.rol != "admin" and venta.vendedor_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para ver el comprobante de esta venta.",
        )
    anulacion = venta.anulacion
    if anulacion is None or anulacion.estado != "emitida":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El comprobante todavía no está disponible."
        )
    return armar_comprobante_nota_credito(db, anulacion, venta, obtener_configuracion(db), get_settings().arca_cuit)


@router.get("/{venta_id}/fiscal", response_model=VentaFiscalOut, dependencies=[Depends(requerir_admin)])
def ver_estado_fiscal(venta_id: int, db: Session = Depends(get_db)):
    """Solo admin: el estado interno de facturación (pendiente/fallo/CAE, etc.)
    nunca se le devuelve al vendedor. Para que el vendedor sepa si ya puede
    imprimir, el frontend consulta directamente /comprobante (ver Venta.jsx)."""
    venta = db.get(Venta, venta_id)
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    return venta


def _puede_anular_como_vendedor(db: Session, usuario: Usuario, venta: Venta) -> bool:
    """El vendedor solo puede anular SU última venta, y solo dentro de la
    ventana configurada: pasado ese tiempo (o si cobró otra venta después),
    se lo tiene que pedir a un administrador."""
    if venta.vendedor_id != usuario.id:
        return False
    ultima_id = db.scalar(
        select(Venta.id)
        .where(Venta.vendedor_id == usuario.id)
        .order_by(Venta.fecha_hora.desc(), Venta.id.desc())
        .limit(1)
    )
    if ultima_id != venta.id:
        return False
    fecha_venta = venta.fecha_hora if venta.fecha_hora.tzinfo else venta.fecha_hora.replace(tzinfo=timezone.utc)
    limite = timedelta(minutes=obtener_configuracion(db).anulacion_minutos_vendedor)
    return datetime.now(timezone.utc) - fecha_venta <= limite


@router.post("/{venta_id}/anular", status_code=status.HTTP_200_OK, response_model=None)
def anular_venta(
    venta_id: int,
    datos: VentaAnularIn,
    background_tasks: BackgroundTasks,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
) -> VentaOut | VentaRegistradaOut:
    venta = db.get(Venta, venta_id)
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")

    es_admin = usuario.rol == "admin"
    if not es_admin and not _puede_anular_como_vendedor(db, usuario, venta):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Ya pasaron los {obtener_configuracion(db).anulacion_minutos_vendedor} minutos, o no es "
                "tu última venta: pedile a un administrador que la anule."
            ),
        )
    if venta.anulada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta venta ya está anulada.")
    if venta.estado_arca == "pendiente":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Todavía se está facturando esta venta: esperá a que quede facturada o con error antes de anularla.",
        )

    # Si ya tiene CAE hace falta una nota de crédito; si no, no hay nada que
    # reversar ante ARCA y queda anulada al instante.
    necesita_nota_credito = venta.estado_arca == "facturada"
    anulacion = Anulacion(
        venta_id=venta.id,
        motivo=datos.motivo,
        usuario_id=usuario.id,
        estado="pendiente" if necesita_nota_credito else "sin_comprobante",
    )
    db.add(anulacion)
    venta.anulada = True
    venta.anulada_por = usuario.id
    venta.anulada_en = datetime.now(timezone.utc)
    db.flush()
    registrar_auditoria(
        db,
        usuario,
        "venta.anular",
        {"venta_id": venta.id, "motivo": datos.motivo, "anulacion_id": anulacion.id},
        entidad="venta",
        entidad_id=venta.id,
    )
    db.commit()

    if necesita_nota_credito:
        background_tasks.add_task(_emitir_nota_credito_en_segundo_plano, anulacion.id)

    db.refresh(venta)
    return _respuesta_venta(venta, usuario)
