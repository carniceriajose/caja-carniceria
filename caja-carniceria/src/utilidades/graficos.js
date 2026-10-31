// Orden fijo de la paleta categórica (nunca se reordena según los datos): así el
// color de "tarjeta" es siempre el mismo en todos los gráficos.
export const MEDIOS_DE_PAGO = ["efectivo", "tarjeta", "transferencia"];

export const ETIQUETA_MEDIO = {
  efectivo: "Efectivo",
  tarjeta: "Tarjeta",
  transferencia: "Transferencia",
};

export const CLASE_SERIE_MEDIO = {
  efectivo: "serie-1",
  tarjeta: "serie-2",
  transferencia: "serie-3",
};

// Solo para calcular proporciones de dibujo (ancho de barra, arco de la dona).
// La plata en sí nunca se guarda ni se recalcula como número: para mostrarla
// se sigue usando el string exacto que manda el backend con formatearDinero().
export function numeroParaElDibujo(textoDinero) {
  return Number(textoDinero || "0");
}
