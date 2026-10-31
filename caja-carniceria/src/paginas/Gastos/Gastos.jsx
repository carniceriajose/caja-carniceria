import { useCallback, useEffect, useState } from "react";
import { api, descargarArchivo } from "../../api/cliente";
import { useDatos } from "../../context/DatosContext";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import TituloSeccion from "../../componentes/TituloSeccion";
import { IconoCategorias, IconoDinero, IconoReloj } from "../../componentes/Iconos";
import { formatearDinero, totalValido } from "../../utilidades/dinero";
import { hoyArgentina } from "../../utilidades/fechas";
import "./Gastos.css";

const POR_PAGINA = 20;

const FORMULARIO_VACIO = { fecha: hoyArgentina(), monto: "", categoria_id: "", descripcion: "" };

export default function Gastos() {
  const { categorias, cargarCategorias, crearCategoria } = useDatos();

  const [errorCategorias, setErrorCategorias] = useState("");
  const [nombreCategoria, setNombreCategoria] = useState("");
  const [creandoCategoria, setCreandoCategoria] = useState(false);

  const [filtroDesde, setFiltroDesde] = useState("");
  const [filtroHasta, setFiltroHasta] = useState("");
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [pagina, setPagina] = useState(1);

  const [gastos, setGastos] = useState(null);
  const [cargandoGastos, setCargandoGastos] = useState(true);
  const [errorGastos, setErrorGastos] = useState("");

  const [formulario, setFormulario] = useState(FORMULARIO_VACIO);
  const [editandoId, setEditandoId] = useState(null);
  const [errorFormulario, setErrorFormulario] = useState("");
  const [guardando, setGuardando] = useState(false);

  const [descargando, setDescargando] = useState(null); // "excel" | "pdf" | null
  const [errorDescarga, setErrorDescarga] = useState("");

  const cargarListaCategorias = useCallback(async () => {
    setErrorCategorias("");
    try {
      await cargarCategorias();
    } catch (err) {
      setErrorCategorias(err.message);
    }
  }, [cargarCategorias]);

  useEffect(() => {
    if (categorias === null) cargarListaCategorias();
  }, [categorias, cargarListaCategorias]);

  const cargarGastos = useCallback(async () => {
    setCargandoGastos(true);
    setErrorGastos("");
    const parametros = new URLSearchParams({ pagina: String(pagina), por_pagina: String(POR_PAGINA) });
    if (filtroDesde) parametros.set("desde", filtroDesde);
    if (filtroHasta) parametros.set("hasta", filtroHasta);
    if (filtroCategoria) parametros.set("categoria_id", filtroCategoria);
    try {
      setGastos(await api.get(`/gastos?${parametros}`));
    } catch (err) {
      setErrorGastos(err.message);
    } finally {
      setCargandoGastos(false);
    }
  }, [pagina, filtroDesde, filtroHasta, filtroCategoria]);

  useEffect(() => {
    cargarGastos();
  }, [cargarGastos]);

  const rangoInvertido = filtroDesde && filtroHasta && filtroDesde > filtroHasta;

  async function descargar(tipo) {
    setDescargando(tipo);
    setErrorDescarga("");
    try {
      const extension = tipo === "excel" ? "xlsx" : "pdf";
      await descargarArchivo(
        `/reportes/gastos.${extension}?desde=${filtroDesde}&hasta=${filtroHasta}`,
        `gastos_${filtroDesde}_${filtroHasta}.${extension}`
      );
    } catch (err) {
      setErrorDescarga(err.message);
    } finally {
      setDescargando(null);
    }
  }

  async function alCrearCategoria(evento) {
    evento.preventDefault();
    const nombre = nombreCategoria.trim();
    if (!nombre) return;
    setCreandoCategoria(true);
    setErrorCategorias("");
    try {
      await crearCategoria(nombre);
      setNombreCategoria("");
    } catch (err) {
      setErrorCategorias(err.message);
    } finally {
      setCreandoCategoria(false);
    }
  }

  function empezarEdicion(gasto) {
    setEditandoId(gasto.id);
    setFormulario({
      fecha: gasto.fecha,
      monto: gasto.monto,
      categoria_id: String(gasto.categoria.id),
      descripcion: gasto.descripcion ?? "",
    });
    setErrorFormulario("");
  }

  function cancelarEdicion() {
    setEditandoId(null);
    setFormulario(FORMULARIO_VACIO);
    setErrorFormulario("");
  }

  async function alGuardarGasto(evento) {
    evento.preventDefault();
    if (!formulario.categoria_id) {
      setErrorFormulario("Elegí una categoría.");
      return;
    }
    if (!totalValido(formulario.monto)) {
      setErrorFormulario("Ingresá un monto mayor a 0, con hasta 2 decimales.");
      return;
    }
    setErrorFormulario("");
    setGuardando(true);
    const cuerpo = {
      fecha: formulario.fecha,
      monto: formulario.monto,
      categoria_id: Number(formulario.categoria_id),
      descripcion: formulario.descripcion.trim() || null,
    };
    try {
      if (editandoId) {
        await api.put(`/gastos/${editandoId}`, cuerpo);
      } else {
        await api.post("/gastos", cuerpo);
      }
      cancelarEdicion();
      await cargarGastos();
    } catch (err) {
      setErrorFormulario(err.message);
    } finally {
      setGuardando(false);
    }
  }

  async function alBorrar(gasto) {
    if (!window.confirm(`¿Borrar el gasto de ${formatearDinero(gasto.monto)}?`)) return;
    try {
      await api.eliminar(`/gastos/${gasto.id}`);
      if (editandoId === gasto.id) cancelarEdicion();
      await cargarGastos();
    } catch (err) {
      setErrorGastos(err.message);
    }
  }

  const totalPaginas = gastos ? Math.max(1, Math.ceil(gastos.total / POR_PAGINA)) : 1;

  return (
    <div className="gastos">
      <h1>Gastos</h1>

      <section className="gastos-seccion">
        <TituloSeccion Icono={IconoCategorias}>Categorías</TituloSeccion>
        <MensajeError mensaje={errorCategorias} onReintentar={cargarListaCategorias} />
        {categorias === null && !errorCategorias && <Cargando texto="Cargando categorías…" />}
        {categorias !== null && (
          <>
            <ul className="gastos-categorias-lista">
              {categorias.length === 0 && <li className="gastos-categorias-vacio">Todavía no hay categorías.</li>}
              {categorias.map((categoria) => (
                <li key={categoria.id}>{categoria.nombre}</li>
              ))}
            </ul>
            <form className="gastos-nueva-categoria" onSubmit={alCrearCategoria}>
              <input
                type="text"
                placeholder="Nueva categoría (proveedor, seguro, etc.)"
                value={nombreCategoria}
                onChange={(e) => setNombreCategoria(e.target.value)}
                disabled={creandoCategoria}
              />
              <button type="submit" disabled={creandoCategoria || !nombreCategoria.trim()}>
                Agregar
              </button>
            </form>
          </>
        )}
      </section>

      <section className="gastos-seccion">
        <TituloSeccion Icono={IconoDinero}>{editandoId ? "Editar gasto" : "Cargar gasto"}</TituloSeccion>
        <form className="gastos-formulario" onSubmit={alGuardarGasto}>
          <MensajeError mensaje={errorFormulario} />
          <div className="gastos-formulario-fila">
            <label>
              Fecha
              <input
                type="date"
                max={hoyArgentina()}
                value={formulario.fecha}
                onChange={(e) => setFormulario({ ...formulario, fecha: e.target.value })}
                disabled={guardando}
                required
              />
            </label>
            <label>
              Monto
              <input
                type="text"
                inputMode="decimal"
                placeholder="0.00"
                value={formulario.monto}
                onChange={(e) => setFormulario({ ...formulario, monto: e.target.value.trim() })}
                disabled={guardando}
                required
              />
            </label>
            <label>
              Categoría
              <select
                value={formulario.categoria_id}
                onChange={(e) => setFormulario({ ...formulario, categoria_id: e.target.value })}
                disabled={guardando || !categorias?.length}
                required
              >
                <option value="">Elegir…</option>
                {categorias?.map((categoria) => (
                  <option key={categoria.id} value={categoria.id}>
                    {categoria.nombre}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Descripción (opcional)
            <input
              type="text"
              value={formulario.descripcion}
              onChange={(e) => setFormulario({ ...formulario, descripcion: e.target.value })}
              disabled={guardando}
              maxLength={500}
            />
          </label>
          <div className="gastos-formulario-botones">
            <button type="submit" disabled={guardando}>
              {guardando ? "Guardando…" : editandoId ? "Guardar cambios" : "Agregar gasto"}
            </button>
            {editandoId && (
              <button type="button" className="gastos-boton-secundario" onClick={cancelarEdicion} disabled={guardando}>
                Cancelar
              </button>
            )}
          </div>
        </form>
      </section>

      <section className="gastos-seccion">
        <TituloSeccion Icono={IconoReloj}>Historial</TituloSeccion>
        <div className="gastos-filtros">
          <label>
            Desde
            <input type="date" value={filtroDesde} max={hoyArgentina()} onChange={(e) => { setPagina(1); setFiltroDesde(e.target.value); }} />
          </label>
          <label>
            Hasta
            <input type="date" value={filtroHasta} max={hoyArgentina()} onChange={(e) => { setPagina(1); setFiltroHasta(e.target.value); }} />
          </label>
          <label>
            Categoría
            <select value={filtroCategoria} onChange={(e) => { setPagina(1); setFiltroCategoria(e.target.value); }}>
              <option value="">Todas</option>
              {categorias?.map((categoria) => (
                <option key={categoria.id} value={categoria.id}>
                  {categoria.nombre}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="gastos-boton-descargar"
            onClick={() => descargar("excel")}
            disabled={descargando !== null || !filtroDesde || !filtroHasta || rangoInvertido}
            title={!filtroDesde || !filtroHasta ? "Elegí 'Desde' y 'Hasta' para descargar" : undefined}
          >
            {descargando === "excel" ? "Generando…" : "Descargar Excel"}
          </button>
          <button
            type="button"
            className="gastos-boton-descargar"
            onClick={() => descargar("pdf")}
            disabled={descargando !== null || !filtroDesde || !filtroHasta || rangoInvertido}
            title={!filtroDesde || !filtroHasta ? "Elegí 'Desde' y 'Hasta' para descargar" : undefined}
          >
            {descargando === "pdf" ? "Generando…" : "Descargar PDF"}
          </button>
        </div>
        {errorDescarga && <MensajeError mensaje={errorDescarga} />}

        {rangoInvertido && <MensajeError mensaje="La fecha 'desde' no puede ser posterior a 'hasta'." />}
        {!rangoInvertido && cargandoGastos && <Cargando texto="Cargando gastos…" />}
        {!rangoInvertido && !cargandoGastos && errorGastos && (
          <MensajeError mensaje={errorGastos} onReintentar={cargarGastos} />
        )}

        {!rangoInvertido && !cargandoGastos && !errorGastos && gastos && (
          <>
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Categoría</th>
                  <th>Descripción</th>
                  <th className="gastos-numerico">Monto</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {gastos.items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="gastos-vacio">
                      No hay gastos en este período.
                    </td>
                  </tr>
                )}
                {gastos.items.map((gasto) => (
                  <tr key={gasto.id}>
                    <td>{gasto.fecha}</td>
                    <td>{gasto.categoria.nombre}</td>
                    <td>{gasto.descripcion || "—"}</td>
                    <td className="gastos-numerico">{formatearDinero(gasto.monto)}</td>
                    <td className="gastos-acciones">
                      <button type="button" onClick={() => empezarEdicion(gasto)}>
                        Editar
                      </button>
                      <button type="button" className="gastos-boton-borrar" onClick={() => alBorrar(gasto)}>
                        Borrar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {totalPaginas > 1 && (
              <div className="gastos-paginado">
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
      </section>
    </div>
  );
}
