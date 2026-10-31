"""Redondeo de plata compartido entre reportes: siempre a 2 decimales, siempre
Decimal, nunca None (una suma vacía es CERO, no null)."""

from decimal import Decimal

CERO = Decimal("0.00")


def redondear(valor) -> Decimal:
    return CERO if valor is None else Decimal(valor).quantize(CERO)


def formatear_ar(valor: Decimal) -> str:
    """Para los reportes: "$ 1.250,50", con separador de miles argentino."""
    entero, _, decimales = f"{valor:,.2f}".partition(".")
    return f"$ {entero.replace(',', '.')},{decimales}"
