import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import Venta
from tests.utiles import con_token


@pytest.fixture()
def vendedor(cliente, crear_usuario, iniciar_sesion):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    return {"id": vendedor_id, "headers": con_token(iniciar_sesion("vende", "clave-vende-1"))}


def _cuerpo(total="1250.50", medio_pago="efectivo", id_cliente=None):
    return {
        "total": total,
        "medio_pago": medio_pago,
        "id_cliente": str(id_cliente or uuid.uuid4()),
    }


def _cantidad_de_ventas(sesion_pruebas):
    with sesion_pruebas() as db:
        return db.scalar(select(func.count()).select_from(Venta))


# ---------------------------------------------------------------- crear


def test_el_vendedor_crea_una_venta_en_efectivo(cliente, vendedor):
    cuerpo = _cuerpo("1250.50", "efectivo")
    respuesta = cliente.post("/ventas", headers=vendedor["headers"], json=cuerpo)

    assert respuesta.status_code == 201
    venta = respuesta.json()
    assert venta["total"] == "1250.50"
    assert venta["medio_pago"] == "efectivo"
    assert venta["id_cliente"] == cuerpo["id_cliente"]
    assert venta["vendedor_id"] == vendedor["id"]
    assert venta["estado_arca"] == "no_aplica"
    assert venta["fecha_hora"].endswith(("Z", "+00:00"))


@pytest.mark.parametrize("medio", ["tarjeta", "transferencia"])
def test_tarjeta_y_transferencia_quedan_pendientes_de_facturar(cliente, vendedor, medio):
    respuesta = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago=medio))

    assert respuesta.status_code == 201
    assert respuesta.json()["estado_arca"] == "pendiente"


def test_el_estado_fiscal_sigue_la_configuracion(cliente, vendedor, headers_admin):
    cliente.put(
        "/configuracion",
        headers=headers_admin,
        json={"facturar_efectivo": True, "facturar_tarjeta": False, "facturar_transferencia": True},
    )

    efectivo = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago="efectivo"))
    tarjeta = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago="tarjeta"))
    transferencia = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago="transferencia")
    )

    assert efectivo.json()["estado_arca"] == "pendiente"
    assert tarjeta.json()["estado_arca"] == "no_aplica"
    assert transferencia.json()["estado_arca"] == "pendiente"


def test_el_admin_tambien_puede_cobrar(cliente, headers_admin, admin_id):
    respuesta = cliente.post("/ventas", headers=headers_admin, json=_cuerpo())
    assert respuesta.status_code == 201
    assert respuesta.json()["vendedor_id"] == admin_id


def test_el_vendedor_y_la_fecha_no_se_toman_del_cuerpo(cliente, vendedor, admin_id):
    cuerpo = {
        **_cuerpo(),
        "vendedor_id": admin_id,
        "fecha_hora": "2000-01-01T00:00:00Z",
        "estado_arca": "facturada",
    }
    respuesta = cliente.post("/ventas", headers=vendedor["headers"], json=cuerpo)

    assert respuesta.status_code == 201
    venta = respuesta.json()
    assert venta["vendedor_id"] == vendedor["id"]
    assert venta["estado_arca"] == "no_aplica"
    assert not venta["fecha_hora"].startswith("2000")
    ahora = datetime.now(timezone.utc)
    creada = datetime.fromisoformat(venta["fecha_hora"].replace("Z", "+00:00"))
    assert abs((ahora - creada).total_seconds()) < 60


def test_sin_token_no_se_puede_vender(cliente):
    assert cliente.post("/ventas", json=_cuerpo()).status_code == 401


# ---------------------------------------------------------------- idempotencia


