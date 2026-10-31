from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.configuracion import obtener_configuracion
from app.db import get_db
from app.deps import requerir_admin, validar_rango_de_fechas
from app.fechas import rango_utc
from app.models import CategoriaGasto, Gasto, Usuario, Venta
from app.reportes.excel import generar_excel_gastos, generar_excel_iva, generar_excel_ventas
from app.reportes.iva import calcular_iva_por_periodo
from app.reportes.pdf import generar_pdf_gastos, generar_pdf_iva, generar_pdf_resumen
from app.routers.resumen import calcular_resumen

router = APIRouter(prefix="/reportes", tags=["reportes"], dependencies=[Depends(requerir_admin)])

DIAS_MAXIMOS_DEL_RANGO = 366


def _validar_rango(desde: date, hasta: date) -> None:
    validar_rango_de_fechas(desde, hasta)
    if (hasta - desde).days + 1 > DIAS_MAXIMOS_DEL_RANGO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El rango no puede superar un año.",
        )


def _adjunto(contenido: bytes, nombre: str, tipo: str) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(contenido), media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nombre}"'}
    )


@router.get("/ventas.xlsx")
def reporte_ventas_excel(desde: date, hasta: date, db: Session = Depends(get_db)):
    _validar_rango(desde, hasta)
    inicio, fin = rango_utc(desde, hasta)

    Vendedor = aliased(Usuario)
    filas = db.execute(
        select(Venta, Vendedor.nombre)
        .join(Vendedor, Vendedor.id == Venta.vendedor_id)
        .where(Venta.fecha_hora >= inicio, Venta.fecha_hora < fin)
        .order_by(Venta.fecha_hora)
        .execution_options(yield_per=500)
    )
    contenido = generar_excel_ventas(filas)
    return _adjunto(
        contenido,
        f"ventas_{desde.isoformat()}_{hasta.isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/gastos.xlsx")
def reporte_gastos_excel(desde: date, hasta: date, db: Session = Depends(get_db)):
    _validar_rango(desde, hasta)

    filas = db.execute(
        select(Gasto, CategoriaGasto.nombre, Usuario.nombre)
        .join(CategoriaGasto, CategoriaGasto.id == Gasto.categoria_id)
        .join(Usuario, Usuario.id == Gasto.creado_por)
        .where(Gasto.fecha >= desde, Gasto.fecha <= hasta)
        .order_by(CategoriaGasto.nombre, Gasto.fecha)
        .execution_options(yield_per=500)
    )
    contenido = generar_excel_gastos(filas)
    return _adjunto(
        contenido,
        f"gastos_{desde.isoformat()}_{hasta.isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/resumen.pdf")
def reporte_resumen_pdf(desde: date, hasta: date, db: Session = Depends(get_db)):
    _validar_rango(desde, hasta)
    resumen = calcular_resumen(db, desde, hasta)
    contenido = generar_pdf_resumen(resumen, obtener_configuracion(db))
    return _adjunto(contenido, f"resumen_{desde.isoformat()}_{hasta.isoformat()}.pdf", "application/pdf")


@router.get("/gastos.pdf")
def reporte_gastos_pdf(desde: date, hasta: date, db: Session = Depends(get_db)):
    _validar_rango(desde, hasta)

    filas = db.execute(
        select(Gasto, CategoriaGasto.nombre)
        .join(CategoriaGasto, CategoriaGasto.id == Gasto.categoria_id)
        .where(Gasto.fecha >= desde, Gasto.fecha <= hasta)
        .order_by(CategoriaGasto.nombre, Gasto.fecha)
        .execution_options(yield_per=500)
    )
    contenido = generar_pdf_gastos(filas, desde, hasta, obtener_configuracion(db))
    return _adjunto(contenido, f"gastos_{desde.isoformat()}_{hasta.isoformat()}.pdf", "application/pdf")


@router.get("/iva.xlsx")
def reporte_iva_excel(desde: date, hasta: date, db: Session = Depends(get_db)):
    _validar_rango(desde, hasta)
    filas = calcular_iva_por_periodo(db, desde, hasta)
    contenido = generar_excel_iva(filas, desde, hasta)
    return _adjunto(
        contenido,
        f"iva_{desde.isoformat()}_{hasta.isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/iva.pdf")
def reporte_iva_pdf(desde: date, hasta: date, db: Session = Depends(get_db)):
    _validar_rango(desde, hasta)
    filas = calcular_iva_por_periodo(db, desde, hasta)
    contenido = generar_pdf_iva(filas, desde, hasta, obtener_configuracion(db))
    return _adjunto(contenido, f"iva_{desde.isoformat()}_{hasta.isoformat()}.pdf", "application/pdf")
