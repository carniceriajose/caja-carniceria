"""Reporte de IVA por período: neto, IVA e importe total agrupados por
alícuota, para la contadora. Cada venta aporta su propio neto/IVA, calculados
con la alícuota con la que se facturó de verdad (congelada en la venta), así
la suma del reporte coincide centavo a centavo con lo que se le facturó a
cada cliente."""

from collections import OrderedDict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.arca.servicio import calcular_neto_iva
from app.dinero import CERO
from app.fechas import rango_utc
from app.models import Venta
from app.rubros import alicuota_o_predeterminada


def calcular_iva_por_periodo(db: Session, desde: date, hasta: date) -> list[dict]:
    """Solo ventas ya facturadas; una anulada no suma (la nota de crédito
    reversa lo que generó, igual que en el resumen general)."""
    inicio, fin = rango_utc(desde, hasta)
    filas = db.execute(
        select(Venta.tipo_comprobante, Venta.alicuota_iva, Venta.total)
        .where(
            Venta.fecha_hora >= inicio,
            Venta.fecha_hora < fin,
            Venta.anulada.is_(False),
            Venta.estado_arca == "facturada",
        )
        .execution_options(yield_per=500)
    )

    predeterminada: Decimal | None = None
    acumulado: "OrderedDict[Decimal, dict]" = OrderedDict()
    for tipo_comprobante, alicuota_congelada, total in filas:
        if alicuota_congelada is not None:
            alicuota = alicuota_congelada
        else:
            if predeterminada is None:
                predeterminada = alicuota_o_predeterminada(db, None)
            alicuota = predeterminada
        neto, iva = calcular_neto_iva(total, int(tipo_comprobante), alicuota)
        fila = acumulado.setdefault(
            alicuota, {"alicuota": alicuota, "neto": CERO, "iva": CERO, "total": CERO, "cantidad": 0}
        )
        fila["neto"] += neto
        fila["iva"] += iva
        fila["total"] += total
        fila["cantidad"] += 1

    return sorted(acumulado.values(), key=lambda f: f["alicuota"])