def test_repetir_el_mismo_id_cliente_devuelve_la_venta_ya_creada(cliente, vendedor, sesion_pruebas):
    cuerpo = _cuerpo("999.99", "tarjeta")
    primera = cliente.post("/ventas", headers=vendedor["headers"], json=cuerpo)
    segunda = cliente.post("/ventas", headers=vendedor["headers"], json=cuerpo)
    tercera = cliente.post("/ventas", headers=vendedor["headers"], json=cuerpo)

    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert tercera.status_code == 200
    assert segunda.json() == primera.json() == tercera.json()
    assert _cantidad_de_ventas(sesion_pruebas) == 1


def test_el_mismo_id_cliente_con_otros_datos_da_409(cliente, vendedor, sesion_pruebas):
    id_cliente = uuid.uuid4()
    cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo", id_cliente))

    otro_total = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("200.00", "efectivo", id_cliente)
    )
    otro_medio = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", id_cliente)
    )

    assert otro_total.status_code == 409
    assert otro_medio.status_code == 409
    assert _cantidad_de_ventas(sesion_pruebas) == 1


def test_el_id_cliente_de_otro_vendedor_da_409(cliente, vendedor, headers_admin):
    cuerpo = _cuerpo()
    cliente.post("/ventas", headers=vendedor["headers"], json=cuerpo)

    assert cliente.post("/ventas", headers=headers_admin, json=cuerpo).status_code == 409


# ---------------------------------------------------------------- validaciones


@pytest.mark.parametrize("total", ["0", "0.00", "-5", "10.001", "1.234", "abc", "", None, "99999999999"])
def test_total_invalido_da_422(cliente, vendedor, sesion_pruebas, total):
    respuesta = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(total=total))

    assert respuesta.status_code == 422
    assert _cantidad_de_ventas(sesion_pruebas) == 0


@pytest.mark.parametrize(
    "total, esperado",
    [("1000", "1000.00"), ("0.01", "0.01"), (1234.56, "1234.56"), (19.99, "19.99"), (100.5, "100.50")],
)
def test_total_valido_con_dos_decimales_como_texto_o_numero(cliente, vendedor, total, esperado):
    respuesta = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(total=total))

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["total"] == esperado


def test_la_plata_se_guarda_exacta_en_la_base(cliente, vendedor, sesion_pruebas):
    from decimal import Decimal

    cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("0.10"))
    cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("0.20"))

    with sesion_pruebas() as db:
        suma = db.scalar(select(func.sum(Venta.total)))
    assert suma == Decimal("0.30")


def test_medio_de_pago_invalido_da_422(cliente, vendedor):
    respuesta = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago="cheque"))
    assert respuesta.status_code == 422


def test_id_cliente_invalido_o_faltante_da_422(cliente, vendedor):
    invalido = {**_cuerpo(), "id_cliente": "no-es-un-uuid"}
    faltante = {"total": "10.00", "medio_pago": "efectivo"}

    assert cliente.post("/ventas", headers=vendedor["headers"], json=invalido).status_code == 422
    assert cliente.post("/ventas", headers=vendedor["headers"], json=faltante).status_code == 422


# ---------------------------------------------------------------- permisos y listado


def test_el_vendedor_no_puede_listar_ni_ver_ventas(cliente, vendedor, headers_admin):
    creada = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo()).json()

    assert cliente.get("/ventas", headers=vendedor["headers"]).status_code == 403
    assert cliente.get(f"/ventas/{creada['id']}", headers=vendedor["headers"]).status_code == 403
    assert cliente.get("/ventas").status_code == 401


def test_el_admin_ve_una_venta_y_da_404_si_no_existe(cliente, vendedor, headers_admin):
    creada = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("300.00")).json()

    assert cliente.get(f"/ventas/{creada['id']}", headers=headers_admin).json() == creada
    assert cliente.get("/ventas/99999", headers=headers_admin).status_code == 404


