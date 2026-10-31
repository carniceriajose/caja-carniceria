import { useCallback, useEffect, useState } from "react";
import { useDatos } from "../../context/DatosContext";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import TituloSeccion from "../../componentes/TituloSeccion";
import { IconoCategorias } from "../../componentes/Iconos";

// El backend siempre las devuelve con 2 decimales exactos: el <select> tiene
// que ofrecer el mismo formato, para que el valor que viene de la API haga
// match con una de las opciones.
const ALICUOTAS = ["0.00", "2.50", "5.00", "10.50", "21.00", "27.00"];

function filaDesde(rubro) {
  return {
    nombre: rubro.nombre,
    alicuota: rubro.alicuota,
    descripcion_factura: rubro.descripcion_factura,
    activo: rubro.activo,
    orden: rubro.orden,
    es_predeterminado: rubro.es_predeterminado,
  };
}

export default function RubrosConfiguracion() {
  const { rubros, cargarRubros, crearRubro, actualizarRubro } = useDatos();
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [filas, setFilas] = useState({});
  const [guardandoId, setGuardandoId] = useState(null);
  const [errorFilaId, setErrorFilaId] = useState(null);

  const [nueva, setNueva] = useState({
    nombre: "", alicuota: "21.00", descripcion_factura: "", orden: "1",
  });
  const [agregando, setAgregando] = useState(false);
  const [errorAgregar, setErrorAgregar] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      const datos = await cargarRubros();
      setFilas(Object.fromEntries(datos.map((r) => [r.id, filaDesde(r)])));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [cargarRubros]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function cambiarFila(id, campo, valor) {
    setFilas((actuales) => {
      const siguientes = { ...actuales, [id]: { ...actuales[id], [campo]: valor } };
      // Elegir un predeterminado nuevo se lo saca, en la vista, al que lo
      // tenía (el servidor hace lo mismo al guardar).
      if (campo === "es_predeterminado" && valor) {
        for (const otroId of Object.keys(siguientes)) {
          if (otroId !== String(id)) siguientes[otroId] = { ...siguientes[otroId], es_predeterminado: false };
        }
      }
      return siguientes;
    });
  }

  async function guardarFila(id) {
    setErrorFilaId(null);
    setGuardandoId(id);
    try {
      const fila = filas[id];
      await actualizarRubro(id, { ...fila, orden: Number(fila.orden) });
      await cargar();
    } catch (err) {
      setErrorFilaId(id);
      setFilas((actuales) => ({ ...actuales, [id]: { ...actuales[id], _error: err.message } }));
    } finally {
      setGuardandoId(null);
    }
  }

  async function alAgregar(evento) {
    evento.preventDefault();
    setErrorAgregar("");
    setAgregando(true);
    try {
      const rubro = await crearRubro({
        nombre: nueva.nombre,
        alicuota: nueva.alicuota,
        descripcion_factura: nueva.descripcion_factura,
        activo: true,
        orden: Number(nueva.orden),
        es_predeterminado: false,
      });
      setFilas((actuales) => ({ ...actuales, [rubro.id]: filaDesde(rubro) }));
      setNueva({ nombre: "", alicuota: "21.00", descripcion_factura: "", orden: "1" });
    } catch (err) {
      setErrorAgregar(err.message);
    } finally {
      setAgregando(false);
    }
  }

  return (
    <section className="configuracion-seccion">
      <TituloSeccion Icono={IconoCategorias}>Rubros</TituloSeccion>
      <p className="configuracion-ayuda">
        Los que elige el vendedor al cobrar: cada uno define su propia alícuota de IVA y la descripción que
        sale en la factura. El predeterminado es el que viene elegido de entrada. Siempre tiene que haber uno
        predeterminado y al menos uno activo.
      </p>

      {cargando && <Cargando texto="Cargando rubros…" />}
      {!cargando && error && <MensajeError mensaje={error} onReintentar={cargar} />}

      {!cargando && !error && rubros && (
        <>
          <div className="rubros-tabla tabla-apilable">
            <table>
              <thead>
                <tr>
                  <th>Orden</th>
                  <th>Nombre</th>
                  <th>Alícuota</th>
                  <th>Descripción en factura</th>
                  <th>Predet.</th>
                  <th>Activo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rubros.map((r) => {
                  const fila = filas[r.id] ?? filaDesde(r);
                  return (
                    <tr key={r.id}>
                      <td data-label="Orden">
                        <input
                          type="number"
                          min={0}
                          className="rubros-campo-corto"
                          value={fila.orden}
                          onChange={(e) => cambiarFila(r.id, "orden", e.target.value)}
                          disabled={guardandoId === r.id}
                        />
                      </td>
                      <td data-label="Nombre">
                        <input
                          type="text"
                          value={fila.nombre}
                          onChange={(e) => cambiarFila(r.id, "nombre", e.target.value)}
                          disabled={guardandoId === r.id}
                        />
                      </td>
                      <td data-label="Alícuota">
                        <select
                          value={fila.alicuota}
                          onChange={(e) => cambiarFila(r.id, "alicuota", e.target.value)}
                          disabled={guardandoId === r.id}
                        >
                          {ALICUOTAS.map((a) => (
                            <option key={a} value={a}>
                              {Number(a)}%
                            </option>
                          ))}
                        </select>
                      </td>
                      <td data-label="Descripción">
                        <input
                          type="text"
                          value={fila.descripcion_factura}
                          onChange={(e) => cambiarFila(r.id, "descripcion_factura", e.target.value)}
                          disabled={guardandoId === r.id}
                        />
                      </td>
                      <td data-label="Predeterminado">
                        <input
                          type="radio"
                          name="rubro-predeterminado"
                          checked={fila.es_predeterminado}
                          onChange={() => cambiarFila(r.id, "es_predeterminado", true)}
                          disabled={guardandoId === r.id}
                        />
                      </td>
                      <td data-label="Activo">
                        <input
                          type="checkbox"
                          checked={fila.activo}
                          onChange={(e) => cambiarFila(r.id, "activo", e.target.checked)}
                          disabled={guardandoId === r.id}
                        />
                      </td>
                      <td data-label="">
                        <button
                          type="button"
                          className="rubros-boton-guardar"
                          onClick={() => guardarFila(r.id)}
                          disabled={guardandoId === r.id}
                        >
                          {guardandoId === r.id ? "Guardando…" : "Guardar"}
                        </button>
                        {errorFilaId === r.id && <MensajeError mensaje={fila._error} />}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <form className="rubros-agregar" onSubmit={alAgregar}>
            <label>
              Nombre
              <input
                type="text"
                value={nueva.nombre}
                onChange={(e) => setNueva((n) => ({ ...n, nombre: e.target.value }))}
                disabled={agregando}
                required
              />
            </label>
            <label>
              Alícuota
              <select
                value={nueva.alicuota}
                onChange={(e) => setNueva((n) => ({ ...n, alicuota: e.target.value }))}
                disabled={agregando}
              >
                {ALICUOTAS.map((a) => (
                  <option key={a} value={a}>
                    {Number(a)}%
                  </option>
                ))}
              </select>
            </label>
            <label>
              Descripción en factura
              <input
                type="text"
                value={nueva.descripcion_factura}
                onChange={(e) => setNueva((n) => ({ ...n, descripcion_factura: e.target.value }))}
                disabled={agregando}
                required
              />
            </label>
            <label>
              Orden
              <input
                type="number"
                min={0}
                className="rubros-campo-corto"
                value={nueva.orden}
                onChange={(e) => setNueva((n) => ({ ...n, orden: e.target.value }))}
                disabled={agregando}
                required
              />
            </label>
            <button type="submit" disabled={agregando}>
              {agregando ? "Agregando…" : "Agregar rubro"}
            </button>
          </form>
          <MensajeError mensaje={errorAgregar} />
        </>
      )}
    </section>
  );
}
