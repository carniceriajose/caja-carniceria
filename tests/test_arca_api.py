import uuid
from datetime import datetime, timedelta, timezone

from app.arca import wsaa, wsfe
from tests.utiles import con_token

TICKET_FALSO = wsaa.TicketInfo(
    token="token-de-prueba", sign="sign-de-prueba", vence_en=datetime.now(timezone.utc) + timedelta(hours=1)
)


def _respuesta_aprobada(numero, cae):
    return {
        "FeDetResp": {
            "FECAEDetResponse": [
                {"Resultado": "A", "CAE": cae, "CAEFchVto": "20261231", "CbteDesde": numero}
            ]
        }
    }


def _preparar_arca_aprueba_todo(monkeypatch, ultimo_autorizado=10, cae="CAE-100"):
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: True)
    monkeypatch.setattr(wsaa, "obtener_o_renovar_ticket", lambda db: TICKET_FALSO)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: ultimo_autorizado)
    monkeypatch.setattr(
        wsfe, "solicitar_cae", lambda t, pv, tipo, detalle: _respuesta_aprobada(detalle["CbteDesde"], cae)
    )


# ---------------------------------------------------------------- GET /ventas/{id}/fiscal


def test_vendedor_nunca_ve_el_estado_fiscal_ni_de_ventas_ajenas_ni_propias(
    cliente, crear_usuario, iniciar_sesion, crear_venta_db, admin_id
):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    venta_propia_id = crear_venta_db(vendedor_id, "100", "tarjeta", estado_arca="pendiente")
    venta_ajena_id = crear_venta_db(admin_id, "100", "tarjeta", estado_arca="pendiente")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    # El estado fiscal es información administrativa: ni siquiera de su propia venta.
    assert cliente.get(f"/ventas/{venta_propia_id}/fiscal", headers=headers).status_code == 403
    assert cliente.get(f"/ventas/{venta_ajena_id}/fiscal", headers=headers).status_code == 403


def test_admin_puede_ver_el_estado_fiscal_de_cualquier_venta(
    cliente, headers_admin, crear_usuario, crear_venta_db
):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    venta_id = crear_venta_db(vendedor_id, "100", "tarjeta", estado_arca="facturada", numero_comprobante=5)

    respuesta = cliente.get(f"/ventas/{venta_id}/fiscal", headers=headers_admin)
    assert respuesta.status_code == 200
    assert respuesta.json()["estado_arca"] == "facturada"


def test_estado_fiscal_de_venta_inexistente_da_404(cliente, headers_admin):
    assert cliente.get("/ventas/9999/fiscal", headers=headers_admin).status_code == 404


def test_estado_fiscal_sin_token_da_401(cliente, crear_venta_db, admin_id):
    venta_id = crear_venta_db(admin_id, "100", "tarjeta")
    assert cliente.get(f"/ventas/{venta_id}/fiscal").status_code == 401


# ---------------------------------------------------------------- POST /ventas dispara la emisión


def test_post_ventas_factura_en_segundo_plano_y_el_polling_ve_el_resultado(
    cliente, crear_usuario, iniciar_sesion, headers_admin, monkeypatch
):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))
    _preparar_arca_aprueba_todo(monkeypatch, ultimo_autorizado=10, cae="CAE-11")

    creada = cliente.post(
        "/ventas",
        headers=headers,
        json={
            "subtotal": "500.00", "medio_pago": "tarjeta", "tarjeta_id": 1, "rubro_id": 1,
            "id_cliente": str(uuid.uuid4()),
        },
    )
    assert creada.status_code == 201
    assert "estado_arca" not in creada.json()  # el vendedor nunca recibe el dato fiscal

    # El estado real (para el admin) sí queda facturado.
    fiscal = cliente.get(f"/ventas/{creada.json()['id']}/fiscal", headers=headers_admin)
    assert fiscal.json()["estado_arca"] == "facturada"
    assert fiscal.json()["cae"] == "CAE-11"
    assert fiscal.json()["numero_comprobante"] == 11


def test_venta_en_efectivo_no_dispara_nada_y_queda_no_aplica(
    cliente, crear_usuario, iniciar_sesion, headers_admin, monkeypatch
):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    def no_debe_llamarse(*_a, **_k):
        raise AssertionError("una venta en efectivo no debería intentar facturarse")

    monkeypatch.setattr(wsaa, "hay_certificado_configurado", no_debe_llamarse)

    creada = cliente.post(
        "/ventas",
        headers=headers,
        json={"subtotal": "500.00", "medio_pago": "efectivo", "rubro_id": 1, "id_cliente": str(uuid.uuid4())},
    )
    assert creada.status_code == 201
    assert "estado_arca" not in creada.json()

    fiscal = cliente.get(f"/ventas/{creada.json()['id']}/fiscal", headers=headers_admin)
    assert fiscal.json()["estado_arca"] == "no_aplica"


