from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auditoria import registrar as registrar_auditoria
from app.config import get_settings
from app.configuracion import obtener_configuracion
from app.db import get_db
from app.deps import get_usuario_actual, requerir_admin
from app.models import Configuracion, Usuario
from app.schemas import ConfiguracionIn, ConfiguracionOut

router = APIRouter(prefix="/configuracion", tags=["configuracion"])


def _a_salida(configuracion: Configuracion) -> ConfiguracionOut:
    # El CUIT no vive en la tabla (ver app/models.py): se agrega acá, de la
    # misma variable de entorno que ya usa el sistema para facturar.
    campos = {campo: getattr(configuracion, campo) for campo in ConfiguracionIn.model_fields}
    return ConfiguracionOut(cuit=get_settings().arca_cuit, **campos)


@router.get("", response_model=ConfiguracionOut, dependencies=[Depends(get_usuario_actual)])
def ver_configuracion(db: Session = Depends(get_db)):
    return _a_salida(obtener_configuracion(db))


@router.put("", response_model=ConfiguracionOut)
def cambiar_configuracion(
    datos: ConfiguracionIn, admin: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)
):
    configuracion = obtener_configuracion(db)
    for campo, valor in datos.model_dump().items():
        setattr(configuracion, campo, valor)
    registrar_auditoria(
        db,
        admin,
        "configuracion.cambiar",
        datos.model_dump(mode="json"),
        entidad="configuracion",
        entidad_id=1,
    )
    db.commit()
    return _a_salida(configuracion)
