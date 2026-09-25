from datetime import date, datetime, timezone

from sqlalchemy.dialects import postgresql

from app.fechas import NOMBRE_ZONA, dia_local, mes_local
from app.models import Venta
from tests.utiles import con_token


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _cargar_marzo(admin_id, crear_venta_db, crear_categoria_db, crear_gasto_db):
    # 2 de marzo de 2026 es lunes. En Argentina (UTC-3):
    crear_venta_db(admin_id, "1000.00", "efectivo", utc(2026, 3, 3, 1, 0))  # lunes 22:00
    crear_venta_db(  # lunes 23:59:59
        admin_id, "2500.50", "tarjeta", utc(2026, 3, 3, 2, 59, 59), estado_arca="pendiente"
    )
    crear_venta_db(  # martes 00:00
        admin_id, "300.25", "transferencia", utc(2026, 3, 3, 3, 0),
        estado_arca="facturada", numero_comprobante=1,
    )
    crear_venta_db(admin_id, "500.00", "efectivo", utc(2026, 3, 1, 15, 0))  # domingo 12:00
    crear_venta_db(admin_id, "9999.00", "efectivo", utc(2026, 3, 4, 15, 0))  # fuera del rango
    crear_venta_db(admin_id, "8888.00", "efectivo", utc(2026, 2, 28, 15, 0))  # fuera del rango

    proveedores = crear_categoria_db("Proveedores")
    seguro = crear_categoria_db("Seguro")
    crear_gasto_db(admin_id, "700.00", proveedores, date(2026, 3, 2))
    crear_gasto_db(admin_id, "100.10", seguro, date(2026, 3, 3))
    crear_gasto_db(admin_id, "5000.00", proveedores, date(2026, 3, 4))  # fuera del rango


def test_resumen_de_tres_dias(
    cliente, headers_admin, admin_id, crear_venta_db, crear_categoria_db, crear_gasto_db
):
    _cargar_marzo(admin_id, crear_venta_db, crear_categoria_db, crear_gasto_db)

    respuesta = cliente.get("/resumen?desde=2026-03-01&hasta=2026-03-03", headers=headers_admin)

    assert respuesta.status_code == 200
    r = respuesta.json()
    assert r["desde"] == "2026-03-01" and r["hasta"] == "2026-03-03"
    assert r["total_vendido"] == "4300.75"
    assert r["cantidad_ventas"] == 4

    assert r["por_medio_pago"] == [
        {"medio_pago": "efectivo", "monto": "1500.00", "cantidad": 2},
        {"medio_pago": "tarjeta", "monto": "2500.50", "cantidad": 1},
        {"medio_pago": "transferencia", "monto": "300.25", "cantidad": 1},
    ]
    assert r["por_estado_fiscal"] == [
        {"estado_arca": "no_aplica", "monto": "1500.00", "cantidad": 2},
        {"estado_arca": "pendiente", "monto": "2500.50", "cantidad": 1},
        {"estado_arca": "facturada", "monto": "300.25", "cantidad": 1},
        {"estado_arca": "fallo", "monto": "0.00", "cantidad": 0},
    ]

    assert r["total_gastos"] == "800.10"
    assert r["resultado"] == "3500.65"
    assert r["gastos_por_categoria"] == [
        {"categoria_id": 1, "categoria": "Proveedores", "monto": "700.00", "cantidad": 1},
        {"categoria_id": 2, "categoria": "Seguro", "monto": "100.10", "cantidad": 1},
    ]


def test_los_dias_se_cuentan_en_hora_de_argentina(
    cliente, headers_admin, admin_id, crear_venta_db, crear_categoria_db, crear_gasto_db
):
    _cargar_marzo(admin_id, crear_venta_db, crear_categoria_db, crear_gasto_db)

    r = cliente.get("/resumen?desde=2026-03-01&hasta=2026-03-03", headers=headers_admin).json()

    assert r["agrupacion"] == "dia"
    assert r["serie"] == [
        {"periodo": "2026-03-01", "efectivo": "500.00", "tarjeta": "0.00", "transferencia": "0.00", "total": "500.00"},
        # La venta de las 22:00 y la de las 23:59:59 del lunes son del lunes, aunque en UTC ya sea martes.
        {"periodo": "2026-03-02", "efectivo": "1000.00", "tarjeta": "2500.50", "transferencia": "0.00", "total": "3500.50"},
        {"periodo": "2026-03-03", "efectivo": "0.00", "tarjeta": "0.00", "transferencia": "300.25", "total": "300.25"},
    ]


def test_el_rango_de_un_solo_dia_respeta_los_limites_argentinos(
    cliente, headers_admin, admin_id, crear_venta_db
):
    crear_venta_db(admin_id, "10", "efectivo", utc(2026, 3, 3, 2, 59, 59))  # lunes 23:59:59
    crear_venta_db(admin_id, "20", "efectivo", utc(2026, 3, 3, 3, 0))  # martes 00:00

    lunes = cliente.get("/resumen?desde=2026-03-02&hasta=2026-03-02", headers=headers_admin).json()
    martes = cliente.get("/resumen?desde=2026-03-03&hasta=2026-03-03", headers=headers_admin).json()

    assert lunes["total_vendido"] == "10.00"
    assert martes["total_vendido"] == "20.00"


