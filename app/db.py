from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _activar_claves_foraneas(conexion, _registro) -> None:
    cursor = conexion.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def crear_motor(url: str, **opciones) -> Engine:
    if url.startswith("sqlite"):
        opciones.setdefault("connect_args", {"check_same_thread": False})
        motor = create_engine(url, **opciones)
        event.listen(motor, "connect", _activar_claves_foraneas)
        return motor
    opciones.setdefault("pool_pre_ping", True)
    # Sin sentencias preparadas: el pooler de Supabase en modo transacción no las soporta.
    opciones.setdefault("connect_args", {"prepare_threshold": None})
    # Si una consulta falla, SQLAlchemy por default muestra los parámetros en
    # el mensaje de error (quedarían en los logs) — acá puede haber tokens,
    # signs o contraseñas hasheadas, así que se ocultan siempre.
    opciones.setdefault("hide_parameters", True)
    return create_engine(url, **opciones)


motor = crear_motor(get_settings().database_url)
SesionLocal = sessionmaker(bind=motor, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SesionLocal() as sesion:
        yield sesion
