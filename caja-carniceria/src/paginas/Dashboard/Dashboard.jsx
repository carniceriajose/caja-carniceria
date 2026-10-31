import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, descargarArchivo } from "../../api/cliente";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import GraficoDona from "../../componentes/GraficoDona";
import GraficoBarras from "../../componentes/GraficoBarras";
import {
  IconoAnular,
  IconoBalanza,
  IconoBilletes,
  IconoCategorias,
  IconoDocumento,
  IconoEtiqueta,
  IconoReloj,
  IconoTarjeta,
  IconoTransferencia,
} from "../../componentes/Iconos";
import { formatearDinero } from "../../utilidades/dinero";
import { formatearFecha, hoyArgentina, rangosRapidos } from "../../utilidades/fechas";
import { CLASE_SERIE_MEDIO, ETIQUETA_MEDIO as ETIQUETAS_MEDIO } from "../../utilidades/graficos";
import "./Dashboard.css";

const ETIQUETAS_ESTADO = {
  no_aplica: "No se factura",
  pendiente: "Pendiente",
  facturada: "Facturada",
  fallo: "Con error",
};

const ICONO_MEDIO = {
  efectivo: IconoBilletes,
  tarjeta: IconoTarjeta,
  transferencia: IconoTransferencia,
};

const ETIQUETA_TIPO_TARJETA = {
  credito: "Crédito",
  debito: "Débito",
};

const FILAS_POR_PAGINA = 7;

function TituloPanel({ Icono, titulo, subtitulo }) {
  return (
    <div className="dashboard-panel-titulo">
      <span className="dashboard-panel-titulo-icono">
        <Icono tamanio={18} />
      </span>
      <span>
        <h2>{titulo}</h2>
        <p className="dashboard-panel-subtitulo">{subtitulo}</p>
      </span>
    </div>
  );
}

