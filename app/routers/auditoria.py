from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import requerir_admin, validar_rango_de_fechas
from app.fechas import rango_utc
from app.models import Auditoria
from app.schemas import AuditoriaOut, Pagina

router = APIRouter(prefix="/auditoria", tags=["auditoria"], dependencies=[Depends(requerir_admin)])


@router.get("", response_model=Pagina[AuditoriaOut])
def listar_auditoria(
    desde: date | None = None,
    hasta: date | None = None,
    accion: str | None = None,
    usuario_id: int | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    validar_rango_de_fechas(desde, hasta)
    inicio, fin = rango_utc(desde, hasta)

    condiciones = []
    if inicio is not None:
        condiciones.append(Auditoria.creado_en >= inicio)
    if fin is not None:
        condiciones.append(Auditoria.creado_en < fin)
    if accion is not None:
        condiciones.append(Auditoria.accion == accion)
    if usuario_id is not None:
        condiciones.append(Auditoria.usuario_id == usuario_id)

    total = db.scalar(select(func.count()).select_from(Auditoria).where(*condiciones))
    filas = db.scalars(
        select(Auditoria)
        .where(*condiciones)
        .order_by(Auditoria.creado_en.desc(), Auditoria.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()
    return {"items": filas, "total": total, "pagina": pagina, "por_pagina": por_pagina}
