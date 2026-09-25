from tests.utiles import PASSWORD_ADMIN, con_token

NUEVO = {"nombre": "María Pérez", "usuario": "maria", "password": "clave-maria-1", "rol": "vendedor"}


def _login(cliente, usuario, password):
    return cliente.post("/auth/login", json={"usuario": usuario, "password": password})


def test_vendedor_recibe_403_en_todo_usuarios(cliente, crear_usuario, iniciar_sesion, admin_id):
    vendedor_id = crear_usuario("vende", "clave-vende-1", rol="vendedor")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    assert cliente.get("/usuarios", headers=headers).status_code == 403
    assert cliente.post("/usuarios", headers=headers, json=NUEVO).status_code == 403
    assert (
        cliente.patch(f"/usuarios/{vendedor_id}", headers=headers, json={"rol": "admin"}).status_code
        == 403
    )
    assert (
        cliente.put(
            f"/usuarios/{admin_id}/password", headers=headers, json={"password": "hackeada-123"}
        ).status_code
        == 403
    )
    # y no llegó a cambiar nada
    assert _login(cliente, "admin", PASSWORD_ADMIN).status_code == 200


def test_usuarios_sin_token_da_401(cliente):
    assert cliente.get("/usuarios").status_code == 401


def test_admin_lista_usuarios_sin_exponer_el_hash(cliente, headers_admin):
    respuesta = cliente.get("/usuarios", headers=headers_admin)
    assert respuesta.status_code == 200
    assert [u["usuario"] for u in respuesta.json()] == ["admin"]
    assert "password_hash" not in respuesta.json()[0]


def test_admin_crea_un_vendedor_y_este_puede_entrar(cliente, headers_admin):
    creado = cliente.post("/usuarios", headers=headers_admin, json=NUEVO)
    assert creado.status_code == 201
    assert creado.json()["usuario"] == "maria"
    assert creado.json()["rol"] == "vendedor"
    assert creado.json()["activo"] is True
    assert creado.json()["creado_en"].endswith(("Z", "+00:00"))
    assert "password_hash" not in creado.json()

    entrada = _login(cliente, "maria", "clave-maria-1")
    assert entrada.status_code == 200
    assert entrada.json()["usuario"]["rol"] == "vendedor"


def test_el_usuario_se_guarda_en_minusculas(cliente, headers_admin):
    creado = cliente.post("/usuarios", headers=headers_admin, json={**NUEVO, "usuario": " MARIA "})
    assert creado.status_code == 201
    assert creado.json()["usuario"] == "maria"


def test_usuario_repetido_da_409(cliente, headers_admin):
    assert cliente.post("/usuarios", headers=headers_admin, json=NUEVO).status_code == 201
    repetido = cliente.post("/usuarios", headers=headers_admin, json=NUEVO)
    assert repetido.status_code == 409

    con_otras_mayusculas = cliente.post(
        "/usuarios", headers=headers_admin, json={**NUEVO, "usuario": "MARIA"}
    )
    assert con_otras_mayusculas.status_code == 409


def test_password_corta_da_422_y_no_se_devuelve(cliente, headers_admin, admin_id):
    al_crear = cliente.post("/usuarios", headers=headers_admin, json={**NUEVO, "password": "corta1"})
    assert al_crear.status_code == 422
    assert "corta1" not in al_crear.text
    assert "al menos 8 caracteres" in al_crear.json()["detail"][0]["msg"]

    al_cambiar = cliente.put(
        f"/usuarios/{admin_id}/password", headers=headers_admin, json={"password": "corta1"}
    )
    assert al_cambiar.status_code == 422


def test_usuario_con_caracteres_invalidos_da_422(cliente, headers_admin):
    respuesta = cliente.post(
        "/usuarios", headers=headers_admin, json={**NUEVO, "usuario": "con espacio"}
    )
    assert respuesta.status_code == 422


def test_rol_invalido_da_422(cliente, headers_admin):
    respuesta = cliente.post("/usuarios", headers=headers_admin, json={**NUEVO, "rol": "dueño"})
    assert respuesta.status_code == 422


