import { formatearDinero } from "../utilidades/dinero";
import { numeroParaElDibujo } from "../utilidades/graficos";
import "./GraficoDona.css";

const TAMANIO = 160;
const CENTRO = TAMANIO / 2;
const RADIO = 62;
const GROSOR = 30;
const CIRCUNFERENCIA = 2 * Math.PI * RADIO;
const HUECO_ENTRE_SEGMENTOS = 2; // el mismo "surface gap" que separa las barras apiladas

// El número del centro tiene que entrar en el agujero de la dona: cuanto más
// larga la cifra, más chica la letra (nunca se trunca ni se redondea la plata).
function tamanioTextoTotal(texto) {
  if (texto.length <= 9) return 17;
  if (texto.length <= 11) return 14.5;
  if (texto.length <= 13) return 12.5;
  return 11;
}

// segmentos: [{ clave, etiqueta, claseColor, monto (string) }]
export default function GraficoDona({ segmentos, totalTexto }) {
  const total = segmentos.reduce((suma, s) => suma + numeroParaElDibujo(s.monto), 0);

  if (total <= 0) {
    return <p className="grafico-dona-vacio">Sin ventas en este período.</p>;
  }

  let acumulado = 0;
  const arcos = segmentos.map((segmento) => {
    const valor = numeroParaElDibujo(segmento.monto);
    const largoCompleto = (valor / total) * CIRCUNFERENCIA;
    const largoDibujado = Math.max(largoCompleto - HUECO_ENTRE_SEGMENTOS, 0);
    const arco = {
      ...segmento,
      porcentaje: Math.round((valor / total) * 100),
      dasharray: `${largoDibujado} ${CIRCUNFERENCIA - largoDibujado}`,
      dashoffset: -acumulado,
    };
    acumulado += largoCompleto;
    return arco;
  });

  return (
    <div className="grafico-dona">
      <svg
        className="grafico-dona-svg"
        viewBox={`0 0 ${TAMANIO} ${TAMANIO}`}
        width={TAMANIO}
        height={TAMANIO}
        role="img"
        aria-label={`Ventas por medio de pago: ${segmentos
          .map((s) => `${s.etiqueta} ${formatearDinero(s.monto)}`)
          .join(", ")}`}
      >
        <circle
          className="grafico-dona-pista"
          cx={CENTRO}
          cy={CENTRO}
          r={RADIO}
          strokeWidth={GROSOR}
          fill="none"
        />
        {arcos.map((arco) => (
          <circle
            key={arco.clave}
            className={`grafico-dona-segmento ${arco.claseColor}`}
            cx={CENTRO}
            cy={CENTRO}
            r={RADIO}
            fill="none"
            strokeWidth={GROSOR}
            strokeDasharray={arco.dasharray}
            strokeDashoffset={arco.dashoffset}
            transform={`rotate(-90 ${CENTRO} ${CENTRO})`}
          >
            <title>
              {arco.etiqueta}: {formatearDinero(arco.monto)} ({arco.porcentaje}%)
            </title>
          </circle>
        ))}
        <text
          x={CENTRO}
          y={CENTRO - 4}
          textAnchor="middle"
          fontSize={tamanioTextoTotal(formatearDinero(totalTexto))}
          className="grafico-dona-texto-total"
        >
          {formatearDinero(totalTexto)}
        </text>
        <text x={CENTRO} y={CENTRO + 16} textAnchor="middle" className="grafico-dona-texto-etiqueta">
          Total
        </text>
      </svg>

      <ul className="grafico-dona-leyenda">
        {arcos.map((arco) => (
          <li key={arco.clave}>
            <span className={`grafico-dona-marca ${arco.claseColor}`} aria-hidden="true" />
            <span className="grafico-dona-leyenda-etiqueta">{arco.etiqueta}</span>
            <span className="grafico-dona-leyenda-monto">{formatearDinero(arco.monto)}</span>
            <span className="grafico-dona-leyenda-porcentaje">{arco.porcentaje}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
