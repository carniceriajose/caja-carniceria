import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.arca import wsaa, wsfe
from app.arca.servicio import armar_detalle, calcular_neto_iva, emitir_factura
from app.models import Venta

TICKET_FALSO = wsaa.TicketInfo(
    token="token-de-prueba", sign="sign-de-prueba", vence_en=datetime.now(timezone.utc) + timedelta(hours=1)
)


def _preparar_arca_basica(monkeypatch):
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: True)
    monkeypatch.setattr(wsaa, "obtener_o_renovar_ticket", lambda db: TICKET_FALSO)


def _venta_nueva(vendedor_id, total="100.00", medio_pago="tarjeta"):
    return Venta(
        id_cliente=uuid.uuid4(),
        subtotal=Decimal(total),
        total=Decimal(total),
        medio_pago=medio_pago,
        vendedor_id=vendedor_id,
        estado_arca="pendiente",
    )


def _respuesta_aprobada(numero, cae="CAE-1"):
    return {
        "FeCabResp": {"Resultado": "A"},
        "FeDetResp": {
            "FECAEDetResponse": [
                {"Resultado": "A", "CAE": cae, "CAEFchVto": "20261231", "CbteDesde": numero}
            ]
        },
    }


class ArcaFalsa:
    """Simula el servidor de ARCA: cada solicitar_cae avanza el último autorizado."""

    def __init__(self, ultimo_autorizado):
        self.ultimo_autorizado = ultimo_autorizado
        self.llamadas_solicitar = 0
        self._candado = threading.Lock()

    def consultar_ultimo_autorizado(self, *_args, **_kwargs):
        valor = self.ultimo_autorizado
        time.sleep(0.05)  # agranda la ventana de la carrera si el código no la bloquea
        return valor

    def solicitar_cae(self, _ticket, _pv, _tipo, detalle):
        with self._candado:
            self.llamadas_solicitar += 1
            numero = detalle["CbteDesde"]
            self.ultimo_autorizado = numero
            return _respuesta_aprobada(numero, cae=f"CAE-{numero}")


# ---------------------------------------------------------------- cálculo de neto e IVA


def test_factura_c_no_discrimina_iva():
    neto, iva = calcular_neto_iva(Decimal("1000.00"), 11, Decimal("21"))
    assert neto == Decimal("1000.00")
    assert iva == Decimal("0.00")


def test_factura_b_con_21_por_ciento():
    neto, iva = calcular_neto_iva(Decimal("121.00"), 6, Decimal("21"))
    assert neto == Decimal("100.00")
    assert iva == Decimal("21.00")


@pytest.mark.parametrize("total", ["100.00", "133.33", "999.99", "10.01", "1.00", "0.33", "7654.32"])
def test_factura_b_siempre_suma_exacto_el_total(total):
    total_dec = Decimal(total)
    neto, iva = calcular_neto_iva(total_dec, 6, Decimal("10.5"))
    assert neto + iva == total_dec
    assert neto == neto.quantize(Decimal("0.01"))
    assert iva == iva.quantize(Decimal("0.01"))


def test_la_plata_siempre_es_decimal_nunca_float():
    neto, iva = calcular_neto_iva(Decimal("100.00"), 6, Decimal("10.5"))
    assert isinstance(neto, Decimal)
    assert isinstance(iva, Decimal)


# ---------------------------------------------------------------- Id de alícuota de ARCA (rubros)


def test_armar_detalle_usa_el_id_de_alicuota_de_carne_10_5():
    neto, iva = calcular_neto_iva(Decimal("110.50"), 6, Decimal("10.5"))
    detalle = armar_detalle(1, "20260101", Decimal("110.50"), neto, iva, 6, Decimal("10.5"))
    assert detalle["Iva"]["AlicIva"][0]["Id"] == 4


def test_armar_detalle_usa_el_id_de_alicuota_de_embutidos_21():
    neto, iva = calcular_neto_iva(Decimal("121.00"), 6, Decimal("21"))
    detalle = armar_detalle(1, "20260101", Decimal("121.00"), neto, iva, 6, Decimal("21"))
    assert detalle["Iva"]["AlicIva"][0]["Id"] == 5


def test_armar_detalle_sin_id_de_alicuota_valido_lanza_error():
    with pytest.raises(ValueError):
        armar_detalle(1, "20260101", Decimal("100.00"), Decimal("100.00"), Decimal("0.00"), 6, Decimal("15"))


# ---------------------------------------------------------------- numeración y bloqueo


def test_numeracion_correlativa(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    arca = ArcaFalsa(ultimo_autorizado=50)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: arca.consultar_ultimo_autorizado())
    monkeypatch.setattr(wsfe, "solicitar_cae", arca.solicitar_cae)

    numeros = []
    with sesion_pruebas() as db:
        for _ in range(3):
            venta = _venta_nueva(admin_id)
            db.add(venta)
            db.commit()
            emitir_factura(db, venta)
            numeros.append(venta.numero_comprobante)

    assert numeros == [51, 52, 53]


