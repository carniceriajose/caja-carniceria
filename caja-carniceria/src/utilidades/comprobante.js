export function formatearNumeroComprobante(puntoVenta, numero) {
  return `${String(puntoVenta).padStart(4, "0")}-${String(numero).padStart(8, "0")}`;
}
