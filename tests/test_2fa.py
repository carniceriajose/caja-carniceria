import pyotp

from tests.utiles import PASSWORD_ADMIN, con_token


def _login(cliente, usuario, password):
    return cliente.post("/auth/login", json={"usuario": usuario, "password": password})


def _activar_2fa(cliente, headers):
    """Deja al usuario dueño de `headers` con el 2FA activado y devuelve
    (secreto, códigos_de_recuperación)."""
    iniciado = cliente.post("/auth/2fa/iniciar", headers=headers)
    assert iniciado.status_code == 200
    secreto = iniciado.json()["secreto"]
    codigo = pyotp.TOTP(secreto).now()
    activado = cliente.post("/auth/2fa/activar", headers=headers, json={"secreto": secreto, "codigo": codigo})
    assert activado.status_code == 200
    return secreto, activado.json()["codigos"]


# ---------------------------------------------------------------- alta del 2FA


def test_login_normal_no_pide_2fa_si_no_esta_activado(cliente, admin_id):
    respuesta = _login(cliente, "admin", PASSWORD_ADMIN)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token"]
    assert cuerpo["requiere_2fa"] is False


def test_iniciar_2fa_devuelve_secreto_y_qr(cliente, headers_admin):
    respuesta = cliente.post("/auth/2fa/iniciar", headers=headers_admin)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo["secreto"]) >= 16
    assert cuerpo["qr_url"].startswith("otpauth://totp/")
    assert cuerpo["secreto"] in cuerpo["qr_url"]


def test_iniciar_2fa_no_guarda_nada_todavia(cliente, headers_admin):
    """Dos /iniciar seguidos, sin activar ninguno: el usuario sigue sin 2FA."""
    cliente.post("/auth/2fa/iniciar", headers=headers_admin)
    cliente.post("/auth/2fa/iniciar", headers=headers_admin)
    assert _login(cliente, "admin", PASSWORD_ADMIN).json()["requiere_2fa"] is False


def test_solo_admin_puede_iniciar_2fa(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))
    assert cliente.post("/auth/2fa/iniciar", headers=headers).status_code == 403


def test_activar_con_codigo_incorrecto_no_activa(cliente, headers_admin):
    iniciado = cliente.post("/auth/2fa/iniciar", headers=headers_admin).json()
    respuesta = cliente.post(
        "/auth/2fa/activar", headers=headers_admin, json={"secreto": iniciado["secreto"], "codigo": "000000"}
    )
    assert respuesta.status_code == 400

    # sigue sin pedir 2FA al entrar
    assert _login(cliente, "admin", PASSWORD_ADMIN).json()["requiere_2fa"] is False


def test_activar_con_codigo_mal_formado_da_422(cliente, headers_admin):
    iniciado = cliente.post("/auth/2fa/iniciar", headers=headers_admin).json()
    secreto = iniciado["secreto"]
    assert cliente.post("/auth/2fa/activar", headers=headers_admin, json={"secreto": secreto, "codigo": "abc"}).status_code == 422
    assert cliente.post("/auth/2fa/activar", headers=headers_admin, json={"secreto": secreto, "codigo": "12345"}).status_code == 422
    assert cliente.post("/auth/2fa/activar", headers=headers_admin, json={"codigo": "123456"}).status_code == 422


def test_activar_con_codigo_correcto_activa_el_2fa_y_da_codigos_de_recuperacion(cliente, headers_admin):
    _secreto, codigos = _activar_2fa(cliente, headers_admin)
    assert len(codigos) == 8
    assert len(set(codigos)) == 8  # todos distintos

    respuesta = _login(cliente, "admin", PASSWORD_ADMIN)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["requiere_2fa"] is True
    assert cuerpo["token_parcial"]
    assert cuerpo["token"] is None


# ---------------------------------------------------------------- login con 2FA activo


def test_login_con_2fa_no_da_token_completo_hasta_verificar(cliente, headers_admin):
    _activar_2fa(cliente, headers_admin)
    token_parcial = _login(cliente, "admin", PASSWORD_ADMIN).json()["token_parcial"]

    # el token parcial no sirve para nada más de la API
    assert cliente.get("/auth/yo", headers=con_token(token_parcial)).status_code == 401
    assert cliente.get("/usuarios", headers=con_token(token_parcial)).status_code == 401


