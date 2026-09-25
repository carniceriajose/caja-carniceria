from datetime import date, datetime
from decimal import Decimal

from zeep.helpers import serialize_object


def a_json_seguro(valor):
    """Convierte una respuesta de zeep (o un doble de prueba con dicts planos)
    en algo que el tipo JSON/JSONB de la base pueda guardar tal cual: sin
    Decimal ni datetime, solo dict/list/str/int/float/bool/None."""
    convertido = serialize_object(valor, dict)
    return _limpiar(convertido)


def _limpiar(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {clave: _limpiar(v) for clave, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_limpiar(v) for v in valor]
    return valor
