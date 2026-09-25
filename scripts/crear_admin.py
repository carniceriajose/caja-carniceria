"""Crea un usuario administrador por consola.

Uso (desde la carpeta del proyecto, con el entorno virtual activado):
    python -m scripts.crear_admin
"""

import sys
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import SesionLocal, motor
from app.models import Base, Usuario
from app.schemas import UsuarioCrear, mensaje_error
from app.security import hashear_password


def main() -> int:
    if not get_settings().es_produccion:
        Base.metadata.create_all(motor)

    nombre = input("Nombre completo: ")
    usuario = input("Usuario (con el que va a iniciar sesión): ")
    password = getpass("Contraseña (mínimo 8 caracteres): ")
    if password != getpass("Repetir contraseña: "):
        print("Las contraseñas no coinciden.")
        return 1

    try:
        datos = UsuarioCrear(nombre=nombre, usuario=usuario, password=password, rol="admin")
    except ValidationError as error:
        for e in error.errors():
            print(f"- {e['loc'][0]}: {mensaje_error(e)}")
        return 1

    with SesionLocal() as db:
        db.add(
            Usuario(
                nombre=datos.nombre,
                usuario=datos.usuario,
                password_hash=hashear_password(datos.password),
                rol="admin",
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            print(f"Ya existe un usuario llamado '{datos.usuario}'.")
            return 1

    print(f"Administrador '{datos.usuario}' creado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
