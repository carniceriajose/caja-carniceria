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

    # Segundo factor (TOTP), opcional y apagado por defecto. El secreto viaja
    # sin guardar entre /2fa/iniciar y /2fa/activar (el frontend lo mantiene en
    # memoria mientras se muestra el QR): recién se persiste una vez confirmado.
    dos_factores_activo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    dos_factores_secreto: Mapped[str | None] = mapped_column(Text)

    @validates("usuario")
    def _normalizar_usuario(self, _clave: str, valor: str) -> str:
        return valor.strip().lower()


Index("usuarios_usuario_uq", func.lower(Usuario.usuario), unique=True)


class CodigoRecuperacion2FA(Base):
    """Códigos de recuperación del segundo factor: se muestran una sola vez al
    activarlo (en texto plano) y acá solo se guarda el hash, igual que una
    contraseña. Cada uno sirve una sola vez."""

    __tablename__ = "codigos_recuperacion_2fa"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ID, ForeignKey("usuarios.id"))
    codigo_hash: Mapped[str] = mapped_column(Text)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )


Index("codigos_recuperacion_2fa_usuario_idx", CodigoRecuperacion2FA.usuario_id)


class Tarjeta(Base):
    """Un tipo de tarjeta elegible al cobrar (Visa, Naranja, etc.), cada una
    con su propio recargo. No se borran: una venta vieja tiene que poder
    seguir señalando la que usó, así que se desactivan en vez de borrarse."""

    __tablename__ = "tarjetas"
    __table_args__ = (
        CheckConstraint(
            "recargo_porcentaje >= 0 and recargo_porcentaje <= 100",
            name="tarjetas_recargo_rango",
        ),
        CheckConstraint("tipo in ('credito', 'debito')", name="tarjetas_tipo_check"),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)
    recargo_porcentaje: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0")
    )
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    orden: Mapped[int] = mapped_column(Integer)


Index("tarjetas_nombre_uq", func.lower(Tarjeta.nombre), unique=True)


