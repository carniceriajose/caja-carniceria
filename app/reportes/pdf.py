"""Reportes en PDF (reportlab): el resumen del período y el comprobante de un
cierre de caja, listos para imprimir o archivar."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.dinero import CERO, formatear_ar
from app.models import CierreCaja, Configuracion

ETIQUETA_MEDIO = {"efectivo": "Efectivo", "tarjeta": "Tarjeta", "transferencia": "Transferencia"}
ETIQUETA_TIPO_TARJETA = {"credito": "Crédito", "debito": "Débito"}
ETIQUETA_ESTADO = {
    "no_aplica": "No se factura",
    "pendiente": "Pendiente",
    "facturada": "Facturada",
    "fallo": "Con error",
}

_ESTILOS = getSampleStyleSheet()
_TITULO = ParagraphStyle("TituloReporte", parent=_ESTILOS["Title"], fontSize=16, spaceAfter=4)
_SUBTITULO = ParagraphStyle("SubtituloReporte", parent=_ESTILOS["Normal"], fontSize=10, textColor=colors.grey)
_SECCION = ParagraphStyle("SeccionReporte", parent=_ESTILOS["Heading2"], fontSize=12, spaceBefore=14, spaceAfter=6)

_ESTILO_TABLA = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f7f9")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor("#d9dce1")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d9dce1")),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
)


def _documento(buffer: BytesIO) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm
    )


def generar_pdf_resumen(resumen: dict, configuracion: Configuracion) -> bytes:
    buffer = BytesIO()
    doc = _documento(buffer)
    elementos = []

    elementos.append(Paragraph(configuracion.razon_social or "Resumen", _TITULO))
    elementos.append(
        Paragraph(
            f"Del {resumen['desde'].strftime('%d/%m/%Y')} al {resumen['hasta'].strftime('%d/%m/%Y')}",
            _SUBTITULO,
        )
    )

    elementos.append(Paragraph("Por medio de pago", _SECCION))
    filas = [["Medio", "Cantidad", "Monto"]] + [
        [ETIQUETA_MEDIO.get(f["medio_pago"], f["medio_pago"]), str(f["cantidad"]), formatear_ar(f["monto"])]
        for f in resumen["por_medio_pago"]
    ]
    filas.append(["Total", str(resumen["cantidad_ventas"]), formatear_ar(resumen["total_vendido"])])
    tabla = Table(filas, colWidths=[7 * cm, 3.5 * cm, 4.5 * cm])
    tabla.setStyle(_ESTILO_TABLA)
    elementos.append(tabla)

    elementos.append(Paragraph("Por estado de facturación", _SECCION))
    filas = [["Estado", "Cantidad", "Monto"]] + [
        [ETIQUETA_ESTADO.get(f["estado_arca"], f["estado_arca"]), str(f["cantidad"]), formatear_ar(f["monto"])]
        for f in resumen["por_estado_fiscal"]
    ]
    tabla = Table(filas, colWidths=[7 * cm, 3.5 * cm, 4.5 * cm])
    tabla.setStyle(_ESTILO_TABLA)
    elementos.append(tabla)

    if resumen["gastos_por_categoria"]:
        elementos.append(Paragraph("Gastos por categoría", _SECCION))
        filas = [["Categoría", "Cantidad", "Monto"]] + [
            [g["categoria"], str(g["cantidad"]), formatear_ar(g["monto"])] for g in resumen["gastos_por_categoria"]
        ]
        filas.append(["Total gastos", "", formatear_ar(resumen["total_gastos"])])
        tabla = Table(filas, colWidths=[7 * cm, 3.5 * cm, 4.5 * cm])
        tabla.setStyle(_ESTILO_TABLA)
        elementos.append(tabla)

    elementos.append(Paragraph("Anulaciones", _SECCION))
    filas = [
        ["Cantidad", "Monto"],
        [str(resumen["cantidad_anulaciones"]), formatear_ar(resumen["monto_anulaciones"])],
    ]
    tabla = Table(filas, colWidths=[7 * cm, 8 * cm])
    tabla.setStyle(_ESTILO_TABLA)
    elementos.append(tabla)

    elementos.append(Paragraph("Recargos por medio de pago", _SECCION))
    filas = [
        ["Concepto", "Monto"],
        ["Total recargos", formatear_ar(resumen["total_recargos"])],
    ]
    tabla = Table(filas, colWidths=[7 * cm, 8 * cm])
    tabla.setStyle(_ESTILO_TABLA)
    elementos.append(tabla)

    if resumen["ventas_por_rubro"]:
        elementos.append(Paragraph("Ventas por rubro", _SECCION))
        filas = [["Rubro", "Cantidad", "Monto"]] + [
            [r["rubro"], str(r["cantidad"]), formatear_ar(r["monto"])] for r in resumen["ventas_por_rubro"]
        ]
        tabla = Table(filas, colWidths=[7 * cm, 3.5 * cm, 4.5 * cm])
        tabla.setStyle(_ESTILO_TABLA)
        elementos.append(tabla)

    if resumen["ventas_por_tarjeta"]:
        elementos.append(Paragraph("Ventas por tarjeta", _SECCION))
        filas = [["Tarjeta", "Cantidad", "Monto"]] + [
            [t["tarjeta"], str(t["cantidad"]), formatear_ar(t["monto"])] for t in resumen["ventas_por_tarjeta"]
        ]
        tabla = Table(filas, colWidths=[7 * cm, 3.5 * cm, 4.5 * cm])
        tabla.setStyle(_ESTILO_TABLA)
        elementos.append(tabla)

    if resumen["ventas_por_tipo_tarjeta"]:
        elementos.append(Paragraph("Ventas por tipo de tarjeta", _SECCION))
        filas = [["Tipo", "Cantidad", "Monto"]] + [
            [ETIQUETA_TIPO_TARJETA.get(t["tipo"], "Sin tipo"), str(t["cantidad"]), formatear_ar(t["monto"])]
            for t in resumen["ventas_por_tipo_tarjeta"]
        ]
        tabla = Table(filas, colWidths=[7 * cm, 3.5 * cm, 4.5 * cm])
        tabla.setStyle(_ESTILO_TABLA)
        elementos.append(tabla)

    elementos.append(Spacer(1, 0.6 * cm))
    resultado_negativo = resumen["resultado"] < 0
    estilo_resultado = ParagraphStyle(
        "Resultado",
        parent=_ESTILOS["Heading2"],
        textColor=colors.HexColor("#a12a2a") if resultado_negativo else colors.HexColor("#1e7a34"),
    )
    elementos.append(
        Paragraph(
            f"Resultado del período (ventas menos gastos): {formatear_ar(resumen['resultado'])}",
            estilo_resultado,
        )
    )

    doc.build(elementos)
    return buffer.getvalue()


def generar_pdf_gastos(filas, desde, hasta, configuracion: Configuracion) -> bytes:
    """`filas`: iterable de (Gasto, nombre_categoria)."""
    buffer = BytesIO()
    doc = _documento(buffer)
    elementos = []

    elementos.append(Paragraph(configuracion.razon_social or "Gastos", _TITULO))
    elementos.append(Paragraph(f"Del {desde.strftime('%d/%m/%Y')} al {hasta.strftime('%d/%m/%Y')}", _SUBTITULO))

    filas_tabla = [["Fecha", "Categoría", "Detalle", "Monto"]]
    total = CERO
    subtotales: dict[str, object] = {}
    for gasto, nombre_categoria in filas:
        total += gasto.monto
        subtotales[nombre_categoria] = subtotales.get(nombre_categoria, CERO) + gasto.monto
        filas_tabla.append(
            [gasto.fecha.strftime("%d/%m/%Y"), nombre_categoria, gasto.descripcion or "", formatear_ar(gasto.monto)]
        )

    elementos.append(Paragraph("Detalle", _SECCION))
    if len(filas_tabla) == 1:
        elementos.append(Paragraph("No hay gastos en este período.", _ESTILOS["Normal"]))
    else:
        tabla = Table(filas_tabla, colWidths=[2.3 * cm, 3.7 * cm, 5 * cm, 4 * cm], repeatRows=1)
        tabla.setStyle(_ESTILO_TABLA)
        elementos.append(tabla)

    elementos.append(Paragraph("Subtotales por categoría", _SECCION))
    filas_subtotal = [["Categoría", "Monto"]] + [
        [nombre_categoria, formatear_ar(subtotal)] for nombre_categoria, subtotal in subtotales.items()
    ]
    filas_subtotal.append(["Total", formatear_ar(total)])
    tabla = Table(filas_subtotal, colWidths=[10 * cm, 5 * cm])
    tabla.setStyle(_ESTILO_TABLA)
    elementos.append(tabla)

    doc.build(elementos)
    return buffer.getvalue()


def generar_pdf_iva(filas: list[dict], desde, hasta, configuracion: Configuracion) -> bytes:
    """`filas`: lista de dicts {alicuota, neto, iva, total, cantidad}, ya
    agrupados (ver app/reportes/iva.py)."""
    buffer = BytesIO()
    doc = _documento(buffer)
    elementos = []

    elementos.append(Paragraph(configuracion.razon_social or "IVA por alícuota", _TITULO))
    elementos.append(Paragraph(f"Del {desde.strftime('%d/%m/%Y')} al {hasta.strftime('%d/%m/%Y')}", _SUBTITULO))

    elementos.append(Paragraph("IVA por alícuota", _SECCION))
    if not filas:
        elementos.append(Paragraph("No hay ventas facturadas en este período.", _ESTILOS["Normal"]))
    else:
        filas_tabla = [["Alícuota", "Cantidad", "Neto", "IVA", "Total"]] + [
            [f"{f['alicuota']}%", str(f["cantidad"]), formatear_ar(f["neto"]), formatear_ar(f["iva"]), formatear_ar(f["total"])]
            for f in filas
        ]
        neto_total = sum((f["neto"] for f in filas), CERO)
        iva_total = sum((f["iva"] for f in filas), CERO)
        importe_total = sum((f["total"] for f in filas), CERO)
        cantidad_total = sum(f["cantidad"] for f in filas)
        filas_tabla.append(
            ["Total", str(cantidad_total), formatear_ar(neto_total), formatear_ar(iva_total), formatear_ar(importe_total)]
        )
        tabla = Table(filas_tabla, colWidths=[3 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm])
        tabla.setStyle(_ESTILO_TABLA)
        elementos.append(tabla)

    doc.build(elementos)
    return buffer.getvalue()


def generar_pdf_cierre(cierre: CierreCaja) -> bytes:
    buffer = BytesIO()
    doc = _documento(buffer)
    elementos = []

    elementos.append(Paragraph(f"Cierre de caja — {cierre.fecha.strftime('%d/%m/%Y')}", _TITULO))
    elementos.append(
        Paragraph(
            f"Cerrado por {cierre.usuario.nombre} el {cierre.fecha_hora_cierre.strftime('%d/%m/%Y %H:%M')}",
            _SUBTITULO,
        )
    )
    if cierre.anulado:
        elementos.append(Spacer(1, 0.3 * cm))
        estilo_anulado = ParagraphStyle("Anulado", parent=_ESTILOS["Heading2"], textColor=colors.HexColor("#a12a2a"))
        elementos.append(Paragraph("ANULADO", estilo_anulado))
        elementos.append(Paragraph(f"Motivo: {cierre.anulado_motivo}", _ESTILOS["Normal"]))

    elementos.append(Paragraph("Totales del sistema", _SECCION))
    filas = [
        ["Efectivo", formatear_ar(cierre.total_efectivo)],
        ["Tarjeta", formatear_ar(cierre.total_tarjeta)],
        ["Transferencia", formatear_ar(cierre.total_transferencia)],
        ["Total general", formatear_ar(cierre.total_general)],
        ["Cantidad de ventas", str(cierre.cantidad_ventas)],
        ["Anulaciones", f"{cierre.cantidad_anulaciones} ({formatear_ar(cierre.monto_anulaciones)})"],
    ]
    tabla = Table(filas, colWidths=[8 * cm, 7 * cm])
    tabla.setStyle(_ESTILO_TABLA)
    elementos.append(tabla)

    elementos.append(Paragraph("Arqueo", _SECCION))
    diferencia_ok = cierre.diferencia == 0
    filas = [
        ["Efectivo del sistema", formatear_ar(cierre.total_efectivo)],
        ["Efectivo contado", formatear_ar(cierre.efectivo_contado)],
        ["Diferencia", formatear_ar(cierre.diferencia)],
    ]
    tabla = Table(filas, colWidths=[8 * cm, 7 * cm])
    estilo_arqueo = TableStyle(_ESTILO_TABLA.getCommands())
    estilo_arqueo.add(
        "TEXTCOLOR",
        (1, 2),
        (1, 2),
        colors.HexColor("#1e7a34") if diferencia_ok else colors.HexColor("#a12a2a"),
    )
    estilo_arqueo.add("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold")
    tabla.setStyle(estilo_arqueo)
    elementos.append(tabla)

    if cierre.observaciones:
        elementos.append(Paragraph("Observaciones", _SECCION))
        elementos.append(Paragraph(cierre.observaciones, _ESTILOS["Normal"]))

    elementos.append(Spacer(1, 1.5 * cm))
    elementos.append(Paragraph("Firma: ____________________________", _ESTILOS["Normal"]))

    doc.build(elementos)
    return buffer.getvalue()
