import math

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_usuario_actual
from app.models import Usuario
from app.schemas import LoginIn, LoginOut, UsuarioOut
from app.security import (
    HASH_RELLENO,
    crear_token,
    hashear_password,
    limitador,
    necesita_rehash,
    verificar_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

MENSAJE_LOGIN_INVALIDO = "Usuario o contraseña incorrectos."


@router.post("/login", response_model=LoginOut)
def login(datos: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "desconocida"

    espera = limitador.segundos_de_bloqueo(datos.usuario, ip)
    if espera > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Demasiados intentos fallidos. "
                f"Espere {math.ceil(espera / 60)} minuto(s) e intente de nuevo."
            ),
            headers={"Retry-After": str(espera)},
        )

    usuario = db.scalar(select(Usuario).where(Usuario.usuario == datos.usuario))
    # Se verifica siempre una contraseña, exista o no el usuario, para no delatarlo por el tiempo.
    password_correcta = verificar_password(
        usuario.password_hash if usuario else HASH_RELLENO, datos.password
    )

    if usuario is None or not usuario.activo or not password_correcta:
        limitador.registrar_fallo(datos.usuario, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_LOGIN_INVALIDO)

    limitador.limpiar_usuario(datos.usuario)

    if necesita_rehash(usuario.password_hash):
        usuario.password_hash = hashear_password(datos.password)
        db.commit()

    return LoginOut(token=crear_token(usuario), usuario=UsuarioOut.model_validate(usuario))


@router.get("/yo", response_model=UsuarioOut)
def yo(usuario: Usuario = Depends(get_usuario_actual)):
    return usuario
