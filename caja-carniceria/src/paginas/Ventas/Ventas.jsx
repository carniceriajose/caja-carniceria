import { Fragment, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/cliente";
import Cargando from "../../componentes/Cargando";
import Insignia, { ETIQUETA_ESTADO } from "../../componentes/Insignia";
import MensajeError from "../../componentes/MensajeError";
import { formatearDinero } from "../../utilidades/dinero";
import { hoyArgentina, rangosRapidos, formatearFechaHora } from "../../utilidades/fechas";
import { formatearNumeroComprobante } from "../../utilidades/comprobante";
import { ETIQUETA_MEDIO } from "../../utilidades/graficos";
import "./Ventas.css";

const POR_PAGINA = 15;

export default function Ventas() {
  const [desde, setDesde] = useState(rangosRapidos().mes.desde);
  const [hasta, setHasta] = useState(hoyArgentina());
  const [medio, setMedio] = useState("");
  const [estado, setEstado] = useState("");
  const [pagina, setPagina] = useState(1);

  const [datos, setDatos] = useState(null);
  const [nombres, setNombres] = useState({});
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  const [anulandoId, setAnulandoId] = useState(null);
  const [motivo, setMotivo] = useState("");
  const [errorAnular, setErrorAnular] = useState("");
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    api
      .get("/usuarios")
      .then((lista) => setNombres(Object.fromEntries(lista.map((u) => [u.id, u.nombre]))))
      .catch(() => setNombres({}));
  }, []);

  const rangoInvertido = desde && hasta && desde > hasta;

  const cargar = useCallback(async () => {
    if (rangoInvertido) return;
    setCargando(true);
    setError("");
    const parametros = new URLSearchParams({ pagina: String(pagina), por_pagina: String(POR_PAGINA) });
    if (desde) parametros.set("desde", desde);
    if (hasta) parametros.set("hasta", hasta);
    if (medio) parametros.set("medio_pago", medio);
    if (estado) parametros.set("estado_arca", estado);
    try {
      setDatos(await api.get(`/ventas?${parametros}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [pagina, desde, hasta, medio, estado, rangoInvertido]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function cambiarFiltro(setter) {
    return (evento) => {
      setPagina(1);
      setter(evento.target.value);
    };
  }

  function empezarAnulacion(venta) {
    setAnulandoId(venta.id);
    setMotivo("");
    setErrorAnular("");
  }

  function cancelarAnulacion() {
    setAnulandoId(null);
    setMotivo("");
    setErrorAnular("");
  }

  async function confirmarAnulacion(evento, venta) {
    evento.preventDefault();
    setErrorAnular("");
    setGuardando(true);
    try {
      const actualizada = await api.post(`/ventas/${venta.id}/anular`, { motivo });
      setDatos((actuales) => ({
        ...actuales,
        items: actuales.items.map((v) => (v.id === venta.id ? { ...v, ...actualizada } : v)),
      }));
      cancelarAnulacion();
    } catch (err) {
      setErrorAnular(err.message);
    } finally {
      setGuardando(false);
    }
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.total / POR_PAGINA)) : 1;

  return (
    <div className="ventas">
      <h1>Ventas</h1>

      <div className="ventas-filtros">
        <label>
          Desde
          <input type="date" value={desde} max={hoyArgentina()} onChange={cambiarFiltro(setDesde)} />
        </label>
        <label>
          Hasta
          <input type="date" value={hasta} max={hoyArgentina()} onChange={cambiarFiltro(setHasta)} />
        </label>
        <label>
          Medio de pago
          <select value={medio} onChange={cambiarFiltro(setMedio)}>
            <option value="">Todos</option>
            {Object.entries(ETIQUETA_MEDIO).map(([valor, etiqueta]) => (
              <option key={valor} value={valor}>
                {etiqueta}
              </option>
            ))}
          </select>
        </label>
        <label>
          Estado fiscal
          <select value={estado} onChange={cambiarFiltro(setEstado)}>
            <option value="">Todos</option>
            {Object.entries(ETIQUETA_ESTADO).map(([valor, etiqueta]) => (
              <option key={valor} value={valor}>
                {etiqueta}
              </option>
            ))}
          </select>
        </label>
      </div>

      {rangoInvertido && <MensajeError mensaje="La fecha 'desde' no puede ser posterior a 'hasta'." />}
      {!rangoInvertido && cargando && <Cargando texto="Cargando ventas…" />}
      {!rangoInvertido && !cargando && error && <MensajeError mensaje={error} onReintentar={cargar} />}

      {!rangoInvertido && !cargando && !error && datos && (
        <>
          <div className="ventas-tabla tabla-apilable">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Vendedor</th>
                  <th>Medio</th>
                  <th className="ventas-numerico">Monto</th>
                  <th>Estado fiscal</th>
                  <th>Comprobante</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {datos.items.length === 0 && (
                  <tr>
                    <td colSpan={7} className="ventas-vacio">
                      No hay ventas con estos filtros.
                    </td>
                  </tr>
                )}
                {datos.items.map((venta) => {
                  const puedeAnularse = !venta.anulada && venta.estado_arca !== "pendiente";
                  const vaAEmitirNotaDeCredito = venta.estado_arca === "facturada";
                  return (
                    <Fragment key={venta.id}>
                      <tr className={venta.anulada ? "ventas-fila-anulada" : ""}>
                        <td data-label="Fecha" className={venta.anulada ? "ventas-texto-anulado" : ""}>
                          {formatearFechaHora(venta.fecha_hora)}
                        </td>
                        <td data-label="Vendedor" className={venta.anulada ? "ventas-texto-anulado" : ""}>
                          {nombres[venta.vendedor_id] ?? `#${venta.vendedor_id}`}
                        </td>
                        <td data-label="Medio" className={venta.anulada ? "ventas-texto-anulado" : ""}>
                          {ETIQUETA_MEDIO[venta.medio_pago]}
                        </td>
                        <td
                          data-label="Monto"
                          className={`ventas-numerico ${venta.anulada ? "ventas-texto-anulado" : ""}`}
                          title={venta.ajuste_detalle ?? undefined}
                        >
                          {formatearDinero(venta.total)}
                          {venta.ajuste_detalle && <span className="ventas-insignia-ajuste">ajuste</span>}
                        </td>
                        <td data-label="Estado fiscal">
                          <Insignia estado={venta.estado_arca} anulada={venta.anulada} />
                        </td>
                        <td data-label="Comprobante">
                          {venta.numero_comprobante
                            ? formatearNumeroComprobante(venta.punto_venta, venta.numero_comprobante)
                            : "—"}
                        </td>
                        <td data-label="" className="ventas-acciones">
                          <Link to={`/admin/ventas/${venta.id}`} className="ventas-enlace">
                            Ver detalle
                          </Link>
                          {puedeAnularse && (
                            <button
                              type="button"
                              className="ventas-boton-anular"
                              onClick={() =>
                                anulandoId === venta.id ? cancelarAnulacion() : empezarAnulacion(venta)
                              }
                            >
                              Anular
                            </button>
                          )}
                        </td>
                      </tr>
                      {anulandoId === venta.id && (
                        <tr className="ventas-fila-detalle">
                          <td colSpan={7}>
                            <form className="ventas-form-anular" onSubmit={(e) => confirmarAnulacion(e, venta)}>
                              <MensajeError mensaje={errorAnular} />
                              {vaAEmitirNotaDeCredito && (
                                <p className="alerta alerta-aviso">
                                  Se va a emitir una nota de crédito en ARCA. Esta operación no se puede
                                  deshacer.
                                </p>
                              )}
                              <p className="ventas-resumen-anular">
                                {ETIQUETA_MEDIO[venta.medio_pago]} · {formatearDinero(venta.total)} ·{" "}
                                {formatearFechaHora(venta.fecha_hora)}
                              </p>
                              <label>
                                Motivo de la anulación
                                <input
                                  type="text"
                                  value={motivo}
                                  onChange={(e) => setMotivo(e.target.value)}
                                  disabled={guardando}
                                  autoFocus
                                  required
                                />
                              </label>
                              <div className="ventas-form-botones">
                                <button type="submit" disabled={guardando || motivo.trim().length === 0}>
                                  {guardando ? "Anulando…" : "Confirmar anulación"}
                                </button>
                                <button
                                  type="button"
                                  className="ventas-boton-secundario"
                                  onClick={cancelarAnulacion}
                                  disabled={guardando}
                                >
                                  Cancelar
                                </button>
                              </div>
                            </form>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPaginas > 1 && (
            <div className="ventas-paginado">
              <button type="button" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                Anterior
              </button>
              <span>
                Página {pagina} de {totalPaginas}
              </span>
              <button type="button" disabled={pagina >= totalPaginas} onClick={() => setPagina((p) => p + 1)}>
                Siguiente
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
