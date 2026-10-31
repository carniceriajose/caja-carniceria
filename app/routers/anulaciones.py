from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.arca.servicio import emitir_nota_credito
from app.auditoria import registrar as registrar_auditoria
from app.db import get_db
from app.deps import requerir_admin, validar_rango_de_fechas
from app.fechas import rango_utc
from app.models import Anulacion, Usuario, Venta
from app.schemas import AnulacionConVentaOut, EstadoAnulacion, Pagina

router = APIRouter(prefix="/anulaciones", tags=["anulaciones"], dependencies=[Depends(requerir_admin)])


@router.get("", response_model=Pagina[AnulacionConVentaOut])
def listar_anulaciones(
    desde: date | None = None,
    hasta: date | None = None,
    estado: EstadoAnulacion | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    validar_rango_de_fechas(desde, hasta)
    inicio, fin = rango_utc(desde, hasta)

    condiciones = []
    if inicio is not None:
        condiciones.append(Anulacion.fecha_hora >= inicio)
    if fin is not None:
        condiciones.append(Anulacion.fecha_hora < fin)
    if estado is not None:
        condiciones.append(Anulacion.estado == estado)

    total = db.scalar(select(func.count()).select_from(Anulacion).where(*condiciones))
    filas = db.scalars(
        select(Anulacion)
        .where(*condiciones)
        .order_by(Anulacion.fecha_hora.desc(), Anulacion.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()
    return {"items": filas, "total": total, "pagina": pagina, "por_pagina": por_pagina}


@router.post("/{anulacion_id}/reintentar", response_model=AnulacionConVentaOut)
def reintentar_anulacion(anulacion_id: int, admin: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)):
    anulacion = db.get(Anulacion, anulacion_id)
    if anulacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anulación no encontrada.")
    if anulacion.estado not in ("pendiente", "fallo"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta anulación no tiene una nota de crédito pendiente de reintentar.",
        )
    registrar_auditoria(
        db,
        admin,
        "anulacion.reintentar",
        {"anulacion_id": anulacion.id, "venta_id": anulacion.venta_id},
        entidad="venta",
        entidad_id=anulacion.venta_id,
    )
    db.commit()

    venta = db.get(Venta, anulacion.venta_id)
    emitir_nota_credito(db, venta, anulacion)
    db.refresh(anulacion)
    return anulacion
