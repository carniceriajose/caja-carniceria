from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.arca.comprobante import armar_comprobante
from app.arca.servicio import emitir_factura
from app.config import get_settings
from app.db import SesionLocal, get_db
from app.deps import get_usuario_actual, requerir_admin, validar_rango_de_fechas
from app.fechas import rango_utc
from app.models import Usuario, Venta
from app.routers.configuracion import obtener_configuracion
from app.schemas import (
    ComprobanteOut,
    EstadoArca,
    MedioPago,
    Pagina,
    VentaCrear,
    VentaFiscalOut,
    VentaOut,
)

router = APIRouter(prefix="/ventas", tags=["ventas"])


def _emitir_en_segundo_plano(venta_id: int) -> None:
    """Corre después de responderle al vendedor: abre su propia sesión, la del
    pedido ya se cerró para cuando esto se ejecuta."""
    with SesionLocal() as db:
        venta = db.get(Venta, venta_id)
        if venta is not None:
            emitir_factura(db, venta)


def _venta_ya_creada(existente: Venta, datos: VentaCrear, usuario: Usuario, response: Response) -> Venta:
    """El mismo id_cliente con los mismos datos es un reintento: se devuelve la venta original.
    Si los datos difieren es un error del frontend, y no se puede devolver una venta ajena
    como si fuera la que el vendedor acaba de cobrar."""
    if (
        existente.total != datos.total
        or existente.medio_pago != datos.medio_pago
        or existente.vendedor_id != usuario.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese id_cliente ya se usó en otra venta con datos distintos.",
        )
    response.status_code = status.HTTP_200_OK
    return existente


@router.post("", response_model=VentaOut, status_code=status.HTTP_201_CREATED)
def crear_venta(
    datos: VentaCrear,
    response: Response,
    background_tasks: BackgroundTasks,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    existente = db.scalar(select(Venta).where(Venta.id_cliente == datos.id_cliente))
    if existente is not None:
        venta = _venta_ya_creada(existente, datos, usuario, response)
        if venta.estado_arca == "pendiente":
            background_tasks.add_task(_emitir_en_segundo_plano, venta.id)
        return venta

    configuracion = obtener_configuracion(db)
    se_factura = getattr(configuracion, f"facturar_{datos.medio_pago}")

    venta = Venta(
        id_cliente=datos.id_cliente,
        total=datos.total,
        medio_pago=datos.medio_pago,
        vendedor_id=usuario.id,
        estado_arca="pendiente" if se_factura else "no_aplica",
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
        return _venta_ya_creada(existente, datos, usuario, response)

    # La respuesta al vendedor no espera a ARCA: la factura se emite después.
    if venta.estado_arca == "pendiente":
        background_tasks.add_task(_emitir_en_segundo_plano, venta.id)
    return venta


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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="La venta todavía no tiene comprobante."
        )
    return armar_comprobante(venta, get_settings())


@router.get("/{venta_id}/fiscal", response_model=VentaFiscalOut)
def ver_estado_fiscal(
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
            detail="No tiene permiso para ver el estado fiscal de esta venta.",
        )
    return venta
