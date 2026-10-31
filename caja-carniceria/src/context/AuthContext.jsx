import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  alDetectar401,
  api,
  borrarToken,
  guardarToken,
  obtenerToken,
  verificarSegundoFactor,
} from "../api/cliente";
import { expiracionDelToken } from "../utilidades/jwt";

const AuthContext = createContext(null);

// Cuánto antes del vencimiento se avisa, para dar tiempo a escribir la
// contraseña sin llegar a que el token venza de verdad.
const SEGUNDOS_AVISO_ANTES_DE_VENCER = 5 * 60;

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [sesionPorVencer, setSesionPorVencer] = useState(false);
  const temporizadorAviso = useRef(null);

  const cerrarSesion = useCallback(() => {
    borrarToken();
    setUsuario(null);
    setSesionPorVencer(false);
    clearTimeout(temporizadorAviso.current);
  }, []);

  useEffect(() => {
    alDetectar401(cerrarSesion);
  }, [cerrarSesion]);

  const programarAviso = useCallback((token) => {
    clearTimeout(temporizadorAviso.current);
    setSesionPorVencer(false);
    const vencimiento = expiracionDelToken(token);
    if (!vencimiento) return;
    const milisegundosHastaAvisar = vencimiento - Date.now() - SEGUNDOS_AVISO_ANTES_DE_VENCER * 1000;
    if (milisegundosHastaAvisar <= 0) {
      setSesionPorVencer(true);
      return;
    }
    temporizadorAviso.current = setTimeout(() => setSesionPorVencer(true), milisegundosHastaAvisar);
  }, []);

  useEffect(() => {
    async function validarSesionGuardada() {
      const token = obtenerToken();
      if (!token) {
        setCargando(false);
        return;
      }
      try {
        setUsuario(await api.get("/auth/yo"));
        programarAviso(token);
      } catch {
        borrarToken();
      } finally {
        setCargando(false);
      }
    }
    validarSesionGuardada();
    return () => clearTimeout(temporizadorAviso.current);
  }, [programarAviso]);

  // Devuelve { requiere2FA: true, tokenParcial } si falta el segundo factor,
  // o deja la sesión iniciada directamente si el usuario no tiene 2FA.
  const iniciarSesion = useCallback(
    async (usuarioTexto, password) => {
      const respuesta = await api.post("/auth/login", { usuario: usuarioTexto, password });
      if (respuesta.requiere_2fa) {
        return { requiere2FA: true, tokenParcial: respuesta.token_parcial };
      }
      guardarToken(respuesta.token);
      setUsuario(respuesta.usuario);
      programarAviso(respuesta.token);
      return { requiere2FA: false };
    },
    [programarAviso]
  );

  const confirmarSegundoFactor = useCallback(
    async (tokenParcial, codigo) => {
      const respuesta = await verificarSegundoFactor(tokenParcial, codigo);
      guardarToken(respuesta.token);
      setUsuario(respuesta.usuario);
      programarAviso(respuesta.token);
    },
    [programarAviso]
  );

  const actualizarUsuario = useCallback((cambios) => {
    setUsuario((actual) => (actual ? { ...actual, ...cambios } : actual));
  }, []);

  const valor = {
    usuario,
    cargando,
    iniciarSesion,
    confirmarSegundoFactor,
    cerrarSesion,
    actualizarUsuario,
    sesionPorVencer,
  };
  return <AuthContext.Provider value={valor}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const contexto = useContext(AuthContext);
  if (!contexto) throw new Error("useAuth se tiene que usar dentro de <AuthProvider>.");
  return contexto;
}
