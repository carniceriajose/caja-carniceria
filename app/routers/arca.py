import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.arca import wsaa, wsfe
from app.arca.servicio import emitir_factura
from app.db import get_db
from app.deps import requerir_admin
from app.models import Venta
from app.schemas import Pagina, VentaOut

logger = logging.getLogger("arca.router")

router = APIRouter(tags=["arca"], dependencies=[Depends(requerir_admin)])


@router.get("/facturas/con-error", response_model=Pagina[VentaOut])
def listar_facturas_con_error(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    condicion = Venta.estado_arca == "fallo"
    total = db.scalar(select(func.count()).select_from(Venta).where(condicion))
    ventas = db.scalars(
        select(Venta)
        .where(condicion)
        .order_by(Venta.fecha_hora.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()
    return {"items": ventas, "total": total, "pagina": pagina, "por_pagina": por_pagina}


@router.post("/ventas/{venta_id}/reintentar-factura", response_model=VentaOut)
def reintentar_factura(venta_id: int, db: Session = Depends(get_db)):
    venta = db.get(Venta, venta_id)
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    if venta.estado_arca not in ("pendiente", "fallo"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta venta no tiene una factura pendiente de reintentar.",
        )
    emitir_factura(db, venta)
    return venta


@router.get("/arca/estado")
def estado_arca():
    if not wsaa.hay_certificado_configurado():
        return {
            "certificado_configurado": False,
            "en_linea": None,
            "detalle": "No hay un certificado de ARCA configurado en el servidor.",
        }
    try:
        estado = wsfe.verificar_estado()
    except Exception:
        logger.exception("ARCA: FEDummy falló al consultar el estado.")
        return {
            "certificado_configurado": True,
            "en_linea": False,
            "detalle": "No se pudo conectar con ARCA en este momento.",
        }
    return {"certificado_configurado": True, "en_linea": True, "detalle": estado}
