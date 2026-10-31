"""Datos del comprobante para imprimir, incluido el código QR de ARCA (RG 4291).

El QR es una URL con un único parámetro `p`: un JSON (con los campos que fija
la especificación) codificado en base64.
"""

import base64
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.arca.servicio import FACTURA_B, NOTA_CREDITO_B, calcular_neto_iva
from app.fechas import ZONA
from app.models import Anulacion, Configuracion, Venta
from app.rubros import alicuota_o_predeterminada

URL_QR = "https://www.afip.gob.ar/fe/qr/"

# tipo de comprobante -> (letra, nombre, código que se imprime)
TIPOS = {
    6: ("B", "FACTURA B", "006"),
    11: ("C", "FACTURA C", "011"),
    8: ("B", "NOTA DE CRÉDITO B", "008"),
    13: ("C", "NOTA DE CRÉDITO C", "013"),
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


def _fecha_desde_respuesta(respuesta_fiscal: dict | None, fecha_reserva: datetime) -> date:
    """La fecha que ARCA registró (CbteFch); si no está, la fecha de reserva
    (de la venta, o de la anulación) en hora de Argentina."""
    respuesta = respuesta_fiscal or {}
    detalles = (respuesta.get("FeDetResp") or {}).get("FECAEDetResponse") or []
    texto = (detalles[0].get("CbteFch") if detalles else None) or (
        (respuesta.get("ResultGet") or {}).get("CbteFch")
    )
    if texto and len(str(texto)) == 8:
        texto = str(texto)
        return date(int(texto[0:4]), int(texto[4:6]), int(texto[6:8]))
    momento = fecha_reserva
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(ZONA).date()


def _armar_comprobante(
    *,
    tipo: int,
    punto_venta: int,
    numero: int,
    subtotal: Decimal,
    total: Decimal,
    ajuste_detalle: str | None,
    cae: str,
    cae_vencimiento,
    fecha: date,
    alicuota_iva: Decimal,
    descripcion_item: str,
    configuracion: Configuracion,
    cuit: str,
    receptor: str = "Consumidor Final",
) -> dict:
    letra, nombre, codigo = TIPOS.get(tipo, (str(tipo), f"COMPROBANTE {tipo}", str(tipo).zfill(3)))

    iva_contenido = None
    if tipo in (FACTURA_B, NOTA_CREDITO_B):
        _, iva_contenido = calcular_neto_iva(total, FACTURA_B, alicuota_iva)

    return {
        "emisor": {
            "razon_social": configuracion.razon_social,
            "cuit": cuit,
            "domicilio": configuracion.domicilio,
            "condicion_iva": configuracion.condicion_iva,
            "inicio_actividades": configuracion.inicio_actividades.strftime("%d/%m/%Y"),
            "ingresos_brutos": configuracion.ingresos_brutos or "",
        },
        "nombre": nombre,
        "letra": letra,
        "codigo": codigo,
        "punto_venta": punto_venta,
        "numero": numero,
        "fecha": fecha,
        "receptor": receptor,
        "subtotal": subtotal,
        "ajuste_detalle": ajuste_detalle,
        "total": total,
        "iva_contenido": iva_contenido,
        "descripcion_item": descripcion_item,
        "cae": cae,
        "cae_vencimiento": cae_vencimiento,
        "qr_url": construir_url_qr(
            fecha=fecha,
            cuit=cuit,
            punto_venta=punto_venta,
            tipo_comprobante=tipo,
            numero=numero,
            importe=total,
            cae=cae,
        ),
    }


def armar_comprobante(db: Session, venta: Venta, configuracion: Configuracion, cuit: str) -> dict:
    """Todo lo que necesita el ticket. Solo para ventas ya facturadas.

    La alícuota y la descripción del ítem son las del rubro que se eligió al
    cobrar (guardadas en la venta), no las que esté configurado hoy: si
    cambian después, no tienen que afectar a un comprobante ya emitido. Para
    ventas viejas, de antes de que existieran los rubros, se usa el rubro
    predeterminado actual y la descripción general de configuración."""
    if venta.estado_arca != "facturada":
        raise ValueError("La venta todavía no tiene comprobante.")

    tipo = int(venta.tipo_comprobante)
    fecha = _fecha_desde_respuesta(venta.respuesta_fiscal, venta.fecha_hora)
    return _armar_comprobante(
        tipo=tipo,
        punto_venta=venta.punto_venta,
        numero=venta.numero_comprobante,
        subtotal=venta.subtotal,
        total=venta.total,
        ajuste_detalle=venta.ajuste_detalle,
        cae=venta.cae,
        cae_vencimiento=venta.cae_vencimiento,
        fecha=fecha,
        alicuota_iva=alicuota_o_predeterminada(db, venta.alicuota_iva),
        descripcion_item=venta.descripcion_factura or configuracion.descripcion_item,
        configuracion=configuracion,
        cuit=cuit,
    )


def armar_comprobante_nota_credito(
    db: Session, anulacion: Anulacion, venta: Venta, configuracion: Configuracion, cuit: str
) -> dict:
    """Todo lo que necesita el ticket de la nota de crédito. Solo para
    anulaciones que ya tienen su nota de crédito emitida. Usa la misma
    alícuota y descripción que la factura original."""
    if anulacion.estado != "emitida":
        raise ValueError("La nota de crédito todavía no está disponible.")

    fecha = _fecha_desde_respuesta(anulacion.respuesta_fiscal, anulacion.fecha_hora)
    return _armar_comprobante(
        tipo=anulacion.tipo,
        punto_venta=anulacion.punto_venta,
        numero=anulacion.numero,
        subtotal=venta.subtotal,
        total=venta.total,
        ajuste_detalle=venta.ajuste_detalle,
        cae=anulacion.cae,
        cae_vencimiento=anulacion.cae_vencimiento,
        fecha=fecha,
        alicuota_iva=alicuota_o_predeterminada(db, anulacion.alicuota_iva),
        descripcion_item=venta.descripcion_factura or configuracion.descripcion_item,
        configuracion=configuracion,
        cuit=cuit,
    )
