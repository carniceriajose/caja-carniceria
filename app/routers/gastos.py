from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import requerir_admin, validar_rango_de_fechas
from app.models import CategoriaGasto, Gasto, Usuario
from app.schemas import (
    CategoriaGastoCrear,
    CategoriaGastoOut,
    GastoActualizar,
    GastoCrear,
    GastoOut,
    Pagina,
)

router_categorias = APIRouter(
    prefix="/categorias-gasto", tags=["gastos"], dependencies=[Depends(requerir_admin)]
)
router = APIRouter(prefix="/gastos", tags=["gastos"], dependencies=[Depends(requerir_admin)])


# ---------------------------------------------------------------- categorías


def _buscar_categoria_por_nombre(db: Session, nombre: str) -> CategoriaGasto | None:
    return db.scalar(
        select(CategoriaGasto).where(func.lower(CategoriaGasto.nombre) == func.lower(nombre))
    )


@router_categorias.get("", response_model=list[CategoriaGastoOut])
def listar_categorias(db: Session = Depends(get_db)):
    return db.scalars(select(CategoriaGasto).order_by(func.lower(CategoriaGasto.nombre))).all()


@router_categorias.post("", response_model=CategoriaGastoOut, status_code=status.HTTP_201_CREATED)
def crear_categoria(datos: CategoriaGastoCrear, response: Response, db: Session = Depends(get_db)):
    """Si la categoría ya existe (sin distinguir mayúsculas), devuelve la existente."""
    existente = _buscar_categoria_por_nombre(db, datos.nombre)
    if existente is not None:
        response.status_code = status.HTTP_200_OK
        return existente

    nueva = CategoriaGasto(nombre=datos.nombre)
    db.add(nueva)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existente = _buscar_categoria_por_nombre(db, datos.nombre)
        if existente is None:
            raise
        response.status_code = status.HTTP_200_OK
        return existente
    return nueva


# ---------------------------------------------------------------- gastos


def _exigir_categoria(db: Session, categoria_id: int) -> None:
    if db.get(CategoriaGasto, categoria_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La categoría indicada no existe."
        )


def _buscar_gasto(db: Session, gasto_id: int) -> Gasto:
    gasto = db.get(Gasto, gasto_id)
    if gasto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto no encontrado.")
    return gasto


@router.get("", response_model=Pagina[GastoOut])
def listar_gastos(
    desde: date | None = None,
    hasta: date | None = None,
    categoria_id: int | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    validar_rango_de_fechas(desde, hasta)

    condiciones = []
    if desde is not None:
        condiciones.append(Gasto.fecha >= desde)
    if hasta is not None:
        condiciones.append(Gasto.fecha <= hasta)
    if categoria_id is not None:
        condiciones.append(Gasto.categoria_id == categoria_id)

    total = db.scalar(select(func.count()).select_from(Gasto).where(*condiciones))
    gastos = db.scalars(
        select(Gasto)
        .where(*condiciones)
        .order_by(Gasto.fecha.desc(), Gasto.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()
    return {"items": gastos, "total": total, "pagina": pagina, "por_pagina": por_pagina}


@router.post("", response_model=GastoOut, status_code=status.HTTP_201_CREATED)
def crear_gasto(
    datos: GastoCrear,
    admin: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
):
    _exigir_categoria(db, datos.categoria_id)
    gasto = Gasto(
        monto=datos.monto,
        categoria_id=datos.categoria_id,
        descripcion=datos.descripcion,
        creado_por=admin.id,
    )
    if datos.fecha is not None:
        gasto.fecha = datos.fecha
    db.add(gasto)
    db.commit()
    return gasto


@router.put("/{gasto_id}", response_model=GastoOut)
def actualizar_gasto(gasto_id: int, datos: GastoActualizar, db: Session = Depends(get_db)):
    gasto = _buscar_gasto(db, gasto_id)
    _exigir_categoria(db, datos.categoria_id)
    gasto.fecha = datos.fecha
    gasto.monto = datos.monto
    gasto.categoria_id = datos.categoria_id
    gasto.descripcion = datos.descripcion
    db.commit()
    db.refresh(gasto)
    return gasto


@router.delete("/{gasto_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_gasto(gasto_id: int, db: Session = Depends(get_db)):
    db.delete(_buscar_gasto(db, gasto_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