def test_cambiar_password_invalida_el_token_anterior(
    cliente, headers_admin, crear_usuario, iniciar_sesion
):
    vendedor_id = crear_usuario("vende", "clave-vieja-1")
    token_viejo = iniciar_sesion("vende", "clave-vieja-1")
    assert cliente.get("/auth/yo", headers=con_token(token_viejo)).status_code == 200

    cambio = cliente.put(
        f"/usuarios/{vendedor_id}/password", headers=headers_admin, json={"password": "clave-nueva-1"}
    )
    assert cambio.status_code == 204

    assert cliente.get("/auth/yo", headers=con_token(token_viejo)).status_code == 401
    assert _login(cliente, "vende", "clave-vieja-1").status_code == 401
    token_nuevo = iniciar_sesion("vende", "clave-nueva-1")
    assert cliente.get("/auth/yo", headers=con_token(token_nuevo)).status_code == 200


def test_desactivar_saca_al_usuario_al_instante(
    cliente, headers_admin, crear_usuario, iniciar_sesion
):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    token = iniciar_sesion("vende", "clave-vende-1")
    assert cliente.get("/auth/yo", headers=con_token(token)).status_code == 200

    respuesta = cliente.patch(
        f"/usuarios/{vendedor_id}", headers=headers_admin, json={"activo": False}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is False

    assert cliente.get("/auth/yo", headers=con_token(token)).status_code == 401
    assert _login(cliente, "vende", "clave-vende-1").status_code == 401


def test_reactivar_no_revive_los_tokens_viejos(cliente, headers_admin, crear_usuario, iniciar_sesion):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    token_viejo = iniciar_sesion("vende", "clave-vende-1")

    cliente.patch(f"/usuarios/{vendedor_id}", headers=headers_admin, json={"activo": False})
    cliente.patch(f"/usuarios/{vendedor_id}", headers=headers_admin, json={"activo": True})

    assert cliente.get("/auth/yo", headers=con_token(token_viejo)).status_code == 401
    assert _login(cliente, "vende", "clave-vende-1").status_code == 200


def test_cambiar_rol_invalida_el_token_y_da_permisos_nuevos(
    cliente, headers_admin, crear_usuario, iniciar_sesion
):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    token_viejo = iniciar_sesion("vende", "clave-vende-1")

    cliente.patch(f"/usuarios/{vendedor_id}", headers=headers_admin, json={"rol": "admin"})

    assert cliente.get("/usuarios", headers=con_token(token_viejo)).status_code == 401
    token_nuevo = iniciar_sesion("vende", "clave-vende-1")
    assert cliente.get("/usuarios", headers=con_token(token_nuevo)).status_code == 200


def test_cambiar_solo_el_nombre_no_saca_al_usuario(
    cliente, headers_admin, crear_usuario, iniciar_sesion
):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    token = iniciar_sesion("vende", "clave-vende-1")

    respuesta = cliente.patch(
        f"/usuarios/{vendedor_id}", headers=headers_admin, json={"nombre": "Nombre Nuevo"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Nombre Nuevo"
    assert cliente.get("/auth/yo", headers=con_token(token)).status_code == 200


def test_admin_no_puede_desactivarse_a_si_mismo(cliente, headers_admin, admin_id):
    respuesta = cliente.patch(f"/usuarios/{admin_id}", headers=headers_admin, json={"activo": False})
    assert respuesta.status_code == 400
    assert cliente.get("/auth/yo", headers=headers_admin).status_code == 200


def test_admin_no_puede_quitarse_el_rol_a_si_mismo(cliente, headers_admin, admin_id):
    respuesta = cliente.patch(f"/usuarios/{admin_id}", headers=headers_admin, json={"rol": "vendedor"})
    assert respuesta.status_code == 400
    assert cliente.get("/usuarios", headers=headers_admin).status_code == 200


def test_un_admin_puede_desactivar_a_otro_admin(cliente, headers_admin, crear_usuario):
    otro_id = crear_usuario("admin2", "clave-admin2-1", rol="admin")
    respuesta = cliente.patch(f"/usuarios/{otro_id}", headers=headers_admin, json={"activo": False})
    assert respuesta.status_code == 200
    assert cliente.get("/auth/yo", headers=headers_admin).status_code == 200


def test_usuario_inexistente_da_404(cliente, headers_admin):
    assert cliente.patch("/usuarios/9999", headers=headers_admin, json={"activo": False}).status_code == 404
    assert (
        cliente.put("/usuarios/9999/password", headers=headers_admin, json={"password": "clave-nueva-1"}).status_code
        == 404
    )
