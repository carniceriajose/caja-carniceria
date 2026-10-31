import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import MensajeError from "../../componentes/MensajeError";
import "./Login.css";

export default function Login() {
  const { usuario, cargando, iniciarSesion, confirmarSegundoFactor } = useAuth();
  const [usuarioTexto, setUsuarioTexto] = useState("");
  const [password, setPassword] = useState("");
  const [tokenParcial, setTokenParcial] = useState(null);
  const [codigo, setCodigo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

  if (!cargando && usuario) {
    return <Navigate to={usuario.rol === "admin" ? "/admin" : "/venta"} replace />;
  }

  async function alEnviarUsuarioYPassword(evento) {
    evento.preventDefault();
    setError("");
    setEnviando(true);
    try {
      const resultado = await iniciarSesion(usuarioTexto, password);
      if (resultado.requiere2FA) {
        setTokenParcial(resultado.tokenParcial);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setEnviando(false);
    }
  }

  async function alEnviarCodigo(evento) {
    evento.preventDefault();
    setError("");
    setEnviando(true);
    try {
      await confirmarSegundoFactor(tokenParcial, codigo);
    } catch (err) {
      setError(err.message);
      setCodigo("");
    } finally {
      setEnviando(false);
    }
  }

  function volver() {
    setTokenParcial(null);
    setCodigo("");
    setError("");
    setPassword("");
  }

  if (tokenParcial) {
    return (
      <div className="login-pantalla">
        <form className="login-tarjeta" onSubmit={alEnviarCodigo}>
          <h1>Verificación en dos pasos</h1>
          <p className="login-subtitulo">
            Ingresá el código de 6 dígitos de tu aplicación autenticadora, o uno de tus códigos de
            recuperación si no tenés el celular a mano.
          </p>

          <MensajeError mensaje={error} />

          <label htmlFor="login-codigo">Código</label>
          <input
            id="login-codigo"
            type="text"
            autoComplete="one-time-code"
            maxLength={10}
            value={codigo}
            onChange={(evento) => setCodigo(evento.target.value.toUpperCase().slice(0, 10))}
            disabled={enviando}
            autoFocus
            required
          />

          <button type="submit" disabled={enviando || (codigo.length !== 6 && codigo.length !== 10)}>
            {enviando ? "Verificando…" : "Confirmar"}
          </button>
          <button type="button" className="login-boton-volver" onClick={volver} disabled={enviando}>
            Volver
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="login-pantalla">
      <form className="login-tarjeta" onSubmit={alEnviarUsuarioYPassword}>
        <h1 className="login-logo">
          <img src="/logo.png" alt="El Abasto de José" />
        </h1>
        <p className="login-subtitulo">Ingresá con tu usuario para empezar.</p>

        <MensajeError mensaje={error} />

        <label htmlFor="login-usuario">Usuario</label>
        <input
          id="login-usuario"
          type="text"
          autoComplete="username"
          value={usuarioTexto}
          onChange={(evento) => setUsuarioTexto(evento.target.value)}
          disabled={enviando}
          required
        />

        <label htmlFor="login-password">Contraseña</label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(evento) => setPassword(evento.target.value)}
          disabled={enviando}
          required
        />

        <button type="submit" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
