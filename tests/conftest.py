import os

# Variables de entorno de prueba: tienen que estar antes de importar la app.
os.environ["JWT_SECRET"] = "clave-solo-para-pruebas-0123456789abcdef"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ENTORNO"] = "desarrollo"
os.environ["CORS_ORIGENES"] = "http://localhost:5173"
os.environ["JWT_MINUTOS"] = "720"
os.environ["ARCA_TAREAS_DE_FONDO"] = "false"
os.environ["ARCA_CUIT"] = "20000000001"
os.environ["ARCA_PUNTO_VENTA"] = "1"
os.environ["ARCA_TIPO_COMPROBANTE"] = "11"
os.environ["ARCA_ALICUOTA_IVA"] = "21"
os.environ["ARCA_RAZON_SOCIAL"] = "Carnicería de prueba"
os.environ["ARCA_DOMICILIO"] = "Calle Falsa 123, Localidad"
os.environ["ARCA_CONDICION_IVA"] = "Responsable Inscripto"
os.environ["ARCA_INICIO_ACTIVIDADES"] = "01/01/2020"
os.environ["ARCA_INGRESOS_BRUTOS"] = ""
# Sin certificado: los tests nunca tienen que tocar la red real de ARCA, sin
# importar lo que haya configurado en el .env de desarrollo de la máquina.
os.environ["ARCA_CERT"] = ""
os.environ["ARCA_KEY"] = ""
os.environ["ARCA_CERT_BASE64"] = ""
os.environ["ARCA_KEY_BASE64"] = ""

import uuid  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import crear_motor, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, CategoriaGasto, Gasto, Usuario, Venta  # noqa: E402
from app.security import hashear_password, limitador  # noqa: E402
from tests.utiles import PASSWORD_ADMIN, con_token  # noqa: E402


@pytest.fixture()
def motor_pruebas():
    motor = crear_motor("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture()
def sesion_pruebas(motor_pruebas):
    return sessionmaker(bind=motor_pruebas, expire_on_commit=False)


@pytest.fixture()
def cliente(sesion_pruebas, monkeypatch):
    def _get_db():
        with sesion_pruebas() as db:
            yield db

    app.dependency_overrides[get_db] = _get_db
    # La tarea de fondo que emite la factura abre su propia sesión (la del
    # pedido ya se cerró); tiene que apuntar a la misma base que el resto del test.
    monkeypatch.setattr("app.routers.ventas.SesionLocal", sesion_pruebas)
    limitador.reiniciar()
    yield TestClient(app)
    app.dependency_overrides.clear()
    limitador.reiniciar()


@pytest.fixture()
def crear_usuario(sesion_pruebas):
    """Inserta un usuario directo en la base y devuelve su id."""

    def _crear(usuario, password, rol="vendedor", activo=True, nombre=None):
        with sesion_pruebas() as db:
            nuevo = Usuario(
                nombre=nombre or usuario.capitalize(),
                usuario=usuario,
                password_hash=hashear_password(password),
                rol=rol,
                activo=activo,
            )
            db.add(nuevo)
            db.commit()
            return nuevo.id

    return _crear


@pytest.fixture()
def crear_venta_db(sesion_pruebas):
    """Inserta una venta directo en la base (con la fecha en UTC que se quiera) y devuelve su id."""

    def _crear(
        vendedor_id,
        total,
        medio_pago="efectivo",
        fecha_hora=None,
        estado_arca="no_aplica",
        numero_comprobante=None,
        error_detalle=None,
        tipo_comprobante=None,
        punto_venta=None,
        cae=None,
        cae_vencimiento=None,
        respuesta_fiscal=None,
    ):
        if estado_arca == "fallo" and error_detalle is None:
            error_detalle = "Error de prueba."
        with sesion_pruebas() as db:
            venta = Venta(
                id_cliente=uuid.uuid4(),
                total=Decimal(total),
                medio_pago=medio_pago,
                vendedor_id=vendedor_id,
                estado_arca=estado_arca,
                numero_comprobante=numero_comprobante,
                error_detalle=error_detalle,
                tipo_comprobante=tipo_comprobante,
                punto_venta=punto_venta,
                cae=cae,
                cae_vencimiento=cae_vencimiento,
                respuesta_fiscal=respuesta_fiscal,
            )
            if fecha_hora is not None:
                venta.fecha_hora = fecha_hora
            db.add(venta)
            db.commit()
            return venta.id

    return _crear


@pytest.fixture()
def crear_categoria_db(sesion_pruebas):
    def _crear(nombre):
        with sesion_pruebas() as db:
            categoria = CategoriaGasto(nombre=nombre)
            db.add(categoria)
            db.commit()
            return categoria.id

    return _crear


@pytest.fixture()
def crear_gasto_db(sesion_pruebas):
    def _crear(creado_por, monto, categoria_id, fecha, descripcion=None):
        with sesion_pruebas() as db:
            gasto = Gasto(
                monto=Decimal(monto),
                categoria_id=categoria_id,
                fecha=fecha,
                descripcion=descripcion,
                creado_por=creado_por,
            )
            db.add(gasto)
            db.commit()
            return gasto.id

    return _crear


@pytest.fixture()
def iniciar_sesion(cliente):
    """Hace login y devuelve el token (falla si el login no da 200)."""

    def _login(usuario, password):
        respuesta = cliente.post("/auth/login", json={"usuario": usuario, "password": password})
        assert respuesta.status_code == 200, respuesta.text
        return respuesta.json()["token"]

    return _login


@pytest.fixture()
def admin_id(crear_usuario):
    return crear_usuario("admin", PASSWORD_ADMIN, rol="admin")


@pytest.fixture()
def headers_admin(admin_id, iniciar_sesion):
    return con_token(iniciar_sesion("admin", PASSWORD_ADMIN))
