"""Prueba de punta a punta contra ARCA (usa el entorno de ARCA_ENTORNO del .env,
normalmente homologación): login en WSAA, FEDummy, último autorizado y una
factura de $100 a consumidor final. Muestra el CAE obtenido.

Uso (desde la carpeta del proyecto, con el entorno virtual activado):
    python -m scripts.probar_arca
"""

import sys
from decimal import Decimal

from app.arca import wsaa, wsfe
from app.arca.servicio import armar_detalle, calcular_neto_iva
from app.config import get_settings
from app.db import SesionLocal, motor
from app.fechas import hoy_argentina
from app.models import Base
from app.rubros import obtener_rubro_predeterminado


def main() -> int:
    settings = get_settings()
    print(f"Entorno: {settings.arca_entorno}")
    print(f"CUIT: {settings.arca_cuit}")
    print(f"Punto de venta: {settings.arca_punto_venta}  Tipo de comprobante: {settings.arca_tipo_comprobante}")

    if not wsaa.hay_certificado_configurado():
        print("No se encontró el certificado o la clave configurados (ARCA_CERT/ARCA_KEY o sus *_BASE64).")
        return 1

    Base.metadata.create_all(motor)  # por si se corre contra una base nueva

    with SesionLocal() as db:
        print("\n--- WSAA: pidiendo el ticket de acceso ---")
        ticket = wsaa.obtener_o_renovar_ticket(db)
        if ticket is None:
            print("No se pudo obtener el ticket de acceso. Revise los logs.")
            return 1
        print(f"Ticket obtenido, vence: {ticket.vence_en.isoformat()}")

        print("\n--- FEDummy: estado de ARCA ---")
        try:
            estado = wsfe.verificar_estado()
            print(estado)
        except Exception as error:
            print(f"No se pudo consultar FEDummy: {error}")
            return 1

        tipo = settings.arca_tipo_comprobante
        punto_venta = settings.arca_punto_venta

        print("\n--- FECompUltimoAutorizado ---")
        try:
            ultimo = wsfe.consultar_ultimo_autorizado(ticket, punto_venta, tipo)
        except Exception as error:
            print(f"No se pudo consultar el último autorizado: {error}")
            return 1
        numero = ultimo + 1
        print(f"Último autorizado: {ultimo}. Se va a pedir el número {numero}.")

        rubro = obtener_rubro_predeterminado(db)
        if rubro is None:
            print("No hay un rubro predeterminado cargado (correr las migraciones de supabase).")
            return 1
        alicuota = rubro.alicuota
        print(f"Rubro predeterminado: {rubro.nombre} ({alicuota}%)")

        total = Decimal("100.00")
        neto, iva = calcular_neto_iva(total, tipo, alicuota)
        fecha = hoy_argentina().strftime("%Y%m%d")
        detalle = armar_detalle(numero, fecha, total, neto, iva, tipo, alicuota)
        print(f"\nTotal: {total}  Neto: {neto}  IVA: {iva}")

        print("\n--- FECAESolicitar: emitiendo la factura de prueba ---")
        try:
            respuesta = wsfe.solicitar_cae(ticket, punto_venta, tipo, detalle)
        except TimeoutError as error:
            print(f"No llegó respuesta a tiempo: {error}")
            return 1
        except Exception as error:
            print(f"ARCA rechazó el pedido: {error}")
            return 1

        detalle_resp = (respuesta.get("FeDetResp") or {}).get("FECAEDetResponse") or [{}]
        resultado = detalle_resp[0]
        print(f"\nResultado: {resultado.get('Resultado')}")
        if resultado.get("Resultado") == "A":
            print(f"CAE: {resultado.get('CAE')}")
            print(f"Vencimiento del CAE: {resultado.get('CAEFchVto')}")
            print(f"Comprobante: {tipo}-{punto_venta:04d}-{numero:08d}")
            return 0

        observaciones = (resultado.get("Observaciones") or {}).get("Obs") or []
        for obs in observaciones:
            print(f"  Observación {obs.get('Code')}: {obs.get('Msg')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
