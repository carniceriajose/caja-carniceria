from datetime import datetime, timezone

from tests.utiles import con_token


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# ---------------------------------------------------------------- permisos


def test_solo_admin_puede_usar_cierres(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    assert cliente.get("/cierres", headers=headers).status_code == 403
    assert cliente.get("/cierres/previsualizacion?fecha=2026-03-01", headers=headers).status_code == 403
    assert cliente.post("/cierres", headers=headers, json={"fecha": "2026-03-01", "efectivo_contado": "0"}).status_code == 403
    assert cliente.get("/cierres").status_code == 401


# ---------------------------------------------------------------- previsualización / totales


def test_previsualizacion_calcula_los_totales_del_dia_en_hora_argentina(
    cliente, headers_admin, admin_id, crear_venta_db
):
    crear_venta_db(admin_id, "1000.00", "efectivo", utc(2026, 3, 3, 1, 0))  # lunes 22:00 arg
    crear_venta_db(admin_id, "500.00", "tarjeta", utc(2026, 3, 3, 2, 59, 59))  # lunes 23:59:59 arg
    crear_venta_db(admin_id, "300.00", "transferencia", utc(2026, 3, 3, 3, 0))  # martes 00:00 arg: no cuenta

    r = cliente.get("/cierres/previsualizacion?fecha=2026-03-02", headers=headers_admin).json()

    assert r["fecha"] == "2026-03-02"
    assert r["total_efectivo"] == "1000.00"
    assert r["total_tarjeta"] == "500.00"
    assert r["total_transferencia"] == "0.00"
    assert r["total_general"] == "1500.00"
    assert r["cantidad_ventas"] == 2


def test_previsualizacion_excluye_ventas_anuladas(cliente, headers_admin, admin_id, crear_venta_db):
    from app.fechas import hoy_argentina

    venta_id = crear_venta_db(admin_id, "500.00", "efectivo", utc(2026, 3, 2, 15, 0))
    cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "x"})

    del_dia_de_la_venta = cliente.get("/cierres/previsualizacion?fecha=2026-03-02", headers=headers_admin).json()
    assert del_dia_de_la_venta["total_efectivo"] == "0.00"
    assert del_dia_de_la_venta["cantidad_ventas"] == 0

    # La anulación se cuenta en el día en que se anuló (hoy), no en el de la venta original.
    de_hoy = cliente.get(f"/cierres/previsualizacion?fecha={hoy_argentina()}", headers=headers_admin).json()
    assert de_hoy["cantidad_anulaciones"] == 1
    assert de_hoy["monto_anulaciones"] == "500.00"


def test_previsualizacion_sin_ventas_da_todo_cero(cliente, headers_admin):
    r = cliente.get("/cierres/previsualizacion?fecha=2026-03-02", headers=headers_admin).json()
    assert r["total_general"] == "0.00"
    assert r["cantidad_ventas"] == 0


# ---------------------------------------------------------------- crear


def test_crear_cierre_con_diferencia_a_favor(cliente, headers_admin, admin_id, crear_venta_db):
    crear_venta_db(admin_id, "1000.00", "efectivo", utc(2026, 3, 2, 15, 0))

    respuesta = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "1050.00"}
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["total_efectivo"] == "1000.00"
    assert cuerpo["efectivo_contado"] == "1050.00"
    assert cuerpo["diferencia"] == "50.00"  # sobra
    assert cuerpo["anulado"] is False


def test_crear_cierre_con_diferencia_en_contra(cliente, headers_admin, admin_id, crear_venta_db):
    crear_venta_db(admin_id, "1000.00", "efectivo", utc(2026, 3, 2, 15, 0))

    respuesta = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "950.00"}
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["diferencia"] == "-50.00"  # falta


def test_crear_cierre_sin_diferencia(cliente, headers_admin, admin_id, crear_venta_db):
    crear_venta_db(admin_id, "1000.00", "efectivo", utc(2026, 3, 2, 15, 0))

    respuesta = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "1000.00"}
    )
    assert respuesta.json()["diferencia"] == "0.00"


def test_no_se_puede_cerrar_dos_veces_el_mismo_dia(cliente, headers_admin):
    cliente.post("/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "0"})
    respuesta = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "0"}
    )
    assert respuesta.status_code == 409


def test_se_puede_cerrar_un_dia_anterior_no_cerrado(cliente, headers_admin):
    respuesta = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2020-01-01", "efectivo_contado": "0"}
    )
    assert respuesta.status_code == 201


