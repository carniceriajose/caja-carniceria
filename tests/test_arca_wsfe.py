from requests.adapters import HTTPAdapter

from app.arca.wsfe import _AdaptadorCompatibleConArca, _sesion_http


def test_el_adaptador_de_arca_mantiene_la_verificacion_del_certificado():
    """El servidor de WSFEv1 de producción negocia TLS con una clave
    Diffie-Hellman débil que OpenSSL moderno rechaza por default; el
    adaptador baja el nivel de seguridad del cifrado para permitir la
    conexión, pero nunca tiene que desactivar la verificación del
    certificado del servidor."""
    adaptador = _AdaptadorCompatibleConArca()
    contexto = adaptador.poolmanager.connection_pool_kw["ssl_context"]

    assert contexto.verify_mode.name == "CERT_REQUIRED"
    assert contexto.check_hostname is True


def test_produccion_usa_el_adaptador_compatible_con_el_dh_debil():
    sesion = _sesion_http("produccion")
    assert isinstance(sesion.get_adapter("https://servicios1.afip.gov.ar/"), _AdaptadorCompatibleConArca)


def test_homologacion_mantiene_el_tls_normal_sin_tocarlo():
    sesion = _sesion_http("homologacion")
    adaptador = sesion.get_adapter("https://wswhomo.afip.gov.ar/")
    assert type(adaptador) is HTTPAdapter
