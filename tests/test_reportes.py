from datetime import date, datetime, timezone
from io import BytesIO

from openpyxl import load_workbook
from pypdf import PdfReader

from tests.utiles import con_token


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _hoja(contenido: bytes):
    return load_workbook(BytesIO(contenido)).active


def _texto_pdf(contenido: bytes) -> str:
    return "\n".join(pagina.extract_text() or "" for pagina in PdfReader(BytesIO(contenido)).pages)


# ---------------------------------------------------------------- permisos


def test_solo_admin_descarga_reportes(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    assert cliente.get("/reportes/ventas.xlsx?desde=2026-03-01&hasta=2026-03-31", headers=headers).status_code == 403
    assert cliente.get("/reportes/gastos.xlsx?desde=2026-03-01&hasta=2026-03-31", headers=headers).status_code == 403
    assert cliente.get("/reportes/gastos.pdf?desde=2026-03-01&hasta=2026-03-31", headers=headers).status_code == 403
    assert cliente.get("/reportes/resumen.pdf?desde=2026-03-01&hasta=2026-03-31", headers=headers).status_code == 403
    assert cliente.get("/reportes/iva.xlsx?desde=2026-03-01&hasta=2026-03-31", headers=headers).status_code == 403
    assert cliente.get("/reportes/iva.pdf?desde=2026-03-01&hasta=2026-03-31", headers=headers).status_code == 403
    assert cliente.get("/reportes/ventas.xlsx?desde=2026-03-01&hasta=2026-03-31").status_code == 401


# ---------------------------------------------------------------- rango


def test_rango_mayor_a_un_anio_rechazado(cliente, headers_admin):
    respuesta = cliente.get(
        "/reportes/ventas.xlsx?desde=2025-01-01&hasta=2026-06-01", headers=headers_admin
    )
    assert respuesta.status_code == 400


def test_rango_de_un_anio_exacto_se_acepta(cliente, headers_admin):
    respuesta = cliente.get(
        "/reportes/ventas.xlsx?desde=2025-03-02&hasta=2026-03-01", headers=headers_admin
    )
    assert respuesta.status_code == 200


def test_rango_invertido_da_400(cliente, headers_admin):
    respuesta = cliente.get(
        "/reportes/ventas.xlsx?desde=2026-03-05&hasta=2026-03-01", headers=headers_admin
    )
    assert respuesta.status_code == 400


# ---------------------------------------------------------------- ventas.xlsx


def test_excel_de_ventas_tiene_las_filas_y_el_total_correctos(
    cliente, headers_admin, admin_id, crear_venta_db
):
    crear_venta_db(admin_id, "1000.00", "efectivo", utc(2026, 3, 2, 15, 0))
    crear_venta_db(
        admin_id, "500.00", "tarjeta", utc(2026, 3, 2, 16, 0),
        estado_arca="facturada", tipo_comprobante="6", punto_venta=1, numero_comprobante=42, cae="30414141414141",
    )
    crear_venta_db(admin_id, "999.00", "efectivo", utc(2026, 4, 1, 15, 0))  # fuera del rango

    respuesta = cliente.get(
        "/reportes/ventas.xlsx?desde=2026-03-01&hasta=2026-03-31", headers=headers_admin
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "ventas_2026-03-01_2026-03-31.xlsx" in respuesta.headers["content-disposition"]

    hoja = _hoja(respuesta.content)
    filas = list(hoja.iter_rows(values_only=True))
    assert filas[0] == (
        "Fecha y hora", "Subtotal", "Rubro", "Tarjeta", "Tipo de tarjeta", "Ajuste", "Total", "Medio de pago",
        "Vendedor", "Estado fiscal", "Tipo", "Número", "CAE", "Anulada",
    )
    assert filas[1][1] == "$ 1.000,00"
    assert filas[1][6] == "$ 1.000,00"
    assert filas[2][6] == "$ 500,00"
    assert filas[2][11] == "0001-00000042"
    assert filas[2][12] == "30414141414141"
    # fila en blanco y despues el total
    assert filas[-1][0] == "Total"
    assert filas[-1][6] == "$ 1.500,00"
    assert filas[-1][13] == "2 venta(s)"


def test_excel_de_ventas_marca_las_anuladas(cliente, headers_admin, admin_id, crear_venta_db):
    venta_id = crear_venta_db(admin_id, "100.00", "efectivo", utc(2026, 3, 2, 15, 0))
    cliente.post(f"/ventas/{venta_id}/anular", headers=headers_admin, json={"motivo": "x"})

    respuesta = cliente.get(
        "/reportes/ventas.xlsx?desde=2026-03-01&hasta=2026-03-31", headers=headers_admin
    )
    hoja = _hoja(respuesta.content)
    filas = list(hoja.iter_rows(values_only=True))
    assert filas[1][13] == "Sí"


# ---------------------------------------------------------------- gastos.xlsx


def test_excel_de_gastos_tiene_subtotales_por_categoria_y_total(
    cliente, headers_admin, admin_id, crear_categoria_db, crear_gasto_db
):
    proveedores = crear_categoria_db("Proveedores")
    seguro = crear_categoria_db("Seguro")
    crear_gasto_db(admin_id, "700.00", proveedores, date(2026, 3, 2), descripcion="Carne")
    crear_gasto_db(admin_id, "300.00", proveedores, date(2026, 3, 5))
    crear_gasto_db(admin_id, "100.10", seguro, date(2026, 3, 3))

    respuesta = cliente.get(
        "/reportes/gastos.xlsx?desde=2026-03-01&hasta=2026-03-31", headers=headers_admin
    )
    assert respuesta.status_code == 200
    hoja = _hoja(respuesta.content)
    filas = list(hoja.iter_rows(values_only=True))

    assert filas[0] == ("Fecha", "Categoría", "Descripción", "Monto", "Cargado por")
    textos = [str(c) for fila in filas for c in fila if c is not None]
    assert "Subtotales por categoría" in textos
    assert "$ 1.000,00" in textos  # subtotal de Proveedores (700 + 300)
    assert "$ 100,10" in textos  # subtotal de Seguro
    assert filas[-1][0] == "Total"
    assert filas[-1][3] == "$ 1.100,10"


# ---------------------------------------------------------------- gastos.pdf


def test_pdf_de_gastos_tiene_las_filas_y_subtotales_correctos(
    cliente, headers_admin, admin_id, crear_categoria_db, crear_gasto_db
):
    proveedores = crear_categoria_db("Proveedores")
    seguro = crear_categoria_db("Seguro")
    crear_gasto_db(admin_id, "700.00", proveedores, date(2026, 3, 2), descripcion="Carne")
    crear_gasto_db(admin_id, "300.00", proveedores, date(2026, 3, 5))
    crear_gasto_db(admin_id, "100.10", seguro, date(2026, 3, 3))

    respuesta = cliente.get("/reportes/gastos.pdf?desde=2026-03-01&hasta=2026-03-31", headers=headers_admin)
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert "gastos_2026-03-01_2026-03-31.pdf" in respuesta.headers["content-disposition"]
    assert respuesta.content.startswith(b"%PDF")

    texto = _texto_pdf(respuesta.content)
    assert "Proveedores" in texto
    assert "Seguro" in texto
    assert "Carne" in texto
    assert "700,00" in texto
    assert "1.000,00" in texto  # subtotal de Proveedores: 700 + 300
    assert "100,10" in texto  # subtotal de Seguro
    assert "1.100,10" in texto  # total


def test_pdf_de_gastos_sin_gastos_avisa_que_no_hay(cliente, headers_admin):
    respuesta = cliente.get("/reportes/gastos.pdf?desde=2026-03-01&hasta=2026-03-31", headers=headers_admin)
    assert respuesta.status_code == 200
    texto = _texto_pdf(respuesta.content)
    assert "No hay gastos" in texto


# ---------------------------------------------------------------- resumen.pdf


def test_pdf_de_resumen_se_genera(cliente, headers_admin, admin_id, crear_venta_db):
    crear_venta_db(admin_id, "1000.00", "efectivo", utc(2026, 3, 2, 15, 0))

    respuesta = cliente.get(
        "/reportes/resumen.pdf?desde=2026-03-01&hasta=2026-03-31", headers=headers_admin
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert "resumen_2026-03-01_2026-03-31.pdf" in respuesta.headers["content-disposition"]
    assert respuesta.content.startswith(b"%PDF")


# ---------------------------------------------------------------- iva.xlsx / iva.pdf


def test_el_reporte_de_iva_agrupa_bien_por_alicuota(cliente, headers_admin, admin_id, crear_venta_db):
    # Dos ventas facturadas a 10,5% y una a 21%; una "no_aplica" no debería entrar.
    crear_venta_db(
        admin_id, "110.50", "tarjeta", utc(2026, 3, 2, 10, 0),
        estado_arca="facturada", numero_comprobante=1, tipo_comprobante="6", punto_venta=1, cae="CAE-1",
        alicuota_iva="10.50",
    )
    crear_venta_db(
        admin_id, "221.00", "tarjeta", utc(2026, 3, 2, 11, 0),
        estado_arca="facturada", numero_comprobante=2, tipo_comprobante="6", punto_venta=1, cae="CAE-2",
        alicuota_iva="10.50",
    )
    crear_venta_db(
        admin_id, "121.00", "tarjeta", utc(2026, 3, 2, 12, 0),
        estado_arca="facturada", numero_comprobante=3, tipo_comprobante="6", punto_venta=1, cae="CAE-3",
        alicuota_iva="21.00",
    )
    crear_venta_db(admin_id, "500.00", "efectivo", utc(2026, 3, 2, 13, 0))  # no facturada: no entra

    respuesta = cliente.get("/reportes/iva.xlsx?desde=2026-03-01&hasta=2026-03-31", headers=headers_admin)
    assert respuesta.status_code == 200
    hoja = _hoja(respuesta.content)
    filas = list(hoja.iter_rows(values_only=True))
    textos = [str(c) for fila in filas for c in fila if c is not None]

    assert "10.50%" in textos
    assert "21.00%" in textos
    # 110.50 a 10,5%: neto 100.00, IVA 10.50; 221.00 a 10,5%: neto 200.00, IVA 21.00
    assert "$ 300,00" in textos  # neto acumulado de 10,5% (100 + 200)
    assert "$ 31,50" in textos  # IVA acumulado de 10,5% (10.50 + 21.00)


def test_el_reporte_de_iva_en_pdf_se_genera(cliente, headers_admin, admin_id, crear_venta_db):
    crear_venta_db(
        admin_id, "121.00", "tarjeta", utc(2026, 3, 2, 10, 0),
        estado_arca="facturada", numero_comprobante=1, tipo_comprobante="6", punto_venta=1, cae="CAE-1",
        alicuota_iva="21.00",
    )

    respuesta = cliente.get("/reportes/iva.pdf?desde=2026-03-01&hasta=2026-03-31", headers=headers_admin)
    assert respuesta.status_code == 200
    assert respuesta.content.startswith(b"%PDF")
    texto = _texto_pdf(respuesta.content)
    assert "21" in texto
    assert "100,00" in texto  # neto
    assert "21,00" in texto  # iva
