"""Segundo factor (TOTP, compatible con Google Authenticator, Authy, etc.).

Solo para el rol admin. El secreto se guarda en texto plano en la base (no se
puede hashear: hace falta poder recalcular el código para verificarlo), igual
que el JWT_SECRET vive en el .env: la protección es que solo el backend accede
a la base. Nunca se loguea ni se devuelve por la API una vez activado.
"""

import pyotp

EMISOR = "Carnicería"


def generar_secreto() -> str:
    return pyotp.random_base32()


def url_de_aprovisionamiento(secreto: str, usuario: str) -> str:
    """Lo que se convierte en el código QR que escanea la app autenticadora."""
    return pyotp.TOTP(secreto).provisioning_uri(name=usuario, issuer_name=EMISOR)


def verificar_codigo(secreto: str, codigo: str) -> bool:
    codigo = (codigo or "").strip()
    if not codigo.isdigit():
        return False
    # valid_window=1: tolera que el reloj del celular esté hasta 30s desincronizado.
    return pyotp.TOTP(secreto).verify(codigo, valid_window=1)
