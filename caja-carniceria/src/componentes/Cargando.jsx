import "./Cargando.css";

export default function Cargando({ texto = "Cargando…" }) {
  return (
    <div className="cargando" role="status">
      <div className="cargando-spinner" aria-hidden="true" />
      <p>{texto}</p>
    </div>
  );
}
