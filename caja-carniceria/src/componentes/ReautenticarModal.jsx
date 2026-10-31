import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import MensajeError from "./MensajeError";
import "./ReautenticarModal.css";

// Overlay global: cuando el token está por vencer, pide la contraseña de
// nuevo sin navegar a ningún lado, así lo que la persona tenía escrito en la
// pantalla (un total cargado, un formulario a mitad de llenar) no se pierde.
export default function ReautenticarModal() {
  const { usuario, sesionPorVencer, iniciarSesion, confirmarSegundoFactor, cerrarSesion } = useAuth();
  const [descartado, setDescartado] = useState(false);
  const [password, setPassword] = useState("");
  const [tokenParcial, setTokenParcial] = useState(null);
  const [codigo, setCodigo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

  if (!usuario || !sesionPorVencer || descartado) return null;

  async function alConfirmarPassword(evento) {
    evento.preventDefault();
    setError("");
    setEnviando(true);
    try {
      const resultado = await iniciarSesion(usuario.usuario, password);
      if (resultado.requiere2FA) {
        setTokenParcial(resultado.tokenParcial);
      } else {
        setPassword("");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setEnviando(false);
    }
  }

  async function alConfirmarCodigo(evento) {
    evento.preventDefault();
    setError("");
    setEnviando(true);
    try {
      await confirmarSegundoFactor(tokenParcial, codigo);
      setPassword("");
      setCodigo("");
      setTokenParcial(null);
    } catch (err) {
      setError(err.message);
      setCodigo("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="reautenticar-fondo" role="dialog" aria-modal="true">
      <div className="reautenticar-tarjeta">
        <h2>Tu sesión está por vencer</h2>
        {!tokenParcial ? (
          <form onSubmit={alConfirmarPassword}>
            <p>Ingresá tu contraseña para seguir sin perder lo que estabas haciendo.</p>
            <MensajeError mensaje={error} />
            <label htmlFor="reautenticar-password">Contraseña</label>
            <input
              id="reautenticar-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={enviando}
              autoFocus
              required
            />
            <div className="reautenticar-botones">
              <button type="submit" disabled={enviando}>
                {enviando ? "Confirmando…" : "Seguir conectado"}
              </button>
              <button type="button" className="reautenticar-secundario" onClick={() => setDescartado(true)}>
                Ahora no
              </button>
              <button type="button" className="reautenticar-secundario" onClick={cerrarSesion}>
                Cerrar sesión
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={alConfirmarCodigo}>
            <p>Ingresá el código de tu aplicación autenticadora.</p>
            <MensajeError mensaje={error} />
            <label htmlFor="reautenticar-codigo">Código</label>
            <input
              id="reautenticar-codigo"
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={codigo}
              onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))}
              disabled={enviando}
              autoFocus
              required
            />
            <div className="reautenticar-botones">
              <button type="submit" disabled={enviando || codigo.length !== 6}>
                {enviando ? "Confirmando…" : "Confirmar"}
              </button>
              <button type="button" className="reautenticar-secundario" onClick={cerrarSesion}>
                Cerrar sesión
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
