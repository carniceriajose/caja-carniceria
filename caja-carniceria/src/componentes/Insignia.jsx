import "./Insignia.css";

export const ETIQUETA_ESTADO = {
  no_aplica: "No se factura",
  pendiente: "Pendiente",
  facturada: "Facturada",
  fallo: "Con error",
};

// Estado fiscal de una venta como píldora de color. Si está anulada, eso
// pisa cualquier otro estado: ya no cuenta como venta real.
export default function Insignia({ estado, anulada = false }) {
  if (anulada) {
    return <span className="insignia insignia-anulada">Anulada</span>;
  }
  return <span className={`insignia insignia-${estado}`}>{ETIQUETA_ESTADO[estado] ?? estado}</span>;
}
