import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./SelectEstilizado.css";

// Reemplaza un <select> nativo: el menú desplegado de uno nativo lo dibuja
// el sistema operativo y no se puede estilar. Mismo comportamiento básico
// (teclado con flechas/Enter/Escape, cierra al hacer clic afuera).
//
// El menú se dibuja con un portal directo a <body>, no adentro del
// contenedor: así no lo recorta ningún "overflow" de una sección con scroll
// (como las tablas apilables o los paneles con scroll horizontal).
export default function SelectEstilizado({ value, onChange, opciones, etiqueta, id, disabled = false, title }) {
  const [abierto, setAbierto] = useState(false);
  const [posicion, setPosicion] = useState(null);
  const contenedorRef = useRef(null);
  const botonRef = useRef(null);
  const listaRef = useRef(null);

  function recalcularPosicion() {
    const rect = botonRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosicion({
      top: rect.bottom + window.scrollY + 4,
      left: rect.left + window.scrollX,
      width: rect.width,
    });
  }

  useEffect(() => {
    if (!abierto) return undefined;
    recalcularPosicion();

    function alHacerClicAfuera(evento) {
      const adentroDelBoton = contenedorRef.current?.contains(evento.target);
      const adentroDeLaLista = listaRef.current?.contains(evento.target);
      if (!adentroDelBoton && !adentroDeLaLista) {
        setAbierto(false);
      }
    }
    document.addEventListener("mousedown", alHacerClicAfuera);
    // capture:true también agarra el scroll de un contenedor interno (los
    // eventos "scroll" no burbujean, pero sí se capturan desde arriba).
    window.addEventListener("scroll", recalcularPosicion, true);
    window.addEventListener("resize", recalcularPosicion);
    return () => {
      document.removeEventListener("mousedown", alHacerClicAfuera);
      window.removeEventListener("scroll", recalcularPosicion, true);
      window.removeEventListener("resize", recalcularPosicion);
    };
  }, [abierto]);

  // Comparación floja (String): algunas pantallas pasan números (ids, códigos
  // de comprobante) y otras strings; así funciona igual en los dos casos.
  const elegida = opciones.find((o) => String(o.valor) === String(value)) ?? opciones[0];

  function elegir(valor) {
    onChange(valor);
    setAbierto(false);
  }

  function alTecla(evento) {
    if (evento.key === "Escape") {
      setAbierto(false);
      return;
    }
    if (evento.key === "Enter" || evento.key === " ") {
      evento.preventDefault();
      setAbierto((actual) => !actual);
      return;
    }
    if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
      evento.preventDefault();
      const indiceActual = opciones.findIndex((o) => String(o.valor) === String(value));
      const paso = evento.key === "ArrowDown" ? 1 : -1;
      const siguiente = opciones[(indiceActual + paso + opciones.length) % opciones.length];
      elegir(siguiente.valor);
    }
  }

  return (
    <div className="select-estilizado" ref={contenedorRef}>
      <button
        ref={botonRef}
        type="button"
        id={id}
        className="select-estilizado-boton"
        aria-haspopup="listbox"
        aria-expanded={abierto}
        aria-label={etiqueta}
        disabled={disabled}
        title={title}
        onClick={() => setAbierto((actual) => !actual)}
        onKeyDown={alTecla}
      >
        <span>{elegida?.etiqueta}</span>
        <svg viewBox="0 0 24 24" width="16" height="16" className="select-estilizado-flecha" aria-hidden="true">
          <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {abierto &&
        posicion &&
        createPortal(
          <ul
            className="select-estilizado-lista"
            role="listbox"
            ref={listaRef}
            style={{ top: posicion.top, left: posicion.left, minWidth: posicion.width }}
          >
            {opciones.map((opcion) => (
              <li key={opcion.valor} role="option" aria-selected={String(opcion.valor) === String(value)}>
                <button
                  type="button"
                  className={`select-estilizado-opcion ${String(opcion.valor) === String(value) ? "select-estilizado-opcion-elegida" : ""}`}
                  onClick={() => elegir(opcion.valor)}
                >
                  {opcion.etiqueta}
                </button>
              </li>
            ))}
          </ul>,
          document.body
        )}
    </div>
  );
}
