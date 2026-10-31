import "./TituloSeccion.css";

// Encabezado de sección reutilizable (ícono en chip + título), el mismo
// lenguaje visual que ya usan los paneles del Dashboard y la pantalla de Caja.
export default function TituloSeccion({ Icono, children, className = "" }) {
  return (
    <div className={`titulo-seccion ${className}`}>
      <span className="titulo-seccion-icono">
        <Icono tamanio={18} />
      </span>
      <h2>{children}</h2>
    </div>
  );
}
