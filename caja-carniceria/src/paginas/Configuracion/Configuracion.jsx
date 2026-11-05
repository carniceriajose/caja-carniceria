import { useCallback, useEffect, useState } from "react";
import { useDatos } from "../../context/DatosContext";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import TituloSeccion from "../../componentes/TituloSeccion";
import TarjetasConfiguracion from "./TarjetasConfiguracion";
import RubrosConfiguracion from "./RubrosConfiguracion";
import { formatearCuit } from "../../utilidades/fechas";
import { IconoComercio, IconoDocumento, IconoEngranaje, IconoTransferencia } from "../../componentes/Iconos";
import "./Configuracion.css";

// Los campos que se mandan en el PUT (todo lo de ConfiguracionIn, nunca el CUIT).
function formularioDesde(configuracion) {
  return {
    facturar_efectivo: configuracion.facturar_efectivo,
    facturar_tarjeta: configuracion.facturar_tarjeta,
    facturar_transferencia: configuracion.facturar_transferencia,
    razon_social: configuracion.razon_social,
    domicilio: configuracion.domicilio,
    condicion_iva: configuracion.condicion_iva,
    inicio_actividades: configuracion.inicio_actividades,
    ingresos_brutos: configuracion.ingresos_brutos ?? "",
    tipo_comprobante: configuracion.tipo_comprobante,
    punto_venta: configuracion.punto_venta,
    descripcion_item: configuracion.descripcion_item,
    anulacion_minutos_vendedor: configuracion.anulacion_minutos_vendedor,
    recargo_transferencia_porcentaje: configuracion.recargo_transferencia_porcentaje,
  };
}

