"""Cliente del servicio WSFE (comprobantes electrónicos): FEDummy,
FECompUltimoAutorizado, FECAESolicitar y FECompConsultar.

Todas las funciones devuelven dict/list/str/int planos (nunca objetos de
zeep ni Decimal/datetime), listos para guardar en respuesta_fiscal o para
que los pruebas los reemplacen con dobles simples.
"""

import logging

from zeep import Client
from zeep.exceptions import Fault, TransportError
from zeep.transports import Transport

from app.arca.wsaa import TicketInfo
from app.arca.utilidades import a_json_seguro
from app.config import get_settings

logger = logging.getLogger("arca.wsfe")

URLS_WSFE = {
    "homologacion": "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL",
    "produccion": "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL",
}


class ErrorArca(Exception):
    """ARCA respondió, pero con un problema de negocio (no de red)."""


def _cliente() -> Client:
    settings = get_settings()
    url = URLS_WSFE[settings.arca_entorno]
    transporte = Transport(timeout=30, operation_timeout=30)
    return Client(wsdl=url, transport=transporte)


def _auth(ticket: TicketInfo) -> dict:
    return {"Token": ticket.token, "Sign": ticket.sign, "Cuit": get_settings().arca_cuit}


def _sin_cortar_por_la_red(funcion, *args, **kwargs):
    """Traduce cualquier problema de transporte/tiempo de espera a TimeoutError,
    que es la señal que usa servicio.py para "no sabemos si se procesó"."""
    try:
        return funcion(*args, **kwargs)
    except Fault:
        raise
    except (TransportError, TimeoutError, OSError) as error:
        raise TimeoutError(str(error)) from error


def verificar_estado() -> dict:
    respuesta = _sin_cortar_por_la_red(lambda: _cliente().service.FEDummy())
    return a_json_seguro(respuesta)


def consultar_ultimo_autorizado(ticket: TicketInfo, punto_venta: int, tipo_comprobante: int) -> int:
    respuesta = _sin_cortar_por_la_red(
        lambda: _cliente().service.FECompUltimoAutorizado(
            Auth=_auth(ticket), PtoVta=punto_venta, CbteTipo=tipo_comprobante
        )
    )
    datos = a_json_seguro(respuesta)
    return int(datos["CbteNro"])


def solicitar_cae(ticket: TicketInfo, punto_venta: int, tipo_comprobante: int, detalle: dict) -> dict:
    """Puede tardar la respuesta del server pero haber quedado registrada en ARCA:
    ante un TimeoutError, quien llama tiene que consultar antes de reintentar."""
    pedido = {
        "FeCabReq": {"CantReg": 1, "PtoVta": punto_venta, "CbteTipo": tipo_comprobante},
        "FeDetReq": {"FECAEDetRequest": [detalle]},
    }
    respuesta = _sin_cortar_por_la_red(
        lambda: _cliente().service.FECAESolicitar(Auth=_auth(ticket), FeCAEReq=pedido)
    )
    return a_json_seguro(respuesta)


def consultar_comprobante(
    ticket: TicketInfo, punto_venta: int, tipo_comprobante: int, numero: int
) -> dict | None:
    """None si ese número todavía no está autorizado en ARCA (comprobante no
    encontrado): en ese caso es seguro reintentar con el mismo número."""
    pedido = {"FeCompConsReq": {"CbteTipo": tipo_comprobante, "CbteNro": numero, "PtoVta": punto_venta}}
    try:
        respuesta = _sin_cortar_por_la_red(
            lambda: _cliente().service.FECompConsultar(Auth=_auth(ticket), **pedido)
        )
    except Fault as error:
        mensaje = str(error).lower()
        if "no se encuentra" in mensaje or "no existe" in mensaje or "602" in mensaje:
            return None
        raise
    datos = a_json_seguro(respuesta)
    resultado = datos.get("ResultGet")
    if not resultado or not resultado.get("CbteFch"):
        return None
    return resultado
