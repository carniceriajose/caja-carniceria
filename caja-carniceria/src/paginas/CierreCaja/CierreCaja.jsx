import { Fragment, useCallback, useEffect, useState } from "react";
import { api, descargarArchivo } from "../../api/cliente";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import TituloSeccion from "../../componentes/TituloSeccion";
import { IconoReloj } from "../../componentes/Iconos";
import { formatearDinero } from "../../utilidades/dinero";
import { formatearFecha, formatearFechaHora, hoyArgentina } from "../../utilidades/fechas";
import "./CierreCaja.css";

const POR_PAGINA = 15;

// Igual que en la caja: nunca pasa por Number, solo texto sobre centavos.
function aCentavos(texto) {
  if (!texto) return 0;
  const limpio = texto.replace(",", ".").trim();
  if (!/^\d{0,10}(\.\d{1,2})?$/.test(limpio)) return null;
  return Math.round(parseFloat(limpio) * 100);
}

function deCentavos(centavos) {
  return (centavos / 100).toFixed(2);
}

export default function CierreCaja() {
  const [fecha, setFecha] = useState(hoyArgentina());
  const [previsualizacion, setPrevisualizacion] = useState(null);
  const [cargandoPrevisualizacion, setCargandoPrevisualizacion] = useState(true);
  const [errorPrevisualizacion, setErrorPrevisualizacion] = useState("");

  const [efectivoContado, setEfectivoContado] = useState("");
  const [observaciones, setObservaciones] = useState("");
  const [cerrando, setCerrando] = useState(false);
  const [errorCerrar, setErrorCerrar] = useState("");

  const [historial, setHistorial] = useState(null);
  const [paginaHistorial, setPaginaHistorial] = useState(1);
  const [cargandoHistorial, setCargandoHistorial] = useState(true);
  const [errorHistorial, setErrorHistorial] = useState("");

  const [anulandoId, setAnulandoId] = useState(null);
  const [motivoAnular, setMotivoAnular] = useState("");
  const [errorAnular, setErrorAnular] = useState("");
  const [guardandoAnular, setGuardandoAnular] = useState(false);

  const [descargandoId, setDescargandoId] = useState(null);

  const cargarPrevisualizacion = useCallback(async () => {
    setCargandoPrevisualizacion(true);
    setErrorPrevisualizacion("");
    try {
      setPrevisualizacion(await api.get(`/cierres/previsualizacion?fecha=${fecha}`));
    } catch (err) {
      setErrorPrevisualizacion(err.message);
    } finally {
      setCargandoPrevisualizacion(false);
    }
  }, [fecha]);

  useEffect(() => {
    cargarPrevisualizacion();
    setEfectivoContado("");
    setObservaciones("");
    setErrorCerrar("");
  }, [cargarPrevisualizacion]);

  const cargarHistorial = useCallback(async () => {
    setCargandoHistorial(true);
    setErrorHistorial("");
    try {
      setHistorial(
        await api.get(`/cierres?pagina=${paginaHistorial}&por_pagina=${POR_PAGINA}`)
      );
    } catch (err) {
      setErrorHistorial(err.message);
    } finally {
      setCargandoHistorial(false);
    }
  }, [paginaHistorial]);

  useEffect(() => {
    cargarHistorial();
  }, [cargarHistorial]);

  const centavosContado = aCentavos(efectivoContado);
  const efectivoContadoValido = centavosContado !== null;
  const centavosSistema = previsualizacion ? aCentavos(previsualizacion.total_efectivo) : 0;
  const diferenciaCentavos = efectivoContadoValido ? centavosContado - centavosSistema : null;

  async function cerrarElDia(evento) {
    evento.preventDefault();
    if (!efectivoContadoValido) {
      setErrorCerrar("Ingresá el efectivo contado, con hasta 2 decimales.");
      return;
    }
    setErrorCerrar("");
    setCerrando(true);
    try {
      await api.post("/cierres", {
        fecha,
        efectivo_contado: deCentavos(centavosContado),
        observaciones: observaciones.trim() || null,
      });
      setPaginaHistorial(1);
      await Promise.all([cargarPrevisualizacion(), cargarHistorial()]);
    } catch (err) {
      setErrorCerrar(err.message);
    } finally {
      setCerrando(false);
    }
  }

  function empezarAnulacion(cierre) {
    setAnulandoId(cierre.id);
    setMotivoAnular("");
    setErrorAnular("");
  }

  function cancelarAnulacion() {
    setAnulandoId(null);
    setMotivoAnular("");
    setErrorAnular("");
  }

  async function confirmarAnulacion(evento, cierre) {
    evento.preventDefault();
    setErrorAnular("");
    setGuardandoAnular(true);
    try {
      await api.post(`/cierres/${cierre.id}/anular`, { motivo: motivoAnular });
      cancelarAnulacion();
      await Promise.all([cargarPrevisualizacion(), cargarHistorial()]);
    } catch (err) {
      setErrorAnular(err.message);
    } finally {
      setGuardandoAnular(false);
    }
  }

  async function descargarPdf(cierre) {
    setDescargandoId(cierre.id);
    try {
      await descargarArchivo(`/cierres/${cierre.id}.pdf`, `cierre_${cierre.fecha}.pdf`);
    } catch (err) {
      setErrorHistorial(err.message);
    } finally {
      setDescargandoId(null);
    }
  }

  const totalPaginasHistorial = historial ? Math.max(1, Math.ceil(historial.total / POR_PAGINA)) : 1;

  return (
    <div className="cierre-caja">
      <h1>Cierre de caja</h1>

      <section className="cierre-caja-seccion">
        <label className="cierre-caja-fecha">
          Fecha a cerrar
          <input
            type="date"
            value={fecha}
            max={hoyArgentina()}
            onChange={(e) => setFecha(e.target.value)}
          />
        </label>

        {cargandoPrevisualizacion && <Cargando texto="Calculando los totales del día…" />}
        {!cargandoPrevisualizacion && errorPrevisualizacion && (
          <MensajeError mensaje={errorPrevisualizacion} onReintentar={cargarPrevisualizacion} />
        )}

        {!cargandoPrevisualizacion && !errorPrevisualizacion && previsualizacion && (
          <form className="cierre-caja-formulario" onSubmit={cerrarElDia}>
            <div className="cierre-caja-totales">
              <div className="cierre-caja-total">
                <span className="cierre-caja-total-etiqueta">Efectivo</span>
                <span className="cierre-caja-total-valor">{formatearDinero(previsualizacion.total_efectivo)}</span>
              </div>
              <div className="cierre-caja-total">
                <span className="cierre-caja-total-etiqueta">Tarjeta</span>
                <span className="cierre-caja-total-valor">{formatearDinero(previsualizacion.total_tarjeta)}</span>
              </div>
              <div className="cierre-caja-total">
                <span className="cierre-caja-total-etiqueta">Transferencia</span>
                <span className="cierre-caja-total-valor">
                  {formatearDinero(previsualizacion.total_transferencia)}
                </span>
              </div>
              <div className="cierre-caja-total">
                <span className="cierre-caja-total-etiqueta">Total general</span>
                <span className="cierre-caja-total-valor">{formatearDinero(previsualizacion.total_general)}</span>
              </div>
              <div className="cierre-caja-total">
                <span className="cierre-caja-total-etiqueta">Ventas</span>
                <span className="cierre-caja-total-valor">{previsualizacion.cantidad_ventas}</span>
              </div>
              <div className="cierre-caja-total">
                <span className="cierre-caja-total-etiqueta">Anulaciones</span>
                <span className="cierre-caja-total-valor">
                  {previsualizacion.cantidad_anulaciones} ({formatearDinero(previsualizacion.monto_anulaciones)})
                </span>
              </div>
            </div>

            <MensajeError mensaje={errorCerrar} />

            <div className="cierre-caja-fila">
              <label>
                Efectivo contado
                <input
                  type="text"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={efectivoContado}
                  onChange={(e) => setEfectivoContado(e.target.value.trim())}
                  disabled={cerrando}
                  required
                />
              </label>

              <div className="cierre-caja-diferencia-caja">
                <span className="cierre-caja-total-etiqueta">Diferencia</span>
                <span
                  className={
                    diferenciaCentavos === null
                      ? "cierre-caja-diferencia"
                      : diferenciaCentavos === 0
                      ? "cierre-caja-diferencia cierre-caja-diferencia-ok"
                      : "cierre-caja-diferencia cierre-caja-diferencia-mal"
                  }
                >
                  {diferenciaCentavos === null ? "—" : formatearDinero(deCentavos(diferenciaCentavos))}
                </span>
              </div>
            </div>

            <label>
              Observaciones (opcional)
              <textarea
                value={observaciones}
                onChange={(e) => setObservaciones(e.target.value)}
                disabled={cerrando}
                rows={3}
                maxLength={500}
              />
            </label>

            <button type="submit" className="cierre-caja-boton-cerrar" disabled={cerrando}>
              {cerrando ? "Cerrando…" : "Cerrar el día"}
            </button>
          </form>
        )}
      </section>

      <section className="cierre-caja-seccion">
        <TituloSeccion Icono={IconoReloj}>Historial</TituloSeccion>
        {cargandoHistorial && <Cargando texto="Cargando historial…" />}
        {!cargandoHistorial && errorHistorial && (
          <MensajeError mensaje={errorHistorial} onReintentar={cargarHistorial} />
        )}

        {!cargandoHistorial && !errorHistorial && historial && (
          <>
            {historial.items.length === 0 ? (
              <p className="cierre-caja-vacio">Todavía no se cerró ningún día.</p>
            ) : (
              <div className="cierre-caja-tabla">
                <table>
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Cerrado por</th>
                      <th className="cierre-caja-numerico">Total sistema</th>
                      <th className="cierre-caja-numerico">Contado</th>
                      <th className="cierre-caja-numerico">Diferencia</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {historial.items.map((c) => (
                      <Fragment key={c.id}>
                        <tr className={c.anulado ? "cierre-caja-fila-anulada" : ""}>
                          <td>{formatearFecha(c.fecha)}</td>
                          <td>{c.usuario.nombre}</td>
                          <td className="cierre-caja-numerico">{formatearDinero(c.total_efectivo)}</td>
                          <td className="cierre-caja-numerico">{formatearDinero(c.efectivo_contado)}</td>
                          <td
                            className={`cierre-caja-numerico ${
                              c.diferencia === "0.00"
                                ? "cierre-caja-diferencia-ok"
                                : "cierre-caja-diferencia-mal"
                            }`}
                          >
                            {formatearDinero(c.diferencia)}
                          </td>
                          <td className="cierre-caja-acciones">
                            {c.anulado ? (
                              <span className="cierre-caja-anulado-etiqueta">Anulado</span>
                            ) : (
                              <>
                                <button
                                  type="button"
                                  onClick={() => descargarPdf(c)}
                                  disabled={descargandoId === c.id}
                                >
                                  {descargandoId === c.id ? "Generando…" : "PDF"}
                                </button>
                                <button
                                  type="button"
                                  className="cierre-caja-boton-anular"
                                  onClick={() =>
                                    anulandoId === c.id ? cancelarAnulacion() : empezarAnulacion(c)
                                  }
                                >
                                  Anular
                                </button>
                              </>
                            )}
                          </td>
                        </tr>
                        {anulandoId === c.id && (
                          <tr className="cierre-caja-fila-detalle">
                            <td colSpan={6}>
                              <form className="cierre-caja-form-anular" onSubmit={(e) => confirmarAnulacion(e, c)}>
                                <MensajeError mensaje={errorAnular} />
                                <label>
                                  Motivo de la anulación
                                  <input
                                    type="text"
                                    value={motivoAnular}
                                    onChange={(e) => setMotivoAnular(e.target.value)}
                                    disabled={guardandoAnular}
                                    autoFocus
                                    required
                                  />
                                </label>
                                <div className="cierre-caja-form-botones">
                                  <button type="submit" disabled={guardandoAnular || motivoAnular.trim().length === 0}>
                                    {guardandoAnular ? "Anulando…" : "Confirmar anulación"}
                                  </button>
                                  <button
                                    type="button"
                                    className="cierre-caja-boton-secundario"
                                    onClick={cancelarAnulacion}
                                    disabled={guardandoAnular}
                                  >
                                    Cancelar
                                  </button>
                                </div>
                              </form>
                            </td>
                          </tr>
                        )}
                        {c.anulado && (
                          <tr className="cierre-caja-fila-detalle">
                            <td colSpan={6} className="cierre-caja-motivo-anulado">
                              Motivo: {c.anulado_motivo} — {formatearFechaHora(c.anulado_en)}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {totalPaginasHistorial > 1 && (
              <div className="cierre-caja-paginado">
                <button
                  type="button"
                  disabled={paginaHistorial <= 1}
                  onClick={() => setPaginaHistorial((p) => p - 1)}
                >
                  Anterior
                </button>
                <span>
                  Página {paginaHistorial} de {totalPaginasHistorial}
                </span>
                <button
                  type="button"
                  disabled={paginaHistorial >= totalPaginasHistorial}
                  onClick={() => setPaginaHistorial((p) => p + 1)}
                >
                  Siguiente
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
