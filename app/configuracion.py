"""La única fila de configuración: qué se factura, los datos del comercio y
los demás parámetros que un admin puede cambiar sin tocar el servidor.

Vive acá (no en app/routers/configuracion.py) porque el resto del backend
—la emisión de facturas, los reportes— también necesita leerla."""

from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Configuracion


def _fecha_desde_texto(texto: str | None) -> date | None:
    """Convierte "dd/mm/aaaa" (el formato de ARCA_INICIO_ACTIVIDADES) a date."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _completar_desde_variables_de_entorno(configuracion: Configuracion) -> None:
    """Migración en caliente: la fila de configuración ya existía (de antes de
    esta función), pero los campos nuevos todavía no se cargaron nunca. Se
    completan una sola vez con lo que ya había en las variables de entorno,
    para no perder los datos reales que el admin ya había cargado ahí."""
    settings = get_settings()
    configuracion.razon_social = settings.arca_razon_social
    configuracion.domicilio = settings.arca_domicilio
    configuracion.condicion_iva = settings.arca_condicion_iva
    configuracion.inicio_actividades = _fecha_desde_texto(settings.arca_inicio_actividades) or date(2020, 1, 1)
    configuracion.ingresos_brutos = settings.arca_ingresos_brutos or None
    configuracion.tipo_comprobante = settings.arca_tipo_comprobante
    configuracion.punto_venta = settings.arca_punto_venta
    configuracion.anulacion_minutos_vendedor = settings.anulacion_minutos_vendedor


def obtener_configuracion(db: Session) -> Configuracion:
    """Devuelve la única fila de configuración; si falta, la crea (con los
    valores de las variables de entorno, si hay alguna todavía configurada)."""
    configuracion = db.get(Configuracion, 1)
    if configuracion is None:
        configuracion = Configuracion(id=1)
        _completar_desde_variables_de_entorno(configuracion)
        db.add(configuracion)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        configuracion = db.get(Configuracion, 1)
    elif not configuracion.razon_social:
        # La fila ya existía de antes (creada para "qué se factura" nada más):
        # es la primera vez que se lee después de agregar las columnas nuevas.
        _completar_desde_variables_de_entorno(configuracion)
        db.commit()
    return configuracion
