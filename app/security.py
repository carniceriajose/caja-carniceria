import math
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings
from app.models import Usuario

_hasher = PasswordHasher()

# Hash de relleno: se verifica cuando el usuario no existe, para que la respuesta
# tarde lo mismo que con un usuario real.
HASH_RELLENO = _hasher.hash("relleno-para-igualar-tiempos-de-respuesta")


def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(hash_guardado: str, password: str) -> bool:
    try:
        return _hasher.verify(hash_guardado, password)
    except (VerificationError, InvalidHashError):
        return False


def necesita_rehash(hash_guardado: str) -> bool:
    return _hasher.check_needs_rehash(hash_guardado)


ALGORITMO = "HS256"


def crear_token(usuario: Usuario) -> str:
    settings = get_settings()
    ahora = datetime.now(timezone.utc)
    datos = {
        "sub": str(usuario.id),
        "rol": usuario.rol,
        "ver": usuario.token_version,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.jwt_minutos),
    }
    return jwt.encode(datos, settings.jwt_secret, algorithm=ALGORITMO)


def leer_token(token: str) -> tuple[int, int]:
    """Devuelve (id_usuario, token_version). Lanza jwt.InvalidTokenError si no sirve."""
    datos = jwt.decode(
        token,
        get_settings().jwt_secret,
        algorithms=[ALGORITMO],
        options={"require": ["exp", "iat", "sub"]},
    )
    version = datos.get("ver")
    if not isinstance(version, int) or isinstance(version, bool):
        raise jwt.InvalidTokenError("Versión de token inválida")
    try:
        return int(datos["sub"]), version
    except (ValueError, TypeError):
        raise jwt.InvalidTokenError("Usuario del token inválido") from None


# Toda la carnicería sale a internet por la misma IP: el límite por IP es más alto
# que el de un usuario para que los errores de varias personas no bloqueen a todos.
MAX_INTENTOS_USUARIO = 5
MAX_INTENTOS_IP = 20
VENTANA_SEGUNDOS = 15 * 60


class _ContadorDeFallos:
    """Cuenta fallos por clave dentro de la ventana y bloquea la clave al llegar al máximo."""

    LIMITE_ENTRADAS = 10_000

    def __init__(self, max_intentos: int, ventana_segundos: int) -> None:
        self.max_intentos = max_intentos
        self.ventana_segundos = ventana_segundos
        self._fallos: dict[str, list[float]] = {}
        self._bloqueos: dict[str, float] = {}

    def segundos_de_bloqueo(self, clave: str, ahora: float) -> float:
        hasta = self._bloqueos.get(clave)
        if hasta is None:
            return 0.0
        if hasta <= ahora:
            del self._bloqueos[clave]
            return 0.0
        return hasta - ahora

    def registrar_fallo(self, clave: str, ahora: float) -> None:
        vigentes = [t for t in self._fallos.get(clave, []) if ahora - t < self.ventana_segundos]
        vigentes.append(ahora)
        if len(vigentes) >= self.max_intentos:
            self._bloqueos[clave] = ahora + self.ventana_segundos
            self._fallos.pop(clave, None)
        else:
            self._fallos[clave] = vigentes
        if len(self._fallos) + len(self._bloqueos) > self.LIMITE_ENTRADAS:
            self._podar(ahora)

    def limpiar(self, clave: str) -> None:
        self._fallos.pop(clave, None)
        self._bloqueos.pop(clave, None)

    def vaciar(self) -> None:
        self._fallos.clear()
        self._bloqueos.clear()

    def _podar(self, ahora: float) -> None:
        self._bloqueos = {c: h for c, h in self._bloqueos.items() if h > ahora}
        self._fallos = {
            c: v
            for c, v in self._fallos.items()
            if any(ahora - t < self.ventana_segundos for t in v)
        }


class LimitadorIntentos:
    """Bloquea el login por usuario y por IP tras varios fallos seguidos.

    Guarda todo en memoria: alcanza para una sola instancia del servidor.
    """

    def __init__(
        self,
        max_intentos_usuario: int = MAX_INTENTOS_USUARIO,
        max_intentos_ip: int = MAX_INTENTOS_IP,
        ventana_segundos: int = VENTANA_SEGUNDOS,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._usuarios = _ContadorDeFallos(max_intentos_usuario, ventana_segundos)
        self._ips = _ContadorDeFallos(max_intentos_ip, ventana_segundos)
        self._reloj = reloj
        self._cerrojo = threading.Lock()

    def segundos_de_bloqueo(self, usuario: str, ip: str) -> int:
        """Segundos que faltan para que se libere el bloqueo más largo (0 si no hay)."""
        with self._cerrojo:
            ahora = self._reloj()
            restante = max(
                self._usuarios.segundos_de_bloqueo(usuario, ahora),
                self._ips.segundos_de_bloqueo(ip, ahora),
            )
            return math.ceil(restante)

    def registrar_fallo(self, usuario: str, ip: str) -> None:
        with self._cerrojo:
            ahora = self._reloj()
            self._usuarios.registrar_fallo(usuario, ahora)
            self._ips.registrar_fallo(ip, ahora)

    def limpiar_usuario(self, usuario: str) -> None:
        """Un login correcto reinicia el contador del usuario, pero no el de la IP:
        si también lo hiciera, quien tenga una cuenta propia podría reiniciarlo
        entre intento e intento."""
        with self._cerrojo:
            self._usuarios.limpiar(usuario)

    def reiniciar(self) -> None:
        with self._cerrojo:
            self._usuarios.vaciar()
            self._ips.vaciar()


limitador = LimitadorIntentos()
