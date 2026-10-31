"""Registro de quién hizo cada cosa: solo acciones administrativas que cambian
algo, nunca lecturas. Se agrega a la sesión sin hacer commit: queda en la
misma transacción que el cambio que audita (si el cambio no se guarda,
tampoco queda un rastro suelto)."""

from sqlalchemy.orm import Session

from app.models import Auditoria, Usuario


def registrar(
    db: Session,
    usuario: Usuario | None,
    accion: str,
    detalle: dict | None = None,
    *,
    entidad: str | None = None,
    entidad_id: int | None = None,
) -> None:
    db.add(
        Auditoria(
            usuario_id=usuario.id if usuario else None,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            detalle=detalle,
        )
    )
