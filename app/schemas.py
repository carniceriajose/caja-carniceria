import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    field_validator,
)

Rol = Literal["vendedor", "admin"]
MedioPago = Literal["efectivo", "tarjeta", "transferencia"]
EstadoArca = Literal["no_aplica", "pendiente", "facturada", "fallo"]

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Password = Annotated[str, Field(min_length=8, max_length=128)]

# Plata: siempre Decimal. Entra como número o texto y sale como texto con 2 decimales
# ("1250.50"), para que nunca pase por un float.
DineroPositivo = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
DineroNoNegativo = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Dinero = Annotated[
    Decimal, PlainSerializer(lambda valor: f"{valor:.2f}", return_type=str, when_used="json")
]


def _con_zona_horaria(valor: datetime) -> datetime:
    # SQLite devuelve las fechas sin zona; Postgres, con zona. Se unifica en UTC.
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


FechaHora = Annotated[datetime, AfterValidator(_con_zona_horaria)]


def _normalizar_usuario(valor: Any) -> Any:
    return valor.strip().lower() if isinstance(valor, str) else valor


def _limpiar_espacios(valor: Any) -> Any:
    return " ".join(valor.split()) if isinstance(valor, str) else valor


def _texto_o_none(valor: Any) -> Any:
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return valor


T = TypeVar("T")


class Pagina(BaseModel, Generic[T]):
    items: list[T]
    total: int
    pagina: int
    por_pagina: int


class PaginaConTotalMonto(Pagina[T], Generic[T]):
    """Como Pagina, pero con la suma de "total" de todo lo que cumple el
    filtro (no solo la página visible). No cuenta lo anulado."""

    total_monto: Dinero


# ---------------------------------------------------------------- usuarios y login


class LoginIn(BaseModel):
    usuario: Annotated[str, Field(min_length=1, max_length=100)]
    password: Annotated[str, Field(min_length=1, max_length=256)]

    _usuario_normalizado = field_validator("usuario", mode="before")(_normalizar_usuario)


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    usuario: str
    rol: Rol
    activo: bool
    dos_factores_activo: bool
    creado_en: FechaHora


class LoginOut(BaseModel):
    """La respuesta de /auth/login es una de estas dos formas: o vienen
    `token` + `usuario` (login completo), o `token_parcial` (falta el
    segundo factor) — nunca las dos juntas."""

    token: str | None = None
    usuario: UsuarioOut | None = None
    requiere_2fa: bool = False
    token_parcial: str | None = None


def _normalizar_codigo_2fa(valor: Any) -> Any:
    if not isinstance(valor, str):
        return valor
    limpio = valor.strip()
    if limpio.isdigit():
        return limpio
    return limpio.upper().replace("-", "").replace(" ", "")


class Codigo2FAIn(BaseModel):
    """El código de 6 dígitos de la app autenticadora, o uno de los 8 códigos
    de recuperación (10 caracteres) si se perdió el celular."""

    codigo: Annotated[str, Field(min_length=6, max_length=10, pattern=r"^(\d{6}|[A-Z0-9]{10})$")]

    _codigo_normalizado = field_validator("codigo", mode="before")(_normalizar_codigo_2fa)


class Iniciar2FAOut(BaseModel):
    secreto: str
    qr_url: str


class Activar2FAIn(BaseModel):
    """El secreto viaja de vuelta desde el frontend (no se guardó en /iniciar):
    recién se persiste acá, una vez confirmado con un código real."""

    secreto: Annotated[str, Field(min_length=16, max_length=64)]
    codigo: Annotated[str, Field(min_length=6, max_length=6, pattern=r"^\d{6}$")]


class CodigosRecuperacionOut(BaseModel):
    codigos: list[str]


class UsuarioCrear(BaseModel):
    nombre: Nombre
    usuario: Annotated[
        str, Field(min_length=3, max_length=30, pattern=r"^[a-z0-9._-]+$")
    ]
    password: Password
    rol: Rol

    _usuario_normalizado = field_validator("usuario", mode="before")(_normalizar_usuario)


class UsuarioActualizar(BaseModel):
    nombre: Nombre | None = None
    rol: Rol | None = None
    activo: bool | None = None


class PasswordIn(BaseModel):
    password: Password


class UsuarioResumenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    usuario: str


class AuditoriaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario: UsuarioResumenOut | None
    accion: str
    entidad: str | None
    entidad_id: int | None
    detalle: dict | None
    creado_en: FechaHora


# ---------------------------------------------------------------- configuración

# Tiene que coincidir con IDS_ALICUOTA_IVA de app/arca/servicio.py: son los
# únicos valores de alícuota que ARCA reconoce.
ALICUOTAS_IVA_PERMITIDAS = {
    Decimal("0"),
    Decimal("2.5"),
    Decimal("5"),
    Decimal("10.5"),
    Decimal("21"),
    Decimal("27"),
}

TipoComprobante = Literal[6, 11]  # 6 = Factura B, 11 = Factura C


class ConfiguracionIn(BaseModel):
    facturar_efectivo: bool
    facturar_tarjeta: bool
    facturar_transferencia: bool

    # Datos del comercio: salen impresos en el encabezado del ticket.
    razon_social: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    domicilio: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    condicion_iva: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    inicio_actividades: date
    ingresos_brutos: Annotated[str | None, Field(max_length=200)] = None

    # Facturación. La alícuota de IVA ya no se configura acá: la define cada
    # rubro (ver RubroOut / app/routers/rubros.py).
    tipo_comprobante: TipoComprobante
    punto_venta: Annotated[int, Field(gt=0, le=9999)]
    descripcion_item: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

    # Operación.
    anulacion_minutos_vendedor: Annotated[int, Field(gt=0, le=120)]

    # Recargo automático por transferencia (el de tarjeta se define por tipo
    # de tarjeta, ver TarjetaOut). No hay descuentos ni ajustes manuales.
    recargo_transferencia_porcentaje: Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]

    _ingresos_brutos_limpio = field_validator("ingresos_brutos", mode="before")(_texto_o_none)

    @field_validator("inicio_actividades")
    @classmethod
    def _no_futura(cls, valor: date) -> date:
        if valor > date.today():
            raise ValueError("La fecha de inicio de actividades no puede ser futura.")
        return valor


class ConfiguracionOut(ConfiguracionIn):
    # El CUIT no está en ConfiguracionIn (no se edita acá, ver app/models.py),
    # pero sí se muestra: por eso se agrega solo en la salida.
    cuit: str


# ---------------------------------------------------------------- tarjetas


TipoTarjeta = Literal["credito", "debito"]


class TarjetaCrear(BaseModel):
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    tipo: TipoTarjeta
    recargo_porcentaje: Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
    activa: bool = True
    orden: Annotated[int, Field(ge=0)]


class TarjetaEditar(TarjetaCrear):
    pass


class TarjetaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    tipo: TipoTarjeta
    recargo_porcentaje: Dinero
    activa: bool
    orden: int


# ---------------------------------------------------------------- rubros


class RubroCrear(BaseModel):
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    alicuota: Decimal
    descripcion_factura: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    activo: bool = True
    orden: Annotated[int, Field(ge=0)]
    es_predeterminado: bool = False

    @field_validator("alicuota")
    @classmethod
    def _alicuota_permitida(cls, valor: Decimal) -> Decimal:
        if valor not in ALICUOTAS_IVA_PERMITIDAS:
            permitidas = ", ".join(str(a) for a in sorted(ALICUOTAS_IVA_PERMITIDAS))
            raise ValueError(f"Alícuota no válida para ARCA. Valores permitidos: {permitidas}.")
        return valor.quantize(Decimal("0.01"))


class RubroEditar(RubroCrear):
    pass


class RubroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    alicuota: Dinero
    descripcion_factura: str
    activo: bool
    orden: int
    es_predeterminado: bool


# ---------------------------------------------------------------- ventas


# El único ajuste que existe es el recargo automático por tarjeta/transferencia
# que calcula el servidor solo, según la configuración vigente: no hay
# descuentos ni ajustes manuales.
TipoAjuste = Literal["recargo"]
OrigenAjuste = Literal["medio_pago"]


class VentaCrear(BaseModel):
    subtotal: DineroPositivo
    medio_pago: MedioPago
    id_cliente: uuid.UUID
    # Obligatorio (y solo válido) cuando medio_pago = "tarjeta": qué tarjeta
    # se usó, para saber qué recargo aplicarle.
    tarjeta_id: int | None = None
    # Siempre obligatorio: determina la alícuota de IVA y la descripción del
    # ítem en la factura.
    rubro_id: int


