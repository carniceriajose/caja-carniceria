import { useState } from "react";
import { formatearDinero } from "../utilidades/dinero";
import { formatearFecha } from "../utilidades/fechas";
import { CLASE_SERIE_MEDIO, ETIQUETA_MEDIO, MEDIOS_DE_PAGO, numeroParaElDibujo } from "../utilidades/graficos";
import "./GraficoBarras.css";

const ALTO_GRAFICO = 170;
const MARGEN_SUPERIOR = 14;
const ANCHO_POR_BARRA = 28;
const ANCHO_MAXIMO_BARRA = 24;
const HUECO_ENTRE_SEGMENTOS = 2;
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

function etiquetaPeriodo(periodo, agrupacion) {
  const [, mes, dia] = periodo.split("-");
  return agrupacion === "mes" ? MESES[Number(mes) - 1] : `${dia}/${mes}`;
}

function nombrePeriodo(periodo, agrupacion) {
  if (agrupacion !== "mes") return formatearFecha(periodo);
  const [anio, mes] = periodo.split("-");
  return `${MESES[Number(mes) - 1]} ${anio}`;
}

function redondearEjeArriba(valor) {
  if (valor <= 0) return 0;
  const magnitud = 10 ** Math.floor(Math.log10(valor));
  for (const paso of [1, 2, 5, 10]) {
    const candidato = paso * magnitud;
    if (candidato >= valor) return candidato;
  }
  return 10 * magnitud;
}

