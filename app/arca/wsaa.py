"""Login contra WSAA: pide y guarda el ticket de acceso (token + sign) para WSFE.

Nunca se loguea, imprime ni devuelve el contenido de la clave privada, el
token ni el sign: solo se registra que la operación ocurrió y, si falló, el
motivo genérico.
"""

import base64
import binascii
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from sqlalchemy import select
from sqlalchemy.orm import Session
from zeep import Client
from zeep.exceptions import Fault
from zeep.transports import Transport

from app.config import get_settings
from app.fechas import ZONA
from app.models import TicketAcceso

logger = logging.getLogger("arca.wsaa")

URLS_WSAA = {
    "homologacion": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl",
    "produccion": "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl",
}

# Se renueva si faltan 10 minutos o menos para el vencimiento.
MARGEN_RENOVACION = timedelta(minutes=10)


@dataclass(frozen=True)
class TicketInfo:
    token: str
    sign: str
    vence_en: datetime


def _material(ruta: str | None, contenido_base64: str | None) -> bytes | None:
    if contenido_base64:
        try:
            return base64.b64decode(contenido_base64, validate=True)
        except (binascii.Error, ValueError):
            logger.error("ARCA: el contenido en base64 del certificado/clave no es válido.")
            return None
    if ruta:
        archivo = Path(ruta)
        if archivo.is_file():
            return archivo.read_bytes()
    return None


def _cargar_certificado_y_clave():
    settings = get_settings()
    cert_pem = _material(settings.arca_cert, settings.arca_cert_base64)
    key_pem = _material(settings.arca_key, settings.arca_key_base64)
    if cert_pem is None or key_pem is None:
        return None, None
    try:
        certificado = x509.load_pem_x509_certificate(cert_pem)
        clave = serialization.load_pem_private_key(key_pem, password=None)
    except ValueError:
        logger.error("ARCA: el certificado o la clave no se pudieron leer (formato inválido).")
        return None, None
    return certificado, clave


def hay_certificado_configurado() -> bool:
    certificado, clave = _cargar_certificado_y_clave()
    return certificado is not None and clave is not None


def _armar_tra(servicio: str) -> bytes:
    ahora = datetime.now(ZONA)
    generacion = ahora - timedelta(minutes=10)
    expiracion = ahora + timedelta(minutes=10)
    unique_id = int(ahora.timestamp())
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<loginTicketRequest version="1.0">'
        "<header>"
        f"<uniqueId>{unique_id}</uniqueId>"
        f"<generationTime>{generacion.isoformat(timespec='seconds')}</generationTime>"
        f"<expirationTime>{expiracion.isoformat(timespec='seconds')}</expirationTime>"
        "</header>"
        f"<service>{servicio}</service>"
        "</loginTicketRequest>"
    )
    return xml.encode("utf-8")


def _firmar_tra(tra_xml: bytes, certificado, clave) -> str:
    cms_der = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra_xml)
        .add_signer(certificado, clave, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
    )
    return base64.b64encode(cms_der).decode("ascii")


def _pedir_login_cms(cms_base64: str) -> str:
    settings = get_settings()
    url = URLS_WSAA[settings.arca_entorno]
    transporte = Transport(timeout=30, operation_timeout=30)
    cliente = Client(wsdl=url, transport=transporte)
    return cliente.service.loginCms(in0=cms_base64)


def _parsear_login_ticket_response(xml_texto: str) -> TicketInfo:
    raiz = ElementTree.fromstring(xml_texto)
    token = raiz.findtext(".//token")
    sign = raiz.findtext(".//sign")
    vencimiento_texto = raiz.findtext(".//expirationTime")
    vence_en = datetime.fromisoformat(vencimiento_texto).astimezone(timezone.utc)
    if not token or not sign:
        raise ValueError("La respuesta de WSAA no trae token o sign.")
    return TicketInfo(token=token, sign=sign, vence_en=vence_en)


def _leer_ticket_guardado(db: Session, servicio: str, entorno: str, cuit: str) -> TicketAcceso | None:
    return db.scalar(
        select(TicketAcceso).where(
            TicketAcceso.servicio == servicio,
            TicketAcceso.entorno == entorno,
            TicketAcceso.cuit == cuit,
        )
    )


def _guardar_ticket(db: Session, servicio: str, entorno: str, cuit: str, info: TicketInfo) -> None:
    fila = _leer_ticket_guardado(db, servicio, entorno, cuit)
    if fila is None:
        fila = TicketAcceso(servicio=servicio, entorno=entorno, cuit=cuit)
        db.add(fila)
    fila.token = info.token
    fila.sign = info.sign
    fila.vence_en = info.vence_en
    fila.generado_en = datetime.now(timezone.utc)
    db.commit()


def obtener_o_renovar_ticket(db: Session, servicio: str = "wsfe") -> TicketInfo | None:
    """Devuelve un ticket vigente, reutilizando el guardado si todavía le
    quedan más de 10 minutos y es del mismo entorno y CUIT configurados
    ahora mismo (si se cambió cualquiera de los dos, se pide uno nuevo, no
    se reutiliza el de otro entorno). Si hay que renovarlo y algo falla (sin
    certificado, ARCA caído, o ARCA dice que ya hay uno vigente), no
    reintenta en loop: registra el motivo y devuelve None para que el que
    llama lo intente de nuevo en el próximo ciclo."""
    settings = get_settings()
    fila = _leer_ticket_guardado(db, servicio, settings.arca_entorno, settings.arca_cuit)
    if fila is not None:
        vence_en = fila.vence_en if fila.vence_en.tzinfo else fila.vence_en.replace(tzinfo=timezone.utc)
        if vence_en - datetime.now(timezone.utc) > MARGEN_RENOVACION:
            return TicketInfo(token=fila.token, sign=fila.sign, vence_en=vence_en)

    certificado, clave = _cargar_certificado_y_clave()
    if certificado is None or clave is None:
        logger.warning("ARCA: no hay certificado configurado, no se puede pedir el ticket de acceso.")
        return None

    try:
        tra = _armar_tra(servicio)
        cms_base64 = _firmar_tra(tra, certificado, clave)
        respuesta_xml = _pedir_login_cms(cms_base64)
        info = _parsear_login_ticket_response(respuesta_xml)
    except Fault as error:
        if "ya posee un ta valido" in str(error).lower():
            logger.warning(
                "ARCA (WSAA): ya existe un ticket de acceso vigente en AFIP (entorno=%s, cuit=%s); se espera al próximo ciclo.",
                settings.arca_entorno,
                settings.arca_cuit,
            )
        else:
            logger.error(
                "ARCA (WSAA): ARCA rechazó el pedido de ticket de acceso (entorno=%s, cuit=%s): %s",
                settings.arca_entorno,
                settings.arca_cuit,
                error,
            )
        return None
    except Exception:  # noqa: BLE001 - cualquier falla de red, XML o firma
        logger.exception(
            "ARCA (WSAA): no se pudo obtener el ticket de acceso (entorno=%s, cuit=%s).",
            settings.arca_entorno,
            settings.arca_cuit,
        )
        return None

    _guardar_ticket(db, servicio, settings.arca_entorno, settings.arca_cuit, info)
    return info
