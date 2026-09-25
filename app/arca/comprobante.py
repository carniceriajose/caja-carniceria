"""Datos del comprobante para imprimir, incluido el código QR de ARCA (RG 4291).

El QR es una URL con un único parámetro `p`: un JSON (con los campos que fija
la especificación) codificado en base64.
"""

import base64
from datetime import date, datetime, timezone
from decimal import Decimal

from app.arca.servicio import FACTURA_B, calcular_neto_iva
from app.config import Settings
from app.fechas import ZONA
from app.models import Venta

URL_QR = "https://www.afip.gob.ar/fe/qr/"

# tipo de comprobante -> (letra, nombre, código que se imprime)
TIPOS = {
    6: ("B", "FACTURA B", "006"),
    11: ("C", "FACTURA C", "011"),
}


def construir_url_qr(
    *,
    fecha: date,
    cuit: str,
    punto_venta: int,
    tipo_comprobante: int,
    numero: int,
    importe: Decimal,
    cae: str,
) -> str:
    """Consumidor final sin identificar (tipoDocRec 99, nroDocRec 0), en pesos.
    El importe se arma como texto con 2 decimales: nunca pasa por un float."""
    if not cuit.isdigit() or not cae.isdigit():
        raise ValueError("El CUIT y el CAE tienen que ser numéricos para armar el QR.")
    contenido = (
        '{"ver":1,'
        f'"fecha":"{fecha.isoformat()}",'
        f'"cuit":{int(cuit)},'
        f'"ptoVta":{punto_venta},'
        f'"tipoCmp":{tipo_comprobante},'
        f'"nroCmp":{numero},'
        f'"importe":{importe:.2f},'
        '"moneda":"PES",'
        '"ctz":1,'
        '"tipoDocRec":99,'
        '"nroDocRec":0,'
        '"tipoCodAut":"E",'
        f'"codAut":{int(cae)}'
        "}"
    )
    codificado = base64.b64encode(contenido.encode("utf-8")).decode("ascii")
    return f"{URL_QR}?p={codificado}"


def _fecha_del_comprobante(venta: Venta) -> date:
    """La que ARCA registró (CbteFch); si no está, el día de la venta en Argentina."""
    respuesta = venta.respuesta_fiscal or {}
    detalles = (respuesta.get("FeDetResp") or {}).get("FECAEDetResponse") or []
    texto = (detalles[0].get("CbteFch") if detalles else None) or (
        (respuesta.get("ResultGet") or {}).get("CbteFch")
    )
    if texto and len(str(texto)) == 8:
        texto = str(texto)
        return date(int(texto[0:4]), int(texto[4:6]), int(texto[6:8]))
    momento = venta.fecha_hora
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(ZONA).date()


def armar_comprobante(venta: Venta, settings: Settings) -> dict:
    """Todo lo que necesita el ticket. Solo para ventas ya facturadas."""
    if venta.estado_arca != "facturada":
        raise ValueError("La venta todavía no tiene comprobante.")

    tipo = int(venta.tipo_comprobante)
    letra, nombre, codigo = TIPOS.get(tipo, (str(tipo), f"COMPROBANTE {tipo}", str(tipo).zfill(3)))
    fecha = _fecha_del_comprobante(venta)

    iva_contenido = None
    if tipo == FACTURA_B:
        _, iva_contenido = calcular_neto_iva(venta.total, tipo, settings.arca_alicuota_iva)

    return {
        "emisor": {
            "razon_social": settings.arca_razon_social,
            "cuit": settings.arca_cuit,
            "domicilio": settings.arca_domicilio,
            "condicion_iva": settings.arca_condicion_iva,
            "inicio_actividades": settings.arca_inicio_actividades,
            "ingresos_brutos": settings.arca_ingresos_brutos,
        },
        "nombre": nombre,
        "letra": letra,
        "codigo": codigo,
        "punto_venta": venta.punto_venta,
        "numero": venta.numero_comprobante,
        "fecha": fecha,
        "receptor": "Consumidor Final",
        "total": venta.total,
        "iva_contenido": iva_contenido,
        "cae": venta.cae,
        "cae_vencimiento": venta.cae_vencimiento,
        "qr_url": construir_url_qr(
            fecha=fecha,
            cuit=settings.arca_cuit,
            punto_venta=venta.punto_venta,
            tipo_comprobante=tipo,
            numero=venta.numero_comprobante,
            importe=venta.total,
            cae=venta.cae,
        ),
    }
