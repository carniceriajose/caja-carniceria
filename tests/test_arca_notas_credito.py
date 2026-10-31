import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.arca import wsaa, wsfe
from app.arca.servicio import emitir_nota_credito
from app.models import Anulacion, Venta

TICKET_FALSO = wsaa.TicketInfo(
    token="token-de-prueba", sign="sign-de-prueba", vence_en=datetime.now(timezone.utc) + timedelta(hours=1)
)


def _preparar_arca_basica(monkeypatch):
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: True)
    monkeypatch.setattr(wsaa, "obtener_o_renovar_ticket", lambda db: TICKET_FALSO)


def _venta_facturada(
    vendedor_id, total="121.00", tipo_comprobante="6", numero=100, cae="CAE-orig", punto_venta=1,
    alicuota_iva=Decimal("21"),
):
    return Venta(
        id_cliente=uuid.uuid4(),
        subtotal=Decimal(total),
        total=Decimal(total),
        medio_pago="tarjeta",
        vendedor_id=vendedor_id,
        estado_arca="facturada",
        tipo_comprobante=tipo_comprobante,
        punto_venta=punto_venta,
        numero_comprobante=numero,
        cae=cae,
        cae_vencimiento=None,
        alicuota_iva=alicuota_iva,
    )


def _anulacion(venta_id, usuario_id, motivo="Reclamo del cliente"):
    return Anulacion(venta_id=venta_id, motivo=motivo, usuario_id=usuario_id, estado="pendiente")


def _respuesta_aprobada(numero, cae):
    return {
        "FeDetResp": {
            "FECAEDetResponse": [
                {"Resultado": "A", "CAE": cae, "CAEFchVto": "20261231", "CbteDesde": numero}
            ]
        }
    }


class ArcaFalsa:
    def __init__(self, ultimo_autorizado):
        self.ultimo_autorizado = ultimo_autorizado
        self.llamadas_solicitar = 0
        self.ultimo_detalle = None
        self.ultimo_tipo_pedido = None
        self._candado = threading.Lock()

    def consultar_ultimo_autorizado(self, *_args, **_kwargs):
        valor = self.ultimo_autorizado
        time.sleep(0.02)
        return valor

    def solicitar_cae(self, _ticket, _pv, tipo, detalle):
        with self._candado:
            self.llamadas_solicitar += 1
            self.ultimo_detalle = detalle
            self.ultimo_tipo_pedido = tipo
            numero = detalle["CbteDesde"]
            self.ultimo_autorizado = numero
            return _respuesta_aprobada(numero, cae=f"CAE-NC-{numero}")


# ---------------------------------------------------------------- efectivo (sin_comprobante) no toca ARCA


def test_anulacion_sin_comprobante_nunca_llama_a_arca(sesion_pruebas, monkeypatch, admin_id):
    """Ni siquiera se pregunta si hay certificado: para una venta que nunca
    tuvo CAE no hace falta nota de crédito."""
    llamado = {"veces": 0}

    def marcar(*_a, **_k):
        llamado["veces"] += 1
        return False

    monkeypatch.setattr(wsaa, "hay_certificado_configurado", marcar)

    with sesion_pruebas() as db:
        venta = Venta(
            id_cliente=uuid.uuid4(), subtotal=Decimal("100"), total=Decimal("100"), medio_pago="efectivo",
            vendedor_id=admin_id, estado_arca="no_aplica",
        )
        db.add(venta)
        db.commit()
        anulacion = Anulacion(venta_id=venta.id, motivo="x", usuario_id=admin_id, estado="sin_comprobante")
        db.add(anulacion)
        db.commit()

    # No se llama emitir_nota_credito para una anulación "sin_comprobante"
    # (ver app/routers/ventas.py: solo se dispara si necesita_nota_credito).
    assert llamado["veces"] == 0


# ---------------------------------------------------------------- tipo de nota de crédito


def test_factura_b_genera_nota_de_credito_b(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    arca = ArcaFalsa(ultimo_autorizado=10)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: arca.consultar_ultimo_autorizado())
    monkeypatch.setattr(wsfe, "solicitar_cae", arca.solicitar_cae)

    with sesion_pruebas() as db:
        venta = _venta_facturada(admin_id, total="121.00", tipo_comprobante="6", numero=55, punto_venta=2)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)

        assert anulacion.estado == "emitida"
        assert anulacion.tipo == 8  # nota de crédito B
        assert arca.ultimo_tipo_pedido == 8
        assert anulacion.cae == "CAE-NC-11"


def test_factura_c_genera_nota_de_credito_c(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    arca = ArcaFalsa(ultimo_autorizado=20)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: arca.consultar_ultimo_autorizado())
    monkeypatch.setattr(wsfe, "solicitar_cae", arca.solicitar_cae)

    with sesion_pruebas() as db:
        venta = _venta_facturada(admin_id, total="100.00", tipo_comprobante="11", numero=8)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)

        assert anulacion.estado == "emitida"
        assert anulacion.tipo == 13  # nota de crédito C


# ---------------------------------------------------------------- comprobante asociado e importes


def test_el_comprobante_asociado_apunta_a_la_factura_original(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    arca = ArcaFalsa(ultimo_autorizado=1)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: arca.consultar_ultimo_autorizado())
    monkeypatch.setattr(wsfe, "solicitar_cae", arca.solicitar_cae)

    with sesion_pruebas() as db:
        venta = _venta_facturada(admin_id, total="200.00", tipo_comprobante="11", numero=777, punto_venta=3)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)

        asociado = arca.ultimo_detalle["CbtesAsoc"]["CbteAsoc"][0]
        assert asociado == {"Tipo": 11, "PtoVta": 3, "Nro": 777}


