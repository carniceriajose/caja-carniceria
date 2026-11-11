import { useCallback, useEffect, useState } from "react";
import { useDatos } from "../../context/DatosContext";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import TituloSeccion from "../../componentes/TituloSeccion";
import { IconoTarjeta } from "../../componentes/Iconos";
import SelectEstilizado from "../../componentes/SelectEstilizado";

function filaDesde(tarjeta) {
  return {
    nombre: tarjeta.nombre,
    tipo: tarjeta.tipo,
    recargo_porcentaje: tarjeta.recargo_porcentaje,
    activa: tarjeta.activa,
    orden: tarjeta.orden,
  };
}

export default function TarjetasConfiguracion() {
  const { tarjetas, cargarTarjetas, crearTarjeta, actualizarTarjeta } = useDatos();
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [filas, setFilas] = useState({});
  const [guardandoId, setGuardandoId] = useState(null);
  const [errorFilaId, setErrorFilaId] = useState(null);

  const [nueva, setNueva] = useState({ nombre: "", tipo: "credito", recargo_porcentaje: "0", orden: "1" });
  const [agregando, setAgregando] = useState(false);
  const [errorAgregar, setErrorAgregar] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      const datos = await cargarTarjetas();
      setFilas(Object.fromEntries(datos.map((t) => [t.id, filaDesde(t)])));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [cargarTarjetas]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function cambiarFila(id, campo, valor) {
    setFilas((actuales) => ({ ...actuales, [id]: { ...actuales[id], [campo]: valor } }));
  }

  async function guardarFila(id) {
    setErrorFilaId(null);
    setGuardandoId(id);
    try {
      const fila = filas[id];
      await actualizarTarjeta(id, {
        ...fila,
        recargo_porcentaje: String(fila.recargo_porcentaje),
        orden: Number(fila.orden),
      });
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
      const tarjeta = await crearTarjeta({
        nombre: nueva.nombre,
        tipo: nueva.tipo,
        recargo_porcentaje: String(nueva.recargo_porcentaje),
        activa: true,
        orden: Number(nueva.orden),
      });
      setFilas((actuales) => ({ ...actuales, [tarjeta.id]: filaDesde(tarjeta) }));
      setNueva({ nombre: "", tipo: "credito", recargo_porcentaje: "0", orden: "1" });
    } catch (err) {
      setErrorAgregar(err.message);
    } finally {
      setAgregando(false);
    }
  }

  return (
    <section className="configuracion-seccion">
      <TituloSeccion Icono={IconoTarjeta}>Tarjetas</TituloSeccion>
      <p className="configuracion-ayuda">
        Las que elige el vendedor al cobrar con tarjeta, cada una con su propio recargo. Una tarjeta
        desactivada no se puede volver a elegir, pero las ventas que ya la usaron no cambian.
      </p>

      {cargando && <Cargando texto="Cargando tarjetas…" />}
      {!cargando && error && <MensajeError mensaje={error} onReintentar={cargar} />}

      {!cargando && !error && tarjetas && (
        <>
          <div className="tarjetas-tabla tabla-apilable">
            <table>
              <thead>
                <tr>
                  <th>Orden</th>
                  <th>Nombre</th>
                  <th>Tipo</th>
                  <th>Recargo (%)</th>
                  <th>Activa</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tarjetas.map((t) => {
                  const fila = filas[t.id] ?? filaDesde(t);
                  return (
                    <tr key={t.id}>
                      <td data-label="Orden">
                        <input
                          type="number"
                          min={0}
                          className="tarjetas-campo-corto"
                          value={fila.orden}
                          onChange={(e) => cambiarFila(t.id, "orden", e.target.value)}
                          disabled={guardandoId === t.id}
                        />
                      </td>
                      <td data-label="Nombre">
                        <input
                          type="text"
                          value={fila.nombre}
                          onChange={(e) => cambiarFila(t.id, "nombre", e.target.value)}
                          disabled={guardandoId === t.id}
                        />
                      </td>
                      <td data-label="Tipo">
                        <SelectEstilizado
                          etiqueta="Tipo"
                          value={fila.tipo}
                          onChange={(valor) => cambiarFila(t.id, "tipo", valor)}
                          disabled={guardandoId === t.id}
                          opciones={[
                            { valor: "credito", etiqueta: "Crédito" },
                            { valor: "debito", etiqueta: "Débito" },
                          ]}
                        />
                      </td>
                      <td data-label="Recargo (%)">
                        <input
                          type="number"
                          min={0}
                          max={100}
                          step="0.01"
                          className="tarjetas-campo-corto"
                          value={fila.recargo_porcentaje}
                          onChange={(e) => cambiarFila(t.id, "recargo_porcentaje", e.target.value)}
                          disabled={guardandoId === t.id}
                        />
                      </td>
                      <td data-label="Activa">
                        <input
                          type="checkbox"
                          checked={fila.activa}
                          onChange={(e) => cambiarFila(t.id, "activa", e.target.checked)}
                          disabled={guardandoId === t.id}
                        />
                      </td>
                      <td data-label="">
                        <button
                          type="button"
                          className="tarjetas-boton-guardar"
                          onClick={() => guardarFila(t.id)}
                          disabled={guardandoId === t.id}
                        >
                          {guardandoId === t.id ? "Guardando…" : "Guardar"}
                        </button>
                        {errorFilaId === t.id && <MensajeError mensaje={fila._error} />}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <form className="tarjetas-agregar" onSubmit={alAgregar}>
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
              Tipo
              <SelectEstilizado
                etiqueta="Tipo"
                value={nueva.tipo}
                onChange={(valor) => setNueva((n) => ({ ...n, tipo: valor }))}
                disabled={agregando}
                opciones={[
                  { valor: "credito", etiqueta: "Crédito" },
                  { valor: "debito", etiqueta: "Débito" },
                ]}
              />
            </label>
            <label>
              Recargo (%)
              <input
                type="number"
                min={0}
                max={100}
                step="0.01"
                className="tarjetas-campo-corto"
                value={nueva.recargo_porcentaje}
                onChange={(e) => setNueva((n) => ({ ...n, recargo_porcentaje: e.target.value }))}
                disabled={agregando}
                required
              />
            </label>
            <label>
              Orden
              <input
                type="number"
                min={0}
                className="tarjetas-campo-corto"
                value={nueva.orden}
                onChange={(e) => setNueva((n) => ({ ...n, orden: e.target.value }))}
                disabled={agregando}
                required
              />
            </label>
            <button type="submit" disabled={agregando}>
              {agregando ? "Agregando…" : "Agregar tarjeta"}
            </button>
          </form>
          <MensajeError mensaje={errorAgregar} />
        </>
      )}
    </section>
  );
}