class Rubro(Base):
    """Rubro de venta (Carne, Embutidos, etc.): cada uno define su propia
    alícuota de IVA y la descripción que sale en la factura. No se borran, se
    desactivan. Siempre tiene que haber exactamente uno predeterminado (el que
    viene elegido de entrada en la pantalla de venta) y al menos uno activo;
    eso lo garantiza la aplicación, no la base (ver app/rubros.py)."""

    __tablename__ = "rubros"
    __table_args__ = (
        CheckConstraint(
            "alicuota in (0, 2.5, 5, 10.5, 21, 27)",
            name="rubros_alicuota_valida",
        ),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(Text)
    alicuota: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    descripcion_factura: Mapped[str] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    orden: Mapped[int] = mapped_column(Integer)
    es_predeterminado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


Index("rubros_nombre_uq", func.lower(Rubro.nombre), unique=True)
Index(
    "rubros_predeterminado_uq",
    Rubro.es_predeterminado,
    unique=True,
    postgresql_where=text("es_predeterminado"),
    sqlite_where=text("es_predeterminado"),
)


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
        CheckConstraint(
            "not anulada or anulada_en is not null", name="ventas_anulada_completa"
        ),
        CheckConstraint(
            "ajuste_tipo is null or ajuste_tipo = 'recargo'",
            name="ventas_ajuste_tipo_check",
        ),
        CheckConstraint(
            "ajuste_origen is null or ajuste_origen = 'medio_pago'",
            name="ventas_ajuste_origen_check",
        ),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    # Lo genera el frontend al empezar la venta: evita duplicarla si el pedido se repite.
    id_cliente: Mapped[uuid.UUID] = mapped_column(Uuid)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )
    # "total" es lo que se cobra y se factura de verdad (con el recargo por
    # medio de pago ya aplicado, si corresponde); "subtotal" es lo que se
    # tipeó antes de aplicar nada. En efectivo son siempre iguales. El detalle
    # del recargo queda congelado acá: si el % configurado cambia después, no
    # tiene que alterar esta venta.
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    ajuste_tipo: Mapped[str | None] = mapped_column(Text)
    ajuste_origen: Mapped[str | None] = mapped_column(Text)
    ajuste_monto: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ajuste_detalle: Mapped[str | None] = mapped_column(Text)
    medio_pago: Mapped[str] = mapped_column(Text)
    # Solo cuando medio_pago = "tarjeta": qué tarjeta se eligió (determina el
    # recargo). Nunca se borra una tarjeta, así que esta referencia no se rompe;
    # nombre y recargo quedan además congelados acá, por si la tarjeta cambia
    # de nombre o de recargo (o se desactiva) más adelante.
    tarjeta_id: Mapped[int | None] = mapped_column(ID, ForeignKey("tarjetas.id"))
    tarjeta_nombre: Mapped[str | None] = mapped_column(Text)
    tarjeta_recargo_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    tarjeta_tipo: Mapped[str | None] = mapped_column(Text)
    vendedor_id: Mapped[int] = mapped_column(ID, ForeignKey("usuarios.id"))

    # Rubro elegido (determina la alícuota de IVA y la descripción del ítem en
    # la factura): nunca se borra un rubro, y nombre/descripción quedan
    # también congelados acá por si cambian después. Nulo solo en ventas de
    # antes de que existiera esto.
    rubro_id: Mapped[int | None] = mapped_column(ID, ForeignKey("rubros.id"))
    rubro_nombre: Mapped[str | None] = mapped_column(Text)
    descripcion_factura: Mapped[str | None] = mapped_column(Text)

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
    # La alícuota del rubro elegido, congelada al cobrar: si el rubro cambia
    # de alícuota después, no tiene que alterar el comprobante ya impreso
    # (nulo en las ventas de antes de este campo: para esas se usa el rubro
    # predeterminado actual).
    alicuota_iva: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    # Anulación: la venta nunca se borra ni se edita, solo se marca. El motivo,
    # el estado de la nota de crédito (si la venta ya tenía CAE) y el resto del
    # detalle fiscal viven en la tabla "anulaciones" (ver clase Anulacion).
    anulada: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    anulada_por: Mapped[int | None] = mapped_column(ID, ForeignKey("usuarios.id"))
    anulada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    anulacion: Mapped["Anulacion | None"] = relationship(lazy="joined", uselist=False, viewonly=True)


class Anulacion(Base):
    """Anulación de una venta. Si la venta ya tenía CAE, esto es lo que hace
    falta emitir ante ARCA (una nota de crédito) para que quede saldada; si
    no, queda "sin_comprobante" de una: no hay nada que reversar ante ARCA."""

    __tablename__ = "anulaciones"
    __table_args__ = (
        CheckConstraint(
            "estado in ('pendiente', 'emitida', 'fallo', 'sin_comprobante')",
            name="anulaciones_estado_check",
        ),
        Index("anulaciones_venta_id_uq", "venta_id", unique=True),
        Index(
            "anulaciones_pendientes_idx",
            "estado",
            postgresql_where=text("estado in ('pendiente', 'fallo')"),
            sqlite_where=text("estado in ('pendiente', 'fallo')"),
        ),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    venta_id: Mapped[int] = mapped_column(ID, ForeignKey("ventas.id"))
    motivo: Mapped[str] = mapped_column(Text)
    usuario_id: Mapped[int] = mapped_column(ID, ForeignKey("usuarios.id"))
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )
    estado: Mapped[str] = mapped_column(Text, default="pendiente", server_default=text("'pendiente'"))

    # Nota de crédito (solo si la venta tenía CAE): mismo significado que los
    # campos análogos de Venta, pero acá (nunca se tocan los de la venta original).
    tipo: Mapped[int | None] = mapped_column(Integer)
    punto_venta: Mapped[int | None] = mapped_column(Integer)
    numero: Mapped[int | None] = mapped_column(BigInteger)
    cae: Mapped[str | None] = mapped_column(Text)
    cae_vencimiento: Mapped[date | None] = mapped_column(Date)
    error_detalle: Mapped[str | None] = mapped_column(Text)
    alicuota_iva: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    respuesta_fiscal: Mapped[dict | None] = mapped_column(JSON_FLEXIBLE)

    venta: Mapped[Venta] = relationship(lazy="joined")
    usuario: Mapped[Usuario] = relationship(lazy="joined")


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


