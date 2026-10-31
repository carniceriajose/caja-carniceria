"""Reportes en Excel (openpyxl, modo write_only): cada fila se escribe apenas
se lee de la base, sin acumular toda la planilla en memoria."""

from collections import OrderedDict
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from app.dinero import CERO, formatear_ar
from app.fechas import ZONA

ETIQUETA_MEDIO = {"efectivo": "Efectivo", "tarjeta": "Tarjeta", "transferencia": "Transferencia"}
ETIQUETA_TIPO_TARJETA = {"credito": "Crédito", "debito": "Débito"}
ETIQUETA_ESTADO = {
    "no_aplica": "No se factura",
    "pendiente": "Pendiente",
    "facturada": "Facturada",
    "fallo": "Con error",
}


def _numero_comprobante(punto_venta, numero) -> str:
    if not punto_venta or not numero:
        return ""
    return f"{str(punto_venta).zfill(4)}-{str(numero).zfill(8)}"


def generar_excel_ventas(filas) -> bytes:
    """`filas`: iterable de (Venta, nombre_vendedor)."""
    wb = Workbook(write_only=True)
    hoja = wb.create_sheet("Ventas")
    hoja.append(
        [
            "Fecha y hora", "Subtotal", "Rubro", "Tarjeta", "Tipo de tarjeta", "Ajuste", "Total", "Medio de pago",
            "Vendedor", "Estado fiscal", "Tipo", "Número", "CAE", "Anulada",
        ]
    )

    total = CERO
    cantidad = 0
    for venta, nombre_vendedor in filas:
        total += venta.total
        cantidad += 1
        momento = venta.fecha_hora.astimezone(ZONA)
        hoja.append(
            [
                momento.strftime("%d/%m/%Y %H:%M"),
                formatear_ar(venta.subtotal),
                venta.rubro_nombre or "",
                venta.tarjeta_nombre or "",
                ETIQUETA_TIPO_TARJETA.get(venta.tarjeta_tipo, ""),
                venta.ajuste_detalle or "",
                formatear_ar(venta.total),
                ETIQUETA_MEDIO.get(venta.medio_pago, venta.medio_pago),
                nombre_vendedor,
                ETIQUETA_ESTADO.get(venta.estado_arca, venta.estado_arca),
                venta.tipo_comprobante or "",
                _numero_comprobante(venta.punto_venta, venta.numero_comprobante),
                venta.cae or "",
                "Sí" if venta.anulada else "",
            ]
        )

    hoja.append([])
    hoja.append(["Total", "", "", "", "", "", formatear_ar(total), "", "", "", "", "", "", f"{cantidad} venta(s)"])

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def generar_excel_iva(filas, desde, hasta) -> bytes:
    """`filas`: lista de dicts {alicuota, neto, iva, total, cantidad}, ya
    agrupados (ver app/reportes/iva.py)."""
    wb = Workbook(write_only=True)
    hoja = wb.create_sheet("IVA por alícuota")
    hoja.append([f"Del {desde.strftime('%d/%m/%Y')} al {hasta.strftime('%d/%m/%Y')}"])
    hoja.append([])
    hoja.append(["Alícuota", "Cantidad", "Neto", "IVA", "Total"])

    neto_total = iva_total = importe_total = CERO
    cantidad_total = 0
    for fila in filas:
        neto_total += fila["neto"]
        iva_total += fila["iva"]
        importe_total += fila["total"]
        cantidad_total += fila["cantidad"]
        hoja.append(
            [
                f"{fila['alicuota']}%",
                fila["cantidad"],
                formatear_ar(fila["neto"]),
                formatear_ar(fila["iva"]),
                formatear_ar(fila["total"]),
            ]
        )

    hoja.append([])
    hoja.append(["Total", cantidad_total, formatear_ar(neto_total), formatear_ar(iva_total), formatear_ar(importe_total)])

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def generar_excel_gastos(filas):
    """`filas`: iterable de (Gasto, nombre_categoria, nombre_usuario)."""
    wb = Workbook(write_only=True)
    hoja = wb.create_sheet("Gastos")
    hoja.append(["Fecha", "Categoría", "Descripción", "Monto", "Cargado por"])

    total = CERO
    subtotales: "OrderedDict[str, Decimal]" = OrderedDict()
    for gasto, nombre_categoria, nombre_usuario in filas:
        total += gasto.monto
        subtotales[nombre_categoria] = subtotales.get(nombre_categoria, CERO) + gasto.monto
        hoja.append(
            [
                gasto.fecha.strftime("%d/%m/%Y"),
                nombre_categoria,
                gasto.descripcion or "",
                formatear_ar(gasto.monto),
                nombre_usuario,
            ]
        )

    hoja.append([])
    hoja.append(["Subtotales por categoría"])
    for nombre_categoria, subtotal in subtotales.items():
        hoja.append(["", nombre_categoria, "", formatear_ar(subtotal)])

    hoja.append([])
    hoja.append(["Total", "", "", formatear_ar(total)])

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
