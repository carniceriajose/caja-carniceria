from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auditoria import registrar as registrar_auditoria
from app.db import get_db
from app.deps import get_usuario_actual, requerir_admin
from app.models import Rubro, Usuario
from app.rubros import obtener_rubro_predeterminado
from app.schemas import RubroCrear, RubroEditar, RubroOut

router = APIRouter(prefix="/rubros", tags=["rubros"])


def _buscar(db: Session, rubro_id: int) -> Rubro:
    rubro = db.get(Rubro, rubro_id)
    if rubro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubro no encontrado.")
    return rubro


def _quitar_predeterminado_actual(db: Session, excepto_id: int | None = None) -> None:
    """Deja sin predeterminado al que lo tenga hoy (si no es excepto_id), para
    que el próximo flush no choque con el índice único parcial de la base."""
    actual = obtener_rubro_predeterminado(db)
    if actual is not None and actual.id != excepto_id:
        actual.es_predeterminado = False
        db.flush()


@router.get("", response_model=list[RubroOut])
def listar_rubros(usuario: Usuario = Depends(get_usuario_actual), db: Session = Depends(get_db)):
    """Al vendedor (pantalla de venta) solo le llegan los activos: un rubro
    desactivado no se puede volver a elegir. El admin ve todos, para poder
    reactivarlos desde Configuración."""
    condiciones = [] if usuario.rol == "admin" else [Rubro.activo.is_(True)]
    return db.scalars(select(Rubro).where(*condiciones).order_by(Rubro.orden)).all()


@router.post(
    "", response_model=RubroOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(requerir_admin)]
)
def crear_rubro(datos: RubroCrear, admin: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)):
    if datos.es_predeterminado and not datos.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="El rubro predeterminado tiene que estar activo."
        )
    # Primero se le saca el predeterminado al que lo tenga (si corresponde):
    # así, cuando se inserte este, el índice único parcial nunca ve dos a la vez.
    if datos.es_predeterminado:
        _quitar_predeterminado_actual(db)

    rubro = Rubro(**datos.model_dump())
    db.add(rubro)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe un rubro con ese nombre."
        ) from None
    registrar_auditoria(
        db,
        admin,
        "rubro.crear",
        {
            "rubro_id": rubro.id,
            "nombre": rubro.nombre,
            "alicuota": str(rubro.alicuota),
            "es_predeterminado": rubro.es_predeterminado,
        },
        entidad="rubro",
        entidad_id=rubro.id,
    )
    db.commit()
    db.refresh(rubro)
    return rubro


@router.put("/{rubro_id}", response_model=RubroOut, dependencies=[Depends(requerir_admin)])
def actualizar_rubro(
    rubro_id: int,
    datos: RubroEditar,
    admin: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
):
    rubro = _buscar(db, rubro_id)

    if rubro.es_predeterminado and not datos.es_predeterminado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tiene que haber un rubro predeterminado: elegí otro antes de sacarle este a este.",
        )
    if datos.es_predeterminado and not datos.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="El rubro predeterminado tiene que estar activo."
        )
    if not datos.activo and rubro.activo:
        activos_restantes = db.scalar(
            select(func.count()).select_from(Rubro).where(Rubro.activo.is_(True), Rubro.id != rubro_id)
        )
        if not activos_restantes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Tiene que quedar al menos un rubro activo."
            )

    anterior = {
        "nombre": rubro.nombre,
        "alicuota": str(rubro.alicuota),
        "descripcion_factura": rubro.descripcion_factura,
        "activo": rubro.activo,
        "orden": rubro.orden,
        "es_predeterminado": rubro.es_predeterminado,
    }
    rubro.nombre = datos.nombre
    rubro.alicuota = datos.alicuota
    rubro.descripcion_factura = datos.descripcion_factura
    rubro.activo = datos.activo
    rubro.orden = datos.orden
    if datos.es_predeterminado and not rubro.es_predeterminado:
        _quitar_predeterminado_actual(db, excepto_id=rubro.id)
    rubro.es_predeterminado = datos.es_predeterminado
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe un rubro con ese nombre."
        ) from None
    registrar_auditoria(
        db,
        admin,
        "rubro.actualizar",
        {
            "rubro_id": rubro.id,
            "antes": anterior,
            "despues": {
                "nombre": rubro.nombre,
                "alicuota": str(rubro.alicuota),
                "descripcion_factura": rubro.descripcion_factura,
                "activo": rubro.activo,
                "orden": rubro.orden,
                "es_predeterminado": rubro.es_predeterminado,
            },
        },
        entidad="rubro",
        entidad_id=rubro.id,
    )
    db.commit()
    db.refresh(rubro)
    return rubro
