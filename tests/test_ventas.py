import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import Venta
from tests.utiles import con_token


@pytest.fixture()
def vendedor(cliente, crear_usuario, iniciar_sesion):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    return {"id": vendedor_id, "headers": con_token(iniciar_sesion("vende", "clave-vende-1"))}


def _cuerpo(total="1250.50", medio_pago="efectivo", id_cliente=None, tarjeta_id=None, rubro_id=1):
    # Id 1: "Carne", el rubro predeterminado de prueba que siembra el fixture "cliente".
    cuerpo = {
        "subtotal": total,
        "medio_pago": medio_pago,
        "id_cliente": str(id_cliente or uuid.uuid4()),
        "rubro_id": rubro_id,
    }
    if medio_pago == "tarjeta":
        # Id 1: la tarjeta de prueba que siembra el fixture "cliente".
        cuerpo["tarjeta_id"] = 1 if tarjeta_id is None else tarjeta_id
    return cuerpo


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
    assert venta["fecha_hora"].endswith(("Z", "+00:00"))


def test_la_respuesta_de_crear_venta_no_trae_ningun_dato_fiscal(cliente, vendedor):
    """El vendedor solo se entera de que la venta se registró: nada de estado
    de facturación, CAE ni número de comprobante, ni siquiera para un medio
    que no se factura (estado "no_aplica")."""
    respuesta = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago="efectivo"))

    assert respuesta.status_code == 201
    campos_fiscales = {
        "estado_arca",
        "tipo_comprobante",
        "punto_venta",
        "numero_comprobante",
        "cae",
        "cae_vencimiento",
        "error_detalle",
        "anulada",
        "anulada_motivo",
        "anulada_por",
        "anulada_en",
    }
    assert campos_fiscales.isdisjoint(respuesta.json().keys())


@pytest.mark.parametrize("medio", ["tarjeta", "transferencia"])
def test_tarjeta_y_transferencia_quedan_pendientes_de_facturar(cliente, vendedor, headers_admin, medio):
    respuesta = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago=medio))

    assert respuesta.status_code == 201
    venta_admin = cliente.get(f"/ventas/{respuesta.json()['id']}", headers=headers_admin).json()
    assert venta_admin["estado_arca"] == "pendiente"


def test_el_estado_fiscal_sigue_la_configuracion(cliente, vendedor, headers_admin):
    from tests.test_configuracion import CAMBIO_VALIDO

    cliente.put(
        "/configuracion",
        headers=headers_admin,
        json={**CAMBIO_VALIDO, "facturar_efectivo": True, "facturar_tarjeta": False, "facturar_transferencia": True},
    )

    efectivo = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago="efectivo"))
    tarjeta = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago="tarjeta"))
    transferencia = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo(medio_pago="transferencia")
    )

    def estado(respuesta):
        return cliente.get(f"/ventas/{respuesta.json()['id']}", headers=headers_admin).json()["estado_arca"]

    assert estado(efectivo) == "pendiente"
    assert estado(tarjeta) == "no_aplica"
    assert estado(transferencia) == "pendiente"


def test_el_admin_tambien_puede_cobrar(cliente, headers_admin, admin_id):
    respuesta = cliente.post("/ventas", headers=headers_admin, json=_cuerpo())
    assert respuesta.status_code == 201
    assert respuesta.json()["vendedor_id"] == admin_id


def test_el_admin_si_recibe_el_dato_fiscal_al_cobrar(cliente, headers_admin):
    """A diferencia del vendedor: al admin no hace falta ocultárselo."""
    respuesta = cliente.post("/ventas", headers=headers_admin, json=_cuerpo(medio_pago="tarjeta"))
    assert respuesta.status_code == 201
    assert respuesta.json()["estado_arca"] == "pendiente"


def test_el_vendedor_y_la_fecha_no_se_toman_del_cuerpo(cliente, vendedor, admin_id, headers_admin):
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
    venta_admin = cliente.get(f"/ventas/{venta['id']}", headers=headers_admin).json()
    assert venta_admin["estado_arca"] == "no_aplica"
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
    faltante = {"subtotal": "10.00", "medio_pago": "efectivo"}

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

    venta_admin = cliente.get(f"/ventas/{creada['id']}", headers=headers_admin).json()
    assert venta_admin["id"] == creada["id"]
    assert venta_admin["total"] == creada["total"]
    assert venta_admin["estado_arca"] == "no_aplica"
    assert venta_admin["anulada"] is False
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


# ---------------------------------------------------------------- anulación: reglas generales


