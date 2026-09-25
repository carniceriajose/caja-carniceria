"""Reintento automático de las ventas que quedaron "pendiente" de facturar.
Se programa desde app.main para correr cada 1 minuto."""

import logging
import threading
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.arca.servicio import emitir_factura
from app.db import SesionLocal
from app.models import Venta

logger = logging.getLogger("arca.tareas")

TOPE_ESPERA_MINUTOS = 30

_fallos_consecutivos = 0
_proximo_intento_permitido: datetime | None = None
_candado_estado = threading.Lock()


def reintentar_pendientes() -> None:
    """Un ciclo del reintento. Si nada avanza (sin certificado, ARCA caído,
    o timeouts que siguen sin resolverse), espera cada vez más antes del
    próximo intento, hasta un tope de 30 minutos."""
    global _fallos_consecutivos, _proximo_intento_permitido

    ahora = datetime.now(timezone.utc)
    with _candado_estado:
        if _proximo_intento_permitido is not None and ahora < _proximo_intento_permitido:
            return

    with SesionLocal() as db:
        ventas = db.scalars(
            select(Venta).where(Venta.estado_arca == "pendiente").order_by(Venta.fecha_hora)
        ).all()

        if not ventas:
            with _candado_estado:
                _fallos_consecutivos = 0
                _proximo_intento_permitido = None
            return

        hubo_avance = False
        for venta in ventas:
            estado_antes = venta.estado_arca
            try:
                emitir_factura(db, venta)
            except Exception:  # noqa: BLE001 - una venta no puede tirar abajo el ciclo entero
                logger.exception("ARCA: fallo inesperado al reintentar la venta %s.", venta.id)
            if venta.estado_arca != estado_antes:
                hubo_avance = True

    with _candado_estado:
        if hubo_avance:
            _fallos_consecutivos = 0
            _proximo_intento_permitido = None
        else:
            _fallos_consecutivos += 1
            espera = min(2**_fallos_consecutivos, TOPE_ESPERA_MINUTOS)
            _proximo_intento_permitido = ahora + timedelta(minutes=espera)
            logger.warning(
                "ARCA: %s venta(s) siguen pendientes; próximo intento en %s minuto(s).",
                len(ventas),
                espera,
            )


def reiniciar_backoff() -> None:
    """Solo para los tests: vuelve el backoff a cero entre pruebas."""
    global _fallos_consecutivos, _proximo_intento_permitido
    with _candado_estado:
        _fallos_consecutivos = 0
        _proximo_intento_permitido = None


_programador: BackgroundScheduler | None = None


def iniciar_programador() -> None:
    global _programador
    if _programador is not None:
        return
    _programador = BackgroundScheduler(timezone="UTC")
    _programador.add_job(reintentar_pendientes, "interval", minutes=1, id="reintentar_pendientes")
    _programador.start()


def detener_programador() -> None:
    global _programador
    if _programador is not None:
        _programador.shutdown(wait=False)
        _programador = None