class Auditoria(Base):
    """Quién hizo cada cosa: se graba a mano en cada acción administrativa que
    cambia algo (no en las simples lecturas)."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int | None] = mapped_column(ID, ForeignKey("usuarios.id"))
    accion: Mapped[str] = mapped_column(Text)
    entidad: Mapped[str | None] = mapped_column(Text)
    entidad_id: Mapped[int | None] = mapped_column(ID)
    detalle: Mapped[dict | None] = mapped_column(JSON_FLEXIBLE)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )

    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


Index("auditoria_creado_en_idx", Auditoria.creado_en.desc())
Index("auditoria_usuario_idx", Auditoria.usuario_id)


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
    """Una sola fila: qué medios de pago se facturan, los datos del comercio
    que salen en el ticket, y el resto de los parámetros de facturación y de
    operación que un admin puede ajustar sin tocar el servidor.

    El CUIT queda afuera a propósito: es el que ya se usa para autenticarse
    ante ARCA (junto con el certificado, en las variables de entorno) y para
    el QR fiscal, así que cambiarlo acá sin cambiar el certificado real
    rompería la facturación. Se muestra de solo lectura en la pantalla."""

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

    # Datos del comercio (encabezado del ticket).
    razon_social: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    domicilio: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    condicion_iva: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    inicio_actividades: Mapped[date] = mapped_column(Date, default=date(2020, 1, 1))
    ingresos_brutos: Mapped[str | None] = mapped_column(Text)

    # Facturación. La alícuota de IVA ya no se configura acá: la define cada
    # rubro (ver clase Rubro). descripcion_item queda solo como texto de
    # respaldo para ventas de antes de que existieran los rubros.
    tipo_comprobante: Mapped[int] = mapped_column(Integer, default=11, server_default=text("11"))
    punto_venta: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    descripcion_item: Mapped[str] = mapped_column(Text, default="Venta de mercadería", server_default=text("'Venta de mercadería'"))

    # Operación.
    anulacion_minutos_vendedor: Mapped[int] = mapped_column(Integer, default=10, server_default=text("10"))

    # Recargo automático por transferencia (el de tarjeta se define por tipo
    # de tarjeta, ver clase Tarjeta). No hay descuentos ni ajustes manuales.
    recargo_transferencia_porcentaje: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0")
    )


class CierreCaja(Base):
    """El corte diario: los totales que calculó el sistema, contra lo que el
    admin contó a mano en el cajón. Nunca se edita ni se borra; si hay un
    error se anula (queda el registro) y se hace uno nuevo para el mismo día."""

    __tablename__ = "cierres_caja"
    __table_args__ = (
        # Un solo cierre ACTIVO por día: anulado uno, se puede cerrar de nuevo.
        Index(
            "cierres_caja_fecha_activo_uq",
            "fecha",
            unique=True,
            postgresql_where=text("not anulado"),
            sqlite_where=text("not anulado"),
        ),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date)
    usuario_id: Mapped[int] = mapped_column(ID, ForeignKey("usuarios.id"))
    fecha_hora_cierre: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, server_default=func.now()
    )

    # Totales calculados por el sistema al momento de cerrar.
    total_general: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_efectivo: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_tarjeta: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_transferencia: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cantidad_ventas: Mapped[int] = mapped_column(Integer)
    cantidad_anulaciones: Mapped[int] = mapped_column(Integer)
    monto_anulaciones: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    efectivo_contado: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # contado - total_efectivo: positiva si sobra, negativa si falta.
    diferencia: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    observaciones: Mapped[str | None] = mapped_column(Text)
    # Foto completa del momento (todo lo anterior, más el detalle que se
    # quiera guardar) para no depender de que las ventas no cambien después.
    detalle: Mapped[dict] = mapped_column(JSON_FLEXIBLE)

    anulado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    anulado_motivo: Mapped[str | None] = mapped_column(Text)
    anulado_por: Mapped[int | None] = mapped_column(ID, ForeignKey("usuarios.id"))
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    usuario: Mapped[Usuario] = relationship(foreign_keys=[usuario_id], lazy="joined")