def test_admin_anula_una_venta_en_efectivo_de_una_sin_tocar_arca(cliente, headers_admin, admin_id, crear_venta_db):
    """no_aplica (efectivo, nunca se facturó): no hay nada que reversar ante
    ARCA, así que queda anulada al instante, en estado "sin_comprobante"."""
    venta_id = crear_venta_db(admin_id, "100", "efectivo")

    respuesta = cliente.post(
        f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "Se cobró por error"}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["anulada"] is True
    assert cuerpo["anulada_por"] == admin_id
    assert cuerpo["anulada_en"] is not None
    assert cuerpo["anulacion"]["estado"] == "sin_comprobante"
    assert cuerpo["anulacion"]["motivo"] == "Se cobró por error"
    assert cuerpo["anulacion"]["cae"] is None


def test_admin_anula_una_venta_con_fallo_de_facturacion_de_una(cliente, headers_admin, admin_id, crear_venta_db):
    """Nunca tuvo CAE (ARCA la rechazó): tampoco hay nada que reversar."""
    venta_id = crear_venta_db(admin_id, "100", "tarjeta", estado_arca="fallo", error_detalle="rechazada")

    respuesta = cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "x"})
    assert respuesta.status_code == 200
    assert respuesta.json()["anulacion"]["estado"] == "sin_comprobante"


def test_no_se_puede_anular_una_venta_pendiente_de_facturar(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = crear_venta_db(admin_id, "100", "tarjeta", estado_arca="pendiente")

    respuesta = cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "x"})
    assert respuesta.status_code == 400
    assert "pendiente" in respuesta.json()["detail"].lower() or "facturando" in respuesta.json()["detail"].lower()


def test_anular_una_venta_facturada_arma_la_anulacion_pendiente_de_nota_de_credito(
    cliente, headers_admin, admin_id, crear_venta_db, monkeypatch
):
    from app.arca import wsaa

    venta_id = crear_venta_db(
        admin_id,
        "121.00",
        "tarjeta",
        estado_arca="facturada",
        numero_comprobante=5,
        tipo_comprobante="6",
        punto_venta=1,
        cae="CAE-5",
    )
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: False)  # no llega a tocar la red

    respuesta = cliente.post(
        f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "Reclamo del cliente"}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["anulada"] is True
    assert cuerpo["anulacion"]["estado"] == "pendiente"  # sin certificado: se reintenta en el próximo ciclo
    assert cuerpo["anulacion"]["cae"] is None


def test_no_se_puede_anular_dos_veces(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = crear_venta_db(admin_id, "100", "efectivo")
    cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "primera"})

    respuesta = cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "segunda"})
    assert respuesta.status_code == 400


def test_anular_venta_inexistente_da_404(cliente, headers_admin):
    assert cliente.post("/ventas/9999/anular", headers=headers_admin, json={"motivo": "x"}).status_code == 404


def test_anular_sin_motivo_da_422(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = crear_venta_db(admin_id, "100", "efectivo")
    assert cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": ""}).status_code == 422
    assert cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={}).status_code == 422


def test_anular_queda_en_la_auditoria(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = crear_venta_db(admin_id, "100", "efectivo")
    cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "Duplicada"})

    filas = cliente.get("/auditoria?accion=venta.anular", headers=headers_admin).json()["items"]
    assert len(filas) == 1
    assert filas[0]["entidad"] == "venta"
    assert filas[0]["entidad_id"] == venta_id
    assert filas[0]["detalle"]["motivo"] == "Duplicada"


def test_una_venta_anulada_no_cuenta_en_el_resumen_y_las_anulaciones_se_ven_aparte(
    cliente, headers_admin, admin_id, crear_venta_db
):
    from app.fechas import hoy_argentina

    venta_id = crear_venta_db(admin_id, "500", "efectivo")
    hoy = hoy_argentina().isoformat()

    antes = cliente.get(f"/resumen?desde={hoy}&hasta={hoy}", headers=headers_admin).json()
    assert antes["total_vendido"] == "500.00"
    assert antes["cantidad_anulaciones"] == 0
    assert antes["monto_anulaciones"] == "0.00"

    cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "x"})

    despues = cliente.get(f"/resumen?desde={hoy}&hasta={hoy}", headers=headers_admin).json()
    assert despues["total_vendido"] == "0.00"
    assert despues["cantidad_ventas"] == 0
    assert despues["cantidad_anulaciones"] == 1
    assert despues["monto_anulaciones"] == "500.00"


# ---------------------------------------------------------------- anulación: el vendedor