export default function Configuracion() {
  const { configuracion, cargarConfiguracion, guardarConfiguracion } = useDatos();
  const [formulario, setFormulario] = useState(null);
  const [cuit, setCuit] = useState("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [errorGuardar, setErrorGuardar] = useState("");
  const [mensajeGuardado, setMensajeGuardado] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      const datos = await cargarConfiguracion();
      setFormulario(formularioDesde(datos));
      setCuit(datos.cuit);
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [cargarConfiguracion]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function cambiar(campo, valor) {
    setFormulario((actual) => ({ ...actual, [campo]: valor }));
  }

  async function alGuardar(evento) {
    evento.preventDefault();
    setErrorGuardar("");
    setMensajeGuardado("");
    setGuardando(true);
    try {
      const cuerpo = {
        ...formulario,
        tipo_comprobante: Number(formulario.tipo_comprobante),
        punto_venta: Number(formulario.punto_venta),
        anulacion_minutos_vendedor: Number(formulario.anulacion_minutos_vendedor),
        ingresos_brutos: formulario.ingresos_brutos.trim() || null,
        recargo_transferencia_porcentaje: String(formulario.recargo_transferencia_porcentaje),
      };
      const actualizada = await guardarConfiguracion(cuerpo);
      setFormulario(formularioDesde(actualizada));
      setMensajeGuardado("Guardado. Se va a usar desde la próxima factura.");
    } catch (err) {
      setErrorGuardar(err.message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="configuracion">
      <h1>Configuración</h1>

      {cargando && <Cargando texto="Cargando configuración…" />}
      {!cargando && error && <MensajeError mensaje={error} onReintentar={cargar} />}

      {!cargando && !error && formulario && (
        <form className="configuracion-formulario" onSubmit={alGuardar}>
          <section className="configuracion-seccion">
            <TituloSeccion Icono={IconoComercio}>Datos del comercio</TituloSeccion>
            <p className="configuracion-ayuda">Salen impresos en el encabezado del ticket.</p>

            <div className="configuracion-fila">
              <label>
                Razón social
                <input
                  type="text"
                  value={formulario.razon_social}
                  onChange={(e) => cambiar("razon_social", e.target.value)}
                  disabled={guardando}
                  required
                />
              </label>
              <label>
                CUIT
                <input type="text" value={formatearCuit(cuit)} disabled title="No se edita acá: es el mismo con el que el sistema se autentica ante ARCA." />
              </label>
            </div>

            <label>
              Domicilio
              <input
                type="text"
                value={formulario.domicilio}
                onChange={(e) => cambiar("domicilio", e.target.value)}
                disabled={guardando}
                required
              />
            </label>

            <div className="configuracion-fila">
              <label>
                Condición frente al IVA
                <input
                  type="text"
                  value={formulario.condicion_iva}
                  onChange={(e) => cambiar("condicion_iva", e.target.value)}
                  disabled={guardando}
                  required
                />
              </label>
              <label>
                Inicio de actividades
                <input
                  type="date"
                  value={formulario.inicio_actividades}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={(e) => cambiar("inicio_actividades", e.target.value)}
                  disabled={guardando}
                  required
                />
              </label>
            </div>

            <label>
              Ingresos brutos (opcional)
              <input
                type="text"
                value={formulario.ingresos_brutos}
                onChange={(e) => cambiar("ingresos_brutos", e.target.value)}
                disabled={guardando}
                maxLength={200}
              />
            </label>
          </section>

          <section className="configuracion-seccion">
            <TituloSeccion Icono={IconoDocumento}>Facturación</TituloSeccion>
            <p className="configuracion-ayuda">
              La alícuota de IVA y la descripción del ítem se definen por rubro, más abajo.
            </p>

            <span className="configuracion-etiqueta-grupo">Qué medios se facturan</span>
            <div className="configuracion-opciones">
              <label className="configuracion-opcion">
                <input
                  type="checkbox"
                  checked={formulario.facturar_efectivo}
                  disabled={guardando}
                  onChange={(e) => cambiar("facturar_efectivo", e.target.checked)}
                />
                Efectivo
              </label>
              <label className="configuracion-opcion">
                <input
                  type="checkbox"
                  checked={formulario.facturar_tarjeta}
                  disabled={guardando}
                  onChange={(e) => cambiar("facturar_tarjeta", e.target.checked)}
                />
                Tarjeta
              </label>
              <label className="configuracion-opcion">
                <input
                  type="checkbox"
                  checked={formulario.facturar_transferencia}
                  disabled={guardando}
                  onChange={(e) => cambiar("facturar_transferencia", e.target.checked)}
                />
                Transferencia
              </label>
            </div>

            <div className="configuracion-fila">
              <label>
                Tipo de comprobante
                <select
                  value={formulario.tipo_comprobante}
                  onChange={(e) => cambiar("tipo_comprobante", e.target.value)}
                  disabled={guardando}
                >
                  <option value={11}>Factura C</option>
                  <option value={6}>Factura B</option>
                </select>
              </label>
              <label>
                Punto de venta
                <input
                  type="number"
                  min={1}
                  max={9999}
                  value={formulario.punto_venta}
                  onChange={(e) => cambiar("punto_venta", e.target.value)}
                  disabled={guardando}
                  required
                />
              </label>
            </div>

            <label>
              Descripción de respaldo (solo para ventas de antes de los rubros)
              <input
                type="text"
                value={formulario.descripcion_item}
                onChange={(e) => cambiar("descripcion_item", e.target.value)}
                disabled={guardando}
                placeholder="Carnicería"
                required
              />
            </label>
          </section>

          <section className="configuracion-seccion">
            <TituloSeccion Icono={IconoEngranaje}>Operación</TituloSeccion>
            <label className="configuracion-campo-corto">
              Minutos para que el vendedor pueda anular su última venta
              <input
                type="number"
                min={1}
                max={120}
                value={formulario.anulacion_minutos_vendedor}
                onChange={(e) => cambiar("anulacion_minutos_vendedor", e.target.value)}
                disabled={guardando}
                required
              />
            </label>
          </section>

          <section className="configuracion-seccion">
            <TituloSeccion Icono={IconoTransferencia}>Recargo por transferencia</TituloSeccion>
            <p className="configuracion-ayuda">
              En efectivo el precio queda igual. El recargo por tarjeta se define por tipo de tarjeta, más
              abajo. Se aplica a las ventas nuevas: cambiar esto nunca afecta a las que ya se cobraron.
            </p>

            <label className="configuracion-campo-corto">
              Recargo por transferencia (%)
              <input
                type="number"
                min={0}
                max={100}
                step="0.01"
                value={formulario.recargo_transferencia_porcentaje}
                onChange={(e) => cambiar("recargo_transferencia_porcentaje", e.target.value)}
                disabled={guardando}
                required
              />
            </label>
          </section>

          <div className="configuracion-guardar-barra">
            <button type="submit" className="configuracion-boton-guardar" disabled={guardando}>
              {guardando ? "Guardando…" : "Guardar cambios"}
            </button>
            <MensajeError mensaje={errorGuardar} />
            {mensajeGuardado && <p className="configuracion-guardado">{mensajeGuardado}</p>}
          </div>
        </form>
      )}

      {!cargando && !error && <RubrosConfiguracion />}
      {!cargando && !error && <TarjetasConfiguracion />}
    </div>
  );
}