def test_efectivo_contado_no_puede_ser_negativo(cliente, headers_admin):
    respuesta = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "-1"}
    )
    assert respuesta.status_code == 422


# ---------------------------------------------------------------- anular


def test_anular_cierre_permite_cerrar_de_nuevo_ese_dia(cliente, headers_admin):
    creado = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "0"}
    ).json()

    anulado = cliente.post(f"/cierres/{creado['id']}/anular", headers=headers_admin, json={"motivo": "Error de tipeo"})
    assert anulado.status_code == 200
    assert anulado.json()["anulado"] is True
    assert anulado.json()["anulado_motivo"] == "Error de tipeo"

    otra_vez = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "10"}
    )
    assert otra_vez.status_code == 201


def test_no_se_puede_anular_un_cierre_dos_veces(cliente, headers_admin):
    creado = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "0"}
    ).json()
    cliente.post(f"/cierres/{creado['id']}/anular", headers=headers_admin, json={"motivo": "x"})

    respuesta = cliente.post(f"/cierres/{creado['id']}/anular", headers=headers_admin, json={"motivo": "x"})
    assert respuesta.status_code == 400


def test_anular_cierre_inexistente_da_404(cliente, headers_admin):
    assert cliente.post("/cierres/9999/anular", headers=headers_admin, json={"motivo": "x"}).status_code == 404


def test_cierre_y_anulacion_quedan_en_la_auditoria(cliente, headers_admin, admin_id):
    creado = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "0"}
    ).json()
    cliente.post(f"/cierres/{creado['id']}/anular", headers=headers_admin, json={"motivo": "Error"})

    crear_filas = cliente.get("/auditoria?accion=cierre.crear", headers=headers_admin).json()["items"]
    anular_filas = cliente.get("/auditoria?accion=cierre.anular", headers=headers_admin).json()["items"]
    assert len(crear_filas) == 1
    assert crear_filas[0]["entidad"] == "cierre_caja"
    assert crear_filas[0]["entidad_id"] == creado["id"]
    assert len(anular_filas) == 1
    assert anular_filas[0]["detalle"]["motivo"] == "Error"


# ---------------------------------------------------------------- listado


def test_lista_y_pagina_cierres(cliente, headers_admin):
    for dia in ["2026-03-01", "2026-03-02", "2026-03-03"]:
        cliente.post("/cierres", headers=headers_admin, json={"fecha": dia, "efectivo_contado": "0"})

    pagina1 = cliente.get("/cierres?pagina=1&por_pagina=2", headers=headers_admin).json()
    pagina2 = cliente.get("/cierres?pagina=2&por_pagina=2", headers=headers_admin).json()
    assert pagina1["total"] == 3
    assert len(pagina1["items"]) == 2
    assert len(pagina2["items"]) == 1
    # más reciente primero
    assert pagina1["items"][0]["fecha"] == "2026-03-03"


def test_filtra_cierres_por_fecha(cliente, headers_admin):
    cliente.post("/cierres", headers=headers_admin, json={"fecha": "2026-03-01", "efectivo_contado": "0"})
    cliente.post("/cierres", headers=headers_admin, json={"fecha": "2026-03-05", "efectivo_contado": "0"})

    r = cliente.get("/cierres?desde=2026-03-01&hasta=2026-03-01", headers=headers_admin).json()
    assert r["total"] == 1
    assert r["items"][0]["fecha"] == "2026-03-01"


# ---------------------------------------------------------------- pdf


def test_descarga_pdf_de_cierre(cliente, headers_admin):
    creado = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "10", "observaciones": "todo ok"}
    ).json()

    respuesta = cliente.get(f"/cierres/{creado['id']}.pdf", headers=headers_admin)
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert "cierre_2026-03-02.pdf" in respuesta.headers["content-disposition"]
    assert respuesta.content.startswith(b"%PDF")


def test_pdf_de_cierre_inexistente_da_404(cliente, headers_admin):
    assert cliente.get("/cierres/9999.pdf", headers=headers_admin).status_code == 404


def test_solo_admin_descarga_pdf_de_cierre(cliente, headers_admin, crear_usuario, iniciar_sesion):
    creado = cliente.post(
        "/cierres", headers=headers_admin, json={"fecha": "2026-03-02", "efectivo_contado": "0"}
    ).json()
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    assert cliente.get(f"/cierres/{creado['id']}.pdf", headers=headers).status_code == 403
