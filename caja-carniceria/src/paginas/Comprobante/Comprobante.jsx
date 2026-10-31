import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../api/cliente";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import TicketComprobante from "../../componentes/TicketComprobante";
import "./Comprobante.css";

export default function Comprobante() {
  const { id } = useParams();
  const [parametros] = useSearchParams();
  const esNotaCredito = parametros.get("tipo") === "nota-credito";
  const navegar = useNavigate();
  const [comprobante, setComprobante] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      const ruta = esNotaCredito ? `/ventas/${id}/nota-credito/comprobante` : `/ventas/${id}/comprobante`;
      setComprobante(await api.get(ruta));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }, [id, esNotaCredito]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <div className="comprobante-pantalla">
      <div className="comprobante-acciones">
        <button type="button" className="comprobante-boton-secundario" onClick={() => navegar(-1)}>
          Volver
        </button>
        <button type="button" onClick={() => window.print()} disabled={!comprobante}>
          Imprimir
        </button>
      </div>

      {cargando && <Cargando texto="Cargando comprobante…" />}
      {!cargando && error && <MensajeError mensaje={error} onReintentar={cargar} />}
      {!cargando && !error && comprobante && (
        <>
          <p className="comprobante-ayuda">
            Se imprime en formato ticket de 80 mm: elegí la impresora térmica en el cuadro de impresión.
          </p>
          <div className="comprobante-hoja">
            <TicketComprobante comprobante={comprobante} />
          </div>
        </>
      )}
    </div>
  );
}
