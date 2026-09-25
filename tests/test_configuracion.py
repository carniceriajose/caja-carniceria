from tests.utiles import con_token

DEFECTO = {"facturar_efectivo": False, "facturar_tarjeta": True, "facturar_transferencia": True}


def test_valores_por_defecto(cliente, headers_admin):
    respuesta = cliente.get("/configuracion", headers=headers_admin)
    assert respuesta.status_code == 200
    assert respuesta.json() == DEFECTO


def test_el_vendedor_puede_ver_la_configuracion(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    assert cliente.get("/configuracion", headers=headers).json() == DEFECTO


def test_sin_token_da_401(cliente):
    assert cliente.get("/configuracion").status_code == 401
    assert cliente.put("/configuracion", json=DEFECTO).status_code == 401


def test_el_vendedor_no_puede_cambiarla(cliente, crear_usuario, iniciar_sesion, headers_admin):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    cambio = {**DEFECTO, "facturar_efectivo": True}
    assert cliente.put("/configuracion", headers=headers, json=cambio).status_code == 403
    assert cliente.get("/configuracion", headers=headers_admin).json() == DEFECTO


def test_el_admin_puede_cambiarla_y_queda_guardada(cliente, headers_admin):
    cambio = {"facturar_efectivo": True, "facturar_tarjeta": False, "facturar_transferencia": True}
    respuesta = cliente.put("/configuracion", headers=headers_admin, json=cambio)

    assert respuesta.status_code == 200
    assert respuesta.json() == cambio
    assert cliente.get("/configuracion", headers=headers_admin).json() == cambio


def test_faltando_un_campo_da_422(cliente, headers_admin):
    respuesta = cliente.put("/configuracion", headers=headers_admin, json={"facturar_efectivo": True})
    assert respuesta.status_code == 422
