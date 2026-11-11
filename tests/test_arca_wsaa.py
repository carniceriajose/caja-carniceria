from datetime import datetime, timedelta, timezone

from zeep.exceptions import Fault

from app.arca import wsaa
from app.models import TicketAcceso

RESPUESTA_LOGIN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<loginTicketResponse version="1.0">
  <header>
    <source>C=AR,O=AFIP,CN=wsaahomo</source>
    <destination>CN=prueba</destination>
    <uniqueId>123456789</uniqueId>
    <generationTime>2026-01-01T00:00:00-03:00</generationTime>
    <expirationTime>2099-01-01T12:00:00-03:00</expirationTime>
  </header>
  <credentials>
    <token>tok-nuevo</token>
    <sign>sig-nuevo</sign>
  </credentials>
</loginTicketResponse>"""


def _preparar_login_falso(monkeypatch, xml=RESPUESTA_LOGIN_XML, excepcion=None):
    """Evita tocar archivos de certificado reales o la red: firma y transporte simulados."""
    monkeypatch.setattr(wsaa, "_cargar_certificado_y_clave", lambda: ("cert-falso", "clave-falsa"))
    monkeypatch.setattr(wsaa, "_firmar_tra", lambda tra, cert, clave: "cms-falso-en-base64")

    def _pedir(_cms):
        if excepcion is not None:
            raise excepcion
        return xml

    monkeypatch.setattr(wsaa, "_pedir_login_cms", _pedir)


def test_se_reutiliza_el_ticket_si_falta_mas_de_diez_minutos(sesion_pruebas, monkeypatch):
    # Si hiciera falta pedir uno nuevo, esto haría fallar el test.
    monkeypatch.setattr(wsaa, "_pedir_login_cms", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no debería llamarse")))

    with sesion_pruebas() as db:
        db.add(
            TicketAcceso(
                servicio="wsfe",
                entorno="homologacion",
                cuit="20000000001",
                token="tok-vigente",
                sign="sig-vigente",
                vence_en=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        db.commit()

        info = wsaa.obtener_o_renovar_ticket(db)

        assert info.token == "tok-vigente"
        assert info.sign == "sig-vigente"


def test_se_renueva_si_falta_menos_de_diez_minutos(sesion_pruebas, monkeypatch):
    _preparar_login_falso(monkeypatch)

    with sesion_pruebas() as db:
        db.add(
            TicketAcceso(
                servicio="wsfe",
                entorno="homologacion",
                cuit="20000000001",
                token="tok-viejo",
                sign="sig-viejo",
                vence_en=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        db.commit()

        info = wsaa.obtener_o_renovar_ticket(db)

        assert info.token == "tok-nuevo"
        assert info.sign == "sig-nuevo"

        fila = db.query(TicketAcceso).filter_by(servicio="wsfe").one()
        assert fila.token == "tok-nuevo"
        assert fila.sign == "sig-nuevo"


def test_se_pide_uno_nuevo_si_no_hay_ninguno_guardado(sesion_pruebas, monkeypatch):
    _preparar_login_falso(monkeypatch)

    with sesion_pruebas() as db:
        info = wsaa.obtener_o_renovar_ticket(db)

        assert info.token == "tok-nuevo"
        assert db.query(TicketAcceso).count() == 1


def test_sin_certificado_no_pide_nada_y_devuelve_none(sesion_pruebas, monkeypatch):
    monkeypatch.setattr(wsaa, "_cargar_certificado_y_clave", lambda: (None, None))

    with sesion_pruebas() as db:
        assert wsaa.obtener_o_renovar_ticket(db) is None
        assert db.query(TicketAcceso).count() == 0


def test_si_arca_dice_que_ya_hay_un_ticket_valido_no_reintenta_y_devuelve_none(sesion_pruebas, monkeypatch):
    _preparar_login_falso(
        monkeypatch, excepcion=Fault("El CEE ya posee un TA valido para el acceso al WSN solicitado")
    )

    with sesion_pruebas() as db:
        # Una sola llamada, sin loop: si esto no lanzara y devolviera None, el
        # llamador (emitir_factura) simplemente deja la venta para el próximo ciclo.
        resultado = wsaa.obtener_o_renovar_ticket(db)

        assert resultado is None
        assert db.query(TicketAcceso).count() == 0


def test_otro_tipo_de_falla_de_arca_tambien_devuelve_none_sin_lanzar(sesion_pruebas, monkeypatch):
    _preparar_login_falso(monkeypatch, excepcion=Fault("Certificado revocado"))

    with sesion_pruebas() as db:
        assert wsaa.obtener_o_renovar_ticket(db) is None
