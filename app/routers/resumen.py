from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import requerir_admin, validar_rango_de_fechas
from app.fechas import dia_local, mes_local, rango_utc
from app.models import CategoriaGasto, Gasto, Venta
from app.schemas import ResumenOut

router = APIRouter(prefix="/resumen", tags=["resumen"], dependencies=[Depends(requerir_admin)])

MEDIOS_DE_PAGO = ("efectivo", "tarjeta", "transferencia")
ESTADOS_FISCALES = ("no_aplica", "pendiente", "facturada", "fallo")
DIAS_MAXIMOS_PARA_SERIE_DIARIA = 62
DIAS_MAXIMOS_DEL_RANGO = 3660
CERO = Decimal("0.00")


def _dinero(valor) -> Decimal:
    return CERO if valor is None else Decimal(valor).quantize(CERO)


def _periodos(desde: date, hasta: date, por_mes: bool) -> list[date]:
    if not por_mes:
        return [desde + timedelta(days=n) for n in range((hasta - desde).days + 1)]
    periodos = []
    actual = desde.replace(day=1)
    while actual <= hasta:
        periodos.append(actual)
        actual = (actual + timedelta(days=32)).replace(day=1)
    return periodos


@router.get("", response_model=ResumenOut)
def resumen(desde: date, hasta: date, db: Session = Depends(get_db)):
    validar_rango_de_fechas(desde, hasta)
    dias = (hasta - desde).days + 1
    if dias > DIAS_MAXIMOS_DEL_RANGO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El rango no puede superar los 10 años.",
        )

    inicio, fin = rango_utc(desde, hasta)
    ventas_del_periodo = (Venta.fecha_hora >= inicio, Venta.fecha_hora < fin)

    # Todas las sumas se hacen en la base: acá solo llegan los totales ya agrupados.
    por_medio = {medio: (CERO, 0) for medio in MEDIOS_DE_PAGO}
    for medio, monto, cantidad in db.execute(
        select(Venta.medio_pago, func.sum(Venta.total), func.count())
        .where(*ventas_del_periodo)
        .group_by(Venta.medio_pago)
    ):
        por_medio[medio] = (_dinero(monto), cantidad)

    por_estado = {estado: (CERO, 0) for estado in ESTADOS_FISCALES}
    for estado, monto, cantidad in db.execute(
        select(Venta.estado_arca, func.sum(Venta.total), func.count())
        .where(*ventas_del_periodo)
        .group_by(Venta.estado_arca)
    ):
        por_estado[estado] = (_dinero(monto), cantidad)

    total_vendido = sum((monto for monto, _ in por_medio.values()), CERO)
    cantidad_ventas = sum(cantidad for _, cantidad in por_medio.values())

    gastos_del_periodo = (Gasto.fecha >= desde, Gasto.fecha <= hasta)
    gastos_por_categoria = [
        {"categoria_id": categoria_id, "categoria": nombre, "monto": _dinero(monto), "cantidad": cantidad}
        for categoria_id, nombre, monto, cantidad in db.execute(
            select(CategoriaGasto.id, CategoriaGasto.nombre, func.sum(Gasto.monto), func.count())
            .join(Gasto, Gasto.categoria_id == CategoriaGasto.id)
            .where(*gastos_del_periodo)
            .group_by(CategoriaGasto.id, CategoriaGasto.nombre)
            .order_by(func.sum(Gasto.monto).desc())
        )
    ]
    total_gastos = sum((g["monto"] for g in gastos_por_categoria), CERO)

    por_mes = dias > DIAS_MAXIMOS_PARA_SERIE_DIARIA
    periodo = mes_local(Venta.fecha_hora) if por_mes else dia_local(Venta.fecha_hora)
    montos_por_periodo: dict[date, dict[str, Decimal]] = {}
    for dia, medio, monto in db.execute(
        select(periodo, Venta.medio_pago, func.sum(Venta.total))
        .where(*ventas_del_periodo)
        .group_by(periodo, Venta.medio_pago)
    ):
        montos_por_periodo.setdefault(dia, {})[medio] = _dinero(monto)

    serie = []
    for dia in _periodos(desde, hasta, por_mes):
        montos = montos_por_periodo.get(dia, {})
        efectivo, tarjeta, transferencia = (montos.get(m, CERO) for m in MEDIOS_DE_PAGO)
        serie.append(
            {
                "periodo": dia,
                "efectivo": efectivo,
                "tarjeta": tarjeta,
                "transferencia": transferencia,
                "total": efectivo + tarjeta + transferencia,
            }
        )

    return {
        "desde": desde,
        "hasta": hasta,
        "total_vendido": total_vendido,
        "cantidad_ventas": cantidad_ventas,
        "por_medio_pago": [
            {"medio_pago": m, "monto": por_medio[m][0], "cantidad": por_medio[m][1]}
            for m in MEDIOS_DE_PAGO
        ],
        "por_estado_fiscal": [
            {"estado_arca": e, "monto": por_estado[e][0], "cantidad": por_estado[e][1]}
            for e in ESTADOS_FISCALES
        ],
        "total_gastos": total_gastos,
        "resultado": total_vendido - total_gastos,
        "gastos_por_categoria": gastos_por_categoria,
        "agrupacion": "mes" if por_mes else "dia",
        "serie": serie,
    }
