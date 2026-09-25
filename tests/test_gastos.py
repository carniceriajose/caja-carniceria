from datetime import date

import pytest

from app.fechas import hoy_argentina
from tests.utiles import con_token


@pytest.fixture()
def headers_vendedor(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    return con_token(iniciar_sesion("vende", "clave-vende-1"))


# ---------------------------------------------------------------- categorías


def test_crear_y_listar_categorias(cliente, headers_admin):
    creada = cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "Proveedores"})
    assert creada.status_code == 201
    assert creada.json()["nombre"] == "Proveedores"

    cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "alquiler"})
    cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "Seguro"})

    nombres = [c["nombre"] for c in cliente.get("/categorias-gasto", headers=headers_admin).json()]
    assert nombres == ["alquiler", "Proveedores", "Seguro"]


def test_categoria_repetida_devuelve_la_existente(cliente, headers_admin):
    primera = cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "Seguro"})
    repetida = cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "SEGURO"})
    con_espacios = cliente.post(
        "/categorias-gasto", headers=headers_admin, json={"nombre": "  seguro  "}
    )

    assert primera.status_code == 201
    assert repetida.status_code == 200
    assert con_espacios.status_code == 200
    assert repetida.json() == primera.json() == con_espacios.json()
    assert len(cliente.get("/categorias-gasto", headers=headers_admin).json()) == 1


def test_categoria_con_nombre_vacio_da_422(cliente, headers_admin):
    assert cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "   "}).status_code == 422


def test_el_vendedor_no_puede_usar_categorias_ni_gastos(cliente, headers_vendedor, headers_admin):
    categoria = cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "Seguro"}).json()
    gasto = {"monto": "10.00", "categoria_id": categoria["id"]}

    assert cliente.get("/categorias-gasto", headers=headers_vendedor).status_code == 403
    assert cliente.post("/categorias-gasto", headers=headers_vendedor, json={"nombre": "X"}).status_code == 403
    assert cliente.get("/gastos", headers=headers_vendedor).status_code == 403
    assert cliente.post("/gastos", headers=headers_vendedor, json=gasto).status_code == 403
    assert cliente.put("/gastos/1", headers=headers_vendedor, json={**gasto, "fecha": "2026-03-01"}).status_code == 403
    assert cliente.delete("/gastos/1", headers=headers_vendedor).status_code == 403


def test_sin_token_da_401(cliente):
    assert cliente.get("/gastos").status_code == 401
    assert cliente.get("/categorias-gasto").status_code == 401


# ---------------------------------------------------------------- gastos


@pytest.fixture()
def categoria(cliente, headers_admin):
    return cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "Proveedores"}).json()


def test_crear_un_gasto(cliente, headers_admin, admin_id, categoria):
    respuesta = cliente.post(
        "/gastos",
        headers=headers_admin,
        json={
            "fecha": "2026-03-02",
            "monto": "15000.50",
            "categoria_id": categoria["id"],
            "descripcion": "  Res  ",
        },
    )

    assert respuesta.status_code == 201
    gasto = respuesta.json()
    assert gasto["fecha"] == "2026-03-02"
    assert gasto["monto"] == "15000.50"
    assert gasto["categoria"] == categoria
    assert gasto["descripcion"] == "Res"
    assert gasto["creado_por"] == admin_id


