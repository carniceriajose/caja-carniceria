import os

# Variables de entorno de prueba: tienen que estar antes de importar la app.
os.environ["JWT_SECRET"] = "clave-solo-para-pruebas-0123456789abcdef"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ENTORNO"] = "desarrollo"
os.environ["CORS_ORIGENES"] = "http://localhost:5173"
os.environ["JWT_MINUTOS_ADMIN"] = "120"
os.environ["JWT_MINUTOS_VENDEDOR"] = "720"
os.environ["ARCA_TAREAS_DE_FONDO"] = "false"
# Explícito acá (no solo el default): los tests no tienen que depender de lo
# que diga el .env real de la máquina de quien los corre.
os.environ["ARCA_ENTORNO"] = "homologacion"
os.environ["ARCA_CUIT"] = "20000000001"
os.environ["ARCA_PUNTO_VENTA"] = "1"
os.environ["ARCA_TIPO_COMPROBANTE"] = "11"
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
from app.models import Base, CategoriaGasto, Gasto, Rubro, Tarjeta, Usuario, Venta  # noqa: E402
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
    # Una tarjeta de prueba, siempre con id 1: así una venta en "tarjeta" no
    # necesita que cada test cree la suya para poder elegir una. Lo mismo con
    # dos rubros (los mismos que siembra la migración real): "Carne" (id 1,
    # predeterminado) y "Embutidos" (id 2).
    with sesion_pruebas() as db:
        db.add(
            Tarjeta(
                id=1, nombre="Tarjeta de prueba", tipo="credito", recargo_porcentaje=Decimal("0"),
                activa=True, orden=1,
            )
        )
        db.add(
            Rubro(
                id=1, nombre="Carne", alicuota=Decimal("10.5"), descripcion_factura="Venta de carne",
                activo=True, orden=1, es_predeterminado=True,
            )
        )
        db.add(
            Rubro(
                id=2, nombre="Embutidos", alicuota=Decimal("21"), descripcion_factura="Venta de embutidos",
                activo=True, orden=2, es_predeterminado=False,
            )
        )
        db.commit()
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
        subtotal=None,
        ajuste_tipo=None,
        ajuste_origen=None,
        ajuste_monto=None,
        ajuste_detalle=None,
        tarjeta_id=None,
        tarjeta_nombre=None,
        tarjeta_recargo_porcentaje=None,
        tarjeta_tipo=None,
        rubro_id=None,
        rubro_nombre=None,
        descripcion_factura=None,
        alicuota_iva=None,
    ):
        if estado_arca == "fallo" and error_detalle is None:
            error_detalle = "Error de prueba."
        with sesion_pruebas() as db:
            venta = Venta(
                id_cliente=uuid.uuid4(),
                subtotal=Decimal(subtotal) if subtotal is not None else Decimal(total),
                total=Decimal(total),
                ajuste_tipo=ajuste_tipo,
                ajuste_origen=ajuste_origen,
                ajuste_monto=Decimal(ajuste_monto) if ajuste_monto is not None else None,
                ajuste_detalle=ajuste_detalle,
                tarjeta_id=tarjeta_id,
                tarjeta_nombre=tarjeta_nombre,
                tarjeta_recargo_porcentaje=(
                    Decimal(tarjeta_recargo_porcentaje) if tarjeta_recargo_porcentaje is not None else None
                ),
                tarjeta_tipo=tarjeta_tipo,
                rubro_id=rubro_id,
                rubro_nombre=rubro_nombre,
                descripcion_factura=descripcion_factura,
                alicuota_iva=Decimal(alicuota_iva) if alicuota_iva is not None else None,
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
def crear_tarjeta_db(sesion_pruebas):
    def _crear(nombre, recargo_porcentaje="0", activa=True, orden=1, tipo="credito"):
        with sesion_pruebas() as db:
            tarjeta = Tarjeta(
                nombre=nombre, tipo=tipo, recargo_porcentaje=Decimal(recargo_porcentaje), activa=activa, orden=orden
            )
            db.add(tarjeta)
            db.commit()
            return tarjeta.id

    return _crear


@pytest.fixture()
def crear_rubro_db(sesion_pruebas):
    def _crear(nombre, alicuota="10.5", descripcion_factura=None, activo=True, orden=1, es_predeterminado=False):
        with sesion_pruebas() as db:
            if es_predeterminado:
                anterior = db.query(Rubro).filter_by(es_predeterminado=True).first()
                if anterior is not None:
                    anterior.es_predeterminado = False
                    db.flush()
            rubro = Rubro(
                nombre=nombre,
                alicuota=Decimal(alicuota),
                descripcion_factura=descripcion_factura or f"Venta de {nombre.lower()}",
                activo=activo,
                orden=orden,
                es_predeterminado=es_predeterminado,
            )
            db.add(rubro)
            db.commit()
            return rubro.id

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
