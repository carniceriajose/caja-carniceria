from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./dev.db"
    jwt_secret: str = Field(min_length=32)
    # Sesión más corta para admin: menos ventana si dejan la sesión abierta en
    # el mostrador. El vendedor dura un turno completo.
    jwt_minutos_admin: int = Field(default=120, gt=0)
    jwt_minutos_vendedor: int = Field(default=720, gt=0)
    # Ventana en la que el vendedor puede anular su propia última venta sin
    # pedirle a un administrador.
    anulacion_minutos_vendedor: int = Field(default=10, gt=0)
    cors_origenes: str = "http://localhost:5173"
    entorno: Literal["desarrollo", "produccion"] = "desarrollo"

    # --- ARCA (facturación electrónica) ---
    arca_entorno: Literal["homologacion", "produccion"] = "homologacion"
    arca_cuit: str = ""
    # En desarrollo, el certificado y la clave se leen de estos archivos. En
    # producción se recomienda cargarlos desde las variables *_BASE64 (el
    # contenido del .crt/.key codificado en base64), sin tocar el disco.
    arca_cert: str | None = None
    arca_key: str | None = None
    arca_cert_base64: str | None = None
    arca_key_base64: str | None = None
    arca_punto_venta: int = Field(default=1, gt=0)
    arca_tipo_comprobante: int = 11  # 11 = Factura C, 6 = Factura B
    # Datos del emisor que salen impresos en el comprobante (el CUIT es ARCA_CUIT).
    arca_razon_social: str = ""
    arca_domicilio: str = ""
    arca_condicion_iva: str = ""
    arca_inicio_actividades: str = ""
    arca_ingresos_brutos: str = ""
    # Los reintentos automáticos se apagan en los tests para no lanzar tareas de fondo.
    arca_tareas_de_fondo: bool = True

    @field_validator("database_url")
    @classmethod
    def _usar_psycopg3(cls, valor: str) -> str:
        valor = valor.strip()
        for prefijo in ("postgresql://", "postgres://"):
            if valor.startswith(prefijo):
                return "postgresql+psycopg://" + valor[len(prefijo):]
        return valor

    @property
    def origenes_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origenes.split(",") if o.strip()]

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "produccion"

    @property
    def es_arca_produccion(self) -> bool:
        return self.arca_entorno == "produccion"


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as error:
        variables = ", ".join(sorted({str(e["loc"][0]).upper() for e in error.errors()}))
        raise RuntimeError(
            f"Configuración inválida. Revise estas variables del .env: {variables}. "
            "JWT_SECRET es obligatoria y debe tener al menos 32 caracteres; "
            "ENTORNO debe ser 'desarrollo' o 'produccion'."
        ) from None
