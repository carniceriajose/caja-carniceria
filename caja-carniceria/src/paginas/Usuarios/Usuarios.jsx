import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../../api/cliente";
import { useAuth } from "../../context/AuthContext";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import TituloSeccion from "../../componentes/TituloSeccion";
import SelectEstilizado from "../../componentes/SelectEstilizado";
import { IconoUsuarios } from "../../componentes/Iconos";
import SeguridadPropia from "./SeguridadPropia";
import "./Usuarios.css";

const FORMULARIO_VACIO = { nombre: "", usuario: "", password: "", rol: "vendedor" };

export default function Usuarios() {
  const { usuario: propio } = useAuth();

  const [usuarios, setUsuarios] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  const [formulario, setFormulario] = useState(FORMULARIO_VACIO);
  const [editandoId, setEditandoId] = useState(null);
  const [errorFormulario, setErrorFormulario] = useState("");
  const [guardando, setGuardando] = useState(false);

  const [restableciendoId, setRestableciendoId] = useState(null);
  const [passwordNueva, setPasswordNueva] = useState("");
  const [errorPassword, setErrorPassword] = useState("");
  const [restableciendo, setRestableciendo] = useState(false);

  const [errorFila, setErrorFila] = useState({ id: null, mensaje: "" });

  const cargarUsuarios = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      setUsuarios(await api.get("/usuarios"));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargarUsuarios();
  }, [cargarUsuarios]);

  function empezarEdicion(fila) {
    setEditandoId(fila.id);
    setFormulario({ nombre: fila.nombre, usuario: fila.usuario, password: "", rol: fila.rol });
    setErrorFormulario("");
  }

  function cancelarEdicion() {
    setEditandoId(null);
    setFormulario(FORMULARIO_VACIO);
    setErrorFormulario("");
  }

  async function alGuardar(evento) {
    evento.preventDefault();
    setErrorFormulario("");
    setGuardando(true);
    try {
      if (editandoId) {
        const actualizado = await api.patch(`/usuarios/${editandoId}`, {
          nombre: formulario.nombre,
          rol: formulario.rol,
        });
        setUsuarios((actuales) => actuales.map((u) => (u.id === actualizado.id ? actualizado : u)));
      } else {
        const creado = await api.post("/usuarios", {
          nombre: formulario.nombre,
          usuario: formulario.usuario,
          password: formulario.password,
          rol: formulario.rol,
        });
        setUsuarios((actuales) => [...actuales, creado]);
      }
      cancelarEdicion();
    } catch (err) {
      setErrorFormulario(err.message);
    } finally {
      setGuardando(false);
    }
  }

  async function alCambiarActivo(fila) {
    if (fila.activo) {
      const confirmar = window.confirm(`¿Desactivar a ${fila.nombre}? No va a poder iniciar sesión.`);
      if (!confirmar) return;
    }
    setErrorFila({ id: null, mensaje: "" });
    try {
      const actualizado = await api.patch(`/usuarios/${fila.id}`, { activo: !fila.activo });
      setUsuarios((actuales) => actuales.map((u) => (u.id === actualizado.id ? actualizado : u)));
    } catch (err) {
      setErrorFila({ id: fila.id, mensaje: err.message });
    }
  }

  function empezarRestablecer(fila) {
    setRestableciendoId(fila.id);
    setPasswordNueva("");
    setErrorPassword("");
  }

  function cancelarRestablecer() {
    setRestableciendoId(null);
    setPasswordNueva("");
    setErrorPassword("");
  }

  async function alRestablecer(evento, fila) {
    evento.preventDefault();
    const confirmar = window.confirm(`¿Restablecer la contraseña de ${fila.nombre}?`);
    if (!confirmar) return;
    setErrorPassword("");
    setRestableciendo(true);
    try {
      await api.put(`/usuarios/${fila.id}/password`, { password: passwordNueva });
      cancelarRestablecer();
    } catch (err) {
      setErrorPassword(err.message);
    } finally {
      setRestableciendo(false);
    }
  }

  async function resetear2FA(fila) {
    const confirmar = window.confirm(
      `¿Desactivar la verificación en dos pasos de ${fila.nombre}? Va a poder entrar de nuevo solo con su contraseña.`
    );
    if (!confirmar) return;
    setErrorFila({ id: null, mensaje: "" });
    try {
      await api.put(`/usuarios/${fila.id}/2fa`);
      setUsuarios((actuales) => actuales.map((u) => (u.id === fila.id ? { ...u, dos_factores_activo: false } : u)));
    } catch (err) {
      setErrorFila({ id: fila.id, mensaje: err.message });
    }
  }

  return (
    <div className="usuarios">
      <h1>Usuarios</h1>

      <SeguridadPropia />

      <section className="usuarios-seccion">
        <TituloSeccion Icono={IconoUsuarios}>{editandoId ? "Editar usuario" : "Nuevo usuario"}</TituloSeccion>
        <form className="usuarios-formulario" onSubmit={alGuardar}>
          <MensajeError mensaje={errorFormulario} />
          <div className="usuarios-formulario-fila">
            <label>
              Nombre
              <input
                type="text"
                value={formulario.nombre}
                onChange={(e) => setFormulario({ ...formulario, nombre: e.target.value })}
                disabled={guardando}
                required
              />
            </label>
            <label>
              Usuario
              <input
                type="text"
                value={formulario.usuario}
                onChange={(e) => setFormulario({ ...formulario, usuario: e.target.value })}
                disabled={guardando || Boolean(editandoId)}
                title={editandoId ? "El nombre de usuario no se puede cambiar." : undefined}
                required
              />
            </label>
            {!editandoId && (
              <label>
                Contraseña
                <input
                  type="password"
                  value={formulario.password}
                  onChange={(e) => setFormulario({ ...formulario, password: e.target.value })}
                  disabled={guardando}
                  minLength={8}
                  required
                />
              </label>
            )}
            <label>
              Rol
              <SelectEstilizado
                etiqueta="Rol"
                value={formulario.rol}
                onChange={(valor) => setFormulario({ ...formulario, rol: valor })}
                disabled={guardando || (editandoId === propio?.id)}
                title={editandoId === propio?.id ? "No podés cambiar tu propio rol." : undefined}
                opciones={[
                  { valor: "vendedor", etiqueta: "Vendedor" },
                  { valor: "admin", etiqueta: "Admin" },
                ]}
              />
            </label>
          </div>
          <div className="usuarios-formulario-botones">
            <button type="submit" disabled={guardando}>
              {guardando ? "Guardando…" : editandoId ? "Guardar cambios" : "Crear usuario"}
            </button>
            {editandoId && (
              <button type="button" className="usuarios-boton-secundario" onClick={cancelarEdicion} disabled={guardando}>
                Cancelar
              </button>
            )}
          </div>
        </form>
      </section>

      <section className="usuarios-seccion">
        <TituloSeccion Icono={IconoUsuarios}>Listado</TituloSeccion>
        {cargando && <Cargando texto="Cargando usuarios…" />}
        {!cargando && error && <MensajeError mensaje={error} onReintentar={cargarUsuarios} />}
        {!cargando && !error && usuarios && (
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Usuario</th>
                <th>Rol</th>
                <th>Estado</th>
                <th>2FA</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map((fila) => {
                const esUnoMismo = fila.id === propio?.id;
                return (
                  <Fragment key={fila.id}>
                    <tr>
                      <td>{fila.nombre}</td>
                      <td>{fila.usuario}</td>
                      <td>{fila.rol === "admin" ? "Admin" : "Vendedor"}</td>
                      <td>
                        <span className={`usuarios-estado ${fila.activo ? "usuarios-estado-activo" : "usuarios-estado-inactivo"}`}>
                          {fila.activo ? "Activo" : "Inactivo"}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`usuarios-estado ${fila.dos_factores_activo ? "usuarios-estado-activo" : "usuarios-estado-inactivo"}`}
                        >
                          {fila.dos_factores_activo ? "Activado" : "Desactivado"}
                        </span>
                      </td>
                      <td className="usuarios-acciones">
                        <button type="button" onClick={() => empezarEdicion(fila)}>
                          Editar
                        </button>
                        <button
                          type="button"
                          className={fila.activo ? "usuarios-boton-desactivar" : ""}
                          onClick={() => alCambiarActivo(fila)}
                          disabled={esUnoMismo && fila.activo}
                          title={esUnoMismo && fila.activo ? "No podés desactivarte a vos mismo." : undefined}
                        >
                          {fila.activo ? "Desactivar" : "Activar"}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            restableciendoId === fila.id ? cancelarRestablecer() : empezarRestablecer(fila)
                          }
                        >
                          Resetear contraseña
                        </button>
                        {fila.dos_factores_activo && (
                          <button
                            type="button"
                            onClick={() => resetear2FA(fila)}
                            disabled={esUnoMismo}
                            title={esUnoMismo ? "Desactivala vos misma en 'Mi verificación en dos pasos'." : undefined}
                          >
                            Resetear 2FA
                          </button>
                        )}
                      </td>
                    </tr>
                    {errorFila.id === fila.id && (
                      <tr className="usuarios-fila-detalle">
                        <td colSpan={6}>
                          <MensajeError mensaje={errorFila.mensaje} />
                        </td>
                      </tr>
                    )}
                    {restableciendoId === fila.id && (
                      <tr className="usuarios-fila-detalle">
                        <td colSpan={6}>
                          <form className="usuarios-restablecer" onSubmit={(e) => alRestablecer(e, fila)}>
                            <MensajeError mensaje={errorPassword} />
                            <label>
                              Nueva contraseña para {fila.nombre}
                              <input
                                type="password"
                                value={passwordNueva}
                                onChange={(e) => setPasswordNueva(e.target.value)}
                                minLength={8}
                                disabled={restableciendo}
                                autoFocus
                                required
                              />
                            </label>
                            <div className="usuarios-formulario-botones">
                              <button type="submit" disabled={restableciendo}>
                                {restableciendo ? "Guardando…" : "Confirmar"}
                              </button>
                              <button
                                type="button"
                                className="usuarios-boton-secundario"
                                onClick={cancelarRestablecer}
                                disabled={restableciendo}
                              >
                                Cancelar
                              </button>
                            </div>
                          </form>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
