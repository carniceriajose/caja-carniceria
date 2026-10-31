import pyotp

from app.arca import wsaa, wsfe
from tests.utiles import PASSWORD_ADMIN, con_token


def _accion(cliente, headers_admin, accion=None):
    parametros = f"?accion={accion}" if accion else ""
    return cliente.get(f"/auditoria{parametros}", headers=headers_admin).json()["items"]


# ---------------------------------------------------------------- quién puede verla


def test_solo_admin_ve_la_auditoria(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))
    assert cliente.get("/auditoria", headers=headers).status_code == 403
    assert cliente.get("/auditoria").status_code == 401


# ---------------------------------------------------------------- qué queda registrado


def test_crear_usuario_queda_en_la_auditoria(cliente, headers_admin, admin_id):
    cliente.post(
        "/usuarios",
        headers=headers_admin,
        json={"nombre": "Vendedor Nuevo", "usuario": "vende_nuevo", "password": "clave-nueva-1", "rol": "vendedor"},
    )
    filas = _accion(cliente, headers_admin, "usuario.crear")
    assert len(filas) == 1
    assert filas[0]["usuario"]["id"] == admin_id
    assert filas[0]["detalle"]["usuario_afectado"] == "vende_nuevo"


def test_cambiar_rol_y_desactivar_quedan_en_la_auditoria(cliente, headers_admin, crear_usuario):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    cliente.patch(f"/usuarios/{vendedor_id}", headers=headers_admin, json={"rol": "admin"})
    cliente.patch(f"/usuarios/{vendedor_id}", headers=headers_admin, json={"activo": False})

    filas = _accion(cliente, headers_admin, "usuario.actualizar")
    assert len(filas) == 2
    assert filas[0]["detalle"]["cambios"]["activo"] == {"antes": True, "despues": False}
    assert filas[1]["detalle"]["cambios"]["rol"] == {"antes": "vendedor", "despues": "admin"}


def test_cambiar_solo_el_nombre_no_genera_ruido_si_no_cambia_nada(cliente, headers_admin, crear_usuario):
    vendedor_id = crear_usuario("vende", "clave-vende-1", nombre="Vende Dedor")
    # Mismo nombre: no debería registrar un cambio vacío.
    cliente.patch(f"/usuarios/{vendedor_id}", headers=headers_admin, json={"nombre": "Vende Dedor"})
    assert _accion(cliente, headers_admin, "usuario.actualizar") == []


def test_resetear_password_queda_en_la_auditoria(cliente, headers_admin, crear_usuario):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    cliente.put(f"/usuarios/{vendedor_id}/password", headers=headers_admin, json={"password": "clave-nueva-1"})
    filas = _accion(cliente, headers_admin, "usuario.resetear_password")
    assert len(filas) == 1
    assert filas[0]["detalle"]["usuario_afectado"] == "vende"


def test_cambiar_configuracion_queda_en_la_auditoria(cliente, headers_admin):
    from tests.test_configuracion import CAMBIO_VALIDO

    cliente.put(
        "/configuracion",
        headers=headers_admin,
        json={**CAMBIO_VALIDO, "facturar_efectivo": True, "facturar_tarjeta": False, "facturar_transferencia": True},
    )
    filas = _accion(cliente, headers_admin, "configuracion.cambiar")
    assert len(filas) == 1
    assert filas[0]["detalle"]["facturar_efectivo"] is True
    assert filas[0]["detalle"]["facturar_tarjeta"] is False
    assert filas[0]["detalle"]["facturar_transferencia"] is True
    assert filas[0]["entidad"] == "configuracion"
    assert filas[0]["entidad_id"] == 1


def test_gastos_crear_editar_borrar_quedan_en_la_auditoria(cliente, headers_admin):
    categoria = cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "Proveedores"}).json()
    gasto = cliente.post(
        "/gastos", headers=headers_admin, json={"monto": "100.00", "categoria_id": categoria["id"]}
    ).json()
    cliente.put(
        f"/gastos/{gasto['id']}",
        headers=headers_admin,
        json={"fecha": gasto["fecha"], "monto": "150.00", "categoria_id": categoria["id"]},
    )
    cliente.delete(f"/gastos/{gasto['id']}", headers=headers_admin)

    assert len(_accion(cliente, headers_admin, "gasto.crear")) == 1
    assert len(_accion(cliente, headers_admin, "gasto.actualizar")) == 1
    assert len(_accion(cliente, headers_admin, "gasto.borrar")) == 1


def test_reintentar_factura_queda_en_la_auditoria(cliente, headers_admin, admin_id, crear_venta_db, monkeypatch):
    venta_id = crear_venta_db(admin_id, "100", "tarjeta", estado_arca="fallo", error_detalle="x")
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: False)  # que no intente facturar de verdad

    cliente.post(f"/ventas/{venta_id}/reintentar-factura", headers=headers_admin)

    filas = _accion(cliente, headers_admin, "factura.reintentar")
    assert len(filas) == 1
    assert filas[0]["detalle"]["venta_id"] == venta_id


