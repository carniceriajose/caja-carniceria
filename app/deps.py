from datetime import date

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Usuario
from app.security import leer_token

_esquema_bearer = HTTPBearer(auto_error=False)


def _no_autenticado() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado o sesión vencida.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_esquema_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    """Valida el token y vuelve a leer al usuario de la base en cada pedido, así
    desactivarlo o cambiarle la contraseña o el rol lo saca al instante."""
    if credenciales is None:
        raise _no_autenticado()
    try:
        usuario_id, version = leer_token(credenciales.credentials)
    except jwt.InvalidTokenError:
        raise _no_autenticado() from None

    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo or usuario.token_version != version:
        raise _no_autenticado()
    return usuario


def validar_rango_de_fechas(desde: date | None, hasta: date | None) -> None:
    if desde and hasta and desde > hasta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha 'desde' no puede ser posterior a 'hasta'.",
        )


def requerir_admin(usuario: Usuario = Depends(get_usuario_actual)) -> Usuario:
    if usuario.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para realizar esta acción.",
        )
    return usuario
