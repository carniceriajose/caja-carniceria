"""El rubro predeterminado: lo necesitan tanto el router de rubros (para
saber cuál es, y para validar que siempre quede uno) como la emisión de
facturas y el armado del comprobante (como mejor estimación para ventas de
antes de que existieran los rubros, igual que antes se usaba la alícuota de
configuración)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Rubro


def obtener_rubro_predeterminado(db: Session) -> Rubro | None:
    return db.scalar(select(Rubro).where(Rubro.es_predeterminado.is_(True)))


def alicuota_o_predeterminada(db: Session, alicuota_congelada: Decimal | None) -> Decimal:
    """La alícuota se congela en la venta (o en la anulación) al emitir, según
    el rubro elegido; esto es solo el resguardo para las de antes de que
    existiera eso."""
    if alicuota_congelada is not None:
        return alicuota_congelada
    predeterminado = obtener_rubro_predeterminado(db)
    return predeterminado.alicuota if predeterminado is not None else Decimal("0.00")
