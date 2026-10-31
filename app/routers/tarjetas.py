from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auditoria import registrar as registrar_auditoria
from app.db import get_db
from app.deps import get_usuario_actual, requerir_admin
from app.models import Tarjeta, Usuario
from app.schemas import TarjetaCrear, TarjetaEditar, TarjetaOut

router = APIRouter(prefix="/tarjetas", tags=["tarjetas"])


def _buscar(db: Session, tarjeta_id: int) -> Tarjeta:
    tarjeta = db.get(Tarjeta, tarjeta_id)
    if tarjeta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarjeta no encontrada.")
    return tarjeta


@router.get("", response_model=list[TarjetaOut])
def listar_tarjetas(usuario: Usuario = Depends(get_usuario_actual), db: Session = Depends(get_db)):
    """Al vendedor (pantalla de venta) solo le llegan las activas: una tarjeta
    desactivada no se puede volver a elegir. El admin ve todas, para poder
    reactivarlas desde Configuración."""
    condiciones = [] if usuario.rol == "admin" else [Tarjeta.activa.is_(True)]
    return db.scalars(select(Tarjeta).where(*condiciones).order_by(Tarjeta.orden)).all()


@router.post(
    "", response_model=TarjetaOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(requerir_admin)]
)
def crear_tarjeta(datos: TarjetaCrear, admin: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)):
    tarjeta = Tarjeta(**datos.model_dump())
    db.add(tarjeta)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe una tarjeta con ese nombre."
        ) from None
    registrar_auditoria(
        db,
        admin,
        "tarjeta.crear",
        {
            "tarjeta_id": tarjeta.id,
            "nombre": tarjeta.nombre,
            "tipo": tarjeta.tipo,
            "recargo_porcentaje": str(tarjeta.recargo_porcentaje),
        },
        entidad="tarjeta",
        entidad_id=tarjeta.id,
    )
    db.commit()
    return tarjeta


@router.put("/{tarjeta_id}", response_model=TarjetaOut, dependencies=[Depends(requerir_admin)])
def actualizar_tarjeta(
    tarjeta_id: int,
    datos: TarjetaEditar,
    admin: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
):
    tarjeta = _buscar(db, tarjeta_id)
    anterior = {
        "nombre": tarjeta.nombre,
        "tipo": tarjeta.tipo,
        "recargo_porcentaje": str(tarjeta.recargo_porcentaje),
        "activa": tarjeta.activa,
        "orden": tarjeta.orden,
    }
    tarjeta.nombre = datos.nombre
    tarjeta.tipo = datos.tipo
    tarjeta.recargo_porcentaje = datos.recargo_porcentaje
    tarjeta.activa = datos.activa
    tarjeta.orden = datos.orden
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe una tarjeta con ese nombre."
        ) from None
    registrar_auditoria(
        db,
        admin,
        "tarjeta.actualizar",
        {
            "tarjeta_id": tarjeta.id,
            "antes": anterior,
            "despues": {
                "nombre": tarjeta.nombre,
                "tipo": tarjeta.tipo,
                "recargo_porcentaje": str(tarjeta.recargo_porcentaje),
                "activa": tarjeta.activa,
                "orden": tarjeta.orden,
            },
        },
        entidad="tarjeta",
        entidad_id=tarjeta.id,
    )
    db.commit()
    db.refresh(tarjeta)
    return tarjeta