// puntos: la serie del resumen [{ periodo, efectivo, tarjeta, transferencia, total }]
// activo: período resaltado (lo controla quien lo usa, para sincronizarlo con la tabla)
export default function GraficoBarras({
  puntos,
  agrupacion,
  activo = null,
  alResaltar = () => {},
  alElegir = () => {},
}) {
  const [ocultas, setOcultas] = useState([]);
  const visibles = MEDIOS_DE_PAGO.filter((medio) => !ocultas.includes(medio));

  function alternar(medio) {
    setOcultas((actuales) => {
      if (actuales.includes(medio)) return actuales.filter((m) => m !== medio);
      return visibles.length > 1 ? [...actuales, medio] : actuales; // siempre queda uno
    });
  }

  const cantidad = puntos.length;
  const totalVisible = (punto) => visibles.reduce((suma, m) => suma + numeroParaElDibujo(punto[m]), 0);
  const maxTotal = Math.max(...puntos.map(totalVisible), 0);
  const puntoActivo = puntos.find((p) => p.periodo === activo) ?? null;

  const hayDatos = maxTotal > 0;
  const maxEje = redondearEjeArriba(maxTotal);
  const escala = hayDatos ? (ALTO_GRAFICO - MARGEN_SUPERIOR) / maxEje : 0;
  const anchoSvg = Math.max(cantidad * ANCHO_POR_BARRA, 280);
  const anchoSlot = anchoSvg / cantidad;
  const anchoBarra = Math.min(ANCHO_MAXIMO_BARRA, anchoSlot * 0.6);
  const pasoEtiqueta = Math.max(1, Math.ceil(cantidad / 10));
  const altoSvg = ALTO_GRAFICO + 26;

  const barras = puntos.map((punto) => {
    let pisoAcumulado = ALTO_GRAFICO;
    const segmentos = visibles.map((medio, indice) => {
      const valor = numeroParaElDibujo(punto[medio]);
      const alturaCompleta = valor * escala;
      const esElUltimo = indice === visibles.length - 1;
      const altura = esElUltimo ? alturaCompleta : Math.max(alturaCompleta - HUECO_ENTRE_SEGMENTOS, 0);
      const y = pisoAcumulado - altura;
      pisoAcumulado -= alturaCompleta;
      return { medio, y, altura, esElUltimo };
    });
    return { periodo: punto.periodo, segmentos };
  });

  return (
    <div className="grafico-barras">
      <div className="grafico-barras-detalle" aria-live="polite">
        {puntoActivo ? (
          <>
            <strong>{nombrePeriodo(puntoActivo.periodo, agrupacion)}</strong>
            {MEDIOS_DE_PAGO.map((medio) => (
              <span key={medio} className="grafico-barras-detalle-medio">
                <span className={`grafico-barras-marca ${CLASE_SERIE_MEDIO[medio]}`} aria-hidden="true" />
                {ETIQUETA_MEDIO[medio]} {formatearDinero(puntoActivo[medio])}
              </span>
            ))}
            <span className="grafico-barras-detalle-total">Total {formatearDinero(puntoActivo.total)}</span>
          </>
        ) : (
          <span className="grafico-barras-ayuda">
            Pasá el mouse por una barra, o tocala, para ver el detalle.
          </span>
        )}
      </div>

      {hayDatos ? (
        <svg
          className={`grafico-barras-svg ${activo ? "grafico-barras-con-activo" : ""}`}
          viewBox={`0 0 ${anchoSvg} ${altoSvg}`}
          width="100%"
          height={altoSvg}
          preserveAspectRatio="xMinYMid meet"
          role="group"
          aria-label={`Ventas por ${agrupacion === "mes" ? "mes" : "día"}, ${cantidad} período(s)`}
        >
          <line
            className="grafico-barras-eje-tope"
            x1={0}
            y1={ALTO_GRAFICO - maxEje * escala}
            x2={anchoSvg}
            y2={ALTO_GRAFICO - maxEje * escala}
          />
          <text className="grafico-barras-etiqueta-eje" x={0} y={ALTO_GRAFICO - maxEje * escala - 4}>
            {formatearDinero(maxEje.toFixed(2))}
          </text>

          {barras.map((barra, indice) => (
            <g
              key={barra.periodo}
              className={`grafico-barras-grupo ${activo === barra.periodo ? "grafico-barras-activa" : ""}`}
              transform={`translate(${indice * anchoSlot + (anchoSlot - anchoBarra) / 2} 0)`}
            >
              <rect
                className="grafico-barras-zona"
                x={-(anchoSlot - anchoBarra) / 2}
                y={0}
                width={anchoSlot}
                height={ALTO_GRAFICO + 22}
                tabIndex={0}
                role="button"
                aria-label={`${nombrePeriodo(barra.periodo, agrupacion)}: ver detalle`}
                onMouseEnter={() => alResaltar(barra.periodo)}
                onMouseLeave={() => alResaltar(null)}
                onFocus={() => alResaltar(barra.periodo)}
                onBlur={() => alResaltar(null)}
                onClick={() => alElegir(barra.periodo)}
                onKeyDown={(evento) => {
                  if (evento.key === "Enter" || evento.key === " ") {
                    evento.preventDefault();
                    alElegir(barra.periodo);
                  }
                }}
              />
              {barra.segmentos.map((segmento) => (
                <rect
                  key={segmento.medio}
                  className={`grafico-barras-segmento ${CLASE_SERIE_MEDIO[segmento.medio]}`}
                  x={0}
                  y={segmento.y}
                  width={anchoBarra}
                  height={segmento.altura}
                  rx={segmento.esElUltimo ? 3 : 0}
                />
              ))}
              {indice % pasoEtiqueta === 0 && (
                <text
                  className="grafico-barras-etiqueta-x"
                  x={anchoBarra / 2}
                  y={ALTO_GRAFICO + 16}
                  textAnchor="middle"
                >
                  {etiquetaPeriodo(barra.periodo, agrupacion)}
                </text>
              )}
            </g>
          ))}

          <line className="grafico-barras-linea-base" x1={0} y1={ALTO_GRAFICO} x2={anchoSvg} y2={ALTO_GRAFICO} />
        </svg>
      ) : (
        <p className="grafico-barras-vacio">Sin ventas para mostrar en este período.</p>
      )}

      <ul className="grafico-barras-leyenda">
        {MEDIOS_DE_PAGO.map((medio) => {
          const encendido = !ocultas.includes(medio);
          return (
            <li key={medio}>
              <button
                type="button"
                className={`grafico-barras-filtro ${encendido ? "" : "grafico-barras-filtro-apagado"}`}
                aria-pressed={encendido}
                onClick={() => alternar(medio)}
                title={encendido ? "Ocultar en el gráfico" : "Mostrar en el gráfico"}
              >
                <span className={`grafico-barras-marca ${CLASE_SERIE_MEDIO[medio]}`} aria-hidden="true" />
                {ETIQUETA_MEDIO[medio]}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