def test_2fa_activar_desactivar_y_resetear_quedan_en_la_auditoria(cliente, headers_admin, crear_usuario, iniciar_sesion):
    iniciado = cliente.post("/auth/2fa/iniciar", headers=headers_admin).json()
    codigo = pyotp.TOTP(iniciado["secreto"]).now()
    cliente.post("/auth/2fa/activar", headers=headers_admin, json={"secreto": iniciado["secreto"], "codigo": codigo})
    assert len(_accion(cliente, headers_admin, "2fa.activar")) == 1

    cliente.post("/auth/2fa/desactivar", headers=headers_admin, json={"password": "clave-admin-1"})
    assert len(_accion(cliente, headers_admin, "2fa.desactivar")) == 1

    otro_id = crear_usuario("admin2", "clave-admin2-1", rol="admin")
    headers_otro = con_token(iniciar_sesion("admin2", "clave-admin2-1"))
    iniciado2 = cliente.post("/auth/2fa/iniciar", headers=headers_otro).json()
    codigo2 = pyotp.TOTP(iniciado2["secreto"]).now()
    cliente.post(
        "/auth/2fa/activar", headers=headers_otro, json={"secreto": iniciado2["secreto"], "codigo": codigo2}
    )

    cliente.put(f"/usuarios/{otro_id}/2fa", headers=headers_admin)
    filas = _accion(cliente, headers_admin, "2fa.resetear_por_admin")
    assert len(filas) == 1
    assert filas[0]["detalle"]["usuario_afectado"] == "admin2"
    assert filas[0]["entidad"] == "usuario"
    assert filas[0]["entidad_id"] == otro_id


# ---------------------------------------------------------------- login


def test_login_exitoso_y_fallido_quedan_en_la_auditoria(cliente, admin_id, headers_admin):
    cliente.post("/auth/login", json={"usuario": "admin", "password": PASSWORD_ADMIN})
    cliente.post("/auth/login", json={"usuario": "admin", "password": "mal"})
    cliente.post("/auth/login", json={"usuario": "fantasma", "password": "mal"})

    exitosos = _accion(cliente, headers_admin, "login.exitoso")
    fallidos = _accion(cliente, headers_admin, "login.fallido")
    assert len(exitosos) >= 1
    assert any(f["usuario"] is not None and f["usuario"]["id"] == admin_id for f in fallidos)
    assert any(f["usuario"] is None and f["detalle"]["usuario_intentado"] == "fantasma" for f in fallidos)


# ---------------------------------------------------------------- filtros y paginado


def test_filtra_por_fecha(cliente, headers_admin):
    cliente.post(
        "/usuarios",
        headers=headers_admin,
        json={"nombre": "Vende Dor", "usuario": "vende_fecha", "password": "clave-cualquiera-1", "rol": "vendedor"},
    )
    hoy = cliente.get("/auditoria", headers=headers_admin).json()["items"][0]["creado_en"][:10]

    con_hoy = cliente.get(f"/auditoria?desde={hoy}&hasta={hoy}", headers=headers_admin).json()
    assert con_hoy["total"] >= 1

    sin_resultados = cliente.get("/auditoria?desde=2000-01-01&hasta=2000-01-02", headers=headers_admin).json()
    assert sin_resultados["total"] == 0
    assert sin_resultados["items"] == []


def test_pagina(cliente, headers_admin):
    for i in range(3):
        cliente.post(
            "/usuarios",
            headers=headers_admin,
            json={"nombre": f"U{i}", "usuario": f"usuario{i}", "password": "clave-cualquiera-1", "rol": "vendedor"},
        )
    pagina1 = cliente.get(
        "/auditoria?accion=usuario.crear&pagina=1&por_pagina=2", headers=headers_admin
    ).json()
    pagina2 = cliente.get(
        "/auditoria?accion=usuario.crear&pagina=2&por_pagina=2", headers=headers_admin
    ).json()
    assert pagina1["total"] == 3
    assert len(pagina1["items"]) == 2
    assert len(pagina2["items"]) == 1


def test_filtra_por_usuario(cliente, headers_admin, admin_id, crear_usuario, iniciar_sesion):
    otro_id = crear_usuario("admin2", "clave-admin2-1", rol="admin")
    headers_otro = con_token(iniciar_sesion("admin2", "clave-admin2-1"))
    cliente.post(
        "/usuarios",
        headers=headers_otro,
        json={"nombre": "X", "usuario": "usuario_x", "password": "clave-cualquiera-1", "rol": "vendedor"},
    )

    filas = cliente.get(f"/auditoria?usuario_id={otro_id}&accion=usuario.crear", headers=headers_admin).json()[
        "items"
    ]
    assert len(filas) == 1
    assert filas[0]["usuario"]["id"] == otro_id
