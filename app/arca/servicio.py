"""Lógica de negocio de la facturación: cuánto neto/IVA calcular, qué número
pedir, cómo evitar pedir el mismo número dos veces y qué hacer si ARCA no
contesta a tiempo. No sabe nada de HTTP ni de FastAPI.
"""

import logging
import threading
from contextlib import contextmanager
from datetime import date as Fecha
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.arca import wsaa, wsfe
from app.config import get_settings
from app.fechas import hoy_argentina
from app.models import Venta

logger = logging.getLogger("arca.servicio")

FACTURA_B = 6
FACTURA_C = 11
CERO = Decimal("0.00")

# Tabla oficial de Ids de alícuota de IVA de ARCA (WSFE).
IDS_ALICUOTA_IVA = {
    Decimal("0"): 3,
    Decimal("10.5"): 4,
    Decimal("21"): 5,
    Decimal("27"): 6,
    Decimal("5"): 8,
    Decimal("2.5"): 9,
}

# Lock de proceso + pg_advisory_lock: para que dos ventas no pidan el mismo
# número de comprobante al mismo tiempo. La clave es arbitraria pero fija.
_CANDADO_PROCESO = threading.Lock()
_CLAVE_ADVISORY_LOCK = 875_501_001


@contextmanager
def _bloqueo_de_emision(db: Session):
    with _CANDADO_PROCESO:
        es_postgres = db.bind.dialect.name == "postgresql"
        if es_postgres:
            db.execute(text("select pg_advisory_lock(:clave)"), {"clave": _CLAVE_ADVISORY_LOCK})
        try:
            yield
        finally:
            if es_postgres:
                db.execute(text("select pg_advisory_unlock(:clave)"), {"clave": _CLAVE_ADVISORY_LOCK})


