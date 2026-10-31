from datetime import date, datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auditoria import registrar as registrar_auditoria
from app.db import get_db
from app.deps import requerir_admin, validar_rango_de_fechas
from app.dinero import CERO, redondear
from app.fechas import rango_utc
from app.models import Anulacion, CierreCaja, Usuario, Venta
from app.reportes.pdf import generar_pdf_cierre
from app.schemas import CierreAnularIn, CierreCrear, CierreOut, CierreTotalesOut, Pagina

router = APIRouter(prefix="/cierres", tags=["cierres"], dependencies=[Depends(requerir_admin)])

MEDIOS_DE_PAGO = ("efectivo", "tarjeta", "transferencia")


def calcular_totales_del_dia(db: Session, fecha: date) -> dict:
    """Los totales del sistema para un día (hora de Argentina), excluyendo lo
    anulado: lo mismo que muestra la previsualización, y lo que queda
    "fotografiado" en cada cierre."""
    inicio, fin = rango_utc(fecha, fecha)
    condiciones_ventas = (Venta.fecha_hora >= inicio, Venta.fecha_hora < fin, Venta.anulada.is_(False))

    totales_medio = {medio: CERO for medio in MEDIOS_DE_PAGO}
    cantidad_ventas = 0
    for medio, monto, cantidad in db.execute(
        select(Venta.medio_pago, func.sum(Venta.total), func.count())
        .where(*condiciones_ventas)
        .group_by(Venta.medio_pago)
    ):
        totales_medio[medio] = redondear(monto)
        cantidad_ventas += cantidad

    total_general = sum(totales_medio.values(), CERO)

    cantidad_anulaciones, monto_anulaciones = db.execute(
        select(func.count(), func.sum(Venta.total))
        .select_from(Anulacion)
        .join(Venta, Venta.id == Anulacion.venta_id)
        .where(Anulacion.fecha_hora >= inicio, Anulacion.fecha_hora < fin)
    ).one()

    return {
        "fecha": fecha,
        "total_general": total_general,
        "total_efectivo": totales_medio["efectivo"],
        "total_tarjeta": totales_medio["tarjeta"],
        "total_transferencia": totales_medio["transferencia"],
        "cantidad_ventas": cantidad_ventas,
        "cantidad_anulaciones": cantidad_anulaciones,
        "monto_anulaciones": redondear(monto_anulaciones),
    }


@router.get("/previsualizacion", response_model=CierreTotalesOut)
def previsualizar_cierre(fecha: date, db: Session = Depends(get_db)):
    return calcular_totales_del_dia(db, fecha)


@router.get("", response_model=Pagina[CierreOut])
def listar_cierres(
    desde: date | None = None,
    hasta: date | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    validar_rango_de_fechas(desde, hasta)

    condiciones = []
    if desde is not None:
        condiciones.append(CierreCaja.fecha >= desde)
    if hasta is not None:
        condiciones.append(CierreCaja.fecha <= hasta)

    total = db.scalar(select(func.count()).select_from(CierreCaja).where(*condiciones))
    filas = db.scalars(
        select(CierreCaja)
        .where(*condiciones)
        .order_by(CierreCaja.fecha.desc(), CierreCaja.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()
    return {"items": filas, "total": total, "pagina": pagina, "por_pagina": por_pagina}


@router.post("", response_model=CierreOut, status_code=status.HTTP_201_CREATED)
def crear_cierre(datos: CierreCrear, admin: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)):
    totales = calcular_totales_del_dia(db, datos.fecha)
    diferencia = datos.efectivo_contado - totales["total_efectivo"]

    cierre = CierreCaja(
        fecha=datos.fecha,
        usuario_id=admin.id,
        total_general=totales["total_general"],
        total_efectivo=totales["total_efectivo"],
        total_tarjeta=totales["total_tarjeta"],
        total_transferencia=totales["total_transferencia"],
        cantidad_ventas=totales["cantidad_ventas"],
        cantidad_anulaciones=totales["cantidad_anulaciones"],
        monto_anulaciones=totales["monto_anulaciones"],
        efectivo_contado=datos.efectivo_contado,
        diferencia=diferencia,
        observaciones=datos.observaciones,
        detalle={**{k: str(v) for k, v in totales.items() if k != "fecha"}, "fecha": totales["fecha"].isoformat()},
    )
    db.add(cierre)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya hay un cierre para ese día. Si tiene un error, anulalo y hacé uno nuevo.",
        ) from None

    registrar_auditoria(
        db,
        admin,
        "cierre.crear",
        {"fecha": datos.fecha.isoformat(), "diferencia": str(diferencia)},
        entidad="cierre_caja",
        entidad_id=cierre.id,
    )
    db.commit()
    return cierre


def _buscar(db: Session, cierre_id: int) -> CierreCaja:
    cierre = db.get(CierreCaja, cierre_id)
    if cierre is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cierre no encontrado.")
    return cierre


@router.post("/{cierre_id}/anular", response_model=CierreOut)
def anular_cierre(
    cierre_id: int, datos: CierreAnularIn, admin: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)
):
    cierre = _buscar(db, cierre_id)
    if cierre.anulado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Este cierre ya está anulado.")

    cierre.anulado = True
    cierre.anulado_motivo = datos.motivo
    cierre.anulado_por = admin.id
    cierre.anulado_en = datetime.now(timezone.utc)
    registrar_auditoria(
        db,
        admin,
        "cierre.anular",
        {"fecha": cierre.fecha.isoformat(), "motivo": datos.motivo},
        entidad="cierre_caja",
        entidad_id=cierre.id,
    )
    db.commit()
    return cierre


@router.get("/{cierre_id}.pdf")
def descargar_cierre_pdf(cierre_id: int, db: Session = Depends(get_db)):
    cierre = _buscar(db, cierre_id)
    pdf = generar_pdf_cierre(cierre)
    nombre = f"cierre_{cierre.fecha.isoformat()}.pdf"
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