class VentaRegistradaOut(BaseModel):
    """Lo que recibe quien cobra al crear la venta: nunca datos fiscales (todavía
    ni se sabe si se va a facturar bien). Si el medio se factura, se entera de
    que salió bien cuando puede imprimir el comprobante, no antes.

    El subtotal y el ajuste sí viajan: no son datos fiscales, son la propia
    cuenta que el vendedor acaba de cobrar."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    id_cliente: uuid.UUID
    fecha_hora: FechaHora
    subtotal: Dinero
    ajuste_tipo: TipoAjuste | None
    ajuste_origen: OrigenAjuste | None
    ajuste_monto: Dinero | None
    ajuste_detalle: str | None
    total: Dinero
    medio_pago: MedioPago
    tarjeta_id: int | None
    tarjeta_nombre: str | None
    tarjeta_tipo: TipoTarjeta | None
    rubro_id: int | None
    rubro_nombre: str | None
    vendedor_id: int


EstadoAnulacion = Literal["pendiente", "emitida", "fallo", "sin_comprobante"]


class VentaResumenAnuladaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    total: Dinero
    medio_pago: MedioPago
    fecha_hora: FechaHora
    vendedor_id: int


class AnulacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    venta_id: int
    motivo: str
    usuario: UsuarioResumenOut
    fecha_hora: FechaHora
    estado: EstadoAnulacion
    tipo: int | None
    punto_venta: int | None
    numero: int | None
    cae: str | None
    cae_vencimiento: date | None
    error_detalle: str | None


class AnulacionConVentaOut(AnulacionOut):
    venta: VentaResumenAnuladaOut


class VentaOut(BaseModel):
    """Vista completa, solo para admin: acá sí importa el estado fiscal."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    id_cliente: uuid.UUID
    fecha_hora: FechaHora
    subtotal: Dinero
    ajuste_tipo: TipoAjuste | None
    ajuste_origen: OrigenAjuste | None
    ajuste_monto: Dinero | None
    ajuste_detalle: str | None
    total: Dinero
    medio_pago: MedioPago
    tarjeta_id: int | None
    tarjeta_nombre: str | None
    tarjeta_recargo_porcentaje: Dinero | None
    tarjeta_tipo: TipoTarjeta | None
    rubro_id: int | None
    rubro_nombre: str | None
    vendedor_id: int
    estado_arca: EstadoArca
    tipo_comprobante: str | None
    punto_venta: int | None
    numero_comprobante: int | None
    cae: str | None
    cae_vencimiento: date | None
    error_detalle: str | None
    anulada: bool
    anulada_por: int | None
    anulada_en: FechaHora | None
    anulacion: AnulacionOut | None


class VentaFiscalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    estado_arca: EstadoArca
    tipo_comprobante: str | None
    punto_venta: int | None
    numero_comprobante: int | None
    cae: str | None
    cae_vencimiento: date | None
    error_detalle: str | None


class VentaAnularIn(BaseModel):
    motivo: Annotated[str, Field(min_length=1, max_length=300)]

    _motivo_limpio = field_validator("motivo", mode="before")(_limpiar_espacios)


class EmisorOut(BaseModel):
    razon_social: str
    cuit: str
    domicilio: str
    condicion_iva: str
    inicio_actividades: str
    ingresos_brutos: str


class ComprobanteOut(BaseModel):
    emisor: EmisorOut
    nombre: str
    letra: str
    codigo: str
    punto_venta: int
    numero: int
    fecha: date
    receptor: str
    subtotal: Dinero
    ajuste_detalle: str | None
    total: Dinero
    iva_contenido: Dinero | None
    descripcion_item: str
    cae: str
    cae_vencimiento: date | None
    qr_url: str


# ---------------------------------------------------------------- gastos


class CategoriaGastoCrear(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=60)]

    _nombre_limpio = field_validator("nombre", mode="before")(_limpiar_espacios)


class CategoriaGastoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str


Descripcion = Annotated[str | None, Field(max_length=500)]