# ---------------------------------------------------------------- /facturas/con-error y reintentar


def test_solo_admin_ve_facturas_con_error(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    assert cliente.get("/facturas/con-error", headers=headers).status_code == 403
    assert cliente.get("/facturas/con-error").status_code == 401


def test_facturas_con_error_lista_solo_las_fallidas(cliente, headers_admin, admin_id, crear_venta_db):
    crear_venta_db(admin_id, "100", "tarjeta", estado_arca="pendiente")
    crear_venta_db(admin_id, "200", "tarjeta", estado_arca="facturada", numero_comprobante=1)
    crear_venta_db(admin_id, "300", "tarjeta", estado_arca="fallo", error_detalle="ARCA rechazó el comprobante.")

    respuesta = cliente.get("/facturas/con-error", headers=headers_admin)
    assert respuesta.status_code == 200
    items = respuesta.json()["items"]
    assert len(items) == 1
    assert items[0]["total"] == "300.00"
    assert items[0]["error_detalle"] == "ARCA rechazó el comprobante."


def test_reintentar_factura_la_emite_de_nuevo(cliente, headers_admin, admin_id, crear_venta_db, monkeypatch):
    venta_id = crear_venta_db(admin_id, "100", "tarjeta", estado_arca="fallo", error_detalle="Falla anterior")
    _preparar_arca_aprueba_todo(monkeypatch, ultimo_autorizado=999, cae="CAE-1000")

    respuesta = cliente.post(f"/ventas/{venta_id}/reintentar-factura", headers=headers_admin)

    assert respuesta.status_code == 200
    assert respuesta.json()["estado_arca"] == "facturada"
    assert respuesta.json()["cae"] == "CAE-1000"


def test_no_se_puede_reintentar_una_venta_ya_facturada(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = crear_venta_db(admin_id, "100", "tarjeta", estado_arca="facturada", numero_comprobante=5)

    respuesta = cliente.post(f"/ventas/{venta_id}/reintentar-factura", headers=headers_admin)
    assert respuesta.status_code == 400


def test_reintentar_factura_inexistente_da_404(cliente, headers_admin):
    assert cliente.post("/ventas/9999/reintentar-factura", headers=headers_admin).status_code == 404


def test_solo_admin_puede_reintentar(cliente, crear_usuario, iniciar_sesion, crear_venta_db, admin_id):
    venta_id = crear_venta_db(admin_id, "100", "tarjeta", estado_arca="fallo", error_detalle="x")
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    assert cliente.post(f"/ventas/{venta_id}/reintentar-factura", headers=headers).status_code == 403


# ---------------------------------------------------------------- /arca/estado


def test_arca_estado_sin_certificado_no_revela_la_ruta(cliente, headers_admin, monkeypatch):
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: False)

    respuesta = cliente.get("/arca/estado", headers=headers_admin)
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["certificado_configurado"] is False
    assert datos["en_linea"] is None
    assert "c:" not in datos["detalle"].lower()
    assert ".key" not in datos["detalle"].lower() and ".crt" not in datos["detalle"].lower()


def test_arca_estado_con_certificado_y_arca_en_linea(cliente, headers_admin, monkeypatch):
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: True)
    monkeypatch.setattr(wsfe, "verificar_estado", lambda: {"AppServer": "OK", "DbServer": "OK", "AuthServer": "OK"})

    respuesta = cliente.get("/arca/estado", headers=headers_admin)
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["certificado_configurado"] is True
    assert datos["en_linea"] is True


def test_arca_estado_con_certificado_pero_arca_caida(cliente, headers_admin, monkeypatch):
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: True)

    def falla(*_a, **_k):
        raise TimeoutError("no responde")

    monkeypatch.setattr(wsfe, "verificar_estado", falla)

    respuesta = cliente.get("/arca/estado", headers=headers_admin)
    assert respuesta.status_code == 200
    assert respuesta.json()["en_linea"] is False


def test_solo_admin_ve_arca_estado(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))
    assert cliente.get("/arca/estado", headers=headers).status_code == 403
