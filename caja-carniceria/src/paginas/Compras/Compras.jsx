import { useCallback, useEffect, useRef, useState } from "react";
import { api, obtenerImagenComoUrl } from "../../api/cliente";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import TituloSeccion from "../../componentes/TituloSeccion";
import { IconoCerrarX, IconoComentario, IconoCompras, IconoImagen, IconoPapelera } from "../../componentes/Iconos";
import { formatearFecha, formatearFechaHora, hoyArgentina } from "../../utilidades/fechas";
import "./Compras.css";

const POR_PAGINA = 15;
const LADO_MAXIMO_PX = 1280;
const CALIDAD_JPEG = 0.72;

const FORMULARIO_VACIO = { fecha: hoyArgentina(), nombre_comercio: "", descripcion: "" };

// Achica la foto en el navegador (más liviana para subir y para guardar) y la
// deja siempre en JPEG, sin importar el formato original.
function comprimirImagen(archivo) {
  return new Promise((resolver, rechazar) => {
    const lector = new FileReader();
    lector.onerror = () => rechazar(new Error("No se pudo leer la imagen."));
    lector.onload = () => {
      const imagen = new Image();
      imagen.onerror = () => rechazar(new Error("El archivo elegido no es una imagen válida."));
      imagen.onload = () => {
        const escala = Math.min(1, LADO_MAXIMO_PX / Math.max(imagen.width, imagen.height));
        const ancho = Math.round(imagen.width * escala);
        const alto = Math.round(imagen.height * escala);
        const lienzo = document.createElement("canvas");
        lienzo.width = ancho;
        lienzo.height = alto;
        lienzo.getContext("2d").drawImage(imagen, 0, 0, ancho, alto);
        const dataUrl = lienzo.toDataURL("image/jpeg", CALIDAD_JPEG);
        resolver(dataUrl.slice(dataUrl.indexOf(",") + 1));
      };
      imagen.src = lector.result;
    };
    lector.readAsDataURL(archivo);
  });
}

