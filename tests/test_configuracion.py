from tests.utiles import con_token

DEFECTO = {
    "facturar_efectivo": False,
    "facturar_tarjeta": True,
    "facturar_transferencia": True,
    "razon_social": "Carnicería de prueba",
    "domicilio": "Calle Falsa 123, Localidad",
    "condicion_iva": "Responsable Inscripto",
    "inicio_actividades": "2020-01-01",
    "ingresos_brutos": None,
    "tipo_comprobante": 11,
    "punto_venta": 1,
    "descripcion_item": "Venta de mercadería",
    "anulacion_minutos_vendedor": 10,
    "cuit": "20000000001",
    "recargo_transferencia_porcentaje": "0.00",
}

# Lo que se manda en un PUT: todo lo de DEFECTO menos "cuit" (no se edita acá).
CAMBIO_VALIDO = {k: v for k, v in DEFECTO.items() if k != "cuit"}


def test_valores_por_defecto_se_completan_desde_las_variables_de_entorno(cliente, headers_admin):
    """La fila se crea vacía y se completa sola, una sola vez, con lo que ya
    había en el .env (para no perder los datos reales al agregar esta pantalla)."""
    respuesta = cliente.get("/configuracion", headers=headers_admin)
    assert respuesta.status_code == 200
    assert respuesta.json() == DEFECTO


def test_el_vendedor_puede_ver_la_configuracion(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    assert cliente.get("/configuracion", headers=headers).json() == DEFECTO


def test_sin_token_da_401(cliente):
    assert cliente.get("/configuracion").status_code == 401
    assert cliente.put("/configuracion", json=CAMBIO_VALIDO).status_code == 401


def test_el_vendedor_no_puede_cambiarla(cliente, crear_usuario, iniciar_sesion, headers_admin):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    cambio = {**CAMBIO_VALIDO, "facturar_efectivo": True}
    assert cliente.put("/configuracion", headers=headers, json=cambio).status_code == 403
    assert cliente.get("/configuracion", headers=headers_admin).json() == DEFECTO


def test_el_admin_puede_cambiarla_y_queda_guardada(cliente, headers_admin):
    cambio = {
        **CAMBIO_VALIDO,
        "facturar_efectivo": True,
        "facturar_tarjeta": False,
        "razon_social": "Otra razón social",
        "punto_venta": 3,
        "tipo_comprobante": 6,
        "descripcion_item": "Carnicería",
        "anulacion_minutos_vendedor": 15,
    }
    respuesta = cliente.put("/configuracion", headers=headers_admin, json=cambio)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["facturar_efectivo"] is True
    assert cuerpo["facturar_tarjeta"] is False
    assert cuerpo["razon_social"] == "Otra razón social"
    assert cuerpo["punto_venta"] == 3
    assert cuerpo["tipo_comprobante"] == 6
    assert cuerpo["descripcion_item"] == "Carnicería"
    assert cuerpo["anulacion_minutos_vendedor"] == 15
    assert cuerpo["cuit"] == "20000000001"  # no cambia: no se manda ni se puede

    assert cliente.get("/configuracion", headers=headers_admin).json() == cuerpo


def test_el_cuit_enviado_en_el_put_se_ignora(cliente, headers_admin):
    """No está en ConfiguracionIn: aunque el cliente lo mande, no rompe nada y
    la respuesta sigue trayendo el de siempre (el de la variable de entorno)."""
    cambio = {**CAMBIO_VALIDO, "cuit": "99999999999"}
    respuesta = cliente.put("/configuracion", headers=headers_admin, json=cambio)
    assert respuesta.status_code == 200
    assert respuesta.json()["cuit"] == "20000000001"


def test_faltando_un_campo_da_422(cliente, headers_admin):
    respuesta = cliente.put("/configuracion", headers=headers_admin, json={"facturar_efectivo": True})
    assert respuesta.status_code == 422


def test_razon_social_vacia_da_422(cliente, headers_admin):
    cambio = {**CAMBIO_VALIDO, "razon_social": "   "}
    assert cliente.put("/configuracion", headers=headers_admin, json=cambio).status_code == 422


def test_tipo_de_comprobante_invalido_da_422(cliente, headers_admin):
    cambio = {**CAMBIO_VALIDO, "tipo_comprobante": 1}
    assert cliente.put("/configuracion", headers=headers_admin, json=cambio).status_code == 422


def test_punto_de_venta_invalido_da_422(cliente, headers_admin):
    assert cliente.put("/configuracion", headers=headers_admin, json={**CAMBIO_VALIDO, "punto_venta": 0}).status_code == 422
    assert cliente.put("/configuracion", headers=headers_admin, json={**CAMBIO_VALIDO, "punto_venta": -1}).status_code == 422


def test_inicio_de_actividades_futuro_da_422(cliente, headers_admin):
    cambio = {**CAMBIO_VALIDO, "inicio_actividades": "2999-01-01"}
    respuesta = cliente.put("/configuracion", headers=headers_admin, json=cambio)
    assert respuesta.status_code == 422
    assert "futura" in respuesta.text.lower()


def test_minutos_de_anulacion_invalidos_dan_422(cliente, headers_admin):
    assert cliente.put("/configuracion", headers=headers_admin, json={**CAMBIO_VALIDO, "anulacion_minutos_vendedor": 0}).status_code == 422
    assert cliente.put("/configuracion", headers=headers_admin, json={**CAMBIO_VALIDO, "anulacion_minutos_vendedor": 121}).status_code == 422


def test_cambiar_la_configuracion_acorta_la_ventana_de_anulacion_del_vendedor(
    cliente, headers_admin, crear_usuario, iniciar_sesion, crear_venta_db
):
    """Con el valor por defecto (10 minutos) esta venta todavía se podría
    anular; achicando la ventana a 1 minuto, ya no."""
    from datetime import datetime, timedelta, timezone

    cliente.put("/configuracion", headers=headers_admin, json={**CAMBIO_VALIDO, "anulacion_minutos_vendedor": 1})

    vendedor_id = crear_usuario("vende", "clave-vende-1")
    hace_dos_minutos = datetime.now(timezone.utc) - timedelta(minutes=2)
    venta_id = crear_venta_db(vendedor_id, "10.00", "efectivo", fecha_hora=hace_dos_minutos)
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))

    respuesta = cliente.post(f"/ventas/{venta_id}/anular", headers=headers, json={"motivo": "x"})
    assert respuesta.status_code == 403
    assert "1 minutos" in respuesta.json()["detail"]


