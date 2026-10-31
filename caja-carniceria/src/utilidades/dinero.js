// La plata nunca pasa por Number/float acá: son operaciones de texto sobre el
// string que ya manda el backend con 2 decimales exactos.

const PATRON_TOTAL = /^(0|[1-9]\d{0,9})(\.\d{1,2})?$/;

export function totalValido(texto) {
  if (typeof texto !== "string" || !PATRON_TOTAL.test(texto)) return false;
  return !/^0(\.0{1,2})?$/.test(texto); // no puede ser cero
}

export function formatearDinero(valorTexto) {
  if (valorTexto === null || valorTexto === undefined) return "-";
  const negativo = valorTexto.startsWith("-");
  const texto = negativo ? valorTexto.slice(1) : valorTexto;
  const [entero, decimales = "00"] = texto.split(".");
  const conSeparadores = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${negativo ? "-" : ""}$${conSeparadores},${decimales.padEnd(2, "0")}`;
}

// Teclado en pantalla de la caja: arma el monto como texto (nunca como número)
// y no deja escribir más de 10 enteros ni más de 2 decimales.
export function teclearMonto(actual, tecla) {
  if (tecla === "borrar") return actual.slice(0, -1);
  if (tecla === "limpiar") return "";
  if (tecla === ".") {
    if (actual.includes(".")) return actual;
    return `${actual === "" ? "0" : actual}.`;
  }
  const nuevo = actual === "0" ? tecla : actual + tecla; // evita ceros a la izquierda
  const [entero, decimales] = nuevo.split(".");
  if (entero.length > 10 || (decimales !== undefined && decimales.length > 2)) return actual;
  return nuevo;
}

// Lo que se escribe con el teclado físico: acepta coma o punto decimal.
export function normalizarMonto(texto) {
  const limpio = texto.replace(",", ".").trim();
  return /^\d{0,10}(\.\d{0,2})?$/.test(limpio) ? limpio : null;
}