def calcular_neto_iva(total: Decimal, tipo_comprobante: int, alicuota: Decimal) -> tuple[Decimal, Decimal]:
    """Siempre en Decimal. Factura C no discrimina IVA (neto = total, IVA = 0).
    Factura B: neto = total / (1 + alícuota) redondeado a 2 decimales, e
    IVA = total - neto, así los dos suman exactamente el total (nunca queda
    un centavo de diferencia por el redondeo)."""
    if tipo_comprobante == FACTURA_B:
        neto = (total / (1 + alicuota / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        iva = total - neto
        return neto, iva
    return total, CERO


def armar_detalle(numero: int, fecha: str, total: Decimal, neto: Decimal, iva: Decimal, tipo_comprobante: int, alicuota: Decimal) -> dict:
    detalle = {
        "Concepto": 1,
        "DocTipo": 99,
        "DocNro": 0,
        "CondicionIVAReceptorId": 5,
        "CbteDesde": numero,
        "CbteHasta": numero,
        "CbteFch": fecha,
        "ImpTotal": total,
        "ImpTotConc": CERO,
        "ImpNeto": neto,
        "ImpOpEx": CERO,
        "ImpTrib": CERO,
        "ImpIVA": iva,
        "MonId": "PES",
        "MonCotiz": 1,
    }
    if tipo_comprobante == FACTURA_B:
        id_alicuota = IDS_ALICUOTA_IVA.get(alicuota)
        if id_alicuota is None:
            raise ValueError(f"No hay un Id de alícuota de IVA de ARCA para {alicuota}%.")
        detalle["Iva"] = {"AlicIva": [{"Id": id_alicuota, "BaseImp": neto, "Importe": iva}]}
    return detalle


def _normalizar_detalle(detalle_resp: dict, respuesta_completa: dict) -> dict:
    aprobado = (detalle_resp or {}).get("Resultado") == "A"
    observaciones = ((detalle_resp or {}).get("Observaciones") or {}).get("Obs") or []
    motivo = "; ".join(f"{o.get('Code')}: {o.get('Msg')}" for o in observaciones)
    if not aprobado and not motivo:
        errores = (respuesta_completa.get("Errors") or {}).get("Err") or []
        motivo = "; ".join(f"{e.get('Code')}: {e.get('Msg')}" for e in errores) or "ARCA rechazó el comprobante."
    return {
        "aprobado": aprobado,
        "cae": (detalle_resp or {}).get("CAE"),
        "cae_vencimiento": (detalle_resp or {}).get("CAEFchVto"),
        "motivo": motivo,
        "respuesta_completa": respuesta_completa,
    }


def _normalizar_respuesta_solicitud(respuesta: dict) -> dict:
    detalles = (respuesta.get("FeDetResp") or {}).get("FECAEDetResponse") or [{}]
    return _normalizar_detalle(detalles[0], respuesta)


def _normalizar_respuesta_consulta(resultado_get: dict) -> dict:
    return _normalizar_detalle(resultado_get, {"ResultGet": resultado_get})


def _fecha_desde_arca(texto: str | None) -> Fecha | None:
    if not texto or len(texto) != 8:
        return None
    return Fecha(int(texto[0:4]), int(texto[4:6]), int(texto[6:8]))


def _guardar_resultado(db: Session, venta: Venta, tipo: int, punto_venta: int, numero: int, resultado: dict) -> None:
    venta.respuesta_fiscal = resultado["respuesta_completa"]
    if resultado["aprobado"]:
        venta.estado_arca = "facturada"
        venta.tipo_comprobante = str(tipo)
        venta.punto_venta = punto_venta
        venta.numero_comprobante = numero
        venta.cae = resultado["cae"]
        venta.cae_vencimiento = _fecha_desde_arca(resultado["cae_vencimiento"])
        venta.error_detalle = None
    else:
        venta.estado_arca = "fallo"
        venta.error_detalle = resultado["motivo"]
    db.commit()


def _resolver_tras_timeout(ticket, punto_venta: int, tipo: int, numero: int) -> dict | None:
    """Nunca se vuelve a pedir un número a ciegas después de un timeout: se
    consulta primero si ARCA terminó de procesar el pedido anterior."""
    try:
        resultado_get = wsfe.consultar_comprobante(ticket, punto_venta, tipo, numero)
    except Exception:
        logger.exception("ARCA: FECompConsultar también falló después del timeout.")
        return None
    if resultado_get is None:
        return None
    return _normalizar_respuesta_consulta(resultado_get)


def emitir_factura(db: Session, venta: Venta) -> None:
    """Un solo intento de facturar `venta`. Si algo queda sin resolver (sin
    certificado, ARCA caído, o un timeout que ni FECompConsultar aclara), la
    venta se deja "pendiente" tal cual estaba: el reintento automático la
    vuelve a intentar en el próximo ciclo. Nunca propaga la excepción."""
    settings = get_settings()

    if not wsaa.hay_certificado_configurado():
        return

    ticket = wsaa.obtener_o_renovar_ticket(db)
    if ticket is None:
        return

    tipo = settings.arca_tipo_comprobante
    punto_venta = settings.arca_punto_venta
    neto, iva = calcular_neto_iva(venta.total, tipo, settings.arca_alicuota_iva)
    fecha = hoy_argentina().strftime("%Y%m%d")

    with _bloqueo_de_emision(db):
        try:
            numero = wsfe.consultar_ultimo_autorizado(ticket, punto_venta, tipo) + 1
        except TimeoutError:
            logger.warning("ARCA: no se pudo consultar el último comprobante autorizado; se reintenta luego.")
            return
        except Exception:
            logger.exception("ARCA: FECompUltimoAutorizado falló.")
            return

        try:
            detalle = armar_detalle(numero, fecha, venta.total, neto, iva, tipo, settings.arca_alicuota_iva)
        except ValueError as error:
            venta.estado_arca = "fallo"
            venta.error_detalle = str(error)
            db.commit()
            return

        try:
            respuesta = wsfe.solicitar_cae(ticket, punto_venta, tipo, detalle)
            resultado = _normalizar_respuesta_solicitud(respuesta)
        except TimeoutError:
            resultado = _resolver_tras_timeout(ticket, punto_venta, tipo, numero)
            if resultado is None:
                logger.warning(
                    "ARCA: no llegó respuesta al pedir el CAE del comprobante %s y todavía no está "
                    "autorizado; se reintenta en el próximo ciclo.",
                    numero,
                )
                return
        except Exception:
            logger.exception("ARCA: FECAESolicitar falló.")
            return

        _guardar_resultado(db, venta, tipo, punto_venta, numero, resultado)
