import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/cliente";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import { formatearDinero } from "../../utilidades/dinero";
import { formatearFechaHora } from "../../utilidades/fechas";
import "./FacturasConError.css";

const ETIQUETA_MEDIO = { efectivo: "Efectivo", tarjeta: "Tarjeta", transferencia: "Transferencia" };
const POR_PAGINA = 20;

export default function FacturasConError() {
  const [pagina, setPagina] = useState(1);
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [reintentandoId, setReintentandoId] = useState(null);
  const [errorReintento, setErrorReintento] = useState({ id: null, mensaje: "" });

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      setDatos(await api.get(`/facturas/con-error?pagina=${pagina}&por_pagina=${POR_PAGINA}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [pagina]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function reintentar(venta) {
    setReintentandoId(venta.id);
    setErrorReintento({ id: null, mensaje: "" });
    try {
      await api.post(`/ventas/${venta.id}/reintentar-factura`);
      await cargar();
    } catch (err) {
      setErrorReintento({ id: venta.id, mensaje: err.message });
    } finally {
      setReintentandoId(null);
    }
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.total / POR_PAGINA)) : 1;

  return (
    <div className="facturas-con-error">
      <h1>Facturas con error</h1>
      <p className="facturas-con-error-subtitulo">
        Ventas que ARCA rechazó al querer facturarlas. El motivo de cada una está en la columna "Motivo".
      </p>

      {cargando && <Cargando texto="Cargando facturas con error…" />}
      {!cargando && error && <MensajeError mensaje={error} onReintentar={cargar} />}

      {!cargando && !error && datos && (
        <>
          {datos.items.length === 0 ? (
            <p className="facturas-con-error-vacio">No hay facturas con error.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Medio</th>
                  <th className="facturas-con-error-numerico">Monto</th>
                  <th>Motivo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {datos.items.map((venta) => (
                  <tr key={venta.id}>
                    <td>{formatearFechaHora(venta.fecha_hora)}</td>
                    <td>{ETIQUETA_MEDIO[venta.medio_pago]}</td>
                    <td className="facturas-con-error-numerico">{formatearDinero(venta.total)}</td>
                    <td className="facturas-con-error-motivo">{venta.error_detalle}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => reintentar(venta)}
                        disabled={reintentandoId === venta.id}
                      >
                        {reintentandoId === venta.id ? "Reintentando…" : "Reintentar"}
                      </button>
                      {errorReintento.id === venta.id && (
                        <p className="facturas-con-error-motivo">{errorReintento.mensaje}</p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {totalPaginas > 1 && (
            <div className="facturas-con-error-paginado">
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
