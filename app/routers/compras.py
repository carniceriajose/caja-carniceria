import base64
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auditoria import registrar as registrar_auditoria
from app.db import get_db
from app.deps import requerir_admin, validar_rango_de_fechas
from app.models import Compra, Usuario
from app.schemas import CompraActualizar, CompraCrear, CompraOut, Pagina

router = APIRouter(prefix="/compras", tags=["compras"], dependencies=[Depends(requerir_admin)])


def _buscar_compra(db: Session, compra_id: int) -> Compra:
    compra = db.get(Compra, compra_id)
    if compra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")
    return compra


@router.get("", response_model=Pagina[CompraOut])
def listar_compras(
    desde: date | None = None,
    hasta: date | None = None,
    comercio: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(15, ge=1, le=200),
    db: Session = Depends(get_db),
):
    validar_rango_de_fechas(desde, hasta)

    condiciones = []
    if desde is not None:
        condiciones.append(Compra.fecha >= desde)
    if hasta is not None:
        condiciones.append(Compra.fecha <= hasta)
    if comercio:
        condiciones.append(Compra.nombre_comercio.ilike(f"%{comercio}%"))

    total = db.scalar(select(func.count()).select_from(Compra).where(*condiciones))
    compras = db.scalars(
        select(Compra)
        .where(*condiciones)
        .order_by(Compra.fecha.desc(), Compra.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()
    return {"items": compras, "total": total, "pagina": pagina, "por_pagina": por_pagina}


@router.get("/{compra_id}/imagen")
def ver_imagen(compra_id: int, db: Session = Depends(get_db)):
    compra = _buscar_compra(db, compra_id)
    return Response(content=base64.b64decode(compra.imagen), media_type=compra.imagen_tipo)


@router.post("", response_model=CompraOut, status_code=status.HTTP_201_CREATED)
def crear_compra(
    datos: CompraCrear,
    admin: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
):
    compra = Compra(
        nombre_comercio=datos.nombre_comercio,
        descripcion=datos.descripcion,
        imagen=datos.imagen,
        imagen_tipo=datos.imagen_tipo,
        creado_por=admin.id,
    )
    if datos.fecha is not None:
        compra.fecha = datos.fecha
    db.add(compra)
    db.flush()
    registrar_auditoria(
        db,
        admin,
        "compra.crear",
        {"compra_id": compra.id, "nombre_comercio": compra.nombre_comercio, "fecha": str(compra.fecha)},
        entidad="compra",
        entidad_id=compra.id,
    )
    db.commit()
    return compra


@router.put("/{compra_id}", response_model=CompraOut)
def actualizar_compra(
    compra_id: int,
    datos: CompraActualizar,
    admin: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
):
    compra = _buscar_compra(db, compra_id)
    anterior = {"nombre_comercio": compra.nombre_comercio, "fecha": str(compra.fecha)}
    compra.fecha = datos.fecha
    compra.nombre_comercio = datos.nombre_comercio
    compra.descripcion = datos.descripcion
    registrar_auditoria(
        db,
        admin,
        "compra.actualizar",
        {
            "compra_id": compra.id,
            "antes": anterior,
            "despues": {"nombre_comercio": compra.nombre_comercio, "fecha": str(compra.fecha)},
        },
        entidad="compra",
        entidad_id=compra.id,
    )
    db.commit()
    db.refresh(compra)
    return compra


@router.delete("/{compra_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_compra(
    compra_id: int, admin: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)
):
    compra = _buscar_compra(db, compra_id)
    registrar_auditoria(
        db,
        admin,
        "compra.borrar",
        {"compra_id": compra.id, "nombre_comercio": compra.nombre_comercio, "fecha": str(compra.fecha)},
        entidad="compra",
        entidad_id=compra.id,
    )
    db.delete(compra)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