def test_vendedor_anula_su_ultima_venta_dentro_de_la_ventana(cliente, vendedor):
    creada = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo")).json()

    respuesta = cliente.post(
        f"/ventas/{creada['id']}/anular", headers=vendedor["headers"], json={"motivo": "Me equivoqué"}
    )
    assert respuesta.status_code == 200
    # Sigue sin recibir ningún dato fiscal, ni siquiera de la anulación.
    campos_fiscales = {"estado_arca", "anulada", "anulacion", "cae", "numero_comprobante"}
    assert campos_fiscales.isdisjoint(respuesta.json().keys())


def test_vendedor_no_puede_anular_si_no_es_su_ultima_venta(cliente, vendedor):
    primera = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo")).json()
    cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("50.00", "efectivo"))

    respuesta = cliente.post(
        f"/ventas/{primera['id']}/anular", headers=vendedor["headers"], json={"motivo": "x"}
    )
    assert respuesta.status_code == 403


def test_vendedor_no_puede_anular_pasada_la_ventana_de_tiempo(cliente, vendedor, crear_venta_db):
    hace_once_minutos = datetime.now(timezone.utc) - timedelta(minutes=11)
    venta_id = crear_venta_db(vendedor["id"], "100", "efectivo", fecha_hora=hace_once_minutos)

    respuesta = cliente.post(f"/ventas/{venta_id}/anular", headers=vendedor["headers"], json={"motivo": "x"})
    assert respuesta.status_code == 403
    assert "10 minutos" in respuesta.json()["detail"]


def test_vendedor_no_puede_anular_la_venta_de_otro(cliente, vendedor, admin_id, crear_venta_db):
    venta_id = crear_venta_db(admin_id, "100", "efectivo")
    respuesta = cliente.post(f"/ventas/{venta_id}/anular", headers=vendedor["headers"], json={"motivo": "x"})
    assert respuesta.status_code == 403


def test_admin_puede_anular_aunque_no_sea_la_ultima_venta_ni_este_en_la_ventana(
    cliente, headers_admin, admin_id, crear_venta_db
):
    hace_una_hora = datetime.now(timezone.utc) - timedelta(hours=1)
    venta_id = crear_venta_db(admin_id, "100", "efectivo", fecha_hora=hace_una_hora)
    crear_venta_db(admin_id, "50", "efectivo")  # una más nueva: igual el admin puede con la vieja

    respuesta = cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "x"})
    assert respuesta.status_code == 200


# ---------------------------------------------------------------- descuentos y recargos


def test_el_recargo_depende_de_la_tarjeta_elegida(cliente, vendedor, crear_tarjeta_db):
    visa_id = crear_tarjeta_db("Visa 1 pago", "10.00")

    efectivo = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo")).json()
    tarjeta = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", tarjeta_id=visa_id)
    ).json()

    assert efectivo["total"] == "100.00"
    assert efectivo["ajuste_tipo"] is None
    assert tarjeta["subtotal"] == "100.00"
    assert tarjeta["total"] == "110.00"
    assert tarjeta["ajuste_tipo"] == "recargo"
    assert tarjeta["ajuste_origen"] == "medio_pago"
    assert tarjeta["ajuste_monto"] == "10.00"
    assert "Visa 1 pago" in tarjeta["ajuste_detalle"]


def test_el_efectivo_nunca_tiene_recargo_aunque_este_configurado(cliente, vendedor, headers_admin):
    from tests.test_configuracion import CAMBIO_VALIDO

    cliente.put(
        "/configuracion", headers=headers_admin, json={**CAMBIO_VALIDO, "recargo_transferencia_porcentaje": "8.00"}
    )

    efectivo = cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo")).json()

    assert efectivo["subtotal"] == "100.00"
    assert efectivo["total"] == "100.00"
    assert efectivo["ajuste_tipo"] is None
    assert efectivo["ajuste_origen"] is None
    assert efectivo["ajuste_monto"] is None


def test_una_tarjeta_con_recargo_cero_no_le_cambia_el_precio(cliente, vendedor, crear_tarjeta_db):
    debito_id = crear_tarjeta_db("Débito", "0")

    respuesta = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", tarjeta_id=debito_id)
    ).json()

    assert respuesta["total"] == "100.00"
    assert respuesta["ajuste_tipo"] is None


def test_distintas_tarjetas_tienen_distinto_recargo(cliente, vendedor, crear_tarjeta_db):
    visa_id = crear_tarjeta_db("Visa 1 pago", "15.00", orden=1)
    naranja_id = crear_tarjeta_db("Naranja 1 pago", "20.00", orden=2)

    visa = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", tarjeta_id=visa_id)
    ).json()
    naranja = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", tarjeta_id=naranja_id)
    ).json()

    assert visa["total"] == "115.00"
    assert naranja["total"] == "120.00"


