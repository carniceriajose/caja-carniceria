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
    creado_en: FechaHora


class LoginOut(BaseModel):
    token: str
    usuario: UsuarioOut


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


# ---------------------------------------------------------------- configuración


class ConfiguracionIn(BaseModel):
    facturar_efectivo: bool
    facturar_tarjeta: bool
    facturar_transferencia: bool


class ConfiguracionOut(ConfiguracionIn):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- ventas


class VentaCrear(BaseModel):
    total: DineroPositivo
    medio_pago: MedioPago
    id_cliente: uuid.UUID


class VentaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_cliente: uuid.UUID
    fecha_hora: FechaHora
    total: Dinero
    medio_pago: MedioPago
    vendedor_id: int
    estado_arca: EstadoArca
    tipo_comprobante: str | None
    punto_venta: int | None
    numero_comprobante: int | None
    cae: str | None
    cae_vencimiento: date | None
    error_detalle: str | None


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
    total: Dinero
    iva_contenido: Dinero | None
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
