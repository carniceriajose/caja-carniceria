import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auditoria import registrar as registrar_auditoria
from app.db import get_db
from app.deps import get_usuario_actual, get_usuario_parcial, requerir_admin
from app.models import CodigoRecuperacion2FA, Usuario
from app.schemas import (
    Activar2FAIn,
    Codigo2FAIn,
    CodigosRecuperacionOut,
    Iniciar2FAOut,
    LoginIn,
    LoginOut,
    PasswordIn,
    UsuarioOut,
)
from app.security import (
    HASH_RELLENO,
    crear_token,
    generar_codigos_recuperacion,
    hashear_password,
    limitador,
    necesita_rehash,
    normalizar_codigo_recuperacion,
    verificar_password,
)
from app.totp import generar_secreto, url_de_aprovisionamiento, verificar_codigo

router = APIRouter(prefix="/auth", tags=["auth"])

MENSAJE_LOGIN_INVALIDO = "Usuario o contraseña incorrectos."
MENSAJE_CODIGO_INVALIDO = "Código incorrecto."


def _borrar_codigos_recuperacion(db: Session, usuario: Usuario) -> None:
    db.query(CodigoRecuperacion2FA).filter(CodigoRecuperacion2FA.usuario_id == usuario.id).delete()


def _intentar_codigo_recuperacion(db: Session, usuario: Usuario, codigo: str) -> bool:
    """Códigos de un solo uso, guardados hasheados. Si alguno coincide, lo marca
    usado y devuelve True."""
    pendientes = db.scalars(
        select(CodigoRecuperacion2FA).where(
            CodigoRecuperacion2FA.usuario_id == usuario.id,
            CodigoRecuperacion2FA.usado_en.is_(None),
        )
    ).all()
    for fila in pendientes:
        if verificar_password(fila.codigo_hash, codigo):
            fila.usado_en = datetime.now(timezone.utc)
            return True
    return False


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
        registrar_auditoria(
            db,
            usuario,
            "login.fallido",
            None if usuario else {"usuario_intentado": datos.usuario},
            entidad="usuario",
            entidad_id=usuario.id if usuario else None,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_LOGIN_INVALIDO)

    limitador.limpiar_usuario(datos.usuario)

    if necesita_rehash(usuario.password_hash):
        usuario.password_hash = hashear_password(datos.password)
        db.commit()

    if usuario.dos_factores_activo:
        # La contraseña ya es correcta, pero falta el código: token de 5 minutos
        # que solo sirve para /auth/2fa/verificar, no para nada más de la API.
        return LoginOut(requiere_2fa=True, token_parcial=crear_token(usuario, parcial=True))

    registrar_auditoria(db, usuario, "login.exitoso", entidad="usuario", entidad_id=usuario.id)
    db.commit()
    return LoginOut(token=crear_token(usuario), usuario=UsuarioOut.model_validate(usuario))


@router.post("/2fa/verificar", response_model=LoginOut)
def verificar_2fa(
    datos: Codigo2FAIn,
    request: Request,
    usuario: Usuario = Depends(get_usuario_parcial),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "desconocida"
    clave = f"2fa:{usuario.usuario}"

    espera = limitador.segundos_de_bloqueo(clave, ip)
    if espera > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Demasiados códigos incorrectos. "
                f"Espere {math.ceil(espera / 60)} minuto(s) e intente de nuevo."
            ),
            headers={"Retry-After": str(espera)},
        )

    es_totp = datos.codigo.isdigit() and len(datos.codigo) == 6
    if es_totp:
        correcto = usuario.dos_factores_activo and verificar_codigo(usuario.dos_factores_secreto, datos.codigo)
    else:
        correcto = usuario.dos_factores_activo and _intentar_codigo_recuperacion(db, usuario, datos.codigo)

    if not correcto:
        limitador.registrar_fallo(clave, ip)
        registrar_auditoria(
            db, usuario, "login.fallido", {"motivo": "codigo_2fa_invalido"}, entidad="usuario", entidad_id=usuario.id
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_CODIGO_INVALIDO)

    limitador.limpiar_usuario(clave)
    if not es_totp:
        registrar_auditoria(db, usuario, "2fa.recuperacion_usada", entidad="usuario", entidad_id=usuario.id)
    registrar_auditoria(db, usuario, "login.exitoso", entidad="usuario", entidad_id=usuario.id)
    db.commit()
    return LoginOut(token=crear_token(usuario), usuario=UsuarioOut.model_validate(usuario))


@router.get("/yo", response_model=UsuarioOut)
def yo(usuario: Usuario = Depends(get_usuario_actual)):
    return usuario


@router.post("/2fa/iniciar", response_model=Iniciar2FAOut)
def iniciar_2fa(usuario: Usuario = Depends(requerir_admin)):
    """Genera un secreto nuevo para armar el QR. No se guarda todavía: recién se
    persiste en /2fa/activar, una vez confirmado con un código real."""
    secreto = generar_secreto()
    return Iniciar2FAOut(secreto=secreto, qr_url=url_de_aprovisionamiento(secreto, usuario.usuario))


@router.post("/2fa/activar", response_model=CodigosRecuperacionOut)
def activar_2fa(
    datos: Activar2FAIn, usuario: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)
):
    """Confirma el secreto (recibido de /2fa/iniciar) con un código real de la
    app autenticadora, y entrega los códigos de recuperación una única vez."""
    if not verificar_codigo(datos.secreto, datos.codigo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código incorrecto. Escaneá el código de nuevo e intentá otra vez.",
        )
    usuario.dos_factores_secreto = datos.secreto
    usuario.dos_factores_activo = True
    _borrar_codigos_recuperacion(db, usuario)
    codigos = generar_codigos_recuperacion()
    for codigo in codigos:
        db.add(CodigoRecuperacion2FA(usuario_id=usuario.id, codigo_hash=hashear_password(codigo)))
    registrar_auditoria(db, usuario, "2fa.activar", entidad="usuario", entidad_id=usuario.id)
    db.commit()
    return CodigosRecuperacionOut(codigos=codigos)


@router.post("/2fa/desactivar", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_2fa(
    datos: PasswordIn, usuario: Usuario = Depends(requerir_admin), db: Session = Depends(get_db)
):
    """Apaga el segundo factor propio; pide la contraseña de nuevo como resguardo.

    400 y no 401: la sesión sigue siendo válida, lo que falló es la
    confirmación de la contraseña. El frontend trata cualquier 401 como
    "sesión vencida" y cerraría la sesión del admin sin necesidad."""
    if not verificar_password(usuario.password_hash, datos.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña incorrecta.")
    usuario.dos_factores_activo = False
    usuario.dos_factores_secreto = None
    _borrar_codigos_recuperacion(db, usuario)
    registrar_auditoria(db, usuario, "2fa.desactivar", entidad="usuario", entidad_id=usuario.id)
    db.commit()