function ComentariosComercio({ nombreComercio }) {
  const [comentarios, setComentarios] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [texto, setTexto] = useState("");
  const [guardando, setGuardando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      setComentarios(await api.get(`/comentarios-comercio?nombre_comercio=${encodeURIComponent(nombreComercio)}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [nombreComercio]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function agregar(evento) {
    evento.preventDefault();
    if (!texto.trim()) return;
    setGuardando(true);
    setError("");
    try {
      await api.post("/comentarios-comercio", { nombre_comercio: nombreComercio, comentario: texto.trim() });
      setTexto("");
      await cargar();
    } catch (err) {
      setError(err.message);
    } finally {
      setGuardando(false);
    }
  }

  async function borrar(id) {
    if (!window.confirm("¿Borrar este comentario?")) return;
    try {
      await api.eliminar(`/comentarios-comercio/${id}`);
      await cargar();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="compras-comentarios">
      <TituloSeccion Icono={IconoCompras}>Comentarios de "{nombreComercio}"</TituloSeccion>
      <form className="compras-comentarios-form" onSubmit={agregar}>
        <input
          type="text"
          placeholder="Agregar una nota sobre este comercio…"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          disabled={guardando}
          maxLength={1000}
        />
        <button type="submit" disabled={guardando || !texto.trim()}>
          {guardando ? "Guardando…" : "Agregar"}
        </button>
      </form>
      <MensajeError mensaje={error} />
      {cargando && <Cargando texto="Cargando comentarios…" />}
      {!cargando && comentarios && comentarios.length === 0 && (
        <p className="compras-vacio">Todavía no hay comentarios sobre este comercio.</p>
      )}
      {!cargando && comentarios && comentarios.length > 0 && (
        <ul className="compras-comentarios-lista">
          {comentarios.map((c) => (
            <li key={c.id}>
              <p>{c.comentario}</p>
              <div className="compras-comentarios-pie">
                <span>{formatearFechaHora(c.creado_en)}</span>
                <button type="button" onClick={() => borrar(c.id)}>
                  Borrar
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MiniaturaCompra({ compraId, alt, onAmpliar }) {
  const [url, setUrl] = useState(null);

  useEffect(() => {
    let cancelado = false;
    let urlCreada = null;
    obtenerImagenComoUrl(`/compras/${compraId}/imagen`)
      .then((valor) => {
        if (cancelado) return;
        urlCreada = valor;
        setUrl(valor);
      })
      .catch(() => {});
    return () => {
      cancelado = true;
      if (urlCreada) URL.revokeObjectURL(urlCreada);
    };
  }, [compraId]);

  if (!url) {
    return (
      <span className="compras-miniatura compras-miniatura-vacia" aria-hidden="true">
        <IconoImagen tamanio={28} />
      </span>
    );
  }
  return (
    <button
      type="button"
      className="compras-miniatura-boton"
      title="Ver comprobante completo"
      onClick={() => onAmpliar(url, alt)}
    >
      <img src={url} alt={alt} className="compras-miniatura" />
    </button>
  );
}

function ImagenAmpliada({ url, alt, onCerrar }) {
  return (
    <div className="compras-lightbox-fondo" onClick={onCerrar}>
      <div className="compras-lightbox-caja" onClick={(e) => e.stopPropagation()}>
        <div className="compras-lightbox-barra">
          <a href={url} download={`${alt}.jpg`} className="compras-lightbox-descargar">
            Descargar
          </a>
          <button type="button" onClick={onCerrar} aria-label="Cerrar">
            <IconoCerrarX tamanio={20} />
          </button>
        </div>
        <img src={url} alt={alt} />
      </div>
    </div>
  );
}

export default function Compras() {
  const [filtroDesde, setFiltroDesde] = useState("");
  const [filtroHasta, setFiltroHasta] = useState("");
  const [filtroComercio, setFiltroComercio] = useState("");
  const [pagina, setPagina] = useState(1);

  const [compras, setCompras] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [comercios, setComercios] = useState([]);

  const [formulario, setFormulario] = useState(FORMULARIO_VACIO);
  const [archivoNombre, setArchivoNombre] = useState("");
  const [imagenBase64, setImagenBase64] = useState("");
  const [vistaPrevia, setVistaPrevia] = useState("");
  const [errorFormulario, setErrorFormulario] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [procesandoImagen, setProcesandoImagen] = useState(false);
  const comentariosRef = useRef(null);
  const [imagenAmpliada, setImagenAmpliada] = useState(null);

  const cargarCompras = useCallback(async () => {
    setCargando(true);
    setError("");
    const parametros = new URLSearchParams({ pagina: String(pagina), por_pagina: String(POR_PAGINA) });
    if (filtroDesde) parametros.set("desde", filtroDesde);
    if (filtroHasta) parametros.set("hasta", filtroHasta);
    if (filtroComercio.trim()) parametros.set("comercio", filtroComercio.trim());
    try {
      setCompras(await api.get(`/compras?${parametros}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [pagina, filtroDesde, filtroHasta, filtroComercio]);

  useEffect(() => {
    cargarCompras();
  }, [cargarCompras]);

  useEffect(() => {
    api
      .get("/compras/comercios")
      .then(setComercios)
      .catch(() => {});
  }, []);

  const rangoInvertido = filtroDesde && filtroHasta && filtroDesde > filtroHasta;

  function cambiarFiltro(setter) {
    return (evento) => {
      setPagina(1);
      setter(evento.target.value);
    };
  }

  async function alElegirArchivo(evento) {
    const archivo = evento.target.files?.[0];
    if (!archivo) return;
    setErrorFormulario("");
    setArchivoNombre(archivo.name);
    setProcesandoImagen(true);
    try {
      const base64 = await comprimirImagen(archivo);
      setImagenBase64(base64);
      setVistaPrevia(`data:image/jpeg;base64,${base64}`);
    } catch (err) {
      setErrorFormulario(err.message);
      setArchivoNombre("");
    } finally {
      setProcesandoImagen(false);
    }
  }

  function limpiarFormulario() {
    setFormulario(FORMULARIO_VACIO);
    setArchivoNombre("");
    setImagenBase64("");
    setVistaPrevia("");
    setErrorFormulario("");
  }

  async function alGuardar(evento) {
    evento.preventDefault();
    if (!formulario.nombre_comercio.trim()) {
      setErrorFormulario("Ingresá el nombre del comercio.");
      return;
    }
    if (!imagenBase64) {
      setErrorFormulario("Elegí una foto del comprobante.");
      return;
    }
    setErrorFormulario("");
    setGuardando(true);
    try {
      await api.post("/compras", {
        fecha: formulario.fecha,
        nombre_comercio: formulario.nombre_comercio,
        descripcion: formulario.descripcion || null,
        imagen: imagenBase64,
        imagen_tipo: "image/jpeg",
      });
      limpiarFormulario();
      await cargarCompras();
      api
        .get("/compras/comercios")
        .then(setComercios)
        .catch(() => {});
    } catch (err) {
      setErrorFormulario(err.message);
    } finally {
      setGuardando(false);
    }
  }

  async function alBorrar(compra) {
    if (!window.confirm(`¿Borrar la compra en "${compra.nombre_comercio}"?`)) return;
    try {
      await api.eliminar(`/compras/${compra.id}`);
      await cargarCompras();
    } catch (err) {
      setError(err.message);
    }
  }

  function irAComentarios(nombreComercio) {
    setPagina(1);
    setFiltroComercio(nombreComercio);
    requestAnimationFrame(() => {
      comentariosRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  const totalPaginas = compras ? Math.max(1, Math.ceil(compras.total / POR_PAGINA)) : 1;

  return (
    <div className="compras">
      <h1>Compras</h1>

      <section className="compras-seccion">
        <TituloSeccion Icono={IconoCompras}>Nueva compra</TituloSeccion>
        <p className="compras-ayuda">Seguimiento de lo que le comprás a cada comercio, con foto del comprobante.</p>
        <form className="compras-formulario" onSubmit={alGuardar}>
          <MensajeError mensaje={errorFormulario} />
          <div className="compras-formulario-fila">
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
              Comercio
              <input
                type="text"
                list="compras-comercios-sugeridos"
                placeholder="Nombre del comercio o proveedor"
                value={formulario.nombre_comercio}
                onChange={(e) => setFormulario({ ...formulario, nombre_comercio: e.target.value })}
                disabled={guardando}
                maxLength={120}
                required
              />
            </label>
          </div>
          <datalist id="compras-comercios-sugeridos">
            {comercios.map((nombre) => (
              <option key={nombre} value={nombre} />
            ))}
          </datalist>
          <label>
            Descripción (opcional)
            <textarea
              className="compras-descripcion"
              rows={4}
              value={formulario.descripcion}
              onChange={(e) => setFormulario({ ...formulario, descripcion: e.target.value })}
              disabled={guardando}
              maxLength={500}
            />
          </label>

          <label className="compras-campo-imagen">
            Foto del comprobante
            <input
              type="file"
              accept="image/*"
              onChange={alElegirArchivo}
              disabled={guardando || procesandoImagen}
            />
          </label>
          {procesandoImagen && <Cargando texto="Preparando la imagen…" />}
          {vistaPrevia && (
            <div className="compras-vista-previa">
              <img src={vistaPrevia} alt={`Vista previa: ${archivoNombre}`} />
            </div>
          )}

          <div className="compras-formulario-botones">
            <button type="submit" disabled={guardando || procesandoImagen}>
              {guardando ? "Guardando…" : "Agregar compra"}
            </button>
          </div>
        </form>
      </section>

      <section className="compras-seccion">
        <TituloSeccion Icono={IconoCompras}>Historial</TituloSeccion>
        <div className="compras-filtros">
          <label>
            Comercio
            <input
              type="text"
              list="compras-comercios-sugeridos"
              placeholder="Buscar por comercio…"
              value={filtroComercio}
              onChange={cambiarFiltro(setFiltroComercio)}
            />
          </label>
          <label>
            Desde
            <input type="date" value={filtroDesde} max={hoyArgentina()} onChange={cambiarFiltro(setFiltroDesde)} />
          </label>
          <label>
            Hasta
            <input type="date" value={filtroHasta} max={hoyArgentina()} onChange={cambiarFiltro(setFiltroHasta)} />
          </label>
        </div>

        {filtroComercio.trim() && (
          <div ref={comentariosRef}>
            <ComentariosComercio nombreComercio={filtroComercio.trim()} />
          </div>
        )}

        {rangoInvertido && <MensajeError mensaje="La fecha 'desde' no puede ser posterior a 'hasta'." />}
        {!rangoInvertido && cargando && <Cargando texto="Cargando compras…" />}
        {!rangoInvertido && !cargando && error && <MensajeError mensaje={error} onReintentar={cargarCompras} />}

        {!rangoInvertido && !cargando && !error && compras && (
          <>
            {compras.items.length === 0 && <p className="compras-vacio">No hay compras cargadas en este período.</p>}
            <div className="compras-historial-lista">
              {compras.items.map((compra) => (
                <article key={compra.id} className="compras-fila">
                  <MiniaturaCompra
                    compraId={compra.id}
                    alt={`Comprobante de ${compra.nombre_comercio}`}
                    onAmpliar={(url, alt) => setImagenAmpliada({ url, alt })}
                  />
                  <div className="compras-fila-datos">
                    <span className="compras-fila-comercio">{compra.nombre_comercio}</span>
                    <span className="compras-fila-meta">
                      {formatearFecha(compra.fecha)}
                      {compra.descripcion ? ` · ${compra.descripcion}` : ""}
                    </span>
                  </div>
                  <div className="compras-fila-acciones">
                    <button
                      type="button"
                      title="Agregar comentario a este comercio"
                      onClick={() => irAComentarios(compra.nombre_comercio)}
                    >
                      <IconoComentario tamanio={18} />
                    </button>
                    <button
                      type="button"
                      className="compras-boton-borrar"
                      title="Borrar"
                      onClick={() => alBorrar(compra)}
                    >
                      <IconoPapelera tamanio={18} />
                    </button>
                  </div>
                </article>
              ))}
            </div>

            {totalPaginas > 1 && (
              <div className="compras-paginado">
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

      {imagenAmpliada && (
        <ImagenAmpliada
          url={imagenAmpliada.url}
          alt={imagenAmpliada.alt}
          onCerrar={() => setImagenAmpliada(null)}
        />
      )}
    </div>
  );
}