def test_los_importes_de_la_nota_de_credito_coinciden_con_los_de_la_factura(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    arca = ArcaFalsa(ultimo_autorizado=1)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: arca.consultar_ultimo_autorizado())
    monkeypatch.setattr(wsfe, "solicitar_cae", arca.solicitar_cae)

    with sesion_pruebas() as db:
        # Factura B, 21%: neto 100.00 + IVA 21.00 = 121.00
        venta = _venta_facturada(admin_id, total="121.00", tipo_comprobante="6", numero=1)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)

        detalle = arca.ultimo_detalle
        assert Decimal(str(detalle["ImpTotal"])) == Decimal("121.00")
        assert Decimal(str(detalle["ImpNeto"])) == Decimal("100.00")
        assert Decimal(str(detalle["ImpIVA"])) == Decimal("21.00")
        assert Decimal(str(detalle["ImpNeto"])) + Decimal(str(detalle["ImpIVA"])) == Decimal(str(detalle["ImpTotal"]))


def test_factura_c_no_discrimina_iva_en_la_nota_de_credito(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    arca = ArcaFalsa(ultimo_autorizado=1)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: arca.consultar_ultimo_autorizado())
    monkeypatch.setattr(wsfe, "solicitar_cae", arca.solicitar_cae)

    with sesion_pruebas() as db:
        venta = _venta_facturada(admin_id, total="100.00", tipo_comprobante="11", numero=1)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)

        assert "Iva" not in arca.ultimo_detalle


# ---------------------------------------------------------------- numeración propia por tipo


def test_la_numeracion_de_notas_de_credito_es_independiente_de_las_facturas(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    consultas = []

    def consultar(_ticket, _pv, tipo):
        consultas.append(tipo)
        return 999  # el "último autorizado" del tipo NC, no de la factura

    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", consultar)
    monkeypatch.setattr(
        wsfe, "solicitar_cae", lambda _t, _pv, tipo, detalle: _respuesta_aprobada(detalle["CbteDesde"], "CAE-NC")
    )

    with sesion_pruebas() as db:
        venta = _venta_facturada(admin_id, tipo_comprobante="6", numero=50)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)

        assert consultas == [8]  # consultó el tipo 8 (NC B), no el 6 (factura B)
        assert anulacion.numero == 1000


# ---------------------------------------------------------------- timeout: no duplicar


def test_timeout_con_nota_de_credito_ya_autorizada_no_duplica(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: 300)

    llamadas = {"solicitar": 0}

    def falla_por_timeout(*_a, **_k):
        llamadas["solicitar"] += 1
        raise TimeoutError("se cortó la conexión")

    def encuentra_la_nota_de_credito(_ticket, _pv, tipo, numero):
        assert tipo == 8
        assert numero == 301
        return {"Resultado": "A", "CAE": "CAE-301", "CAEFchVto": "20261231", "CbteFch": "20260101"}

    monkeypatch.setattr(wsfe, "solicitar_cae", falla_por_timeout)
    monkeypatch.setattr(wsfe, "consultar_comprobante", encuentra_la_nota_de_credito)

    with sesion_pruebas() as db:
        venta = _venta_facturada(admin_id, tipo_comprobante="6", numero=1)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)

        assert anulacion.estado == "emitida"
        assert anulacion.numero == 301
        assert anulacion.cae == "CAE-301"
    assert llamadas["solicitar"] == 1  # nunca se volvió a pedir la nota de crédito


def test_timeout_sin_nota_de_credito_todavia_queda_pendiente(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: 400)
    monkeypatch.setattr(wsfe, "solicitar_cae", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("timeout")))
    monkeypatch.setattr(wsfe, "consultar_comprobante", lambda *a, **k: None)

    with sesion_pruebas() as db:
        venta = _venta_facturada(admin_id, tipo_comprobante="6", numero=1)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)

        assert anulacion.estado == "pendiente"  # sigue igual, se reintenta en el próximo ciclo
        assert anulacion.numero is None


# ---------------------------------------------------------------- rechazo


def test_rechazo_deja_la_anulacion_en_fallo_con_el_motivo(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: 5)

    def solicitar_rechazado(_ticket, _pv, _tipo, _detalle):
        return {
            "FeDetResp": {
                "FECAEDetResponse": [
                    {
                        "Resultado": "R",
                        "Observaciones": {"Obs": [{"Code": 500, "Msg": "Comprobante asociado inexistente."}]},
                    }
                ]
            }
        }

    monkeypatch.setattr(wsfe, "solicitar_cae", solicitar_rechazado)

    with sesion_pruebas() as db:
        venta = _venta_facturada(admin_id, tipo_comprobante="11", numero=1)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)

        assert anulacion.estado == "fallo"
        assert anulacion.numero is None
        assert anulacion.cae is None
        assert "500" in anulacion.error_detalle
        assert anulacion.respuesta_fiscal is not None


# ---------------------------------------------------------------- sin certificado


def test_sin_certificado_la_anulacion_queda_pendiente_sin_romper(sesion_pruebas, monkeypatch, admin_id):
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: False)

    with sesion_pruebas() as db:
        venta = _venta_facturada(admin_id, tipo_comprobante="6", numero=1)
        db.add(venta)
        db.commit()
        anulacion = _anulacion(venta.id, admin_id)
        db.add(anulacion)
        db.commit()

        emitir_nota_credito(db, venta, anulacion)  # no debe lanzar

        assert anulacion.estado == "pendiente"
