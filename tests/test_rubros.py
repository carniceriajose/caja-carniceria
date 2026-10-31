from decimal import Decimal

from tests.utiles import con_token


def test_el_vendedor_solo_ve_los_rubros_activos_y_en_orden(
    cliente, crear_usuario, iniciar_sesion, crear_rubro_db
):
    crear_rubro_db("Pollo", orden=3)
    crear_rubro_db("Vieja", activo=False, orden=2)
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    respuesta = cliente.get("/rubros", headers=headers)
    assert respuesta.status_code == 200
    nombres = [r["nombre"] for r in respuesta.json()]
    # Incluye "Carne" (id 1, predeterminado) y "Embutidos" (id 2) que siembra
    # el fixture "cliente".
    assert nombres == ["Carne", "Embutidos", "Pollo"]


def test_el_admin_ve_tambien_los_inactivos(cliente, headers_admin, crear_rubro_db):
    crear_rubro_db("Vieja", activo=False)

    respuesta = cliente.get("/rubros", headers=headers_admin)
    nombres = [r["nombre"] for r in respuesta.json()]
    assert "Vieja" in nombres


def test_sin_token_da_401(cliente):
    assert cliente.get("/rubros").status_code == 401


def test_solo_admin_puede_crear_rubros(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    respuesta = cliente.post(
        "/rubros",
        headers=headers,
        json={
            "nombre": "Pollo", "alicuota": "21.00", "descripcion_factura": "Venta de pollo",
            "activo": True, "orden": 3, "es_predeterminado": False,
        },
    )
    assert respuesta.status_code == 403


def test_crear_rubro(cliente, headers_admin):
    respuesta = cliente.post(
        "/rubros",
        headers=headers_admin,
        json={
            "nombre": "Pollo", "alicuota": "21.00", "descripcion_factura": "Venta de pollo",
            "activo": True, "orden": 3, "es_predeterminado": False,
        },
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Pollo"
    assert cuerpo["alicuota"] == "21.00"
    assert cuerpo["es_predeterminado"] is False


def test_no_se_puede_repetir_el_nombre_de_un_rubro(cliente, headers_admin, crear_rubro_db):
    crear_rubro_db("Pollo")

    respuesta = cliente.post(
        "/rubros",
        headers=headers_admin,
        json={
            "nombre": "pollo", "alicuota": "21.00", "descripcion_factura": "Venta de pollo",
            "activo": True, "orden": 5, "es_predeterminado": False,
        },
    )
    assert respuesta.status_code == 409


def test_alicuota_no_permitida_da_422(cliente, headers_admin):
    respuesta = cliente.post(
        "/rubros",
        headers=headers_admin,
        json={
            "nombre": "Pollo", "alicuota": "15", "descripcion_factura": "Venta de pollo",
            "activo": True, "orden": 3, "es_predeterminado": False,
        },
    )
    assert respuesta.status_code == 422
    assert "Alícuota no válida" in respuesta.text


def test_rubro_inexistente_da_404(cliente, headers_admin):
    respuesta = cliente.put(
        "/rubros/9999",
        headers=headers_admin,
        json={
            "nombre": "x", "alicuota": "21.00", "descripcion_factura": "x",
            "activo": True, "orden": 1, "es_predeterminado": False,
        },
    )
    assert respuesta.status_code == 404


# ---------------------------------------------------------------- predeterminado y activo


def test_crear_un_rubro_como_predeterminado_le_saca_el_predeterminado_al_anterior(cliente, headers_admin):
    respuesta = cliente.post(
        "/rubros",
        headers=headers_admin,
        json={
            "nombre": "Pollo", "alicuota": "21.00", "descripcion_factura": "Venta de pollo",
            "activo": True, "orden": 3, "es_predeterminado": True,
        },
    )
    assert respuesta.status_code == 201

    rubros = {r["nombre"]: r for r in cliente.get("/rubros", headers=headers_admin).json()}
    assert rubros["Pollo"]["es_predeterminado"] is True
    assert rubros["Carne"]["es_predeterminado"] is False


def test_no_se_puede_sacar_el_predeterminado_sin_elegir_otro(cliente, headers_admin):
    """"Carne" (id 1) es el predeterminado de prueba: no se lo puede editar
    a es_predeterminado=False directamente."""
    respuesta = cliente.put(
        "/rubros/1",
        headers=headers_admin,
        json={
            "nombre": "Carne", "alicuota": "10.50", "descripcion_factura": "Venta de carne",
            "activo": True, "orden": 1, "es_predeterminado": False,
        },
    )
    assert respuesta.status_code == 400


def test_cambiar_el_predeterminado_a_otro_rubro_funciona(cliente, headers_admin):
    respuesta = cliente.put(
        "/rubros/2",
        headers=headers_admin,
        json={
            "nombre": "Embutidos", "alicuota": "21.00", "descripcion_factura": "Venta de embutidos",
            "activo": True, "orden": 2, "es_predeterminado": True,
        },
    )
    assert respuesta.status_code == 200

    rubros = {r["nombre"]: r for r in cliente.get("/rubros", headers=headers_admin).json()}
    assert rubros["Embutidos"]["es_predeterminado"] is True
    assert rubros["Carne"]["es_predeterminado"] is False


def test_el_predeterminado_no_puede_quedar_inactivo(cliente, headers_admin):
    respuesta = cliente.put(
        "/rubros/1",
        headers=headers_admin,
        json={
            "nombre": "Carne", "alicuota": "10.50", "descripcion_factura": "Venta de carne",
            "activo": False, "orden": 1, "es_predeterminado": True,
        },
    )
    assert respuesta.status_code == 400


def test_no_se_puede_desactivar_el_ultimo_rubro_activo(cliente, headers_admin):
    # Desactivar "Embutidos" (no predeterminado) deja solo a "Carne" activo: ok.
    respuesta = cliente.put(
        "/rubros/2",
        headers=headers_admin,
        json={
            "nombre": "Embutidos", "alicuota": "21.00", "descripcion_factura": "Venta de embutidos",
            "activo": False, "orden": 2, "es_predeterminado": False,
        },
    )
    assert respuesta.status_code == 200

    # Pero "Carne" es el predeterminado y ya es el único activo: no se puede
    # tocar (ni por la regla de predeterminado activo, ni por quedar sin ninguno).
    respuesta = cliente.put(
        "/rubros/1",
        headers=headers_admin,
        json={
            "nombre": "Carne", "alicuota": "10.50", "descripcion_factura": "Venta de carne",
            "activo": False, "orden": 1, "es_predeterminado": True,
        },
    )
    assert respuesta.status_code == 400


def test_desactivar_un_rubro_lo_saca_del_listado_del_vendedor(
    cliente, headers_admin, crear_usuario, iniciar_sesion
):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    cliente.put(
        "/rubros/2",
        headers=headers_admin,
        json={
            "nombre": "Embutidos", "alicuota": "21.00", "descripcion_factura": "Venta de embutidos",
            "activo": False, "orden": 2, "es_predeterminado": False,
        },
    )

    nombres = [r["nombre"] for r in cliente.get("/rubros", headers=headers).json()]
    assert "Embutidos" not in nombres


def test_cambiar_la_alicuota_de_un_rubro_no_afecta_ventas_ya_facturadas(
    cliente, headers_admin, admin_id, crear_venta_db
):
    """La alícuota queda congelada en la venta al cobrar (ver app/routers/ventas.py):
    cambiarla en el rubro después no tiene que afectar a una venta ya facturada."""
    venta_id = crear_venta_db(
        admin_id, "121.00", "tarjeta", estado_arca="facturada", numero_comprobante=1,
        tipo_comprobante="6", punto_venta=1, cae="30414141414141",
        rubro_id=1, rubro_nombre="Carne", alicuota_iva="10.5",
    )
    antes = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()
    assert antes["iva_contenido"] == "11.50"  # 121.00 a 10,5%

    cliente.put(
        "/rubros/1",
        headers=headers_admin,
        json={
            "nombre": "Carne", "alicuota": "21.00", "descripcion_factura": "Venta de carne",
            "activo": True, "orden": 1, "es_predeterminado": True,
        },
    )

    despues = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()
    assert despues["iva_contenido"] == "11.50"  # no cambió: ya estaba congelada
