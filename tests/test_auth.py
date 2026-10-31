from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from sqlalchemy import select

from app.config import get_settings
from app.models import Usuario
from tests.utiles import PASSWORD_ADMIN, con_token


def _login(cliente, usuario, password):
    return cliente.post("/auth/login", json={"usuario": usuario, "password": password})


def test_login_correcto(cliente, admin_id):
    respuesta = _login(cliente, "admin", PASSWORD_ADMIN)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token"]
    assert cuerpo["usuario"]["usuario"] == "admin"
    assert cuerpo["usuario"]["rol"] == "admin"
    assert "password_hash" not in cuerpo["usuario"]
    assert "password" not in cuerpo["usuario"]

    claims = jwt.decode(cuerpo["token"], get_settings().jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == str(admin_id)
    assert claims["rol"] == "admin"
    assert claims["ver"] == 0
    assert claims["exp"] - claims["iat"] == 120 * 60  # admin: sesión más corta


def test_login_vendedor_dura_mas_que_admin(cliente, crear_usuario):
    crear_usuario("vende", "clave-vende-1")
    respuesta = _login(cliente, "vende", "clave-vende-1")

    claims = jwt.decode(respuesta.json()["token"], get_settings().jwt_secret, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 720 * 60  # vendedor: un turno completo


def test_login_no_distingue_mayusculas_en_el_usuario(cliente, admin_id):
    assert _login(cliente, "  ADMIN ", PASSWORD_ADMIN).status_code == 200


def test_usuario_inexistente_y_password_mala_dan_la_misma_respuesta(cliente, admin_id):
    password_mala = _login(cliente, "admin", "otra-clave-cualquiera")
    no_existe = _login(cliente, "fantasma", "otra-clave-cualquiera")

    assert password_mala.status_code == no_existe.status_code == 401
    assert password_mala.json() == no_existe.json()


def test_usuario_inactivo_recibe_la_misma_respuesta_que_password_mala(cliente, crear_usuario):
    crear_usuario("baja", "clave-de-baja-1", activo=False)
    inactivo = _login(cliente, "baja", "clave-de-baja-1")
    password_mala = _login(cliente, "baja", "incorrecta")

    assert inactivo.status_code == 401
    assert inactivo.json() == password_mala.json()


def _fallar_desde_la_misma_ip(cliente, cantidad):
    """Fallos repartidos entre usuarios inexistentes, sin que ninguno llegue a 5."""
    for i in range(cantidad):
        assert _login(cliente, f"fantasma{i % 10}", "mal").status_code == 401


def test_cinco_fallos_del_mismo_usuario_lo_bloquean_aunque_la_ip_no_llegue_a_20(
    cliente, admin_id, crear_usuario
):
    crear_usuario("otro", "clave-otro-1")
    for _ in range(5):
        assert _login(cliente, "admin", "mal").status_code == 401

    bloqueado = _login(cliente, "admin", PASSWORD_ADMIN)  # aun con la clave correcta
    assert bloqueado.status_code == 429
    assert int(bloqueado.headers["Retry-After"]) > 0
    # la IP solo lleva 5 fallos: otro usuario desde la misma IP puede entrar
    assert _login(cliente, "otro", "clave-otro-1").status_code == 200


def test_cinco_fallos_de_usuarios_distintos_no_bloquean_a_quien_no_fallo(cliente, admin_id):
    for i in range(5):
        assert _login(cliente, f"fantasma{i}", "mal").status_code == 401

    assert _login(cliente, "admin", PASSWORD_ADMIN).status_code == 200


def test_veinte_fallos_desde_la_misma_ip_bloquean_a_cualquier_usuario(
    cliente, admin_id, crear_usuario
):
    crear_usuario("otro", "clave-otro-1")
    _fallar_desde_la_misma_ip(cliente, 19)
    assert _login(cliente, "admin", PASSWORD_ADMIN).status_code == 200  # 19: todavía no

    assert _login(cliente, "fantasma0", "mal").status_code == 401  # el 20.º fallo

    assert _login(cliente, "admin", PASSWORD_ADMIN).status_code == 429
    assert _login(cliente, "otro", "clave-otro-1").status_code == 429


def test_despues_de_un_login_correcto_el_contador_del_usuario_vuelve_a_cero(cliente, admin_id):
    for _ in range(4):
        assert _login(cliente, "admin", "mal").status_code == 401
    assert _login(cliente, "admin", PASSWORD_ADMIN).status_code == 200

    for _ in range(4):
        assert _login(cliente, "admin", "mal").status_code == 401
    assert _login(cliente, "admin", PASSWORD_ADMIN).status_code == 200  # con 8 en total seguiría bloqueado


def test_un_login_correcto_no_reinicia_el_contador_de_la_ip(cliente, admin_id):
    _fallar_desde_la_misma_ip(cliente, 19)
    assert _login(cliente, "admin", PASSWORD_ADMIN).status_code == 200

    assert _login(cliente, "fantasma0", "mal").status_code == 401  # 20.º fallo desde esta IP
    assert _login(cliente, "admin", PASSWORD_ADMIN).status_code == 429


def test_sin_token_da_401(cliente):
    respuesta = cliente.get("/auth/yo")
    assert respuesta.status_code == 401
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"


def test_token_basura_da_401(cliente, admin_id):
    assert cliente.get("/auth/yo", headers=con_token("esto-no-es-un-token")).status_code == 401
    assert cliente.get("/usuarios", headers=con_token("a.b.c")).status_code == 401


def test_token_firmado_con_otra_clave_da_401(cliente, admin_id):
    ahora = datetime.now(timezone.utc)
    falso = jwt.encode(
        {"sub": str(admin_id), "rol": "admin", "ver": 0, "iat": ahora, "exp": ahora + timedelta(hours=1)},
        "otra-clave-distinta-de-la-del-servidor-1234",
        algorithm="HS256",
    )
    assert cliente.get("/auth/yo", headers=con_token(falso)).status_code == 401


def test_token_vencido_da_401(cliente, admin_id):
    ahora = datetime.now(timezone.utc)
    vencido = jwt.encode(
        {
            "sub": str(admin_id),
            "rol": "admin",
            "ver": 0,
            "iat": ahora - timedelta(hours=2),
            "exp": ahora - timedelta(hours=1),
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert cliente.get("/auth/yo", headers=con_token(vencido)).status_code == 401


def test_token_sin_version_da_401(cliente, admin_id):
    ahora = datetime.now(timezone.utc)
    sin_version = jwt.encode(
        {"sub": str(admin_id), "iat": ahora, "exp": ahora + timedelta(hours=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert cliente.get("/auth/yo", headers=con_token(sin_version)).status_code == 401


def test_yo_devuelve_al_usuario_logueado(cliente, headers_admin):
    respuesta = cliente.get("/auth/yo", headers=headers_admin)
    assert respuesta.status_code == 200
    assert respuesta.json()["usuario"] == "admin"


def test_rehash_automatico_si_los_parametros_de_argon2_quedaron_viejos(
    cliente, crear_usuario, sesion_pruebas
):
    liviano = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    hash_viejo = liviano.hash("clave-vieja-123")
    with sesion_pruebas() as db:
        db.add(
            Usuario(nombre="Viejo", usuario="viejo", password_hash=hash_viejo, rol="vendedor")
        )
        db.commit()

    assert _login(cliente, "viejo", "clave-vieja-123").status_code == 200

    with sesion_pruebas() as db:
        nuevo_hash = db.scalar(select(Usuario.password_hash).where(Usuario.usuario == "viejo"))
    assert nuevo_hash != hash_viejo
    assert _login(cliente, "viejo", "clave-vieja-123").status_code == 200


def test_salud(cliente):
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_cabeceras_de_seguridad(cliente):
    cabeceras = cliente.get("/salud").headers
    assert cabeceras["X-Content-Type-Options"] == "nosniff"
    assert cabeceras["X-Frame-Options"] == "DENY"
    assert cabeceras["Referrer-Policy"] == "no-referrer"
    assert cabeceras["Cache-Control"] == "no-store"
    assert "Strict-Transport-Security" not in cabeceras  # solo en producción


def test_cors_solo_para_origenes_configurados(cliente):
    permitido = cliente.options(
        "/auth/login",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    ajeno = cliente.options(
        "/auth/login",
        headers={"Origin": "http://sitio-malicioso.com", "Access-Control-Request-Method": "POST"},
    )
    assert permitido.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-credentials" not in permitido.headers
    assert "access-control-allow-origin" not in ajeno.headers


def test_ruta_inexistente_responde_en_espanol(cliente):
    respuesta = cliente.get("/no-existe")
    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "No encontrado."}
