const ZONA_ARGENTINA = "America/Argentina/Buenos_Aires";

// en-CA da directo el formato AAAA-MM-DD, que es lo que espera la API.
const formateador = new Intl.DateTimeFormat("en-CA", { timeZone: ZONA_ARGENTINA });

export function hoyArgentina() {
  return formateador.format(new Date());
}

function sumarDias(fechaTexto, dias) {
  const fecha = new Date(`${fechaTexto}T12:00:00Z`); // mediodía UTC: evita cruzar de día
  fecha.setUTCDate(fecha.getUTCDate() + dias);
  return formateador.format(fecha);
}

export function rangosRapidos() {
  const hoy = hoyArgentina();
  const [anio, mes] = hoy.split("-");

  return {
    hoy: { desde: hoy, hasta: hoy },
    semana: { desde: sumarDias(hoy, -6), hasta: hoy },
    mes: { desde: `${anio}-${mes}-01`, hasta: hoy },
    anio: { desde: `${anio}-01-01`, hasta: hoy },
  };
}

// AAAA-MM-DD -> DD/MM/AAAA, sin pasar por Date (no hay corrimientos de zona).
export function formatearFecha(fechaTexto) {
  if (!fechaTexto) return "-";
  const [anio, mes, dia] = fechaTexto.split("-");
  return `${dia}/${mes}/${anio}`;
}

export function formatearFechaHora(iso) {
  return new Date(iso).toLocaleString("es-AR", { timeZone: ZONA_ARGENTINA });
}

// 20111111112 -> 20-11111111-2
export function formatearCuit(cuit) {
  return /^\d{11}$/.test(cuit) ? `${cuit.slice(0, 2)}-${cuit.slice(2, 10)}-${cuit.slice(10)}` : cuit;
}

export function formatearHora(iso) {
  return new Date(iso).toLocaleTimeString("es-AR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: ZONA_ARGENTINA,
  });
}
