import "./Iconos.css";

// Íconos de trazo (24x24). Toman el color del texto (currentColor), así el
// color se maneja desde el CSS de quien los usa.
function Icono({ children, tamanio = 20, clase = "" }) {
  return (
    <svg
      className={`icono ${clase}`}
      viewBox="0 0 24 24"
      width={tamanio}
      height={tamanio}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const IconoInicio = (props) => (
  <Icono {...props}>
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <polyline points="9 22 9 12 15 12 15 22" />
  </Icono>
);

export const IconoCarrito = (props) => (
  <Icono {...props}>
    <circle cx="9" cy="21" r="1" />
    <circle cx="20" cy="21" r="1" />
    <path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6" />
  </Icono>
);

export const IconoDinero = (props) => (
  <Icono {...props}>
    <circle cx="12" cy="12" r="10" />
    <path d="M15 9.5c0-1.4-1.3-2.5-3-2.5s-3 1.1-3 2.5 1.3 2.5 3 2.5 3 1.1 3 2.5-1.3 2.5-3 2.5-3-1.1-3-2.5" />
    <path d="M12 5v2M12 17v2" />
  </Icono>
);

export const IconoDocumento = (props) => (
  <Icono {...props}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
  </Icono>
);

export const IconoUsuarios = (props) => (
  <Icono {...props}>
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </Icono>
);

export const IconoBilletes = (props) => (
  <Icono {...props}>
    <rect x="2" y="6" width="20" height="12" rx="2" />
    <circle cx="12" cy="12" r="2.5" />
    <path d="M6 12h.01M18 12h.01" />
  </Icono>
);

export const IconoTarjeta = (props) => (
  <Icono {...props}>
    <rect x="1" y="4" width="22" height="16" rx="2" />
    <line x1="1" y1="10" x2="23" y2="10" />
  </Icono>
);

export const IconoTransferencia = (props) => (
  <Icono {...props}>
    <path d="M17 3l4 4-4 4" />
    <path d="M21 7H9" />
    <path d="M7 21l-4-4 4-4" />
    <path d="M3 17h12" />
  </Icono>
);

export const IconoEtiqueta = (props) => (
  <Icono {...props}>
    <path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z" />
    <circle cx="7" cy="7" r="1.5" />
  </Icono>
);

export const IconoCategorias = (props) => (
  <Icono {...props}>
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
  </Icono>
);

export const IconoComercio = (props) => (
  <Icono {...props}>
    <path d="M3 9l1-5h16l1 5" />
    <path d="M3 9a2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0" />
    <path d="M5 9v10h14V9" />
    <path d="M9 19v-6h6v6" />
  </Icono>
);

export const IconoBalanza = (props) => (
  <Icono {...props}>
    <path d="M12 3v18M6 21h12M5 7h14" />
    <path d="M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z" />
  </Icono>
);

export const IconoCheck = (props) => (
  <Icono {...props}>
    <polyline points="20 6 9 17 4 12" />
  </Icono>
);

export const IconoBorrar = (props) => (
  <Icono {...props}>
    <path d="M21 4H8l-7 8 7 8h13a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z" />
    <line x1="18" y1="9" x2="12" y2="15" />
    <line x1="12" y1="9" x2="18" y2="15" />
  </Icono>
);

export const IconoImpresora = (props) => (
  <Icono {...props}>
    <polyline points="6 9 6 2 18 2 18 9" />
    <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
    <rect x="6" y="14" width="12" height="8" />
  </Icono>
);

export const IconoReloj = (props) => (
  <Icono {...props}>
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </Icono>
);

export const IconoEscudo = (props) => (
  <Icono {...props}>
    <path d="M12 2l8 4v6c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6z" />
    <polyline points="9 12 11 14 15 10" />
  </Icono>
);

export const IconoMenu = (props) => (
  <Icono {...props}>
    <line x1="3" y1="6" x2="21" y2="6" />
    <line x1="3" y1="12" x2="21" y2="12" />
    <line x1="3" y1="18" x2="21" y2="18" />
  </Icono>
);

export const IconoCerrarX = (props) => (
  <Icono {...props}>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </Icono>
);

export const IconoAnular = (props) => (
  <Icono {...props}>
    <circle cx="12" cy="12" r="9" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </Icono>
);

export const IconoCierreCaja = (props) => (
  <Icono {...props}>
    <rect x="3" y="7" width="18" height="13" rx="2" />
    <path d="M8 7V5a4 4 0 0 1 8 0v2" />
    <path d="M9 13l2 2 4-4" />
  </Icono>
);

export const IconoSalir = (props) => (
  <Icono {...props}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </Icono>
);

export const IconoEngranaje = (props) => (
  <Icono {...props}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </Icono>
);

export const IconoPapelera = (props) => (
  <Icono {...props}>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </Icono>
);

export const IconoCompras = (props) => (
  <Icono {...props}>
    <path d="M6 2 3 7v13a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7l-3-5Z" />
    <path d="M3 7h18" />
    <path d="M16 11a4 4 0 0 1-8 0" />
  </Icono>
);

export const IconoComentario = (props) => (
  <Icono {...props}>
    <path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </Icono>
);

export const IconoImagen = (props) => (
  <Icono {...props}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <circle cx="8.5" cy="8.5" r="1.5" />
    <path d="m21 15-5-5L5 21" />
  </Icono>
);
