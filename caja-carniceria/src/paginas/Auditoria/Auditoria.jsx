import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/cliente";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import SelectEstilizado from "../../componentes/SelectEstilizado";
import { formatearFechaHora, hoyArgentina } from "../../utilidades/fechas";
import "./Auditoria.css";

const POR_PAGINA = 15;

const ETIQUETA_ACCION = {
  "login.exitoso": "Inició sesión",
  "login.fallido": "Intento de acceso fallido",
  "usuario.crear": "Creó un usuario",
  "usuario.actualizar": "Editó un usuario",
  "usuario.resetear_password": "Reseteó una contraseña",
  "configuracion.cambiar": "Cambió la configuración de facturación",
  "gasto.crear": "Cargó un gasto",
  "gasto.actualizar": "Editó un gasto",
  "gasto.borrar": "Borró un gasto",
  "factura.reintentar": "Reintentó una factura",
  "venta.anular": "Anuló una venta",
  "2fa.activar": "Activó su verificación en dos pasos",
  "2fa.desactivar": "Desactivó su verificación en dos pasos",
  "2fa.resetear_por_admin": "Reseteó la verificación en dos pasos de otro usuario",
  "2fa.recuperacion_usada": "Entró con un código de recuperación",
};

function etiquetaDeAccion(accion) {
  return ETIQUETA_ACCION[accion] ?? accion;
}

function resumenDetalle(fila) {
  const d = fila.detalle;
  if (fila.accion === "login.fallido") {
    return d?.usuario_intentado ? `Usuario "${d.usuario_intentado}" no existe` : d?.motivo === "codigo_2fa_invalido" ? "Código de 2FA incorrecto" : "Contraseña incorrecta";
  }
  if (!d) return "";
  if (d.usuario_afectado) {
    if (fila.accion === "usuario.actualizar" && d.cambios) {
      const partes = Object.entries(d.cambios).map(([campo, { antes, despues }]) => `${campo}: ${antes} → ${despues}`);
      return `${d.usuario_afectado} (${partes.join(", ")})`;
    }
    return d.usuario_afectado;
  }
  if (fila.accion === "configuracion.cambiar") {
    const activos = Object.entries(d)
      .filter(([, valor]) => valor === true)
      .map(([clave]) => clave.replace("facturar_", ""));
    return activos.length ? `Se factura: ${activos.join(", ")}` : "No se factura ningún medio";
  }
  if (fila.accion.startsWith("gasto.")) return `Gasto #${d.gasto_id}`;
  if (fila.accion === "factura.reintentar") return `Venta #${d.venta_id}`;
  if (fila.accion === "venta.anular") return `Venta #${d.venta_id}: ${d.motivo}`;
  return JSON.stringify(d);
}

export default function Auditoria() {
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [accion, setAccion] = useState("");
  const [usuarioId, setUsuarioId] = useState("");
  const [pagina, setPagina] = useState(1);

  const [datos, setDatos] = useState(null);
  const [usuarios, setUsuarios] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  const rangoInvertido = desde && hasta && desde > hasta;

  useEffect(() => {
    api
      .get("/usuarios")
      .then(setUsuarios)
      .catch(() => setUsuarios([]));
  }, []);

  const cargar = useCallback(async () => {
    if (rangoInvertido) return;
    setCargando(true);
    setError("");
    const parametros = new URLSearchParams({ pagina: String(pagina), por_pagina: String(POR_PAGINA) });
    if (desde) parametros.set("desde", desde);
    if (hasta) parametros.set("hasta", hasta);
    if (accion) parametros.set("accion", accion);
    if (usuarioId) parametros.set("usuario_id", usuarioId);
    try {
      setDatos(await api.get(`/auditoria?${parametros}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [pagina, desde, hasta, accion, usuarioId, rangoInvertido]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function cambiarFiltro(setter) {
    return (evento) => {
      setPagina(1);
      setter(evento.target.value);
    };
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.total / POR_PAGINA)) : 1;

  return (
    <div className="auditoria">
      <h1>Auditoría</h1>
      <p className="auditoria-subtitulo">Quién hizo cada cambio administrativo, y cuándo.</p>

      <div className="auditoria-filtros">
        <label>
          Desde
          <input type="date" value={desde} max={hoyArgentina()} onChange={cambiarFiltro(setDesde)} />
        </label>
        <label>
          Hasta
          <input type="date" value={hasta} max={hoyArgentina()} onChange={cambiarFiltro(setHasta)} />
        </label>
        <label>
          Acción
          <SelectEstilizado
            etiqueta="Acción"
            value={accion}
            onChange={(valor) => {
              setPagina(1);
              setAccion(valor);
            }}
            opciones={[
              { valor: "", etiqueta: "Todas" },
              ...Object.entries(ETIQUETA_ACCION).map(([valor, etiqueta]) => ({ valor, etiqueta })),
            ]}
          />
        </label>
        <label>
          Usuario
          <SelectEstilizado
            etiqueta="Usuario"
            value={usuarioId}
            onChange={(valor) => {
              setPagina(1);
              setUsuarioId(valor);
            }}
            opciones={[
              { valor: "", etiqueta: "Todos" },
              ...usuarios.map((u) => ({ valor: String(u.id), etiqueta: u.nombre })),
            ]}
          />
        </label>
      </div>

      {rangoInvertido && <MensajeError mensaje="La fecha 'desde' no puede ser posterior a 'hasta'." />}
      {!rangoInvertido && cargando && <Cargando texto="Cargando auditoría…" />}
      {!rangoInvertido && !cargando && error && <MensajeError mensaje={error} onReintentar={cargar} />}

      {!rangoInvertido && !cargando && !error && datos && (
        <>
          <div className="auditoria-tabla">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Quién</th>
                  <th>Acción</th>
                  <th>Detalle</th>
                </tr>
              </thead>
              <tbody>
                {datos.items.length === 0 && (
                  <tr>
                    <td colSpan={4} className="auditoria-vacio">
                      No hay movimientos con estos filtros.
                    </td>
                  </tr>
                )}
                {datos.items.map((fila) => (
                  <tr key={fila.id}>
                    <td>{formatearFechaHora(fila.creado_en)}</td>
                    <td>{fila.usuario?.nombre ?? "—"}</td>
                    <td>{etiquetaDeAccion(fila.accion)}</td>
                    <td className="auditoria-detalle">{resumenDetalle(fila)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPaginas > 1 && (
            <div className="auditoria-paginado">
              <button type="button" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                Anterior
              </button>
              <span>
                Página {pagina} de {totalPaginas}
              </span>
              <button type="button" disabled={pagina >= totalPaginas} onClick={() => setPagina((p) => p + 1)}>
                Siguiente
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