export default function Dashboard() {
  const rangos = rangosRapidos();
  const [desde, setDesde] = useState(rangos.mes.desde);
  const [hasta, setHasta] = useState(rangos.mes.hasta);

  const [resumen, setResumen] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [paginaSerie, setPaginaSerie] = useState(1);
  const [soloConVentas, setSoloConVentas] = useState(true);
  const [resaltado, setResaltado] = useState(null); // por el mouse, en el gráfico o en la tabla
  const [fijado, setFijado] = useState(null); // por un clic
  const [descargando, setDescargando] = useState(null); // "excel" | "pdf" | null
  const [errorDescarga, setErrorDescarga] = useState("");

  const cargarResumen = useCallback(async (rangoDesde, rangoHasta) => {
    setCargando(true);
    setError("");
    try {
      setResumen(await api.get(`/resumen?desde=${rangoDesde}&hasta=${rangoHasta}`));
      setPaginaSerie(1);
      setResaltado(null);
      setFijado(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargarResumen(desde, hasta);
  }, [cargarResumen, desde, hasta]);

  function usarRango(rango) {
    setDesde(rango.desde);
    setHasta(rango.hasta);
  }

  const rangoInvertido = desde > hasta;

  // La tabla muestra primero lo más reciente; el gráfico necesita orden cronológico.
  const serieDescendente = resumen ? [...resumen.serie].reverse() : [];
  const serieMostrada = soloConVentas ? serieDescendente.filter((p) => p.total !== "0.00") : serieDescendente;
  const serieGrafico = resumen
    ? soloConVentas
      ? resumen.serie.filter((p) => p.total !== "0.00")
      : resumen.serie
    : [];
  const totalPaginasSerie = Math.max(1, Math.ceil(serieMostrada.length / FILAS_POR_PAGINA));
  const paginaVisible = Math.min(paginaSerie, totalPaginasSerie);
  const filasSerie = serieMostrada.slice((paginaVisible - 1) * FILAS_POR_PAGINA, paginaVisible * FILAS_POR_PAGINA);
  const periodoActivo = resaltado ?? fijado;

  // Un clic en una barra o en una fila la deja fijada (otro clic la suelta) y lleva la tabla a su página.
  function elegirPeriodo(periodo) {
    const nuevo = fijado === periodo ? null : periodo;
    setFijado(nuevo);
    const posicion = serieMostrada.findIndex((p) => p.periodo === nuevo);
    if (posicion >= 0) setPaginaSerie(Math.floor(posicion / FILAS_POR_PAGINA) + 1);
  }
  const hayGastos = resumen ? resumen.gastos_por_categoria.length > 0 : false;

  async function descargar(tipo) {
    setDescargando(tipo);
    setErrorDescarga("");
    try {
      if (tipo === "excel") {
        await descargarArchivo(
          `/reportes/ventas.xlsx?desde=${desde}&hasta=${hasta}`,
          `ventas_${desde}_${hasta}.xlsx`
        );
      } else if (tipo === "iva") {
        await descargarArchivo(`/reportes/iva.xlsx?desde=${desde}&hasta=${hasta}`, `iva_${desde}_${hasta}.xlsx`);
      } else {
        await descargarArchivo(
          `/reportes/resumen.pdf?desde=${desde}&hasta=${hasta}`,
          `resumen_${desde}_${hasta}.pdf`
        );
      }
    } catch (err) {
      setErrorDescarga(err.message);
    } finally {
      setDescargando(null);
    }
  }

  return (
    <div className="dashboard">
      <header className="dashboard-encabezado">
        <div>
          <h1>Resumen</h1>
          <div className="dashboard-atajos">
            <button type="button" onClick={() => usarRango(rangos.hoy)}>
              Hoy
            </button>
            <button type="button" onClick={() => usarRango(rangos.semana)}>
              Últimos 7 días
            </button>
            <button type="button" onClick={() => usarRango(rangos.mes)}>
              Este mes
            </button>
            <button type="button" onClick={() => usarRango(rangos.anio)}>
              Este año
            </button>
          </div>
        </div>
        <div className="dashboard-fechas">
          <label>
            Desde
            <input type="date" value={desde} max={hoyArgentina()} onChange={(e) => setDesde(e.target.value)} />
          </label>
          <label>
            Hasta
            <input type="date" value={hasta} max={hoyArgentina()} onChange={(e) => setHasta(e.target.value)} />
          </label>
          <div className="dashboard-descargas">
            <button
              type="button"
              onClick={() => descargar("excel")}
              disabled={rangoInvertido || descargando !== null}
            >
              {descargando === "excel" ? "Generando…" : "Descargar ventas (Excel)"}
            </button>
            <button
              type="button"
              onClick={() => descargar("pdf")}
              disabled={rangoInvertido || descargando !== null}
            >
              {descargando === "pdf" ? "Generando…" : "Descargar resumen (PDF)"}
            </button>
            <button
              type="button"
              onClick={() => descargar("iva")}
              disabled={rangoInvertido || descargando !== null}
            >
              {descargando === "iva" ? "Generando…" : "Descargar IVA por alícuota (Excel)"}
            </button>
          </div>
        </div>
      </header>

      {errorDescarga && <MensajeError mensaje={errorDescarga} />}
      {rangoInvertido && <MensajeError mensaje="La fecha 'desde' no puede ser posterior a 'hasta'." />}

      {!rangoInvertido && cargando && <Cargando texto="Calculando el resumen…" />}
      {!rangoInvertido && !cargando && error && (
        <MensajeError mensaje={error} onReintentar={() => cargarResumen(desde, hasta)} />
      )}

      {!rangoInvertido && !cargando && !error && resumen && (
        <>
          <section className="dashboard-indicadores">
            <div className="dashboard-indicador dashboard-indicador-ventas">
              <div>
                <span className="dashboard-indicador-etiqueta">Total vendido</span>
                <span className="dashboard-indicador-valor">{formatearDinero(resumen.total_vendido)}</span>
                <span className="dashboard-indicador-detalle">
                  {resumen.cantidad_ventas} {resumen.cantidad_ventas === 1 ? "venta" : "ventas"}
                </span>
              </div>
              <span className="dashboard-indicador-icono">
                <IconoBilletes tamanio={22} />
              </span>
            </div>

            <div className="dashboard-indicador">
              <div>
                <span className="dashboard-indicador-etiqueta">Gastos</span>
                <span className="dashboard-indicador-valor">{formatearDinero(resumen.total_gastos)}</span>
                <span className="dashboard-indicador-detalle">
                  {hayGastos ? `${resumen.gastos_por_categoria.length} categoría(s)` : "Sin gastos"}
                </span>
              </div>
              <span className="dashboard-indicador-icono">
                <IconoEtiqueta tamanio={22} />
              </span>
            </div>

            <div
              className={`dashboard-indicador ${
                resumen.resultado.startsWith("-") ? "dashboard-indicador-negativo" : "dashboard-indicador-positivo"
              }`}
            >
              <div>
                <span className="dashboard-indicador-etiqueta">Resultado</span>
                <span className="dashboard-indicador-valor">{formatearDinero(resumen.resultado)}</span>
                <span className="dashboard-indicador-detalle">Ventas menos gastos</span>
              </div>
              <span className="dashboard-indicador-icono">
                <IconoBalanza tamanio={22} />
              </span>
            </div>

            <Link to="/admin/anulaciones" className="dashboard-indicador dashboard-indicador-enlace">
              <div>
                <span className="dashboard-indicador-etiqueta">Anulaciones</span>
                <span className="dashboard-indicador-valor">{formatearDinero(resumen.monto_anulaciones)}</span>
                <span className="dashboard-indicador-detalle">
                  {resumen.cantidad_anulaciones} {resumen.cantidad_anulaciones === 1 ? "venta anulada" : "ventas anuladas"}
                </span>
              </div>
              <span className="dashboard-indicador-icono">
                <IconoAnular tamanio={22} />
              </span>
            </Link>

            <div className="dashboard-indicador">
              <div>
                <span className="dashboard-indicador-etiqueta">Recargos</span>
                <span className="dashboard-indicador-valor">{formatearDinero(resumen.total_recargos)}</span>
                <span className="dashboard-indicador-detalle">Por tarjeta y transferencia</span>
              </div>
              <span className="dashboard-indicador-icono">
                <IconoEtiqueta tamanio={22} />
              </span>
            </div>
          </section>

          <div className="dashboard-grilla">
            <section className="dashboard-panel">
              <TituloPanel
                Icono={IconoBilletes}
                titulo="Por medio de pago"
                subtitulo="Distribución de las ventas según el método de pago"
              />
              <GraficoDona
                totalTexto={resumen.total_vendido}
                segmentos={resumen.por_medio_pago.map((fila) => ({
                  clave: fila.medio_pago,
                  etiqueta: ETIQUETAS_MEDIO[fila.medio_pago],
                  claseColor: CLASE_SERIE_MEDIO[fila.medio_pago],
                  monto: fila.monto,
                }))}
              />
            </section>

            <section className="dashboard-panel">
              <TituloPanel
                Icono={IconoDocumento}
                titulo="Detalle por medio de pago"
                subtitulo="Cantidad de ventas y monto total por método de pago"
              />
              <table className="dashboard-tabla">
                <thead>
                  <tr>
                    <th></th>
                    <th>Medio</th>
                    <th className="dashboard-numerico">Cantidad</th>
                    <th className="dashboard-numerico">Monto</th>
                  </tr>
                </thead>
                <tbody>
                  {resumen.por_medio_pago.map((fila) => {
                    const Icono = ICONO_MEDIO[fila.medio_pago];
                    return (
                      <tr key={fila.medio_pago}>
                        <td className="dashboard-celda-icono">
                          <span className={`dashboard-icono-medio dashboard-icono-${fila.medio_pago}`}>
                            <Icono tamanio={20} />
                          </span>
                        </td>
                        <td>{ETIQUETAS_MEDIO[fila.medio_pago]}</td>
                        <td className="dashboard-numerico">{fila.cantidad}</td>
                        <td className="dashboard-numerico">{formatearDinero(fila.monto)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>

            <section className="dashboard-panel">
              <TituloPanel
                Icono={IconoDocumento}
                titulo="Por estado de facturación"
                subtitulo="Estado actual de las facturas"
              />
              <table className="dashboard-tabla">
                <thead>
                  <tr>
                    <th>Estado</th>
                    <th className="dashboard-numerico">Cantidad</th>
                    <th className="dashboard-numerico">Monto</th>
                  </tr>
                </thead>
                <tbody>
                  {resumen.por_estado_fiscal.map((fila) => {
                    const clase = `dashboard-insignia dashboard-insignia-${fila.estado_arca}`;
                    const enlazable = fila.estado_arca === "pendiente" || fila.estado_arca === "fallo";
                    return (
                      <tr key={fila.estado_arca}>
                        <td>
                          {enlazable ? (
                            <Link to="/admin/facturas-con-error" className={`${clase} dashboard-insignia-enlace`}>
                              {ETIQUETAS_ESTADO[fila.estado_arca]}
                            </Link>
                          ) : (
                            <span className={clase}>{ETIQUETAS_ESTADO[fila.estado_arca]}</span>
                          )}
                        </td>
                        <td className="dashboard-numerico">{fila.cantidad}</td>
                        <td className="dashboard-numerico">{formatearDinero(fila.monto)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>

            {resumen.ventas_por_rubro.length > 0 && (
              <section className="dashboard-panel">
                <TituloPanel
                  Icono={IconoEtiqueta}
                  titulo="Ventas por rubro"
                  subtitulo="Distribución de ventas por categoría de productos"
                />
                <table className="dashboard-tabla">
                  <thead>
                    <tr>
                      <th>Rubro</th>
                      <th className="dashboard-numerico">Cantidad</th>
                      <th className="dashboard-numerico">Monto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resumen.ventas_por_rubro.map((fila) => (
                      <tr key={fila.rubro_id ?? "sin-rubro"}>
                        <td>{fila.rubro}</td>
                        <td className="dashboard-numerico">{fila.cantidad}</td>
                        <td className="dashboard-numerico">{formatearDinero(fila.monto)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}

            {resumen.ventas_por_tarjeta.length > 0 && (
              <section className="dashboard-panel">
                <TituloPanel
                  Icono={IconoTarjeta}
                  titulo="Ventas por tarjeta"
                  subtitulo="Distribución de ventas por tarjeta utilizada"
                />
                <table className="dashboard-tabla">
                  <thead>
                    <tr>
                      <th>Tarjeta</th>
                      <th className="dashboard-numerico">Cantidad</th>
                      <th className="dashboard-numerico">Monto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resumen.ventas_por_tarjeta.map((fila) => (
                      <tr key={fila.tarjeta_id ?? "sin-tarjeta"}>
                        <td>{fila.tarjeta}</td>
                        <td className="dashboard-numerico">{fila.cantidad}</td>
                        <td className="dashboard-numerico">{formatearDinero(fila.monto)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}

            {resumen.ventas_por_tipo_tarjeta.length > 0 && (
              <section className="dashboard-panel">
                <TituloPanel
                  Icono={IconoTarjeta}
                  titulo="Ventas por tipo de tarjeta"
                  subtitulo="Distribución de ventas entre crédito y débito"
                />
                <table className="dashboard-tabla">
                  <thead>
                    <tr>
                      <th>Tipo</th>
                      <th className="dashboard-numerico">Cantidad</th>
                      <th className="dashboard-numerico">Monto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resumen.ventas_por_tipo_tarjeta.map((fila) => (
                      <tr key={fila.tipo ?? "sin-tipo"}>
                        <td>{ETIQUETA_TIPO_TARJETA[fila.tipo] ?? "Sin tipo"}</td>
                        <td className="dashboard-numerico">{fila.cantidad}</td>
                        <td className="dashboard-numerico">{formatearDinero(fila.monto)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}

            <section className="dashboard-panel">
              <div className="dashboard-panel-encabezado">
                <span className="dashboard-panel-titulo dashboard-panel-titulo-sinmargen">
                  <span className="dashboard-panel-titulo-icono">
                    <IconoReloj tamanio={18} />
                  </span>
                  <h2>{resumen.agrupacion === "mes" ? "Por mes" : "Por día"}</h2>
                </span>
                <label className="dashboard-interruptor">
                  <input
                    type="checkbox"
                    checked={soloConVentas}
                    onChange={(e) => setSoloConVentas(e.target.checked)}
                  />
                  {resumen.agrupacion === "mes" ? "Solo meses con ventas" : "Solo días con ventas"}
                </label>
              </div>
              <GraficoBarras
                puntos={serieGrafico}
                agrupacion={resumen.agrupacion}
                activo={periodoActivo}
                alResaltar={setResaltado}
                alElegir={elegirPeriodo}
              />
              <div className="dashboard-tabla-scroll">
                <table className="dashboard-tabla dashboard-tabla-compacta">
                  <thead>
                    <tr>
                      <th>{resumen.agrupacion === "mes" ? "Mes" : "Día"}</th>
                      <th className="dashboard-numerico">Efectivo</th>
                      <th className="dashboard-numerico">Tarjeta</th>
                      <th className="dashboard-numerico">Transf.</th>
                      <th className="dashboard-numerico">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filasSerie.length === 0 && (
                      <tr>
                        <td colSpan={5} className="dashboard-vacio">
                          No hay ventas en este período.
                        </td>
                      </tr>
                    )}
                    {filasSerie.map((punto) => (
                      <tr
                        key={punto.periodo}
                        className={`dashboard-fila-interactiva ${
                          periodoActivo === punto.periodo ? "dashboard-fila-activa" : ""
                        }`}
                        onMouseEnter={() => setResaltado(punto.periodo)}
                        onMouseLeave={() => setResaltado(null)}
                        onClick={() => elegirPeriodo(punto.periodo)}
                      >
                        <td>{formatearFecha(punto.periodo)}</td>
                        <td className="dashboard-numerico">{formatearDinero(punto.efectivo)}</td>
                        <td className="dashboard-numerico">{formatearDinero(punto.tarjeta)}</td>
                        <td className="dashboard-numerico">{formatearDinero(punto.transferencia)}</td>
                        <td className="dashboard-numerico">{formatearDinero(punto.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {totalPaginasSerie > 1 && (
                <div className="dashboard-paginado">
                  <button
                    type="button"
                    aria-label="Página anterior"
                    disabled={paginaVisible <= 1}
                    onClick={() => setPaginaSerie(paginaVisible - 1)}
                  >
                    ‹
                  </button>
                  <span>
                    Página {paginaVisible} de {totalPaginasSerie}
                  </span>
                  <button
                    type="button"
                    aria-label="Página siguiente"
                    disabled={paginaVisible >= totalPaginasSerie}
                    onClick={() => setPaginaSerie(paginaVisible + 1)}
                  >
                    ›
                  </button>
                </div>
              )}
            </section>

            {hayGastos && (
              <section className="dashboard-panel">
                <TituloPanel
                  Icono={IconoCategorias}
                  titulo="Gastos por categoría"
                  subtitulo="Cuánto se gastó en cada categoría en el período"
                />
                <table className="dashboard-tabla">
                  <thead>
                    <tr>
                      <th>Categoría</th>
                      <th className="dashboard-numerico">Cantidad</th>
                      <th className="dashboard-numerico">Monto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resumen.gastos_por_categoria.map((fila) => (
                      <tr key={fila.categoria_id}>
                        <td>{fila.categoria}</td>
                        <td className="dashboard-numerico">{fila.cantidad}</td>
                        <td className="dashboard-numerico">{formatearDinero(fila.monto)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
          </div>
        </>
      )}
    </div>
  );
}
