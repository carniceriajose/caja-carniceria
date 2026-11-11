"""Lógica de negocio de la facturación: cuánto neto/IVA calcular, qué número
pedir, cómo evitar pedir el mismo número dos veces y qué hacer si ARCA no
contesta a tiempo. No sabe nada de HTTP ni de FastAPI.
"""

import logging
import threading
import time
from contextlib import contextmanager
from datetime import date as Fecha
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.arca import wsaa, wsfe
from app.auditoria import registrar as registrar_auditoria
from app.config import get_settings
from app.configuracion import obtener_configuracion
from app.fechas import hoy_argentina
from app.models import Anulacion, Venta
from app.rubros import alicuota_o_predeterminada

logger = logging.getLogger("arca.servicio")

FACTURA_B = 6
FACTURA_C = 11
CERO = Decimal("0.00")

# Nota de crédito correspondiente a cada tipo de factura (la única relación
# que soporta este comercio: B->B, C->C).
NOTA_CREDITO_B = 8
NOTA_CREDITO_C = 13
TIPO_NOTA_CREDITO = {FACTURA_B: NOTA_CREDITO_B, FACTURA_C: NOTA_CREDITO_C}

# Tabla oficial de Ids de alícuota de IVA de ARCA (WSFE).
IDS_ALICUOTA_IVA = {
    Decimal("0"): 3,
    Decimal("10.5"): 4,
    Decimal("21"): 5,
    Decimal("27"): 6,
    Decimal("5"): 8,
    Decimal("2.5"): 9,
}

# Lock de proceso + advisory lock de PostgreSQL: para que dos ventas no pidan
# el mismo número de comprobante al mismo tiempo. La clave es arbitraria pero fija.
#
# Se usa la variante "_xact" (por transacción, no por sesión): se libera sola
# al terminar la transacción (commit o rollback), sin un unlock explícito.
# Es la que hay que usar con el pooler de Supabase en modo "Transaction": ahí
# cada sentencia puede caer en una conexión física distinta del servidor, así
# que un lock de sesión pedido en una transacción y liberado "a mano" después
# de otro commit podría intentar liberarse en una conexión que ya no es la que
# lo tomó, y quedar trabado para siempre.
_CANDADO_PROCESO = threading.Lock()
_CLAVE_ADVISORY_LOCK = 875_501_001


@contextmanager
def _bloqueo_de_emision(db: Session):
    with _CANDADO_PROCESO:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("select pg_advisory_xact_lock(:clave)"), {"clave": _CLAVE_ADVISORY_LOCK})
        yield


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


