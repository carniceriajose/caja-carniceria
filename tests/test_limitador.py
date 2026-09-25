from app.security import (
    MAX_INTENTOS_IP,
    MAX_INTENTOS_USUARIO,
    VENTANA_SEGUNDOS,
    LimitadorIntentos,
)


class RelojFalso:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora


def _fallos(limitador, cantidad, usuario="ana", ip="1.1.1.1"):
    for _ in range(cantidad):
        limitador.registrar_fallo(usuario, ip)


def test_los_limites_por_defecto():
    assert MAX_INTENTOS_USUARIO == 5
    assert MAX_INTENTOS_IP == 20
    assert VENTANA_SEGUNDOS == 15 * 60


def test_el_usuario_se_bloquea_al_quinto_fallo_por_quince_minutos():
    reloj = RelojFalso()
    limitador = LimitadorIntentos(reloj=reloj)

    for _ in range(4):
        _fallos(limitador, 1)
        assert limitador.segundos_de_bloqueo("ana", "1.1.1.1") == 0
    _fallos(limitador, 1)

    assert limitador.segundos_de_bloqueo("ana", "9.9.9.9") == 15 * 60  # otra IP: igual bloqueado
    reloj.ahora += 15 * 60 - 1
    assert limitador.segundos_de_bloqueo("ana", "9.9.9.9") == 1
    reloj.ahora += 1
    assert limitador.segundos_de_bloqueo("ana", "9.9.9.9") == 0


def test_la_ip_se_bloquea_recien_al_fallo_numero_veinte():
    limitador = LimitadorIntentos(reloj=RelojFalso())

    for i in range(19):
        limitador.registrar_fallo(f"usuario{i}", "1.1.1.1")
    assert limitador.segundos_de_bloqueo("otro", "1.1.1.1") == 0

    limitador.registrar_fallo("usuario19", "1.1.1.1")
    assert limitador.segundos_de_bloqueo("otro", "1.1.1.1") == 15 * 60
    assert limitador.segundos_de_bloqueo("otro", "2.2.2.2") == 0


def test_cinco_fallos_de_usuarios_distintos_no_bloquean_a_nadie():
    limitador = LimitadorIntentos(reloj=RelojFalso())
    for i in range(5):
        limitador.registrar_fallo(f"usuario{i}", "1.1.1.1")

    assert limitador.segundos_de_bloqueo("otro", "1.1.1.1") == 0


def test_los_fallos_viejos_no_cuentan():
    reloj = RelojFalso()
    limitador = LimitadorIntentos(reloj=reloj)

    _fallos(limitador, 4)
    reloj.ahora += VENTANA_SEGUNDOS
    _fallos(limitador, 1)

    assert limitador.segundos_de_bloqueo("ana", "1.1.1.1") == 0


def test_los_usuarios_son_independientes():
    limitador = LimitadorIntentos(reloj=RelojFalso())
    _fallos(limitador, 5, usuario="ana", ip="1.1.1.1")

    assert limitador.segundos_de_bloqueo("ana", "2.2.2.2") > 0
    assert limitador.segundos_de_bloqueo("beto", "2.2.2.2") == 0


def test_limpiar_usuario_reinicia_al_usuario_pero_no_a_la_ip():
    limitador = LimitadorIntentos(reloj=RelojFalso())
    _fallos(limitador, 4, usuario="ana", ip="1.1.1.1")
    limitador.limpiar_usuario("ana")

    # el usuario arranca de cero: 4 fallos más no lo bloquean
    _fallos(limitador, 4, usuario="ana", ip="1.1.1.1")
    assert limitador.segundos_de_bloqueo("ana", "9.9.9.9") == 0

    # pero la IP siguió sumando: 8 fallos + 12 más llegan a 20
    _fallos(limitador, 12, usuario="ana2", ip="1.1.1.1")
    assert limitador.segundos_de_bloqueo("otro", "1.1.1.1") > 0


def test_limpiar_usuario_libera_a_un_usuario_bloqueado():
    limitador = LimitadorIntentos(reloj=RelojFalso())
    _fallos(limitador, 5, usuario="ana", ip="1.1.1.1")
    limitador.limpiar_usuario("ana")

    assert limitador.segundos_de_bloqueo("ana", "9.9.9.9") == 0