def test_dos_emisiones_simultaneas_no_repiten_numero(tmp_path, monkeypatch, admin_id):
    # Con SQLite en memoria las dos sesiones de prueba comparten una única
    # conexión (StaticPool): dos hilos usándola a la vez son una carrera del
    # motor de pruebas, no del código. Un archivo real le da a cada hilo su
    # propia conexión, como pasaría con PostgreSQL en producción.
    from sqlalchemy.orm import sessionmaker

    from app.db import crear_motor
    from app.models import Base, Usuario

    motor = crear_motor(f"sqlite:///{tmp_path / 'concurrencia.db'}")
    Base.metadata.create_all(motor)
    Sesion = sessionmaker(bind=motor)

    _preparar_arca_basica(monkeypatch)
    arca = ArcaFalsa(ultimo_autorizado=500)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: arca.consultar_ultimo_autorizado())
    monkeypatch.setattr(wsfe, "solicitar_cae", arca.solicitar_cae)

    with Sesion() as db:
        vendedor = Usuario(nombre="Admin", usuario="admin-conc", password_hash="x", rol="admin")
        db.add(vendedor)
        db.commit()
        venta1, venta2 = _venta_nueva(vendedor.id, "100"), _venta_nueva(vendedor.id, "200")
        db.add_all([venta1, venta2])
        db.commit()
        id1, id2 = venta1.id, venta2.id

    resultados = {}

    def _correr(venta_id):
        with Sesion() as db:
            venta = db.get(Venta, venta_id)
            emitir_factura(db, venta)
            resultados[venta_id] = venta.numero_comprobante

    hilo1 = threading.Thread(target=_correr, args=(id1,))
    hilo2 = threading.Thread(target=_correr, args=(id2,))
    hilo1.start()
    hilo2.start()
    hilo1.join()
    hilo2.join()

    motor.dispose()

    assert None not in resultados.values()
    assert resultados[id1] != resultados[id2]
    assert sorted(resultados.values()) == [501, 502]
    assert arca.llamadas_solicitar == 2


# ---------------------------------------------------------------- timeouts


def test_timeout_con_comprobante_ya_autorizado_no_duplica(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: 700)

    llamadas = {"solicitar": 0}

    def falla_por_timeout(*_a, **_k):
        llamadas["solicitar"] += 1
        raise TimeoutError("se cortó la conexión")

    def encuentra_el_comprobante(_ticket, _pv, _tipo, numero):
        assert numero == 701
        return {"Resultado": "A", "CAE": "CAE-701", "CAEFchVto": "20261231", "CbteFch": "20260101"}

    monkeypatch.setattr(wsfe, "solicitar_cae", falla_por_timeout)
    monkeypatch.setattr(wsfe, "consultar_comprobante", encuentra_el_comprobante)

    with sesion_pruebas() as db:
        venta = _venta_nueva(admin_id)
        db.add(venta)
        db.commit()
        emitir_factura(db, venta)

        assert venta.estado_arca == "facturada"
        assert venta.numero_comprobante == 701
        assert venta.cae == "CAE-701"
    assert llamadas["solicitar"] == 1  # nunca se volvió a pedir el CAE


def test_timeout_sin_comprobante_queda_pendiente_y_el_reintento_luego_funciona(
    sesion_pruebas, monkeypatch, admin_id
):
    _preparar_arca_basica(monkeypatch)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: 800)
    monkeypatch.setattr(wsfe, "solicitar_cae", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("timeout")))
    monkeypatch.setattr(wsfe, "consultar_comprobante", lambda *a, **k: None)

    with sesion_pruebas() as db:
        venta = _venta_nueva(admin_id)
        db.add(venta)
        db.commit()
        venta_id = venta.id
        emitir_factura(db, venta)

        assert venta.estado_arca == "pendiente"  # no cambió: queda para el próximo ciclo
        assert venta.numero_comprobante is None
        assert venta.cae is None

    # ARCA ya está respondiendo: el reintento (simulado con otra llamada) tiene que funcionar.
    monkeypatch.setattr(
        wsfe,
        "solicitar_cae",
        lambda _t, _pv, _tipo, detalle: _respuesta_aprobada(detalle["CbteDesde"], cae="CAE-801"),
    )
    with sesion_pruebas() as db:
        venta = db.get(Venta, venta_id)
        emitir_factura(db, venta)

        assert venta.estado_arca == "facturada"
        assert venta.numero_comprobante == 801
        assert venta.cae == "CAE-801"


# ---------------------------------------------------------------- rechazo


def test_rechazo_deja_fallo_con_el_motivo(sesion_pruebas, monkeypatch, admin_id):
    _preparar_arca_basica(monkeypatch)
    monkeypatch.setattr(wsfe, "consultar_ultimo_autorizado", lambda *a, **k: 900)

    def solicitar_rechazado(_ticket, _pv, _tipo, _detalle):
        return {
            "FeDetResp": {
                "FECAEDetResponse": [
                    {
                        "Resultado": "R",
                        "Observaciones": {"Obs": [{"Code": 10016, "Msg": "Fecha de comprobante atrasada."}]},
                    }
                ]
            }
        }

    monkeypatch.setattr(wsfe, "solicitar_cae", solicitar_rechazado)

    with sesion_pruebas() as db:
        venta = _venta_nueva(admin_id)
        db.add(venta)
        db.commit()
        emitir_factura(db, venta)

        assert venta.estado_arca == "fallo"
        assert venta.numero_comprobante is None
        assert venta.cae is None
        assert "10016" in venta.error_detalle
        assert "Fecha de comprobante atrasada" in venta.error_detalle
        assert venta.respuesta_fiscal is not None


def test_sin_certificado_la_venta_queda_pendiente_sin_romper(sesion_pruebas, monkeypatch, admin_id):
    monkeypatch.setattr(wsaa, "hay_certificado_configurado", lambda: False)

    with sesion_pruebas() as db:
        venta = _venta_nueva(admin_id)
        db.add(venta)
        db.commit()
        emitir_factura(db, venta)  # no debe lanzar

        assert venta.estado_arca == "pendiente"
