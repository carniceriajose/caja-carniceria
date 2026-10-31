from tests.utiles import con_token


def test_el_vendedor_solo_ve_las_tarjetas_activas_y_en_orden(
    cliente, crear_usuario, iniciar_sesion, crear_tarjeta_db
):
    crear_tarjeta_db("Naranja 1 pago", "20.00", orden=3)
    crear_tarjeta_db("Vieja", "5.00", activa=False, orden=2)
    crear_tarjeta_db("Visa 1 pago", "15.00", orden=1)
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    respuesta = cliente.get("/tarjetas", headers=headers)
    assert respuesta.status_code == 200
    nombres = [t["nombre"] for t in respuesta.json()]
    # Incluye la "Tarjeta de prueba" (id 1) que siembra el fixture "cliente".
    assert nombres == ["Tarjeta de prueba", "Visa 1 pago", "Naranja 1 pago"]


def test_el_admin_ve_tambien_las_inactivas(cliente, headers_admin, crear_tarjeta_db):
    crear_tarjeta_db("Vieja", "5.00", activa=False, orden=2)

    respuesta = cliente.get("/tarjetas", headers=headers_admin)
    nombres = [t["nombre"] for t in respuesta.json()]
    assert "Vieja" in nombres


def test_sin_token_da_401(cliente):
    assert cliente.get("/tarjetas").status_code == 401


def test_solo_admin_puede_crear_tarjetas(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    respuesta = cliente.post(
        "/tarjetas",
        headers=headers,
        json={"nombre": "Visa", "tipo": "credito", "recargo_porcentaje": "15.00", "activa": True, "orden": 1},
    )
    assert respuesta.status_code == 403


def test_crear_tarjeta(cliente, headers_admin):
    respuesta = cliente.post(
        "/tarjetas",
        headers=headers_admin,
        json={"nombre": "Visa 1 pago", "tipo": "credito", "recargo_porcentaje": "15.00", "activa": True, "orden": 2},
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Visa 1 pago"
    assert cuerpo["tipo"] == "credito"
    assert cuerpo["recargo_porcentaje"] == "15.00"
    assert cuerpo["activa"] is True


def test_no_se_puede_crear_tarjeta_con_tipo_invalido(cliente, headers_admin):
    respuesta = cliente.post(
        "/tarjetas",
        headers=headers_admin,
        json={"nombre": "Visa 1 pago", "tipo": "otro", "recargo_porcentaje": "15.00", "activa": True, "orden": 2},
    )
    assert respuesta.status_code == 422


def test_no_se_puede_repetir_el_nombre_de_una_tarjeta(cliente, headers_admin, crear_tarjeta_db):
    crear_tarjeta_db("Visa 1 pago", "15.00")

    respuesta = cliente.post(
        "/tarjetas",
        headers=headers_admin,
        json={"nombre": "visa 1 pago", "tipo": "credito", "recargo_porcentaje": "10.00", "activa": True, "orden": 5},
    )
    assert respuesta.status_code == 409


def test_actualizar_tarjeta_cambia_recargo_y_estado(cliente, headers_admin, crear_tarjeta_db):
    tarjeta_id = crear_tarjeta_db("Visa 1 pago", "15.00")

    respuesta = cliente.put(
        f"/tarjetas/{tarjeta_id}",
        headers=headers_admin,
        json={"nombre": "Visa 1 pago", "tipo": "credito", "recargo_porcentaje": "18.00", "activa": False, "orden": 1},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["recargo_porcentaje"] == "18.00"
    assert cuerpo["activa"] is False


def test_actualizar_tarjeta_cambia_el_tipo(cliente, headers_admin, crear_tarjeta_db):
    tarjeta_id = crear_tarjeta_db("Débito", "0", tipo="debito")

    respuesta = cliente.put(
        f"/tarjetas/{tarjeta_id}",
        headers=headers_admin,
        json={"nombre": "Débito", "tipo": "credito", "recargo_porcentaje": "0", "activa": True, "orden": 1},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["tipo"] == "credito"


def test_desactivar_una_tarjeta_la_saca_del_listado_del_vendedor(
    cliente, headers_admin, crear_usuario, iniciar_sesion, crear_tarjeta_db
):
    tarjeta_id = crear_tarjeta_db("Visa 1 pago", "15.00")
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    cliente.put(
        f"/tarjetas/{tarjeta_id}",
        headers=headers_admin,
        json={"nombre": "Visa 1 pago", "tipo": "credito", "recargo_porcentaje": "15.00", "activa": False, "orden": 1},
    )

    nombres = [t["nombre"] for t in cliente.get("/tarjetas", headers=headers).json()]
    assert "Visa 1 pago" not in nombres


def test_tarjeta_inexistente_da_404(cliente, headers_admin):
    respuesta = cliente.put(
        "/tarjetas/9999",
        headers=headers_admin,
        json={"nombre": "x", "tipo": "credito", "recargo_porcentaje": "0", "activa": True, "orden": 1},
    )
    assert respuesta.status_code == 404