class GastoCrear(BaseModel):
    fecha: date | None = None  # si no viene, se usa hoy (hora de Argentina)
    monto: DineroPositivo
    categoria_id: int
    descripcion: Descripcion = None

    _descripcion_limpia = field_validator("descripcion", mode="before")(_texto_o_none)


class GastoActualizar(BaseModel):
    fecha: date
    monto: DineroPositivo
    categoria_id: int
    descripcion: Descripcion = None

    _descripcion_limpia = field_validator("descripcion", mode="before")(_texto_o_none)


class GastoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    monto: Dinero
    categoria: CategoriaGastoOut
    descripcion: str | None
    creado_por: int
    creado_en: FechaHora


# ---------------------------------------------------------------- compras

TipoImagen = Literal["image/jpeg", "image/png", "image/webp"]

# ~5 MB en bytes reales; en base64 pesa más, así que el límite del texto es mayor.
TAMANIO_MAXIMO_IMAGEN_BYTES = 5 * 1024 * 1024
NombreComercio = Annotated[str, Field(min_length=1, max_length=120)]


def _validar_imagen_base64(valor: str) -> str:
    import base64
    import binascii

    try:
        decodificado = base64.b64decode(valor, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("La imagen no es un base64 válido.") from None
    if len(decodificado) > TAMANIO_MAXIMO_IMAGEN_BYTES:
        raise ValueError("La imagen no puede pesar más de 5 MB.")
    if not decodificado:
        raise ValueError("La imagen no puede estar vacía.")
    return valor


class CompraCrear(BaseModel):
    fecha: date | None = None  # si no viene, se usa hoy (hora de Argentina)
    nombre_comercio: NombreComercio
    descripcion: Descripcion = None
    imagen: str
    imagen_tipo: TipoImagen

    _nombre_limpio = field_validator("nombre_comercio", mode="before")(_limpiar_espacios)
    _descripcion_limpia = field_validator("descripcion", mode="before")(_texto_o_none)
    _imagen_valida = field_validator("imagen")(_validar_imagen_base64)


class CompraActualizar(BaseModel):
    fecha: date
    nombre_comercio: NombreComercio
    descripcion: Descripcion = None

    _nombre_limpio = field_validator("nombre_comercio", mode="before")(_limpiar_espacios)
    _descripcion_limpia = field_validator("descripcion", mode="before")(_texto_o_none)


class CompraOut(BaseModel):
    """Sin el contenido de la imagen: para eso está GET /compras/{id}/imagen,
    así el listado no viaja pesado."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    nombre_comercio: str
    descripcion: str | None
    creado_por: int
    creado_en: FechaHora


Comentario = Annotated[str, Field(min_length=1, max_length=1000)]


class ComentarioComercioCrear(BaseModel):
    nombre_comercio: NombreComercio
    comentario: Comentario

    _nombre_limpio = field_validator("nombre_comercio", mode="before")(_limpiar_espacios)
    _comentario_limpio = field_validator("comentario", mode="before")(_limpiar_espacios)


class ComentarioComercioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_comercio: str
    comentario: str
    creado_por: int
    creado_en: FechaHora


# ---------------------------------------------------------------- resumen


class PorMedioPago(BaseModel):
    medio_pago: MedioPago
    monto: Dinero
    cantidad: int


class PorEstadoFiscal(BaseModel):
    estado_arca: EstadoArca
    monto: Dinero
    cantidad: int


class GastosPorCategoria(BaseModel):
    categoria_id: int
    categoria: str
    monto: Dinero
    cantidad: int


class VentasPorRubro(BaseModel):
    rubro_id: int | None
    rubro: str
    monto: Dinero
    cantidad: int


class VentasPorTarjeta(BaseModel):
    tarjeta_id: int | None
    tarjeta: str
    monto: Dinero
    cantidad: int


class VentasPorTipoTarjeta(BaseModel):
    # Nulo solo en ventas de antes de que existiera el tipo de tarjeta.
    tipo: TipoTarjeta | None
    monto: Dinero
    cantidad: int


class PuntoDeSerie(BaseModel):
    periodo: date  # el día, o el primer día del mes si la serie es mensual
    efectivo: Dinero
    tarjeta: Dinero
    transferencia: Dinero
    total: Dinero


class ResumenOut(BaseModel):
    desde: date
    hasta: date
    total_vendido: Dinero
    cantidad_ventas: int
    por_medio_pago: list[PorMedioPago]
    por_estado_fiscal: list[PorEstadoFiscal]
    total_gastos: Dinero
    resultado: Dinero
    gastos_por_categoria: list[GastosPorCategoria]
    agrupacion: Literal["dia", "mes"]
    serie: list[PuntoDeSerie]
    cantidad_anulaciones: int
    monto_anulaciones: Dinero
    total_recargos: Dinero
    ventas_por_rubro: list[VentasPorRubro]
    ventas_por_tarjeta: list[VentasPorTarjeta]
    ventas_por_tipo_tarjeta: list[VentasPorTipoTarjeta]


# ---------------------------------------------------------------- cierre de caja


class CierreTotalesOut(BaseModel):
    """Lo que calcula el sistema para un día: es lo que se ve en la
    previsualización, y también lo que queda "fotografiado" en cada cierre."""

    fecha: date
    total_general: Dinero
    total_efectivo: Dinero
    total_tarjeta: Dinero
    total_transferencia: Dinero
    cantidad_ventas: int
    cantidad_anulaciones: int
    monto_anulaciones: Dinero


class CierreCrear(BaseModel):
    fecha: date
    efectivo_contado: DineroNoNegativo
    observaciones: Descripcion = None

    _observaciones_limpias = field_validator("observaciones", mode="before")(_texto_o_none)


class CierreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    usuario: UsuarioResumenOut
    fecha_hora_cierre: FechaHora
    total_general: Dinero
    total_efectivo: Dinero
    total_tarjeta: Dinero
    total_transferencia: Dinero
    cantidad_ventas: int
    cantidad_anulaciones: int
    monto_anulaciones: Dinero
    efectivo_contado: Dinero
    diferencia: Dinero
    observaciones: str | None
    anulado: bool
    anulado_motivo: str | None
    anulado_por: int | None
    anulado_en: FechaHora | None


class CierreAnularIn(BaseModel):
    motivo: Annotated[str, Field(min_length=1, max_length=300)]

    _motivo_limpio = field_validator("motivo", mode="before")(_limpiar_espacios)


# ---------------------------------------------------------------- errores


def mensaje_error(error: dict) -> str:
    """Traduce un error de validación de pydantic a un mensaje en español."""
    tipo = error["type"]
    ctx = error.get("ctx") or {}
    if tipo == "missing":
        return "Este campo es obligatorio."
    if tipo == "string_too_short":
        minimo = ctx["min_length"]
        return f"Debe tener al menos {minimo} {'carácter' if minimo == 1 else 'caracteres'}."
    if tipo == "string_too_long":
        return f"No puede superar los {ctx['max_length']} caracteres."
    if tipo == "string_pattern_mismatch":
        if error["loc"][-1] == "codigo":
            return "Ingresá el código de 6 dígitos de la app, o uno de recuperación."
        return "El formato no es válido (solo minúsculas, números, punto, guion y guion bajo)."
    if tipo == "literal_error":
        return "Valor no permitido."
    if tipo == "json_invalid":
        return "El cuerpo del pedido no es un JSON válido."
    if tipo == "greater_than":
        return f"Debe ser mayor que {ctx['gt']}."
    if tipo == "greater_than_equal":
        return f"Debe ser mayor o igual que {ctx['ge']}."
    if tipo == "less_than_equal":
        return f"Debe ser menor o igual que {ctx['le']}."
    if tipo == "decimal_max_places":
        return f"No puede tener más de {ctx['decimal_places']} decimales."
    if tipo in ("decimal_max_digits", "decimal_whole_digits"):
        return "El número es demasiado grande."
    if tipo in ("decimal_parsing", "decimal_type", "finite_number"):
        return "Debe ser un número válido."
    if tipo in ("int_parsing", "int_type", "int_from_float"):
        return "Debe ser un número entero."
    if tipo.startswith("uuid"):
        return "Debe ser un UUID válido."
    if tipo.startswith("date") or tipo == "datetime_parsing":
        return "Fecha inválida: use el formato AAAA-MM-DD."
    if tipo in ("bool_parsing", "bool_type"):
        return "Debe ser verdadero o falso."
    if tipo == "value_error":
        return str(ctx.get("error", "Valor no válido."))
    return "Valor no válido."