def test_no_impacta_en_facturas_ya_emitidas(cliente, headers_admin, admin_id, crear_venta_db):
    """Los datos del comercio de una venta ya facturada no cambian aunque
    después se edite la configuración."""
    venta_id = crear_venta_db(
        admin_id, "121.00", "tarjeta", estado_arca="facturada", numero_comprobante=1,
        tipo_comprobante="6", punto_venta=1, cae="30414141414141",
    )
    antes = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()
    cliente.put("/configuracion", headers=headers_admin, json={**CAMBIO_VALIDO, "razon_social": "Otro nombre"})
    despues = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()

    assert despues["emisor"]["razon_social"] == "Otro nombre"  # esto sí es "la mejor estimación" de hoy
    # Lo que NUNCA cambia es el comprobante ya impreso.
    assert despues["numero"] == antes["numero"]
    assert despues["cae"] == antes["cae"]
    assert despues["punto_venta"] == antes["punto_venta"]
    assert despues["total"] == antes["total"]


def test_ventas_viejas_sin_rubro_usan_el_predeterminado_actual(cliente, headers_admin, admin_id, crear_venta_db):
    """Una venta vieja (de antes de que existieran los rubros, creada directo
    en la base sin alicuota_iva) usa el rubro predeterminado actual como
    mejor estimación para el IVA; eso sí puede cambiar. Lo que nunca cambia
    es el comprobante ya emitido (tipo, número, CAE, punto de venta)."""
    venta_id = crear_venta_db(
        admin_id, "121.00", "tarjeta", estado_arca="facturada", numero_comprobante=1,
        tipo_comprobante="6", punto_venta=1, cae="30414141414141",
    )
    antes = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()
    assert antes["iva_contenido"] == "11.50"  # 121.00 a 10,5% (rubro predeterminado de prueba: Carne)

    cliente.put(
        "/rubros/1",
        headers=headers_admin,
        json={
            "nombre": "Carne", "alicuota": "21.00", "descripcion_factura": "Venta de carne",
            "activo": True, "orden": 1, "es_predeterminado": True,
        },
    )

    despues = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()
    assert despues["iva_contenido"] == "21.00"  # 121.00 a 21% ahora
    assert despues["numero"] == antes["numero"]
    assert despues["cae"] == antes["cae"]
    assert despues["punto_venta"] == antes["punto_venta"]
