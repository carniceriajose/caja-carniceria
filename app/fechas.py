from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import Date
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement

NOMBRE_ZONA = "America/Argentina/Buenos_Aires"
ZONA = ZoneInfo(NOMBRE_ZONA)

# Argentina no tiene horario de verano: siempre es UTC-3. SQLite (solo desarrollo y
# tests) no conoce zonas horarias, así que se resta ese desfase a mano.
DESFASE_SQLITE = "-3 hours"


def hoy_argentina() -> date:
    return datetime.now(ZONA).date()


def _a_utc(dia: date) -> datetime | None:
    try:
        return datetime.combine(dia, time.min, tzinfo=ZONA).astimezone(timezone.utc)
    except OverflowError:
        return None


def rango_utc(desde: date | None, hasta: date | None) -> tuple[datetime | None, datetime | None]:
    """Convierte fechas argentinas inclusivas en un rango [inicio, fin) en UTC.

    Una venta a las 22:00 del lunes en Argentina es del lunes aunque en UTC ya sea martes.
    None significa sin límite de ese lado.
    """
    inicio = _a_utc(desde) if desde else None
    fin = _a_utc(hasta + timedelta(days=1)) if hasta and hasta < date.max else None
    return inicio, fin


class dia_local(FunctionElement):
    """Día (hora de Argentina) de una columna con fecha y hora en UTC."""

    type = Date()
    name = "dia_local"
    inherit_cache = True


class mes_local(FunctionElement):
    """Primer día del mes (hora de Argentina) de una columna con fecha y hora en UTC."""

    type = Date()
    name = "mes_local"
    inherit_cache = True


@compiles(dia_local, "postgresql")
def _dia_local_postgres(elemento, compilador, **kw):
    columna = compilador.process(elemento.clauses, **kw)
    return f"CAST(({columna}) AT TIME ZONE '{NOMBRE_ZONA}' AS DATE)"


@compiles(mes_local, "postgresql")
def _mes_local_postgres(elemento, compilador, **kw):
    columna = compilador.process(elemento.clauses, **kw)
    return f"CAST(date_trunc('month', ({columna}) AT TIME ZONE '{NOMBRE_ZONA}') AS DATE)"


@compiles(dia_local, "sqlite")
def _dia_local_sqlite(elemento, compilador, **kw):
    columna = compilador.process(elemento.clauses, **kw)
    return f"date({columna}, '{DESFASE_SQLITE}')"


@compiles(mes_local, "sqlite")
def _mes_local_sqlite(elemento, compilador, **kw):
    columna = compilador.process(elemento.clauses, **kw)
    return f"date({columna}, '{DESFASE_SQLITE}', 'start of month')"
