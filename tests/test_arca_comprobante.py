import base64
import json
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from app.arca.comprobante import URL_QR, construir_url_qr
from tests.utiles import con_token


def _decodificar_qr(url):
    assert url.startswith(URL_QR + "?p=")
    parametro = urlparse(url).query[len("p="):]
    texto = base64.b64decode(parametro).decode("utf-8")
    return texto, json.loads(texto)


def _url(**cambios):
    datos = dict(
        fecha=date(2026, 9, 21),
        cuit="20111111112",
        punto_venta=1,
        tipo_comprobante=6,
        numero=2,
        importe=Decimal("321.00"),
        cae="12345678901234",
    )
    datos.update(cambios)
    return construir_url_qr(**datos)


# ---------------------------------------------------------------- QR según la especificación


def test_el_qr_lleva_los_campos_de_la_especificacion_de_arca():
    texto, datos = _decodificar_qr(_url())

    assert datos == {
        "ver": 1,
        "fecha": "2026-09-21",
        "cuit": 20111111112,
        "ptoVta": 1,
        "tipoCmp": 6,
        "nroCmp": 2,
        "importe": 321.0,
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": 99,
        "nroDocRec": 0,
        "tipoCodAut": "E",
        "codAut": 12345678901234,
    }
    # el orden de los campos es el de la especificación
    assert list(datos) == [
        "ver", "fecha", "cuit", "ptoVta", "tipoCmp", "nroCmp", "importe",
        "moneda", "ctz", "tipoDocRec", "nroDocRec", "tipoCodAut", "codAut",
    ]


def test_el_importe_va_con_dos_decimales_armado_como_texto():
    texto, _ = _decodificar_qr(_url(importe=Decimal("1250.5")))
    assert '"importe":1250.50,' in texto

    texto, _ = _decodificar_qr(_url(importe=Decimal("0.10") + Decimal("0.20")))
    assert '"importe":0.30,' in texto


def test_el_qr_rechaza_cuit_o_cae_no_numericos():
    with pytest.raises(ValueError):
        _url(cuit="27-45195505-0")
    with pytest.raises(ValueError):
        _url(cae="ABC123")


def test_la_url_tiene_un_unico_parametro_p():
    assert list(parse_qs(urlparse(_url()).query)) == ["p"]


# ---------------------------------------------------------------- endpoint


def _venta_facturada(crear_venta_db, vendedor_id, **extra):
    datos = dict(
        estado_arca="facturada",
        numero_comprobante=2,
        tipo_comprobante="6",
        punto_venta=1,
        cae="12345678901234",
        cae_vencimiento=date(2026, 10, 1),
        respuesta_fiscal={"FeDetResp": {"FECAEDetResponse": [{"CbteFch": "20260921", "Resultado": "A"}]}},
    )
    datos.update(extra)
    return crear_venta_db(vendedor_id, "321.00", "tarjeta", **datos)


def test_comprobante_de_factura_b_trae_todo_lo_del_ticket(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = _venta_facturada(crear_venta_db, admin_id)

    respuesta = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin)

    assert respuesta.status_code == 200
    c = respuesta.json()
    assert c["emisor"]["razon_social"] == "Carnicería de prueba"
    assert c["emisor"]["cuit"] == "20000000001"
    assert c["emisor"]["domicilio"] == "Calle Falsa 123, Localidad"
    assert c["emisor"]["condicion_iva"] == "Responsable Inscripto"
    assert (c["nombre"], c["letra"], c["codigo"]) == ("FACTURA B", "B", "006")
    assert (c["punto_venta"], c["numero"]) == (1, 2)
    assert c["fecha"] == "2026-09-21"
    assert c["receptor"] == "Consumidor Final"
    assert c["total"] == "321.00"
    assert c["cae"] == "12345678901234"
    assert c["cae_vencimiento"] == "2026-10-01"
    assert c["qr_url"].startswith(URL_QR + "?p=")


def test_factura_b_muestra_el_iva_contenido_que_suma_exacto(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = _venta_facturada(crear_venta_db, admin_id)
    c = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()

    # alícuota de prueba: 21% -> neto 265.29, IVA 55.71
    assert Decimal(c["iva_contenido"]) == Decimal("321.00") - Decimal("265.29")


def test_factura_c_no_tiene_iva_contenido(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = _venta_facturada(crear_venta_db, admin_id, tipo_comprobante="11")
    c = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()

    assert (c["nombre"], c["letra"], c["codigo"]) == ("FACTURA C", "C", "011")
    assert c["iva_contenido"] is None


def test_el_qr_del_endpoint_coincide_con_el_comprobante(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = _venta_facturada(crear_venta_db, admin_id)
    c = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()

    _, datos = _decodificar_qr(c["qr_url"])
    assert datos["cuit"] == int(c["emisor"]["cuit"])
    assert datos["ptoVta"] == c["punto_venta"]
    assert datos["nroCmp"] == c["numero"]
    assert datos["codAut"] == int(c["cae"])
    assert datos["fecha"] == c["fecha"]
    assert Decimal(str(datos["importe"])) == Decimal(c["total"])


def test_sin_fecha_de_arca_usa_el_dia_de_la_venta(cliente, headers_admin, admin_id, crear_venta_db):
    from datetime import datetime, timezone

    venta_id = _venta_facturada(
        crear_venta_db,
        admin_id,
        respuesta_fiscal=None,
        fecha_hora=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),  # lunes 22:00 en Argentina
    )
    c = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()
    assert c["fecha"] == "2026-03-02"


def test_venta_sin_facturar_da_409(cliente, headers_admin, admin_id, crear_venta_db):
    pendiente = crear_venta_db(admin_id, "100", "tarjeta", estado_arca="pendiente")
    efectivo = crear_venta_db(admin_id, "100", "efectivo")

    assert cliente.get(f"/ventas/{pendiente}/comprobante", headers=headers_admin).status_code == 409
    assert cliente.get(f"/ventas/{efectivo}/comprobante", headers=headers_admin).status_code == 409


def test_venta_inexistente_da_404_y_sin_token_401(cliente, headers_admin):
    assert cliente.get("/ventas/9999/comprobante", headers=headers_admin).status_code == 404
    assert cliente.get("/ventas/1/comprobante").status_code == 401


def test_el_vendedor_solo_ve_el_comprobante_de_sus_ventas(
    cliente, crear_usuario, iniciar_sesion, crear_venta_db, admin_id
):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    crear_usuario("otro", "clave-otro-1")
    propia = _venta_facturada(crear_venta_db, vendedor_id)
    ajena = _venta_facturada(crear_venta_db, admin_id)
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))
    otro = con_token(iniciar_sesion("otro", "clave-otro-1"))

    assert cliente.get(f"/ventas/{propia}/comprobante", headers=headers).status_code == 200
    assert cliente.get(f"/ventas/{ajena}/comprobante", headers=headers).status_code == 403
    assert cliente.get(f"/ventas/{propia}/comprobante", headers=otro).status_code == 403