def test_listado_ordenado_por_fecha_descendente_y_paginado(
    cliente, headers_admin, admin_id, crear_venta_db
):
    fechas = [datetime(2026, 3, dia, 15, 0, tzinfo=timezone.utc) for dia in (3, 1, 5, 2, 4)]
    for fecha, monto in zip(fechas, ["30", "10", "50", "20", "40"]):
        crear_venta_db(admin_id, monto, fecha_hora=fecha)

    primera = cliente.get("/ventas?por_pagina=2&pagina=1", headers=headers_admin).json()
    segunda = cliente.get("/ventas?por_pagina=2&pagina=2", headers=headers_admin).json()
    tercera = cliente.get("/ventas?por_pagina=2&pagina=3", headers=headers_admin).json()

    assert primera["total"] == 5
    assert primera["pagina"] == 1 and primera["por_pagina"] == 2
    assert [v["total"] for v in primera["items"]] == ["50.00", "40.00"]
    assert [v["total"] for v in segunda["items"]] == ["30.00", "20.00"]
    assert [v["total"] for v in tercera["items"]] == ["10.00"]


def test_filtros_por_medio_estado_y_vendedor(
    cliente, headers_admin, admin_id, crear_usuario, crear_venta_db
):
    otro_id = crear_usuario("otro", "clave-otro-1")
    crear_venta_db(admin_id, "100", "efectivo", estado_arca="no_aplica")
    crear_venta_db(admin_id, "200", "tarjeta", estado_arca="pendiente")
    crear_venta_db(otro_id, "300", "tarjeta", estado_arca="facturada", numero_comprobante=7)
    crear_venta_db(otro_id, "400", "transferencia", estado_arca="pendiente")

    def totales(consulta):
        items = cliente.get(f"/ventas?{consulta}", headers=headers_admin).json()["items"]
        return sorted(v["total"] for v in items)

    assert totales("medio_pago=tarjeta") == ["200.00", "300.00"]
    assert totales("estado_arca=pendiente") == ["200.00", "400.00"]
    assert totales(f"vendedor_id={otro_id}") == ["300.00", "400.00"]
    assert totales(f"vendedor_id={otro_id}&medio_pago=tarjeta&estado_arca=facturada") == ["300.00"]
    assert cliente.get("/ventas?medio_pago=cheque", headers=headers_admin).status_code == 422


def test_filtro_de_fechas_usa_la_hora_de_argentina(cliente, headers_admin, admin_id, crear_venta_db):
    # 01:30 UTC del 2 de marzo son las 22:30 del 1 de marzo en Argentina.
    crear_venta_db(admin_id, "111", fecha_hora=datetime(2026, 3, 2, 1, 30, tzinfo=timezone.utc))
    # 03:00 UTC del 2 de marzo son las 00:00 del 2 de marzo en Argentina.
    crear_venta_db(admin_id, "222", fecha_hora=datetime(2026, 3, 2, 3, 0, tzinfo=timezone.utc))

    def totales(consulta):
        items = cliente.get(f"/ventas?{consulta}", headers=headers_admin).json()["items"]
        return sorted(v["total"] for v in items)

    assert totales("desde=2026-03-01&hasta=2026-03-01") == ["111.00"]
    assert totales("desde=2026-03-02&hasta=2026-03-02") == ["222.00"]
    assert totales("desde=2026-03-01&hasta=2026-03-02") == ["111.00", "222.00"]
    assert totales("desde=2026-03-02") == ["222.00"]
    assert totales("hasta=2026-03-01") == ["111.00"]


def test_rango_de_fechas_invertido_da_400(cliente, headers_admin):
    respuesta = cliente.get("/ventas?desde=2026-03-05&hasta=2026-03-01", headers=headers_admin)
    assert respuesta.status_code == 400


def test_fecha_con_formato_malo_da_422(cliente, headers_admin):
    assert cliente.get("/ventas?desde=ayer", headers=headers_admin).status_code == 422


def test_por_pagina_fuera_de_rango_da_422(cliente, headers_admin):
    assert cliente.get("/ventas?por_pagina=0", headers=headers_admin).status_code == 422
    assert cliente.get("/ventas?por_pagina=201", headers=headers_admin).status_code == 422
    assert cliente.get("/ventas?pagina=0", headers=headers_admin).status_code == 422
