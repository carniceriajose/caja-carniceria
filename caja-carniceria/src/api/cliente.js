const URL_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const CLAVE_TOKEN = "carniceria_token";

// La sesión vive solo mientras dure la pestaña: nunca en localStorage.
export function guardarToken(token) {
  sessionStorage.setItem(CLAVE_TOKEN, token);
}

export function obtenerToken() {
  return sessionStorage.getItem(CLAVE_TOKEN);
}

export function borrarToken() {
  sessionStorage.removeItem(CLAVE_TOKEN);
}

export class ErrorApi extends Error {
  constructor(mensaje, status) {
    super(mensaje);
    this.status = status;
  }
}

// AuthContext se suscribe acá al montar la app, así un 401 en cualquier
// pedido cierra la sesión sin que cada pantalla tenga que manejarlo.
let alVencerLaSesion = () => {};

export function alDetectar401(funcion) {
  alVencerLaSesion = funcion;
}

export function mensajeDesdeDetalle(detalle) {
  if (!detalle) return "Ocurrió un error inesperado. Probá de nuevo.";
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) {
    return detalle.map((error) => error.msg).filter(Boolean).join(" ") || "Datos inválidos.";
  }
  return "Ocurrió un error inesperado. Probá de nuevo.";
}

async function pedido(ruta, opciones = {}) {
  const encabezados = { ...(opciones.headers || {}) };
  if (opciones.cuerpo !== undefined) {
    encabezados["Content-Type"] = "application/json";
  }
  const token = obtenerToken();
  if (token) {
    encabezados["Authorization"] = `Bearer ${token}`;
  }

  let respuesta;
  try {
    respuesta = await fetch(`${URL_BASE}${ruta}`, {
      method: opciones.metodo || "GET",
      headers: encabezados,
      body: opciones.cuerpo !== undefined ? JSON.stringify(opciones.cuerpo) : undefined,
    });
  } catch {
    throw new ErrorApi("No se pudo conectar con el servidor. Revisá tu conexión.", 0);
  }

  if (respuesta.status === 401) {
    const eraLogin = ruta === "/auth/login";
    if (!eraLogin) {
      borrarToken();
      alVencerLaSesion();
    }
    const datos = await respuesta.json().catch(() => null);
    throw new ErrorApi(mensajeDesdeDetalle(datos?.detail) || "No autenticado.", 401);
  }

  if (respuesta.status === 204) {
    return null;
  }

  const texto = await respuesta.text();
  const datos = texto ? JSON.parse(texto) : null;

  if (!respuesta.ok) {
    throw new ErrorApi(mensajeDesdeDetalle(datos?.detail), respuesta.status);
  }

  return datos;
}

// El paso intermedio del login con segundo factor: el token todavía no es una
// sesión real, así que no pasa por sessionStorage ni por el resto del cliente.
export async function verificarSegundoFactor(tokenParcial, codigo) {
  let respuesta;
  try {
    respuesta = await fetch(`${URL_BASE}/auth/2fa/verificar`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokenParcial}` },
      body: JSON.stringify({ codigo }),
    });
  } catch {
    throw new ErrorApi("No se pudo conectar con el servidor. Revisá tu conexión.", 0);
  }
  const texto = await respuesta.text();
  const datos = texto ? JSON.parse(texto) : null;
  if (!respuesta.ok) {
    throw new ErrorApi(mensajeDesdeDetalle(datos?.detail), respuesta.status);
  }
  return datos;
}

export const api = {
  get: (ruta) => pedido(ruta),
  post: (ruta, cuerpo) => pedido(ruta, { metodo: "POST", cuerpo }),
  put: (ruta, cuerpo) => pedido(ruta, { metodo: "PUT", cuerpo }),
  patch: (ruta, cuerpo) => pedido(ruta, { metodo: "PATCH", cuerpo }),
  eliminar: (ruta) => pedido(ruta, { metodo: "DELETE" }),
};

// Para los reportes (Excel/PDF): en vez de JSON, un archivo que el navegador
// tiene que descargar directo, no mostrar como una respuesta más.
export async function descargarArchivo(ruta, nombrePorDefecto) {
  const encabezados = {};
  const token = obtenerToken();
  if (token) encabezados["Authorization"] = `Bearer ${token}`;

  let respuesta;
  try {
    respuesta = await fetch(`${URL_BASE}${ruta}`, { headers: encabezados });
  } catch {
    throw new ErrorApi("No se pudo conectar con el servidor. Revisá tu conexión.", 0);
  }

  if (!respuesta.ok) {
    if (respuesta.status === 401) {
      borrarToken();
      alVencerLaSesion();
    }
    const datos = await respuesta.json().catch(() => null);
    throw new ErrorApi(mensajeDesdeDetalle(datos?.detail), respuesta.status);
  }

  const disposicion = respuesta.headers.get("Content-Disposition") || "";
  const coincidencia = disposicion.match(/filename="?([^"]+)"?/);
  const nombreArchivo = coincidencia ? coincidencia[1] : nombrePorDefecto;

  const blob = await respuesta.blob();
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

// Para mostrar una imagen protegida (como <img src>): el navegador no manda
// el token en un <img> normal, así que se trae como blob y se arma una URL
// local. Quien la use tiene que revocarla (URL.revokeObjectURL) al desmontar.
export async function obtenerImagenComoUrl(ruta) {
  const encabezados = {};
  const token = obtenerToken();
  if (token) encabezados["Authorization"] = `Bearer ${token}`;

  let respuesta;
  try {
    respuesta = await fetch(`${URL_BASE}${ruta}`, { headers: encabezados });
  } catch {
    throw new ErrorApi("No se pudo conectar con el servidor. Revisá tu conexión.", 0);
  }
  if (!respuesta.ok) {
    if (respuesta.status === 401) {
      borrarToken();
      alVencerLaSesion();
    }
    throw new ErrorApi("No se pudo cargar la imagen.", respuesta.status);
  }
  const blob = await respuesta.blob();
  return URL.createObjectURL(blob);
}
