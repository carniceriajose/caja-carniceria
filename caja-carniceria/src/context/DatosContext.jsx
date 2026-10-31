import { createContext, useCallback, useContext, useState } from "react";
import { api } from "../api/cliente";

// Datos que comparten varias pantallas: qué medios se facturan y las tarjetas
// activas (las necesita la venta del vendedor) y las categorías de gasto
// (las usa la pantalla de gastos).
const DatosContext = createContext(null);

export function DatosProvider({ children }) {
  const [configuracion, setConfiguracion] = useState(null);
  const [categorias, setCategorias] = useState(null);
  const [tarjetas, setTarjetas] = useState(null);
  const [rubros, setRubros] = useState(null);

  const cargarConfiguracion = useCallback(async () => {
    const datos = await api.get("/configuracion");
    setConfiguracion(datos);
    return datos;
  }, []);

  const guardarConfiguracion = useCallback(async (nueva) => {
    const datos = await api.put("/configuracion", nueva);
    setConfiguracion(datos);
    return datos;
  }, []);

  const cargarCategorias = useCallback(async () => {
    const datos = await api.get("/categorias-gasto");
    setCategorias(datos);
    return datos;
  }, []);

  const crearCategoria = useCallback(async (nombre) => {
    const categoria = await api.post("/categorias-gasto", { nombre });
    setCategorias((actuales) => {
      const base = actuales ?? [];
      if (base.some((c) => c.id === categoria.id)) return base;
      return [...base, categoria].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
    });
    return categoria;
  }, []);

  const cargarTarjetas = useCallback(async () => {
    const datos = await api.get("/tarjetas");
    setTarjetas(datos);
    return datos;
  }, []);

  const crearTarjeta = useCallback(async (datos) => {
    const tarjeta = await api.post("/tarjetas", datos);
    setTarjetas((actuales) => [...(actuales ?? []), tarjeta].sort((a, b) => a.orden - b.orden));
    return tarjeta;
  }, []);

  const actualizarTarjeta = useCallback(async (id, datos) => {
    const tarjeta = await api.put(`/tarjetas/${id}`, datos);
    setTarjetas((actuales) =>
      (actuales ?? []).map((t) => (t.id === tarjeta.id ? tarjeta : t)).sort((a, b) => a.orden - b.orden)
    );
    return tarjeta;
  }, []);

  // Al crear o editar un rubro como predeterminado, el servidor le saca el
  // predeterminado al que lo tenía (es exclusivo: ver app/routers/rubros.py);
  // esto refleja lo mismo en el estado local, sin esperar a recargar todo.
  function _reemplazarRubro(actuales, rubro) {
    const base = (actuales ?? []).map((r) =>
      r.id === rubro.id ? rubro : rubro.es_predeterminado ? { ...r, es_predeterminado: false } : r
    );
    if (!base.some((r) => r.id === rubro.id)) base.push(rubro);
    return base.sort((a, b) => a.orden - b.orden);
  }

  const cargarRubros = useCallback(async () => {
    const datos = await api.get("/rubros");
    setRubros(datos);
    return datos;
  }, []);

  const crearRubro = useCallback(async (datos) => {
    const rubro = await api.post("/rubros", datos);
    setRubros((actuales) => _reemplazarRubro(actuales, rubro));
    return rubro;
  }, []);

  const actualizarRubro = useCallback(async (id, datos) => {
    const rubro = await api.put(`/rubros/${id}`, datos);
    setRubros((actuales) => _reemplazarRubro(actuales, rubro));
    return rubro;
  }, []);

  const valor = {
    configuracion,
    cargarConfiguracion,
    guardarConfiguracion,
    categorias,
    cargarCategorias,
    crearCategoria,
    tarjetas,
    cargarTarjetas,
    crearTarjeta,
    actualizarTarjeta,
    rubros,
    cargarRubros,
    crearRubro,
    actualizarRubro,
  };
  return <DatosContext.Provider value={valor}>{children}</DatosContext.Provider>;
}

export function useDatos() {
  const contexto = useContext(DatosContext);
  if (!contexto) throw new Error("useDatos se tiene que usar dentro de <DatosProvider>.");
  return contexto;
}
