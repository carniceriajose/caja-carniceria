import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.arca import wsaa, wsfe
from app.models import Anulacion, Venta
from tests.utiles import con_token


def _venta_facturada(sesion, vendedor_id, tipo="6", numero=1, cae="CAE-orig", total="121.00"):
    with sesion() as db:
        venta = Venta(
            id_cliente=uuid.uuid4(),
            subtotal=Decimal(total),
            total=Decimal(total),
            medio_pago="tarjeta",
            vendedor_id=vendedor_id,
            estado_arca="facturada",
            tipo_comprobante=tipo,
            punto_venta=1,
            numero_comprobante=numero,
            cae=cae,
        )
        db.add(venta)
        db.commit()
        return venta.id


def _preparar_arca_aprueba_todo(monkeypatch, ultimo_autorizado, cae):
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: True)
    monkeypatch.setattr(
        wsaa,
        "obtener_o_renovar_ticket",
        lambda db: wsaa.TicketInfo(token="t", sign="s", vence_en=datetime.now(timezone.utc)),
    )
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: ultimo_autorizado)
    monkeypatch.setattr(
        wsfe,
        "solicitar_cae",
        lambda t, pv, tipo, detalle: {
            "FeDetResp": {"FECAEDetResponse": [{"Resultado": "A", "CAE": cae, "CAEFchVto": "20261231", "CbteDesde": detalle["CbteDesde"]}]}
        },
    )


# ---------------------------------------------------------------- permisos


def test_solo_admin_ve_anulaciones(cliente, crear_usuario, iniciar_sesion):
    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))
    assert cliente.get("/anulaciones", headers=headers).status_code == 403
    assert cliente.get("/anulaciones").status_code == 401


def test_solo_admin_puede_reintentar(cliente, crear_usuario, iniciar_sesion, admin_id, sesion_pruebas):
    venta_id = _venta_facturada(sesion_pruebas, admin_id)
    with sesion_pruebas() as db:
        anulacion = Anulacion(venta_id=venta_id, motivo="x", usuario_id=admin_id, estado="fallo")
        db.add(anulacion)
        db.commit()
        anulacion_id = anulacion.id

    crear_usuario("vende", "clave-vende-1")
    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))
    assert cliente.post(f"/anulaciones/{anulacion_id}/reintentar", headers=headers).status_code == 403


# ---------------------------------------------------------------- listado y filtros


def test_lista_anulaciones_con_la_venta_asociada(cliente, headers_admin, admin_id, sesion_pruebas):
    venta_id = _venta_facturada(sesion_pruebas, admin_id, total="200.00")
    with sesion_pruebas() as db:
        db.add(Anulacion(venta_id=venta_id, motivo="Reclamo", usuario_id=admin_id, estado="fallo", error_detalle="ARCA rechazó"))
        db.commit()

    respuesta = cliente.get("/anulaciones", headers=headers_admin)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    fila = cuerpo["items"][0]
    assert fila["motivo"] == "Reclamo"
    assert fila["estado"] == "fallo"
    assert fila["venta"]["id"] == venta_id
    assert fila["venta"]["total"] == "200.00"
    assert fila["usuario"]["id"] == admin_id


def test_filtra_anulaciones_por_estado(cliente, headers_admin, admin_id, sesion_pruebas):
    v1 = _venta_facturada(sesion_pruebas, admin_id, numero=1)
    v2 = _venta_facturada(sesion_pruebas, admin_id, numero=2)
    with sesion_pruebas() as db:
        db.add(Anulacion(venta_id=v1, motivo="a", usuario_id=admin_id, estado="fallo"))
        db.add(Anulacion(venta_id=v2, motivo="b", usuario_id=admin_id, estado="emitida", tipo=8, numero=1, cae="X"))
        db.commit()

    fallos = cliente.get("/anulaciones?estado=fallo", headers=headers_admin).json()["items"]
    emitidas = cliente.get("/anulaciones?estado=emitida", headers=headers_admin).json()["items"]
    assert len(fallos) == 1 and fallos[0]["venta_id"] == v1
    assert len(emitidas) == 1 and emitidas[0]["venta_id"] == v2