def test_los_dias_sin_ventas_aparecen_en_cero(cliente, headers_admin):
    r = cliente.get("/resumen?desde=2026-03-01&hasta=2026-03-03", headers=headers_admin).json()

    assert r["total_vendido"] == "0.00"
    assert r["cantidad_ventas"] == 0
    assert r["total_gastos"] == "0.00"
    assert r["resultado"] == "0.00"
    assert r["gastos_por_categoria"] == []
    assert [p["periodo"] for p in r["serie"]] == ["2026-03-01", "2026-03-02", "2026-03-03"]
    assert all(p["total"] == "0.00" for p in r["serie"])
    assert [m["monto"] for m in r["por_medio_pago"]] == ["0.00", "0.00", "0.00"]


def test_resultado_negativo_si_los_gastos_superan_las_ventas(
    cliente, headers_admin, admin_id, crear_venta_db, crear_categoria_db, crear_gasto_db
):
    crear_venta_db(admin_id, "100.00", "efectivo", utc(2026, 3, 1, 15, 0))
    crear_gasto_db(admin_id, "250.50", crear_categoria_db("Alquiler"), date(2026, 3, 1))

    r = cliente.get("/resumen?desde=2026-03-01&hasta=2026-03-01", headers=headers_admin).json()

    assert r["resultado"] == "-150.50"


def test_mas_de_62_dias_se_agrupa_por_mes(cliente, headers_admin, admin_id, crear_venta_db):
    crear_venta_db(admin_id, "100", "efectivo", utc(2026, 1, 15, 15, 0))
    crear_venta_db(admin_id, "50", "tarjeta", utc(2026, 1, 20, 15, 0))
    crear_venta_db(admin_id, "300", "transferencia", utc(2026, 3, 2, 15, 0))
    # 02:00 UTC del 1 de abril son las 23:00 del 31 de marzo en Argentina: es de marzo.
    crear_venta_db(admin_id, "7", "efectivo", utc(2026, 4, 1, 2, 0))

    r = cliente.get("/resumen?desde=2026-01-01&hasta=2026-03-31", headers=headers_admin).json()

    assert r["agrupacion"] == "mes"
    assert r["total_vendido"] == "457.00"
    assert r["serie"] == [
        {"periodo": "2026-01-01", "efectivo": "100.00", "tarjeta": "50.00", "transferencia": "0.00", "total": "150.00"},
        {"periodo": "2026-02-01", "efectivo": "0.00", "tarjeta": "0.00", "transferencia": "0.00", "total": "0.00"},
        {"periodo": "2026-03-01", "efectivo": "7.00", "tarjeta": "0.00", "transferencia": "300.00", "total": "307.00"},
    ]


def test_el_limite_entre_serie_diaria_y_mensual_es_62_dias(cliente, headers_admin):
    # del 1 de marzo al 1 de mayo hay 62 días; un día más pasa a mensual
    diaria = cliente.get("/resumen?desde=2026-03-01&hasta=2026-05-01", headers=headers_admin).json()
    mensual = cliente.get("/resumen?desde=2026-03-01&hasta=2026-05-02", headers=headers_admin).json()

    assert diaria["agrupacion"] == "dia" and len(diaria["serie"]) == 62
    assert mensual["agrupacion"] == "mes"
    assert [p["periodo"] for p in mensual["serie"]] == ["2026-03-01", "2026-04-01", "2026-05-01"]


def test_el_vendedor_no_puede_ver_el_resumen(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    assert cliente.get("/resumen?desde=2026-03-01&hasta=2026-03-03", headers=headers).status_code == 403
    assert cliente.get("/resumen?desde=2026-03-01&hasta=2026-03-03").status_code == 401


def test_parametros_invalidos(cliente, headers_admin):
    assert cliente.get("/resumen", headers=headers_admin).status_code == 422
    assert cliente.get("/resumen?desde=2026-03-01", headers=headers_admin).status_code == 422
    assert cliente.get("/resumen?desde=2026-03-05&hasta=2026-03-01", headers=headers_admin).status_code == 400
    assert cliente.get("/resumen?desde=2000-01-01&hasta=2026-03-01", headers=headers_admin).status_code == 400


def test_en_postgres_los_dias_se_calculan_con_la_zona_de_argentina():
    dia = str(dia_local(Venta.fecha_hora).compile(dialect=postgresql.dialect()))
    mes = str(mes_local(Venta.fecha_hora).compile(dialect=postgresql.dialect()))

    assert f"AT TIME ZONE '{NOMBRE_ZONA}'" in dia
    assert dia.startswith("CAST(") and dia.endswith("AS DATE)")
    assert f"date_trunc('month', (ventas.fecha_hora) AT TIME ZONE '{NOMBRE_ZONA}')" in mes
