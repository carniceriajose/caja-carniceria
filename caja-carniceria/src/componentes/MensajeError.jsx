import "./MensajeError.css";

export default function MensajeError({ mensaje, onReintentar }) {
  if (!mensaje) return null;
  return (
    <div className="mensaje-error" role="alert">
      <span>{mensaje}</span>
      {onReintentar && (
        <button type="button" className="mensaje-error-boton" onClick={onReintentar}>
          Reintentar
        </button>
      )}
    </div>
  );
}
