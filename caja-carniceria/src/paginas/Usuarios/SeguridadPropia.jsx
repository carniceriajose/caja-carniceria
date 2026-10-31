import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { api } from "../../api/cliente";
import { useAuth } from "../../context/AuthContext";
import MensajeError from "../../componentes/MensajeError";
import TituloSeccion from "../../componentes/TituloSeccion";
import { IconoEscudo } from "../../componentes/Iconos";

// Autogestión del segundo factor (TOTP) del propio admin logueado.
export default function SeguridadPropia() {
  const { usuario, actualizarUsuario } = useAuth();
  const [configurando, setConfigurando] = useState(false);
  const [datosQr, setDatosQr] = useState(null);
  const [qrImagen, setQrImagen] = useState("");
  const [codigo, setCodigo] = useState("");
  const [codigosRecuperacion, setCodigosRecuperacion] = useState(null);
  const [mostrarDesactivar, setMostrarDesactivar] = useState(false);
  const [passwordDesactivar, setPasswordDesactivar] = useState("");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!datosQr) {
      setQrImagen("");
      return undefined;
    }
    let cancelado = false;
    QRCode.toDataURL(datosQr.qr_url, { margin: 0, width: 200 })
      .then((url) => {
        if (!cancelado) setQrImagen(url);
      })
      .catch(() => {
        if (!cancelado) setQrImagen("");
      });
    return () => {
      cancelado = true;
    };
  }, [datosQr]);

  async function empezarActivacion() {
    setError("");
    setCargando(true);
    try {
      setDatosQr(await api.post("/auth/2fa/iniciar"));
      setConfigurando(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  function cancelarActivacion() {
    setConfigurando(false);
    setDatosQr(null);
    setCodigo("");
    setError("");
  }

  async function confirmarActivacion(evento) {
    evento.preventDefault();
    setError("");
    setCargando(true);
    try {
      const respuesta = await api.post("/auth/2fa/activar", { secreto: datosQr.secreto, codigo });
      actualizarUsuario({ dos_factores_activo: true });
      setCodigosRecuperacion(respuesta.codigos);
      cancelarActivacion();
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  async function desactivar(evento) {
    evento.preventDefault();
    setError("");
    setCargando(true);
    try {
      await api.post("/auth/2fa/desactivar", { password: passwordDesactivar });
      actualizarUsuario({ dos_factores_activo: false });
      setMostrarDesactivar(false);
      setPasswordDesactivar("");
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  if (codigosRecuperacion) {
    return (
      <section className="usuarios-seccion">
        <TituloSeccion Icono={IconoEscudo}>Guardá tus códigos de recuperación</TituloSeccion>
        <p className="usuarios-2fa-estado">
          Si perdés el celular, cada uno de estos códigos sirve una sola vez para entrar en lugar del
          código de la app. Anotalos en un lugar seguro: no se van a volver a mostrar.
        </p>
        <ul className="usuarios-2fa-codigos">
          {codigosRecuperacion.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <button type="button" onClick={() => setCodigosRecuperacion(null)}>
          Ya los anoté
        </button>
      </section>
    );
  }

  return (
    <section className="usuarios-seccion">
      <TituloSeccion Icono={IconoEscudo}>Mi verificación en dos pasos</TituloSeccion>
      <MensajeError mensaje={error} />

      {usuario.dos_factores_activo && (
        <>
          <p className="usuarios-2fa-estado usuarios-2fa-activo">Activada en tu cuenta.</p>
          {!mostrarDesactivar ? (
            <button type="button" className="usuarios-boton-secundario" onClick={() => setMostrarDesactivar(true)}>
              Desactivar
            </button>
          ) : (
            <form className="usuarios-restablecer" onSubmit={desactivar}>
              <label>
                Confirmá tu contraseña para desactivarla
                <input
                  type="password"
                  value={passwordDesactivar}
                  onChange={(e) => setPasswordDesactivar(e.target.value)}
                  disabled={cargando}
                  autoFocus
                  required
                />
              </label>
              <div className="usuarios-formulario-botones">
                <button type="submit" disabled={cargando}>
                  {cargando ? "Guardando…" : "Confirmar"}
                </button>
                <button
                  type="button"
                  className="usuarios-boton-secundario"
                  onClick={() => {
                    setMostrarDesactivar(false);
                    setPasswordDesactivar("");
                  }}
                  disabled={cargando}
                >
                  Cancelar
                </button>
              </div>
            </form>
          )}
        </>
      )}

      {!usuario.dos_factores_activo && !configurando && (
        <>
          <p className="usuarios-2fa-estado">
            No está activada. Con la app autenticadora (Google Authenticator, Authy, etc.) te va a pedir
            un código además de la contraseña al entrar.
          </p>
          <button type="button" onClick={empezarActivacion} disabled={cargando}>
            {cargando ? "Generando…" : "Activar"}
          </button>
        </>
      )}

      {!usuario.dos_factores_activo && configurando && datosQr && (
        <form className="usuarios-2fa-configurar" onSubmit={confirmarActivacion}>
          <p>Escaneá este código con tu aplicación autenticadora:</p>
          {qrImagen && <img src={qrImagen} alt="Código QR para activar la verificación en dos pasos" width={180} height={180} />}
          <p className="usuarios-2fa-secreto">
            O escribilo a mano: <code>{datosQr.secreto}</code>
          </p>
          <label>
            Código de la app
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={codigo}
              onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))}
              disabled={cargando}
              autoFocus
              required
            />
          </label>
          <div className="usuarios-formulario-botones">
            <button type="submit" disabled={cargando || codigo.length !== 6}>
              {cargando ? "Confirmando…" : "Confirmar"}
            </button>
            <button type="button" className="usuarios-boton-secundario" onClick={cancelarActivacion} disabled={cargando}>
              Cancelar
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
