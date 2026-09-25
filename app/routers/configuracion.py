from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_usuario_actual, requerir_admin
from app.models import Configuracion
from app.schemas import ConfiguracionIn, ConfiguracionOut

router = APIRouter(prefix="/configuracion", tags=["configuracion"])


def obtener_configuracion(db: Session) -> Configuracion:
    """Devuelve la única fila de configuración; si falta, la crea con los valores por defecto."""
    configuracion = db.get(Configuracion, 1)
    if configuracion is None:
        db.add(Configuracion(id=1))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        configuracion = db.get(Configuracion, 1)
    return configuracion


@router.get("", response_model=ConfiguracionOut, dependencies=[Depends(get_usuario_actual)])
def ver_configuracion(db: Session = Depends(get_db)):
    return obtener_configuracion(db)


@router.put("", response_model=ConfiguracionOut, dependencies=[Depends(requerir_admin)])
def cambiar_configuracion(datos: ConfiguracionIn, db: Session = Depends(get_db)):
    configuracion = obtener_configuracion(db)
    configuracion.facturar_efectivo = datos.facturar_efectivo
    configuracion.facturar_tarjeta = datos.facturar_tarjeta
    configuracion.facturar_transferencia = datos.facturar_transferencia
    db.commit()
    return configuracion
