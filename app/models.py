import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates

from app.fechas import hoy_argentina

# BIGINT en Postgres; en SQLite tiene que ser INTEGER para que el id se autoincremente.
ID = BigInteger().with_variant(Integer, "sqlite")
JSON_FLEXIBLE = JSON().with_variant(JSONB, "postgresql")


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint("rol in ('vendedor', 'admin')", name="usuarios_rol_check"),
        CheckConstraint("usuario = lower(usuario)", name="usuarios_usuario_minusculas"),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(Text)
    usuario: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )

    @validates("usuario")
    def _normalizar_usuario(self, _clave: str, valor: str) -> str:
        return valor.strip().lower()


Index("usuarios_usuario_uq", func.lower(Usuario.usuario), unique=True)


class Venta(Base):
    __tablename__ = "ventas"
    __table_args__ = (
        CheckConstraint("total > 0", name="ventas_total_positivo"),
        CheckConstraint(
            "medio_pago in ('efectivo', 'tarjeta', 'transferencia')",
            name="ventas_medio_pago_check",
        ),
        CheckConstraint(
            "estado_arca in ('no_aplica', 'pendiente', 'facturada', 'fallo')",
            name="ventas_estado_arca_check",
        ),
        CheckConstraint(
            "estado_arca <> 'facturada' or numero_comprobante is not null",
            name="ventas_facturada_completa",
        ),
        CheckConstraint(
            "estado_arca <> 'fallo' or error_detalle is not null",
            name="ventas_fallo_con_detalle",
        ),
        Index("ventas_fecha_hora_idx", "fecha_hora"),
        Index("ventas_medio_pago_idx", "medio_pago", "fecha_hora"),
        Index(
            "ventas_estado_idx",
            "estado_arca",
            postgresql_where=text("estado_arca in ('pendiente', 'fallo')"),
            sqlite_where=text("estado_arca in ('pendiente', 'fallo')"),
        ),
        Index("ventas_vendedor_idx", "vendedor_id"),
        Index("ventas_id_cliente_uq", "id_cliente", unique=True),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    # Lo genera el frontend al empezar la venta: evita duplicarla si el pedido se repite.
    id_cliente: Mapped[uuid.UUID] = mapped_column(Uuid)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    medio_pago: Mapped[str] = mapped_column(Text)
    vendedor_id: Mapped[int] = mapped_column(ID, ForeignKey("usuarios.id"))

    estado_arca: Mapped[str] = mapped_column(
        Text, default="no_aplica", server_default=text("'no_aplica'")
    )
    tipo_comprobante: Mapped[str | None] = mapped_column(Text)
    punto_venta: Mapped[int | None] = mapped_column(Integer)
    numero_comprobante: Mapped[int | None] = mapped_column(BigInteger)
    cae: Mapped[str | None] = mapped_column(Text)
    cae_vencimiento: Mapped[date | None] = mapped_column(Date)
    error_detalle: Mapped[str | None] = mapped_column(Text)
    respuesta_fiscal: Mapped[dict | None] = mapped_column(JSON_FLEXIBLE)


class CategoriaGasto(Base):
    __tablename__ = "categorias_gasto"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )


Index("categorias_gasto_nombre_uq", func.lower(CategoriaGasto.nombre), unique=True)


class Gasto(Base):
    __tablename__ = "gastos"
    __table_args__ = (
        CheckConstraint("monto > 0", name="gastos_monto_positivo"),
        Index("gastos_fecha_idx", "fecha"),
        Index("gastos_categoria_idx", "categoria_id", "fecha"),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date, default=hoy_argentina)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    categoria_id: Mapped[int] = mapped_column(ID, ForeignKey("categorias_gasto.id"))
    descripcion: Mapped[str | None] = mapped_column(Text)
    creado_por: Mapped[int] = mapped_column(ID, ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )

    categoria: Mapped[CategoriaGasto] = relationship(lazy="joined")


class TicketAcceso(Base):
    """Ticket de acceso (token + sign) de WSAA. Se guarda en la base y no solo
    en memoria porque el servidor se reinicia; un solo registro por servicio
    ('wsfe'), se reemplaza cuando se renueva."""

    __tablename__ = "tickets_acceso"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    servicio: Mapped[str] = mapped_column(Text)
    token: Mapped[str] = mapped_column(Text)
    sign: Mapped[str] = mapped_column(Text)
    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )
    vence_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index("tickets_acceso_servicio_uq", TicketAcceso.servicio, unique=True)


class Configuracion(Base):
    """Una sola fila: qué medios de pago se facturan."""

    __tablename__ = "configuracion"
    __table_args__ = (CheckConstraint("id = 1", name="configuracion_una_sola_fila"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False, default=1)
    facturar_efectivo: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    facturar_tarjeta: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    facturar_transferencia: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