def _guardar_resultado(
    db: Session, venta: Venta, tipo: int, punto_venta: int, alicuota: Decimal, numero: int, resultado: dict
) -> None:
    venta.respuesta_fiscal = resultado["respuesta_completa"]
    if resultado["aprobado"]:
        venta.estado_arca = "facturada"
        venta.tipo_comprobante = str(tipo)
        venta.punto_venta = punto_venta
        venta.numero_comprobante = numero
        venta.alicuota_iva = alicuota
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
    vuelve a intentar en el próximo ciclo. Nunca propaga la excepción.

    Los logs de acá son solo diagnóstico (id de venta, CUIT, punto de venta,
    tipo/número, duración, tipo de excepción): nunca token, sign, clave
    privada ni certificado."""
    inicio = time.monotonic()
    cuit = get_settings().arca_cuit
    logger.info("ARCA: empieza a emitir venta=%s cuit=%s.", venta.id, cuit)

    if not wsaa.hay_certificado_configurado():
        logger.warning("ARCA: no hay certificado configurado (venta=%s).", venta.id)
        return

    ticket = wsaa.obtener_o_renovar_ticket(db)
    if ticket is None:
        logger.warning("ARCA: no se pudo obtener el ticket de acceso (venta=%s, cuit=%s).", venta.id, cuit)
        return

    configuracion = obtener_configuracion(db)
    tipo = configuracion.tipo_comprobante
    punto_venta = configuracion.punto_venta
    # La alícuota es la del rubro que se eligió al cobrar (congelada en la
    # venta); no se vuelve a leer de la configuración.
    alicuota = alicuota_o_predeterminada(db, venta.alicuota_iva)
    neto, iva = calcular_neto_iva(venta.total, tipo, alicuota)
    fecha = hoy_argentina().strftime("%Y%m%d")

    with _bloqueo_de_emision(db):
        inicio_consulta = time.monotonic()
        try:
            numero = wsfe.consultar_ultimo_autorizado(ticket, punto_venta, tipo) + 1
        except TimeoutError as error:
            logger.warning(
                "ARCA: FECompUltimoAutorizado agotó el tiempo de espera (venta=%s, cuit=%s, "
                "pto_vta=%s, tipo=%s, %.1fs, excepcion=%s): %s; se reintenta luego.",
                venta.id, cuit, punto_venta, tipo, time.monotonic() - inicio_consulta, type(error).__name__, error,
            )
            return
        except Exception:
            logger.exception(
                "ARCA: FECompUltimoAutorizado falló (venta=%s, cuit=%s, pto_vta=%s, tipo=%s, %.1fs).",
                venta.id, cuit, punto_venta, tipo, time.monotonic() - inicio_consulta,
            )
            return
        logger.info(
            "ARCA: FECompUltimoAutorizado OK (venta=%s, numero=%s, %.1fs).",
            venta.id, numero, time.monotonic() - inicio_consulta,
        )

        try:
            detalle = armar_detalle(numero, fecha, venta.total, neto, iva, tipo, alicuota)
        except ValueError as error:
            venta.estado_arca = "fallo"
            venta.error_detalle = str(error)
            db.commit()
            return

        inicio_solicitud = time.monotonic()
        try:
            respuesta = wsfe.solicitar_cae(ticket, punto_venta, tipo, detalle)
            resultado = _normalizar_respuesta_solicitud(respuesta)
        except TimeoutError as error:
            logger.warning(
                "ARCA: FECAESolicitar agotó el tiempo de espera (venta=%s, cuit=%s, pto_vta=%s, "
                "tipo=%s, numero=%s, %.1fs, excepcion=%s): %s",
                venta.id, cuit, punto_venta, tipo, numero, time.monotonic() - inicio_solicitud,
                type(error).__name__, error,
            )
            resultado = _resolver_tras_timeout(ticket, punto_venta, tipo, numero)
            if resultado is None:
                logger.warning(
                    "ARCA: no llegó respuesta al pedir el CAE del comprobante %s (venta=%s) y todavía "
                    "no está autorizado; se reintenta en el próximo ciclo.",
                    numero, venta.id,
                )
                return
        except Exception:
            logger.exception(
                "ARCA: FECAESolicitar falló (venta=%s, cuit=%s, pto_vta=%s, tipo=%s, numero=%s, %.1fs).",
                venta.id, cuit, punto_venta, tipo, numero, time.monotonic() - inicio_solicitud,
            )
            return

        logger.info(
            "ARCA: FECAESolicitar respondió (venta=%s, numero=%s, aprobado=%s, motivo=%s, %.1fs, total=%.1fs).",
            venta.id, numero, resultado.get("aprobado"), resultado.get("motivo") or "-",
            time.monotonic() - inicio_solicitud, time.monotonic() - inicio,
        )

        _guardar_resultado(db, venta, tipo, punto_venta, alicuota, numero, resultado)


def _guardar_resultado_nc(
    db: Session,
    anulacion: Anulacion,
    venta: Venta,
    tipo_nc: int,
    punto_venta: int,
    alicuota: Decimal,
    numero: int,
    resultado: dict,
) -> None:
    anulacion.respuesta_fiscal = resultado["respuesta_completa"]
    if resultado["aprobado"]:
        anulacion.estado = "emitida"
        anulacion.tipo = tipo_nc
        anulacion.punto_venta = punto_venta
        anulacion.numero = numero
        anulacion.alicuota_iva = alicuota
        anulacion.cae = resultado["cae"]
        anulacion.cae_vencimiento = _fecha_desde_arca(resultado["cae_vencimiento"])
        anulacion.error_detalle = None
        registrar_auditoria(
            db,
            None,
            "anulacion.emitida",
            {"anulacion_id": anulacion.id, "venta_id": venta.id, "tipo": tipo_nc, "numero": numero},
            entidad="venta",
            entidad_id=venta.id,
        )
    else:
        anulacion.estado = "fallo"
        anulacion.error_detalle = resultado["motivo"]
        registrar_auditoria(
            db,
            None,
            "anulacion.fallo",
            {"anulacion_id": anulacion.id, "venta_id": venta.id, "motivo": resultado["motivo"]},
            entidad="venta",
            entidad_id=venta.id,
        )
    db.commit()


def emitir_nota_credito(db: Session, venta: Venta, anulacion: Anulacion) -> None:
    """Análogo a emitir_factura, pero para la nota de crédito de una venta que
    ya tenía CAE. Un solo intento: si algo queda sin resolver, `anulacion`
    queda "pendiente" (o "fallo", si ARCA la rechazó explícitamente) para el
    reintento automático — a diferencia de una factura, acá también se
    reintenta un "fallo" solo, porque dejar una anulación sin resolver es un
    problema más grave que dejar pendiente una factura nueva. Nunca propaga
    la excepción."""
    if not wsaa.hay_certificado_configurado():
        return

    ticket = wsaa.obtener_o_renovar_ticket(db)
    if ticket is None:
        return

    tipo_original = int(venta.tipo_comprobante)
    tipo_nc = TIPO_NOTA_CREDITO.get(tipo_original)
    if tipo_nc is None:
        anulacion.estado = "fallo"
        anulacion.error_detalle = f"No hay nota de crédito configurada para el tipo de comprobante {tipo_original}."
        db.commit()
        return

    punto_venta = venta.punto_venta
    # Mismos importes que el comprobante original: la alícuota que se usó de
    # verdad al facturar (no la del rubro hoy, que puede haber cambiado), así
    # la nota de crédito siempre cierra exacto contra la factura.
    alicuota = alicuota_o_predeterminada(db, venta.alicuota_iva)
    neto, iva = calcular_neto_iva(venta.total, tipo_original, alicuota)
    fecha = hoy_argentina().strftime("%Y%m%d")  # la fecha de hoy, no la de la venta original

    with _bloqueo_de_emision(db):
        try:
            numero = wsfe.consultar_ultimo_autorizado(ticket, punto_venta, tipo_nc) + 1
        except TimeoutError:
            logger.warning(
                "ARCA: no se pudo consultar el último comprobante autorizado (nota de crédito); se reintenta luego."
            )
            return
        except Exception:
            logger.exception("ARCA: FECompUltimoAutorizado falló (nota de crédito).")
            return

        detalle = armar_detalle(numero, fecha, venta.total, neto, iva, tipo_original, alicuota)
        detalle["CbtesAsoc"] = {
            "CbteAsoc": [
                {"Tipo": tipo_original, "PtoVta": venta.punto_venta, "Nro": venta.numero_comprobante}
            ]
        }

        try:
            respuesta = wsfe.solicitar_cae(ticket, punto_venta, tipo_nc, detalle)
            resultado = _normalizar_respuesta_solicitud(respuesta)
        except TimeoutError:
            resultado = _resolver_tras_timeout(ticket, punto_venta, tipo_nc, numero)
            if resultado is None:
                logger.warning(
                    "ARCA: no llegó respuesta al pedir el CAE de la nota de crédito %s y todavía no "
                    "está autorizada; se reintenta en el próximo ciclo.",
                    numero,
                )
                return
        except Exception:
            logger.exception("ARCA: FECAESolicitar falló (nota de crédito).")
            return

        _guardar_resultado_nc(db, anulacion, venta, tipo_nc, punto_venta, alicuota, numero, resultado)
