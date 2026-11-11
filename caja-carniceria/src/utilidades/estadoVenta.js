// Bandera compartida y simple (no hace falta Context) para que el aviso de
// actualización sepa si hay una venta a medio cargar antes de recargar la página.
let ventaEnCurso = false;

export function marcarVentaEnCurso(valor) {
  ventaEnCurso = valor;
}

export function hayVentaEnCurso() {
  return ventaEnCurso;
}