def test_pagina_de_anulaciones(cliente, headers_admin, admin_id, sesion_pruebas):
    for i in range(3):
        v = _venta_facturada(sesion_pruebas, admin_id, numero=i + 1)
        with sesion_pruebas() as db:
            db.add(Anulacion(venta_id=v, motivo=f"m{i}", usuario_id=admin_id, estado="fallo"))
            db.commit()

    pagina1 = cliente.get("/anulaciones?pagina=1&por_pagina=2", headers=headers_admin).json()
    pagina2 = cliente.get("/anulaciones?pagina=2&por_pagina=2", headers=headers_admin).json()
    assert pagina1["total"] == 3
    assert len(pagina1["items"]) == 2
    assert len(pagina2["items"]) == 1


# ---------------------------------------------------------------- reintentar


def test_reintentar_una_anulacion_en_fallo_la_emite(cliente, headers_admin, admin_id, sesion_pruebas, monkeypatch):
    venta_id = _venta_facturada(sesion_pruebas, admin_id, tipo="11", numero=1)
    with sesion_pruebas() as db:
        anulacion = Anulacion(venta_id=venta_id, motivo="x", usuario_id=admin_id, estado="fallo", error_detalle="antes")
        db.add(anulacion)
        db.commit()
        anulacion_id = anulacion.id

    _preparar_arca_aprueba_todo(monkeypatch, ultimo_autorizado=40, cae="CAE-NC-41")

    respuesta = cliente.post(f"/anulaciones/{anulacion_id}/reintentar", headers=headers_admin)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "emitida"
    assert cuerpo["cae"] == "CAE-NC-41"
    assert cuerpo["tipo"] == 13  # nota de crédito C


def test_no_se_puede_reintentar_una_anulacion_ya_emitida(cliente, headers_admin, admin_id, sesion_pruebas):
    venta_id = _venta_facturada(sesion_pruebas, admin_id)
    with sesion_pruebas() as db:
        anulacion = Anulacion(venta_id=venta_id, motivo="x", usuario_id=admin_id, estado="emitida", tipo=8, numero=1, cae="X")
        db.add(anulacion)
        db.commit()
        anulacion_id = anulacion.id

    assert cliente.post(f"/anulaciones/{anulacion_id}/reintentar", headers=headers_admin).status_code == 400


def test_no_se_puede_reintentar_una_sin_comprobante(cliente, headers_admin, admin_id, sesion_pruebas):
    with sesion_pruebas() as db:
        venta = Venta(
            id_cliente=uuid.uuid4(), subtotal=Decimal("10"), total=Decimal("10"),
            medio_pago="efectivo", vendedor_id=admin_id,
        )
        db.add(venta)
        db.commit()
        anulacion = Anulacion(venta_id=venta.id, motivo="x", usuario_id=admin_id, estado="sin_comprobante")
        db.add(anulacion)
        db.commit()
        anulacion_id = anulacion.id

    assert cliente.post(f"/anulaciones/{anulacion_id}/reintentar", headers=headers_admin).status_code == 400


def test_reintentar_inexistente_da_404(cliente, headers_admin):
    assert cliente.post("/anulaciones/9999/reintentar", headers=headers_admin).status_code == 404


def test_reintentar_queda_en_la_auditoria(cliente, headers_admin, admin_id, sesion_pruebas, monkeypatch):
    venta_id = _venta_facturada(sesion_pruebas, admin_id)
    with sesion_pruebas() as db:
        anulacion = Anulacion(venta_id=venta_id, motivo="x", usuario_id=admin_id, estado="fallo")
        db.add(anulacion)
        db.commit()
        anulacion_id = anulacion.id

    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: False)  # no importa el resultado acá
    cliente.post(f"/anulaciones/{anulacion_id}/reintentar", headers=headers_admin)

    filas = cliente.get("/auditoria?accion=anulacion.reintentar", headers=headers_admin).json()["items"]
    assert len(filas) == 1
    assert filas[0]["entidad_id"] == venta_id


def test_el_resultado_en_arca_queda_registrado_en_la_auditoria(
    cliente, headers_admin, admin_id, sesion_pruebas, monkeypatch
):
    venta_id = _venta_facturada(sesion_pruebas, admin_id, tipo="6", numero=1)
    with sesion_pruebas() as db:
        anulacion = Anulacion(venta_id=venta_id, motivo="x", usuario_id=admin_id, estado="pendiente")
        db.add(anulacion)
        db.commit()
        anulacion_id = anulacion.id

    _preparar_arca_aprueba_todo(monkeypatch, ultimo_autorizado=1, cae="CAE-NC-2")
    cliente.post(f"/anulaciones/{anulacion_id}/reintentar", headers=headers_admin)

    filas = cliente.get("/auditoria?accion=anulacion.emitida", headers=headers_admin).json()["items"]
    assert len(filas) == 1
    assert filas[0]["entidad_id"] == venta_id
    assert filas[0]["usuario"] is None  # lo emite el sistema, no una persona


