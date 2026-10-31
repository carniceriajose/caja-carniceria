// Nunca se verifica la firma acá (para eso está el backend): esto solo lee el
// campo "exp" para saber cuándo avisar que la sesión está por vencer.
export function expiracionDelToken(token) {
  try {
    const payload = token.split(".")[1];
    const decodificado = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const datos = JSON.parse(decodificado);
    return typeof datos.exp === "number" ? datos.exp * 1000 : null;
  } catch {
    return null;
  }
}