def test_verificar_2fa_con_codigo_correcto_da_el_token_completo(cliente, headers_admin):
    secreto, _codigos = _activar_2fa(cliente, headers_admin)
    token_parcial = _login(cliente, "admin", PASSWORD_ADMIN).json()["token_parcial"]

    codigo = pyotp.TOTP(secreto).now()
    respuesta = cliente.post(
        "/auth/2fa/verificar", headers=con_token(token_parcial), json={"codigo": codigo}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token"]
    assert cuerpo["usuario"]["usuario"] == "admin"

    # y ese token sí funciona en el resto de la API
    assert cliente.get("/usuarios", headers=con_token(cuerpo["token"])).status_code == 200


def test_verificar_2fa_con_codigo_incorrecto_da_401(cliente, headers_admin):
    _activar_2fa(cliente, headers_admin)
    token_parcial = _login(cliente, "admin", PASSWORD_ADMIN).json()["token_parcial"]

    respuesta = cliente.post(
        "/auth/2fa/verificar", headers=con_token(token_parcial), json={"codigo": "000000"}
    )
    assert respuesta.status_code == 401


def test_verificar_2fa_se_bloquea_tras_varios_intentos(cliente, headers_admin):
    _activar_2fa(cliente, headers_admin)
    token_parcial = _login(cliente, "admin", PASSWORD_ADMIN).json()["token_parcial"]

    for _ in range(5):
        cliente.post("/auth/2fa/verificar", headers=con_token(token_parcial), json={"codigo": "000000"})

    bloqueado = cliente.post(
        "/auth/2fa/verificar", headers=con_token(token_parcial), json={"codigo": "000000"}
    )
    assert bloqueado.status_code == 429


def test_no_se_puede_usar_un_token_completo_para_verificar_2fa(cliente, headers_admin):
    secreto, _codigos = _activar_2fa(cliente, headers_admin)
    codigo = pyotp.TOTP(secreto).now()
    # headers_admin es un token completo (previo a activar el 2FA en esta sesión de prueba)
    respuesta = cliente.post("/auth/2fa/verificar", headers=headers_admin, json={"codigo": codigo})
    assert respuesta.status_code == 401


# ---------------------------------------------------------------- códigos de recuperación


def test_un_codigo_de_recuperacion_sirve_para_entrar_una_sola_vez(cliente, headers_admin):
    _secreto, codigos = _activar_2fa(cliente, headers_admin)
    token_parcial = _login(cliente, "admin", PASSWORD_ADMIN).json()["token_parcial"]

    primero = cliente.post(
        "/auth/2fa/verificar", headers=con_token(token_parcial), json={"codigo": codigos[0]}
    )
    assert primero.status_code == 200
    assert primero.json()["token"]

    # el mismo código ya no sirve una segunda vez
    token_parcial_2 = _login(cliente, "admin", PASSWORD_ADMIN).json()["token_parcial"]
    repetido = cliente.post(
        "/auth/2fa/verificar", headers=con_token(token_parcial_2), json={"codigo": codigos[0]}
    )
    assert repetido.status_code == 401


def test_codigo_de_recuperacion_con_guiones_o_minuscula_tambien_sirve(cliente, headers_admin):
    _secreto, codigos = _activar_2fa(cliente, headers_admin)
    token_parcial = _login(cliente, "admin", PASSWORD_ADMIN).json()["token_parcial"]

    codigo = codigos[0].lower()
    con_guion = f"{codigo[:5]}-{codigo[5:]}"
    respuesta = cliente.post(
        "/auth/2fa/verificar", headers=con_token(token_parcial), json={"codigo": con_guion}
    )
    assert respuesta.status_code == 200


def test_desactivar_2fa_borra_los_codigos_de_recuperacion(cliente, headers_admin):
    _secreto, codigos = _activar_2fa(cliente, headers_admin)
    cliente.post("/auth/2fa/desactivar", headers=headers_admin, json={"password": PASSWORD_ADMIN})

    # Reactivar y usar un código de la tanda VIEJA no debería funcionar.
    _secreto2, codigos2 = _activar_2fa(cliente, headers_admin)
    token_parcial = _login(cliente, "admin", PASSWORD_ADMIN).json()["token_parcial"]
    con_codigo_viejo = cliente.post(
        "/auth/2fa/verificar", headers=con_token(token_parcial), json={"codigo": codigos[0]}
    )
    assert con_codigo_viejo.status_code == 401
    assert codigos != codigos2


# ---------------------------------------------------------------- apagar el 2FA


def test_desactivar_2fa_con_password_correcta(cliente, headers_admin):
    _activar_2fa(cliente, headers_admin)
    respuesta = cliente.post(
        "/auth/2fa/desactivar", headers=headers_admin, json={"password": "clave-admin-1"}
    )
    assert respuesta.status_code == 204
    assert _login(cliente, "admin", "clave-admin-1").json()["requiere_2fa"] is False


def test_desactivar_2fa_con_password_incorrecta_no_desactiva(cliente, headers_admin):
    _activar_2fa(cliente, headers_admin)
    respuesta = cliente.post(
        "/auth/2fa/desactivar", headers=headers_admin, json={"password": "cualquier-otra-1"}
    )
    # 400 y no 401: la sesión del admin sigue siendo válida, así que el
    # frontend no la tiene que interpretar como "sesión vencida" y cerrarla.
    assert respuesta.status_code == 400
    assert _login(cliente, "admin", "clave-admin-1").json()["requiere_2fa"] is True
    assert cliente.get("/auth/yo", headers=headers_admin).status_code == 200


def test_admin_puede_resetear_el_2fa_de_otro_usuario(cliente, headers_admin, crear_usuario, iniciar_sesion):
    otro_id = crear_usuario("admin2", "clave-admin2-1", rol="admin")
    headers_otro = con_token(iniciar_sesion("admin2", "clave-admin2-1"))
    _activar_2fa(cliente, headers_otro)
    assert _login(cliente, "admin2", "clave-admin2-1").json()["requiere_2fa"] is True

    respuesta = cliente.put(f"/usuarios/{otro_id}/2fa", headers=headers_admin)
    assert respuesta.status_code == 204
    assert _login(cliente, "admin2", "clave-admin2-1").json()["requiere_2fa"] is False


def test_solo_admin_puede_resetear_2fa_ajeno(cliente, crear_usuario, iniciar_sesion, admin_id):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))
    assert cliente.put(f"/usuarios/{admin_id}/2fa", headers=headers).status_code == 403


def test_usuario_out_informa_si_tiene_2fa_activado(cliente, headers_admin):
    antes = cliente.get("/auth/yo", headers=headers_admin).json()
    assert antes["dos_factores_activo"] is False
    _activar_2fa(cliente, headers_admin)
    despues = cliente.get("/auth/yo", headers=headers_admin).json()
    assert despues["dos_factores_activo"] is True


def test_el_secreto_nunca_se_devuelve_en_usuario_out(cliente, headers_admin):
    _activar_2fa(cliente, headers_admin)
    cuerpo = cliente.get("/auth/yo", headers=headers_admin).json()
    assert "dos_factores_secreto" not in cuerpo
    assert "totp_secreto" not in cuerpo