# ---------------------------------------------------------------- comprobante de la nota de crédito


def test_comprobante_de_nota_de_credito_no_disponible_hasta_que_este_emitida(
    cliente, headers_admin, admin_id, sesion_pruebas
):
    venta_id = _venta_facturada(sesion_pruebas, admin_id)
    with sesion_pruebas() as db:
        db.add(Anulacion(venta_id=venta_id, motivo="x", usuario_id=admin_id, estado="fallo"))
        db.commit()

    respuesta = cliente.get(f"/ventas/{venta_id}/nota-credito/comprobante", headers=headers_admin)
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "El comprobante todavía no está disponible."


def test_comprobante_de_nota_de_credito_disponible_cuando_esta_emitida(
    cliente, headers_admin, admin_id, sesion_pruebas
):
    venta_id = _venta_facturada(sesion_pruebas, admin_id, tipo="6", total="121.00")
    with sesion_pruebas() as db:
        db.add(
            Anulacion(
                venta_id=venta_id,
                motivo="x",
                usuario_id=admin_id,
                estado="emitida",
                tipo=8,
                punto_venta=1,
                numero=42,
                cae="30414141414141",
                respuesta_fiscal={"ResultGet": {"CbteFch": "20260315"}},
            )
        )
        db.commit()

    respuesta = cliente.get(f"/ventas/{venta_id}/nota-credito/comprobante", headers=headers_admin)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "NOTA DE CRÉDITO B"
    assert cuerpo["letra"] == "B"
    assert cuerpo["numero"] == 42
    assert cuerpo["cae"] == "30414141414141"
    assert cuerpo["total"] == "121.00"
    assert cuerpo["fecha"] == "2026-03-15"


def test_la_nota_de_credito_replica_la_alicuota_y_la_descripcion_de_la_factura_original(
    cliente, headers_admin, admin_id, sesion_pruebas
):
    venta_id = _venta_facturada(sesion_pruebas, admin_id, tipo="6", total="121.00", cae="30414141414140")
    with sesion_pruebas() as db:
        venta = db.get(Venta, venta_id)
        venta.rubro_id = 2
        venta.rubro_nombre = "Embutidos"
        venta.descripcion_factura = "Venta de embutidos"
        venta.alicuota_iva = Decimal("21.00")
        db.add(
            Anulacion(
                venta_id=venta_id,
                motivo="x",
                usuario_id=admin_id,
                estado="emitida",
                tipo=8,
                punto_venta=1,
                numero=42,
                cae="30414141414141",
                alicuota_iva=Decimal("21.00"),
                respuesta_fiscal={"ResultGet": {"CbteFch": "20260315"}},
            )
        )
        db.commit()

    factura = cliente.get(f"/ventas/{venta_id}/comprobante", headers=headers_admin).json()
    nota_credito = cliente.get(f"/ventas/{venta_id}/nota-credito/comprobante", headers=headers_admin).json()

    assert nota_credito["descripcion_item"] == factura["descripcion_item"] == "Venta de embutidos"
    assert nota_credito["iva_contenido"] == factura["iva_contenido"]


def test_el_vendedor_solo_ve_el_comprobante_de_nota_de_credito_de_su_propia_venta(
    cliente, crear_usuario, iniciar_sesion, sesion_pruebas
):
    vendedor_id = crear_usuario("vende", "clave-vende-1")
    otro_id = crear_usuario("otro", "clave-otro-1")
    propia = _venta_facturada(sesion_pruebas, vendedor_id, numero=1)
    ajena = _venta_facturada(sesion_pruebas, otro_id, numero=2)
    with sesion_pruebas() as db:
        db.add(Anulacion(venta_id=propia, motivo="x", usuario_id=vendedor_id, estado="emitida", tipo=8, punto_venta=1, numero=1, cae="30414141414141"))
        db.add(Anulacion(venta_id=ajena, motivo="x", usuario_id=otro_id, estado="emitida", tipo=8, punto_venta=1, numero=2, cae="30414141414142"))
        db.commit()

    headers = con_token(iniciar_sesion("vende", "clave-vende-1"))
    assert cliente.get(f"/ventas/{propia}/nota-credito/comprobante", headers=headers).status_code == 200
    assert cliente.get(f"/ventas/{ajena}/nota-credito/comprobante", headers=headers).status_code == 403
