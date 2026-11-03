import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/cliente";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import { formatearDinero } from "../../utilidades/dinero";
import { formatearFechaHora, hoyArgentina } from "../../utilidades/fechas";
import { ETIQUETA_MEDIO } from "../../utilidades/graficos";
import "./Anulaciones.css";

const POR_PAGINA = 15;

const ETIQUETA_ESTADO = {
  pendiente: "Emitiendo nota de crédito",
  emitida: "Nota de crédito emitida",
  fallo: "Nota de crédito con error",
  sin_comprobante: "Anulada (sin comprobante)",
};

export default function Anulaciones() {
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [estado, setEstado] = useState("");
  const [pagina, setPagina] = useState(1);

  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [reintentandoId, setReintentandoId] = useState(null);
  const [errorReintento, setErrorReintento] = useState({ id: null, mensaje: "" });

  const rangoInvertido = desde && hasta && desde > hasta;

  const cargar = useCallback(async () => {
    if (rangoInvertido) return;
    setCargando(true);
    setError("");
    const parametros = new URLSearchParams({ pagina: String(pagina), por_pagina: String(POR_PAGINA) });
    if (desde) parametros.set("desde", desde);
    if (hasta) parametros.set("hasta", hasta);
    if (estado) parametros.set("estado", estado);
    try {
      setDatos(await api.get(`/anulaciones?${parametros}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [pagina, desde, hasta, estado, rangoInvertido]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function cambiarFiltro(setter) {
    return (evento) => {
      setPagina(1);
      setter(evento.target.value);
    };
  }

  async function reintentar(anulacion) {
    setReintentandoId(anulacion.id);
    setErrorReintento({ id: null, mensaje: "" });
    try {
      await api.post(`/anulaciones/${anulacion.id}/reintentar`);
      await cargar();
    } catch (err) {
      setErrorReintento({ id: anulacion.id, mensaje: err.message });
    } finally {
      setReintentandoId(null);
    }
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.total / POR_PAGINA)) : 1;

  return (
    <div className="anulaciones">
      <h1>Anulaciones</h1>
      <p className="anulaciones-subtitulo">
        Ventas anuladas. Si ya tenían comprobante, acá se ve el resultado de la nota de crédito ante ARCA.
      </p>

      <div className="anulaciones-filtros">
        <label>
          Desde
          <input type="date" value={desde} max={hoyArgentina()} onChange={cambiarFiltro(setDesde)} />
        </label>
        <label>
          Hasta
          <input type="date" value={hasta} max={hoyArgentina()} onChange={cambiarFiltro(setHasta)} />
        </label>
        <label>
          Estado
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
      {!rangoInvertido && cargando && <Cargando texto="Cargando anulaciones…" />}
      {!rangoInvertido && !cargando && error && <MensajeError mensaje={error} onReintentar={cargar} />}

      {!rangoInvertido && !cargando && !error && datos && (
        <>
          {datos.items.length === 0 ? (
            <p className="anulaciones-vacio">No hay anulaciones con estos filtros.</p>
          ) : (
            <div className="anulaciones-tabla">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Venta</th>
                    <th className="anulaciones-numerico">Monto</th>
                    <th>Motivo</th>
                    <th>Quién</th>
                    <th>Estado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {datos.items.map((fila) => (
                    <tr key={fila.id}>
                      <td>{formatearFechaHora(fila.fecha_hora)}</td>
                      <td>
                        <Link to={`/admin/ventas/${fila.venta.id}`} className="anulaciones-enlace">
                          {ETIQUETA_MEDIO[fila.venta.medio_pago]} · {formatearFechaHora(fila.venta.fecha_hora)}
                        </Link>
                      </td>
                      <td className="anulaciones-numerico">{formatearDinero(fila.venta.total)}</td>
                      <td className="anulaciones-motivo">{fila.motivo}</td>
                      <td>{fila.usuario.nombre}</td>
                      <td>
                        <span className={`anulaciones-estado anulaciones-estado-${fila.estado}`}>
                          {ETIQUETA_ESTADO[fila.estado]}
                        </span>
                        {fila.estado === "fallo" && fila.error_detalle && (
                          <p className="anulaciones-motivo">{fila.error_detalle}</p>
                        )}
                      </td>
                      <td>
                        {(fila.estado === "pendiente" || fila.estado === "fallo") && (
                          <button
                            type="button"
                            onClick={() => reintentar(fila)}
                            disabled={reintentandoId === fila.id}
                          >
                            {reintentandoId === fila.id ? "Reintentando…" : "Reintentar"}
                          </button>
                        )}
                        {fila.estado === "emitida" && (
                          <Link
                            to={`/comprobante/${fila.venta.id}?tipo=nota-credito`}
                            className="anulaciones-enlace"
                          >
                            Ver comprobante
                          </Link>
                        )}
                        {errorReintento.id === fila.id && (
                          <p className="anulaciones-motivo">{errorReintento.mensaje}</p>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {totalPaginas > 1 && (
            <div className="anulaciones-paginado">
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
