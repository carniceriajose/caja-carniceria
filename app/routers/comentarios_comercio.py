from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auditoria import registrar as registrar_auditoria
from app.db import get_db
from app.deps import requerir_admin
from app.models import ComentarioComercio, Usuario
from app.schemas import ComentarioComercioCrear, ComentarioComercioOut

router = APIRouter(
    prefix="/comentarios-comercio", tags=["comentarios-comercio"], dependencies=[Depends(requerir_admin)]
)


@router.get("", response_model=list[ComentarioComercioOut])
def listar_comentarios(nombre_comercio: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return db.scalars(
        select(ComentarioComercio)
        .where(func.lower(ComentarioComercio.nombre_comercio) == func.lower(nombre_comercio.strip()))
        .order_by(ComentarioComercio.creado_en.desc())
    ).all()


@router.post("", response_model=ComentarioComercioOut, status_code=status.HTTP_201_CREATED)
def crear_comentario(
    datos: ComentarioComercioCrear,
    admin: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
):
    comentario = ComentarioComercio(
        nombre_comercio=datos.nombre_comercio,
        comentario=datos.comentario,
        creado_por=admin.id,
    )
    db.add(comentario)
    db.flush()
    registrar_auditoria(
        db,
        admin,
        "comentario_comercio.crear",
        {"comentario_id": comentario.id, "nombre_comercio": comentario.nombre_comercio},
        entidad="comentario_comercio",
        entidad_id=comentario.id,
    )
    db.commit()
    return comentario


@router.delete("/{comentario_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_comentario(
    comentario_id: int, admin: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)
):
    comentario = db.get(ComentarioComercio, comentario_id)
    if comentario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comentario no encontrado.")
    registrar_auditoria(
        db,
        admin,
        "comentario_comercio.borrar",
        {"comentario_id": comentario.id, "nombre_comercio": comentario.nombre_comercio},
        entidad="comentario_comercio",
        entidad_id=comentario.id,
    )
    db.delete(comentario)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