def test_sin_fecha_el_gasto_es_de_hoy_en_argentina(cliente, headers_admin, categoria):
    respuesta = cliente.post(
        "/gastos", headers=headers_admin, json={"monto": "10", "categoria_id": categoria["id"]}
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["fecha"] == hoy_argentina().isoformat()
    assert respuesta.json()["descripcion"] is None


def test_gasto_con_categoria_inexistente_da_400(cliente, headers_admin):
    respuesta = cliente.post("/gastos", headers=headers_admin, json={"monto": "10", "categoria_id": 999})
    assert respuesta.status_code == 400


@pytest.mark.parametrize("monto", ["0", "-1", "1.005", "abc", None])
def test_monto_invalido_da_422(cliente, headers_admin, categoria, monto):
    respuesta = cliente.post(
        "/gastos", headers=headers_admin, json={"monto": monto, "categoria_id": categoria["id"]}
    )
    assert respuesta.status_code == 422


def test_descripcion_demasiado_larga_da_422(cliente, headers_admin, categoria):
    respuesta = cliente.post(
        "/gastos",
        headers=headers_admin,
        json={"monto": "10", "categoria_id": categoria["id"], "descripcion": "x" * 501},
    )
    assert respuesta.status_code == 422


def test_listado_con_filtros(cliente, headers_admin, admin_id, crear_categoria_db, crear_gasto_db):
    proveedores = crear_categoria_db("Proveedores")
    seguro = crear_categoria_db("Seguro")
    crear_gasto_db(admin_id, "100", proveedores, date(2026, 3, 1))
    crear_gasto_db(admin_id, "200", seguro, date(2026, 3, 2))
    crear_gasto_db(admin_id, "300", proveedores, date(2026, 3, 3))
    crear_gasto_db(admin_id, "400", proveedores, date(2026, 4, 1))

    def montos(consulta):
        items = cliente.get(f"/gastos?{consulta}", headers=headers_admin).json()["items"]
        return [g["monto"] for g in items]

    assert montos("") == ["400.00", "300.00", "200.00", "100.00"]  # más nuevos primero
    assert montos("desde=2026-03-02&hasta=2026-03-31") == ["300.00", "200.00"]
    assert montos(f"categoria_id={seguro}") == ["200.00"]
    assert montos(f"categoria_id={proveedores}&hasta=2026-03-03") == ["300.00", "100.00"]
    assert cliente.get("/gastos?desde=2026-03-05&hasta=2026-03-01", headers=headers_admin).status_code == 400


def test_listado_paginado(cliente, headers_admin, admin_id, crear_categoria_db, crear_gasto_db):
    categoria_id = crear_categoria_db("Varios")
    for dia in range(1, 6):
        crear_gasto_db(admin_id, str(dia), categoria_id, date(2026, 3, dia))

    pagina = cliente.get("/gastos?por_pagina=2&pagina=2", headers=headers_admin).json()

    assert pagina["total"] == 5
    assert [g["monto"] for g in pagina["items"]] == ["3.00", "2.00"]


def test_editar_un_gasto_incluida_la_categoria(cliente, headers_admin, admin_id, categoria):
    otra = cliente.post("/categorias-gasto", headers=headers_admin, json={"nombre": "Seguro"}).json()
    gasto = cliente.post(
        "/gastos",
        headers=headers_admin,
        json={"fecha": "2026-03-01", "monto": "100", "categoria_id": categoria["id"]},
    ).json()

    respuesta = cliente.put(
        f"/gastos/{gasto['id']}",
        headers=headers_admin,
        json={
            "fecha": "2026-03-05",
            "monto": "250.75",
            "categoria_id": otra["id"],
            "descripcion": "Corregido",
        },
    )

    assert respuesta.status_code == 200
    editado = respuesta.json()
    assert editado["fecha"] == "2026-03-05"
    assert editado["monto"] == "250.75"
    assert editado["categoria"] == otra
    assert editado["descripcion"] == "Corregido"
    assert editado["creado_por"] == admin_id
    en_lista = cliente.get("/gastos", headers=headers_admin).json()["items"]
    assert en_lista == [editado]


def test_editar_un_gasto_inexistente_o_con_categoria_mala(cliente, headers_admin, categoria):
    cuerpo = {"fecha": "2026-03-05", "monto": "10", "categoria_id": categoria["id"]}
    assert cliente.put("/gastos/999", headers=headers_admin, json=cuerpo).status_code == 404

    gasto = cliente.post("/gastos", headers=headers_admin, json=cuerpo).json()
    mala = {**cuerpo, "categoria_id": 999}
    assert cliente.put(f"/gastos/{gasto['id']}", headers=headers_admin, json=mala).status_code == 400
    sin_fecha = {"monto": "10", "categoria_id": categoria["id"]}
    assert cliente.put(f"/gastos/{gasto['id']}", headers=headers_admin, json=sin_fecha).status_code == 422


def test_borrar_un_gasto(cliente, headers_admin, categoria):
    gasto = cliente.post(
        "/gastos", headers=headers_admin, json={"monto": "10", "categoria_id": categoria["id"]}
    ).json()

    assert cliente.delete(f"/gastos/{gasto['id']}", headers=headers_admin).status_code == 204
    assert cliente.get("/gastos", headers=headers_admin).json()["items"] == []
    assert cliente.delete(f"/gastos/{gasto['id']}", headers=headers_admin).status_code == 404
