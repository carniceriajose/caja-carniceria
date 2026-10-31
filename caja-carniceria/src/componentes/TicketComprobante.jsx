import { useEffect, useState } from "react";
import QRCode from "qrcode";
import logoTicket from "../assets/logo-ticket.png";
import { formatearDinero } from "../utilidades/dinero";
import { formatearCuit, formatearFecha } from "../utilidades/fechas";
import { formatearNumeroComprobante } from "../utilidades/comprobante";
import "./TicketComprobante.css";

// Ticket para impresora térmica de 80 mm. Con soloImpresion no se ve en
// pantalla: existe para que "Imprimir" saque el ticket sin abrir otra página.
export default function TicketComprobante({ comprobante, soloImpresion = false }) {
  const [qr, setQr] = useState("");

  useEffect(() => {
    let cancelado = false;
    QRCode.toDataURL(comprobante.qr_url, { margin: 0, width: 300, errorCorrectionLevel: "M" })
      .then((url) => {
        if (!cancelado) setQr(url);
      })
      .catch(() => {
        if (!cancelado) setQr("");
      });
    return () => {
      cancelado = true;
    };
  }, [comprobante.qr_url]);

  const { emisor } = comprobante;

  return (
    <div className={`ticket ${soloImpresion ? "ticket-solo-impresion" : ""}`}>
      <img src={logoTicket} alt="Hipercarnicería El Abasto de José" className="ticket-logo" />

      <div className="ticket-centrado">
        {emisor.razon_social && <p className="ticket-razon-social">{emisor.razon_social}</p>}
        <p>CUIT: {formatearCuit(emisor.cuit)}</p>
        {emisor.domicilio && <p>{emisor.domicilio}</p>}
        {emisor.condicion_iva && <p>{emisor.condicion_iva}</p>}
        {emisor.inicio_actividades && <p>Inicio de actividades: {emisor.inicio_actividades}</p>}
        {emisor.ingresos_brutos && <p>Ing. Brutos: {emisor.ingresos_brutos}</p>}
      </div>

      <hr className="ticket-separador" />

      <div className="ticket-tipo">
        <span className="ticket-letra">{comprobante.letra}</span>
        <span className="ticket-codigo">Cód. {comprobante.codigo}</span>
      </div>
      <p className="ticket-nombre">{comprobante.nombre}</p>
      <p className="ticket-fila">
        <span>Nº</span>
        <span>{formatearNumeroComprobante(comprobante.punto_venta, comprobante.numero)}</span>
      </p>
      <p className="ticket-fila">
        <span>Fecha</span>
        <span>{formatearFecha(comprobante.fecha)}</span>
      </p>

      <hr className="ticket-separador" />

      <p>A {comprobante.receptor.toUpperCase()}</p>
      <p>{comprobante.descripcion_item}</p>

      <hr className="ticket-separador" />

      <p className="ticket-fila">
        <span>Subtotal</span>
        <span>{formatearDinero(comprobante.subtotal)}</span>
      </p>
      {comprobante.ajuste_detalle && <p className="ticket-ajuste">{comprobante.ajuste_detalle}</p>}
      <p className="ticket-fila ticket-total">
        <span>TOTAL</span>
        <span>{formatearDinero(comprobante.total)}</span>
      </p>

      {comprobante.iva_contenido !== null && (
        <div className="ticket-transparencia">
          <p>Régimen de Transparencia Fiscal al Consumidor (Ley 27.743)</p>
          <p className="ticket-fila">
            <span>IVA contenido</span>
            <span>{formatearDinero(comprobante.iva_contenido)}</span>
          </p>
        </div>
      )}

      <hr className="ticket-separador" />

      <p className="ticket-fila">
        <span>CAE</span>
        <span>{comprobante.cae}</span>
      </p>
      <p className="ticket-fila">
        <span>Vto. CAE</span>
        <span>{formatearFecha(comprobante.cae_vencimiento)}</span>
      </p>

      <div className="ticket-qr">
        {qr && <img src={qr} alt="Código QR de ARCA" width="150" height="150" />}
      </div>
      <p className="ticket-centrado ticket-pie">Comprobante autorizado por ARCA</p>
    </div>
  );
}