def test_elegir_tarjeta_es_obligatorio_al_cobrar_con_tarjeta(cliente, vendedor):
    respuesta = cliente.post(
        "/ventas",
        headers=vendedor["headers"],
        json={"subtotal": "100.00", "medio_pago": "tarjeta", "rubro_id": 1, "id_cliente": str(uuid.uuid4())},
    )
    assert respuesta.status_code == 400


def test_no_se_puede_elegir_una_tarjeta_inactiva(cliente, vendedor, crear_tarjeta_db):
    inactiva_id = crear_tarjeta_db("Vieja", "5.00", activa=False)

    respuesta = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", tarjeta_id=inactiva_id)
    )
    assert respuesta.status_code == 400


def test_tarjeta_id_solo_vale_si_el_medio_de_pago_es_tarjeta(cliente, vendedor):
    respuesta = cliente.post(
        "/ventas",
        headers=vendedor["headers"],
        json={
            "subtotal": "100.00", "medio_pago": "efectivo", "tarjeta_id": 1, "rubro_id": 1,
            "id_cliente": str(uuid.uuid4()),
        },
    )
    assert respuesta.status_code == 400


def test_reintentar_con_otra_tarjeta_da_409(cliente, vendedor, crear_tarjeta_db):
    visa_id = crear_tarjeta_db("Visa 1 pago", "10.00")
    naranja_id = crear_tarjeta_db("Naranja 1 pago", "20.00", orden=2)
    id_cliente = uuid.uuid4()

    cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", id_cliente, visa_id))
    respuesta = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", id_cliente, naranja_id)
    )
    assert respuesta.status_code == 409


def test_cambiar_el_recargo_de_una_tarjeta_no_afecta_ventas_ya_cobradas(
    cliente, vendedor, headers_admin, crear_tarjeta_db
):
    visa_id = crear_tarjeta_db("Visa 1 pago", "10.00")
    creada = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", tarjeta_id=visa_id)
    ).json()
    assert creada["total"] == "110.00"

    cliente.put(
        f"/tarjetas/{visa_id}",
        headers=headers_admin,
        json={"nombre": "Visa 1 pago", "tipo": "credito", "recargo_porcentaje": "25.00", "activa": True, "orden": 1},
    )

    venta_admin = cliente.get(f"/ventas/{creada['id']}", headers=headers_admin).json()
    assert venta_admin["total"] == "110.00"


def test_el_resumen_muestra_el_total_de_recargos(cliente, vendedor, headers_admin, crear_tarjeta_db):
    from app.fechas import hoy_argentina

    visa_id = crear_tarjeta_db("Visa 1 pago", "10.00")
    cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "tarjeta", tarjeta_id=visa_id))
    cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo"))

    hoy = hoy_argentina().isoformat()
    resumen = cliente.get(f"/resumen?desde={hoy}&hasta={hoy}", headers=headers_admin).json()
    assert resumen["total_recargos"] == "10.00"


# ---------------------------------------------------------------- rubros


def test_no_se_puede_cobrar_sin_elegir_rubro(cliente, vendedor):
    respuesta = cliente.post(
        "/ventas",
        headers=vendedor["headers"],
        json={"subtotal": "100.00", "medio_pago": "efectivo", "id_cliente": str(uuid.uuid4())},
    )
    assert respuesta.status_code == 422


def test_no_se_puede_elegir_un_rubro_inactivo(cliente, vendedor, crear_rubro_db):
    inactivo_id = crear_rubro_db("Fiambres", activo=False)

    respuesta = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo", rubro_id=inactivo_id)
    )
    assert respuesta.status_code == 400


def test_rubro_inexistente_da_400(cliente, vendedor):
    respuesta = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo", rubro_id=9999)
    )
    assert respuesta.status_code == 400


def test_reintentar_con_otro_rubro_da_409(cliente, vendedor, crear_rubro_db):
    embutidos_id = crear_rubro_db("Embutidos de prueba", alicuota="21")
    id_cliente = uuid.uuid4()

    cliente.post("/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo", id_cliente, rubro_id=1))
    respuesta = cliente.post(
        "/ventas",
        headers=vendedor["headers"],
        json=_cuerpo("100.00", "efectivo", id_cliente, rubro_id=embutidos_id),
    )
    assert respuesta.status_code == 409


def test_el_rubro_elegido_queda_registrado_en_la_venta(cliente, vendedor, crear_rubro_db):
    embutidos_id = crear_rubro_db("Embutidos de prueba", alicuota="21")

    respuesta = cliente.post(
        "/ventas", headers=vendedor["headers"], json=_cuerpo("100.00", "efectivo", rubro_id=embutidos_id)
    ).json()

    assert respuesta["rubro_id"] == embutidos_id
    assert respuesta["rubro_nombre"] == "Embutidos de prueba"
