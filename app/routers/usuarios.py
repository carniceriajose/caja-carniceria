from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import requerir_admin
from app.models import Usuario
from app.schemas import PasswordIn, UsuarioActualizar, UsuarioCrear, UsuarioOut
from app.security import hashear_password

router = APIRouter(prefix="/usuarios", tags=["usuarios"], dependencies=[Depends(requerir_admin)])


def _buscar(db: Session, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    return usuario


@router.get("", response_model=list[UsuarioOut])
def listar_usuarios(db: Session = Depends(get_db)):
    return db.scalars(select(Usuario).order_by(Usuario.id)).all()


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def crear_usuario(datos: UsuarioCrear, db: Session = Depends(get_db)):
    usuario = Usuario(
        nombre=datos.nombre,
        usuario=datos.usuario,
        password_hash=hashear_password(datos.password),
        rol=datos.rol,
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese nombre de usuario.",
        ) from None
    return usuario


@router.patch("/{usuario_id}", response_model=UsuarioOut)
def actualizar_usuario(
    usuario_id: int,
    datos: UsuarioActualizar,
    actual: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
):
    usuario = _buscar(db, usuario_id)
    nuevo_rol = datos.rol if datos.rol is not None else usuario.rol
    nuevo_activo = datos.activo if datos.activo is not None else usuario.activo

    deja_de_ser_admin_activo = (
        usuario.rol == "admin" and usuario.activo and (nuevo_rol != "admin" or not nuevo_activo)
    )
    if deja_de_ser_admin_activo:
        if usuario.id == actual.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puede desactivarse ni quitarse el rol de administrador a sí mismo.",
            )
        # Se bloquean las filas de los admins activos para que dos admins que se
        # quitan el permiso a la vez no puedan dejar el sistema sin ninguno.
        admins_activos = db.scalars(
            select(Usuario.id)
            .where(Usuario.rol == "admin", Usuario.activo.is_(True))
            .with_for_update()
        ).all()
        if not any(admin_id != usuario.id for admin_id in admins_activos):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tiene que quedar al menos un administrador activo.",
            )

    cambia_el_acceso = nuevo_rol != usuario.rol or nuevo_activo != usuario.activo
    if datos.nombre is not None:
        usuario.nombre = datos.nombre
    usuario.rol = nuevo_rol
    usuario.activo = nuevo_activo
    if cambia_el_acceso:
        usuario.token_version += 1
    db.commit()
    return usuario


@router.put("/{usuario_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def cambiar_password(usuario_id: int, datos: PasswordIn, db: Session = Depends(get_db)):
    usuario = _buscar(db, usuario_id)
    usuario.password_hash = hashear_password(datos.password)
    usuario.token_version += 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
