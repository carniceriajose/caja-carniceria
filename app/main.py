from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.arca import tareas as arca_tareas
from app.config import get_settings
from app.db import get_db, motor
from app.models import Base
from app.routers import (
    anulaciones,
    arca,
    auditoria,
    auth,
    cierres,
    comentarios_comercio,
    compras,
    configuracion,
    gastos,
    reportes,
    resumen,
    rubros,
    tarjetas,
    usuarios,
    ventas,
)
from app.schemas import mensaje_error

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # En producción las tablas se crean con las migraciones SQL de supabase/migrations.
    if not settings.es_produccion:
        Base.metadata.create_all(motor)
    if settings.arca_tareas_de_fondo:
        arca_tareas.iniciar_programador()
    try:
        yield
    finally:
        if settings.arca_tareas_de_fondo:
            arca_tareas.detener_programador()


documentacion = None if settings.es_produccion else "/docs"
app = FastAPI(
    title="Caja de la carnicería",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=documentacion,
    redoc_url=None,
    openapi_url=None if settings.es_produccion else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origenes_cors,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    respuesta.headers["Cache-Control"] = "no-store"
    if settings.es_produccion:
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return respuesta


@app.exception_handler(RequestValidationError)
async def errores_de_validacion(_request: Request, exc: RequestValidationError):
    # No se devuelve el valor recibido (input): podría ser una contraseña.
    detalle = [
        {"loc": list(e["loc"]), "msg": mensaje_error(e), "type": e["type"]} for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detalle})


_HTTP_EN_ESPANOL = {
    404: "No encontrado.",
    405: "Método no permitido.",
}


@app.exception_handler(StarletteHTTPException)
async def errores_http(_request: Request, exc: StarletteHTTPException):
    detalle = exc.detail
    if detalle == HTTPStatus(exc.status_code).phrase:
        detalle = _HTTP_EN_ESPANOL.get(exc.status_code, "Error en el pedido.")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detalle},
        headers=getattr(exc, "headers", None),
    )


@app.get("/salud", tags=["salud"])
def salud(db: Session = Depends(get_db)):
    try:
        db.execute(text("select 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible.") from None
    return {"estado": "ok"}


app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(configuracion.router)
app.include_router(ventas.router)
app.include_router(gastos.router_categorias)
app.include_router(gastos.router)
app.include_router(resumen.router)
app.include_router(arca.router)
app.include_router(auditoria.router)
app.include_router(anulaciones.router)
app.include_router(cierres.router)
app.include_router(reportes.router)
app.include_router(tarjetas.router)
app.include_router(rubros.router)
app.include_router(compras.router)
app.include_router(comentarios_comercio.router)
