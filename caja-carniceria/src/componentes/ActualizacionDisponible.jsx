import { useRegisterSW } from "virtual:pwa-register/react";
import { IconoActualizar } from "./Iconos";
import { hayVentaEnCurso } from "../utilidades/estadoVenta";
import "./ActualizacionDisponible.css";

const TREINTA_MINUTOS_MS = 30 * 60 * 1000;

export default function ActualizacionDisponible() {
  const {
    needRefresh: [needRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_swUrl, registro) {
      if (!registro) return;
      const revisar = () => registro.update().catch(() => {});
      setInterval(revisar, TREINTA_MINUTOS_MS);
      window.addEventListener("focus", revisar);
    },
  });

  function actualizar() {
    if (
      hayVentaEnCurso() &&
      !window.confirm("Hay una venta sin terminar de cargar. Si actualizás ahora la vas a perder. ¿Actualizar igual?")
    ) {
      return;
    }
    updateServiceWorker(true);
  }

  if (!needRefresh) return null;

  return (
    <div className="actualizacion-disponible">
      <div className="actualizacion-disponible-texto">
        <IconoActualizar tamanio={28} />
        <span>Hay una versión nueva del sistema.</span>
      </div>
      <button type="button" onClick={actualizar}>
        Actualizar ahora
      </button>
    </div>
  );
}
