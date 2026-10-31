import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api/cliente";
import Cargando from "../../componentes/Cargando";
import Insignia from "../../componentes/Insignia";
import MensajeError from "../../componentes/MensajeError";
import { formatearDinero } from "../../utilidades/dinero";
import { formatearFecha, formatearFechaHora } from "../../utilidades/fechas";
import { formatearNumeroComprobante } from "../../utilidades/comprobante";
import { ETIQUETA_MEDIO } from "../../utilidades/graficos";
import "./VentaDetalle.css";

const ETIQUETA_ESTADO_ANULACION = {
  pendiente: "Emitiendo la nota de crédito…",
  emitida: "Nota de crédito emitida",
  fallo: "La nota de crédito falló",
  sin_comprobante: "Anulada (no tenía comprobante)",
};

export default function VentaDetalle() {
  const { id } = useParams();
  const [venta, setVenta] = useState(null);
  const [vendedor, setVendedor] = useState("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  const [anulando, setAnulando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [errorAnular, setErrorAnular] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [reintentando, setReintentando] = useState(false);
  const [errorReintentar, setErrorReintentar] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      const datos = await api.get(`/ventas/${id}`);
      setVenta(datos);
      const usuarios = await api.get("/usuarios").catch(() => []);
      setVendedor(usuarios.find((u) => u.id === datos.vendedor_id)?.nombre ?? `#${datos.vendedor_id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function confirmarAnulacion(evento) {
    evento.preventDefault();
    setErrorAnular("");
    setGuardando(true);
    try {
      const actualizada = await api.post(`/ventas/${id}/anular`, { motivo });
      setVenta(actualizada);
      setAnulando(false);
      setMotivo("");
    } catch (err) {
      setErrorAnular(err.message);
    } finally {
      setGuardando(false);
    }
  }

  async function reintentarNotaCredito() {
    setReintentando(true);
    setErrorReintentar("");
    try {
      await api.post(`/anulaciones/${venta.anulacion.id}/reintentar`);
      await cargar();
    } catch (err) {
      setErrorReintentar(err.message);
    } finally {
      setReintentando(false);
    }
  }

  const puedeAnularse = venta && !venta.anulada && venta.estado_arca !== "pendiente";
  const vaAEmitirNotaDeCredito = venta && venta.estado_arca === "facturada";

  return (
    <div className="venta-detalle">
      <Link to="/admin/ventas" className="venta-detalle-volver">
        ← Volver a ventas
      </Link>
      <h1>Detalle de la venta</h1>

      {cargando && <Cargando texto="Cargando venta…" />}
      {!cargando && error && <MensajeError mensaje={error} onReintentar={cargar} />}

      {!cargando && !error && venta && (
        <div className="venta-detalle-tarjeta">
          <dl>
            <dt>Fecha</dt>
            <dd>{formatearFechaHora(venta.fecha_hora)}</dd>
            <dt>Vendedor</dt>
            <dd>{vendedor}</dd>
            <dt>Medio de pago</dt>
            <dd>{ETIQUETA_MEDIO[venta.medio_pago]}</dd>
            {venta.rubro_nombre && (
              <>
                <dt>Rubro</dt>
                <dd>{venta.rubro_nombre}</dd>
              </>
            )}
            {venta.ajuste_detalle && (
              <>
                <dt>Subtotal</dt>
                <dd>{formatearDinero(venta.subtotal)}</dd>
                <dt>Ajuste</dt>
                <dd>{venta.ajuste_detalle}</dd>
              </>
            )}
            <dt>Monto</dt>
            <dd className="venta-detalle-monto">{formatearDinero(venta.total)}</dd>
            <dt>Estado fiscal</dt>
            <dd>
              <Insignia estado={venta.estado_arca} anulada={venta.anulada} />
            </dd>
            {venta.estado_arca === "facturada" && (
              <>
                <dt>Comprobante</dt>
                <dd>
                  {venta.tipo_comprobante === "6" ? "Factura B" : venta.tipo_comprobante === "11" ? "Factura C" : venta.tipo_comprobante}{" "}
                  {formatearNumeroComprobante(venta.punto_venta, venta.numero_comprobante)}
                </dd>
                <dt>CAE</dt>
                <dd>{venta.cae}</dd>
                <dt>Vencimiento del CAE</dt>
                <dd>{formatearFecha(venta.cae_vencimiento)}</dd>
              </>
            )}
            {venta.error_detalle && (
              <>
                <dt>Motivo del error</dt>
                <dd className="venta-detalle-error">{venta.error_detalle}</dd>
              </>
            )}
            {venta.anulacion && (
              <>
                <dt>Motivo de la anulación</dt>
                <dd>{venta.anulacion.motivo}</dd>
                <dt>Anulada el</dt>
                <dd>{formatearFechaHora(venta.anulada_en)}</dd>
                <dt>Nota de crédito</dt>
                <dd className={venta.anulacion.estado === "fallo" ? "venta-detalle-error" : undefined}>
                  {ETIQUETA_ESTADO_ANULACION[venta.anulacion.estado]}
                  {venta.anulacion.estado === "fallo" && venta.anulacion.error_detalle && (
                    <span> — {venta.anulacion.error_detalle}</span>
                  )}
                </dd>
              </>
            )}
          </dl>

          {venta.estado_arca === "facturada" && !venta.anulada && (
            <Link to={`/comprobante/${venta.id}`} className="venta-detalle-imprimir">
              Ver e imprimir comprobante
            </Link>
          )}
          {venta.estado_arca !== "facturada" && !venta.anulada && (
            <p className="venta-detalle-nota">Esta venta no tiene comprobante para imprimir.</p>
          )}
          {venta.anulacion?.estado === "emitida" && (
            <Link to={`/comprobante/${venta.id}?tipo=nota-credito`} className="venta-detalle-imprimir">
              Ver e imprimir la nota de crédito
            </Link>
          )}

          {venta.anulacion && (venta.anulacion.estado === "pendiente" || venta.anulacion.estado === "fallo") && (
            <div className="venta-detalle-reintentar">
              <MensajeError mensaje={errorReintentar} />
              <button type="button" onClick={reintentarNotaCredito} disabled={reintentando}>
                {reintentando ? "Reintentando…" : "Reintentar nota de crédito"}
              </button>
            </div>
          )}

          {puedeAnularse && !anulando && (
            <button type="button" className="venta-detalle-anular" onClick={() => setAnulando(true)}>
              Anular venta
            </button>
          )}
          {venta.estado_arca === "pendiente" && !venta.anulada && (
            <p className="venta-detalle-nota">
              Todavía se está facturando: esperá a que quede facturada o con error antes de anularla.
            </p>
          )}

          {anulando && (
            <form className="venta-detalle-form-anular" onSubmit={confirmarAnulacion}>
              <MensajeError mensaje={errorAnular} />
              {vaAEmitirNotaDeCredito && (
                <p className="alerta alerta-aviso">
                  Se va a emitir una nota de crédito en ARCA. Esta operación no se puede deshacer.
                </p>
              )}
              <p className="venta-detalle-resumen-anular">
                {ETIQUETA_MEDIO[venta.medio_pago]} · {formatearDinero(venta.total)} ·{" "}
                {formatearFechaHora(venta.fecha_hora)}
              </p>
              <label htmlFor="venta-detalle-motivo">Motivo de la anulación</label>
              <textarea
                id="venta-detalle-motivo"
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                disabled={guardando}
                autoFocus
                required
                rows={3}
              />
              <div className="venta-detalle-form-botones">
                <button type="submit" disabled={guardando || motivo.trim().length === 0}>
                  {guardando ? "Anulando…" : "Confirmar anulación"}
                </button>
                <button
                  type="button"
                  className="venta-detalle-cancelar"
                  onClick={() => {
                    setAnulando(false);
                    setMotivo("");
                    setErrorAnular("");
                  }}
                  disabled={guardando}
                >
                  Cancelar
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
