import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/cliente";
import { useAuth } from "../../context/AuthContext";
import { useDatos } from "../../context/DatosContext";
import Cargando from "../../componentes/Cargando";
import MensajeError from "../../componentes/MensajeError";
import TicketComprobante from "../../componentes/TicketComprobante";
import {
  IconoBilletes,
  IconoBorrar,
  IconoCategorias,
  IconoCheck,
  IconoCierreCaja,
  IconoEngranaje,
  IconoImpresora,
  IconoPapelera,
  IconoReloj,
  IconoSalir,
  IconoTarjeta,
  IconoTransferencia,
} from "../../componentes/Iconos";
import { formatearDinero, normalizarMonto, teclearMonto, totalValido } from "../../utilidades/dinero";
import { formatearNumeroComprobante } from "../../utilidades/comprobante";
import { formatearHora } from "../../utilidades/fechas";
import { ETIQUETA_MEDIO } from "../../utilidades/graficos";
import "./Venta.css";

const MEDIOS_DE_PAGO = [
  { valor: "efectivo", Icono: IconoBilletes },
  { valor: "tarjeta", Icono: IconoTarjeta },
  { valor: "transferencia", Icono: IconoTransferencia },
];

const ICONO_MEDIO = Object.fromEntries(MEDIOS_DE_PAGO.map((m) => [m.valor, m.Icono]));

const TECLAS = ["7", "8", "9", "4", "5", "6", "1", "2", "3", ".", "0", "borrar"];

function EtiquetaSeccion({ Icono, children, as: Etiqueta = "span", ...resto }) {
  return (
    <Etiqueta className="caja-etiqueta" {...resto}>
      <span className="caja-etiqueta-icono">
        <Icono tamanio={16} />
      </span>
      {children}
    </Etiqueta>
  );
}

const ETIQUETA_ESTADO = {
  no_aplica: "Sin factura",
  pendiente: "Emitiendo",
  facturada: "Facturada",
  fallo: "Con error",
};

// Sondea el estado fiscal cada 2 segundos, hasta 30 segundos en total.
const INTERVALO_SONDEO_MS = 2000;
const INTENTOS_MAXIMOS = 15;
const VENTAS_RECIENTES = 5;
// Tiene que coincidir con ANULACION_MINUTOS_VENDEDOR del backend: acá solo
// decide cuándo mostrar el botón, el backend es quien de verdad lo hace cumplir.
const MINUTOS_ANULACION = 10;

// La plata del desglose se calcula en centavos (nunca en float) para que la
// vista previa no arrastre error de redondeo antes de mandarla al servidor,
// que es quien de verdad decide los montos finales.
function aCentavos(texto) {
  if (!texto) return 0;
  const limpio = String(texto).replace(",", ".").trim();
  if (!/^\d{0,10}(\.\d{1,2})?$/.test(limpio)) return null;
  return Math.round(parseFloat(limpio) * 100);
}

function deCentavos(centavos) {
  return (centavos / 100).toFixed(2);
}

export default function Venta() {
  const { usuario, cerrarSesion } = useAuth();
  const { configuracion, cargarConfiguracion, tarjetas, cargarTarjetas, rubros, cargarRubros } = useDatos();
  const refSubtotal = useRef(null);

  // Si una venta se factura o no lo ve solo el admin: el vendedor no se
  // entera del estado interno (ni la API se lo manda, ver app/routers/ventas.py).
  const veFiscal = usuario?.rol === "admin";

  const [cargandoConfig, setCargandoConfig] = useState(true);
  const [errorConfig, setErrorConfig] = useState("");

  const [idCliente, setIdCliente] = useState(() => crypto.randomUUID());
  const [subtotal, setSubtotal] = useState("");
  const [medioPago, setMedioPago] = useState("efectivo");
  const [tarjetaId, setTarjetaId] = useState(null);
  const [rubroId, setRubroId] = useState(null);
  const [errorSubtotal, setErrorSubtotal] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [errorEnvio, setErrorEnvio] = useState("");
  const [ventaConfirmada, setVentaConfirmada] = useState(null);
  const [estadoFiscal, setEstadoFiscal] = useState(null);
  const [comprobante, setComprobante] = useState(null);
  const [errorComprobante, setErrorComprobante] = useState("");
  const [comprobanteAgotado, setComprobanteAgotado] = useState(false);
  const [recientes, setRecientes] = useState([]);

  const [mostrarAnular, setMostrarAnular] = useState(false);
  const [motivoAnular, setMotivoAnular] = useState("");
  const [anulando, setAnulando] = useState(false);
  const [errorAnular, setErrorAnular] = useState("");
  const [ventaAnulada, setVentaAnulada] = useState(false);
  const [ahora, setAhora] = useState(() => Date.now());

  const cargarConfig = useCallback(async () => {
    setCargandoConfig(true);
    setErrorConfig("");
    try {
      await Promise.all([cargarConfiguracion(), cargarTarjetas(), cargarRubros()]);
    } catch (err) {
      setErrorConfig(err.message);
    } finally {
      setCargandoConfig(false);
    }
  }, [cargarConfiguracion, cargarTarjetas, cargarRubros]);

  useEffect(() => {
    cargarConfig();
  }, [cargarConfig]);

  // Al elegir "Tarjeta" se preselecciona la primera activa (suele ser la
  // única, o la más usada); igual se puede cambiar antes de cobrar.
  useEffect(() => {
    if (medioPago !== "tarjeta") {
      setTarjetaId(null);
      return;
    }
    if (tarjetaId === null && tarjetas && tarjetas.length > 0) {
      setTarjetaId(tarjetas[0].id);
    }
  }, [medioPago, tarjetas, tarjetaId]);

  // El rubro siempre viene con el predeterminado ya elegido, así la venta
  // habitual no suma pasos; igual se puede cambiar antes de cobrar.
  useEffect(() => {
    if (rubroId !== null || !rubros || rubros.length === 0) return;
    const predeterminado = rubros.find((r) => r.es_predeterminado) ?? rubros[0];
    setRubroId(predeterminado.id);
  }, [rubros, rubroId]);

  // Solo admin: mientras la venta quede "pendiente" de facturar, se consulta
  // el estado interno cada 2 segundos, hasta 30 segundos en total.
  useEffect(() => {
    if (!veFiscal || !ventaConfirmada || ventaConfirmada.estado_arca !== "pendiente") return undefined;

    let cancelado = false;
    let temporizador;

    async function consultar(intento) {
      let datos;
      try {
        datos = await api.get(`/ventas/${ventaConfirmada.id}/fiscal`);
      } catch {
        datos = null; // se sigue intentando hasta agotar el tiempo
      }
      if (cancelado) return;

      if (datos && datos.estado_arca !== "pendiente") {
        setEstadoFiscal(datos);
        return;
      }
      if (intento >= INTENTOS_MAXIMOS) {
        setEstadoFiscal({ ...(datos ?? ventaConfirmada), agotado: true });
        return;
      }
      temporizador = setTimeout(() => consultar(intento + 1), INTERVALO_SONDEO_MS);
    }

    consultar(1);
    return () => {
      cancelado = true;
      clearTimeout(temporizador);
    };
  }, [veFiscal, ventaConfirmada]);

  // Las ventas de esta sesión: se actualiza el estado de la última cuando ARCA responde.
  useEffect(() => {
    if (!ventaConfirmada || !estadoFiscal) return;
    setRecientes((lista) =>
      lista.map((v) => (v.id === ventaConfirmada.id ? { ...v, estado_arca: estadoFiscal.estado_arca } : v))
    );
  }, [estadoFiscal, ventaConfirmada]);

  // Solo admin: cuando la venta queda facturada se trae el comprobante, para
  // poder imprimirlo (usa el estado interno que ya consultó arriba).
  const idFacturada =
    veFiscal && ventaConfirmada && (estadoFiscal ?? ventaConfirmada).estado_arca === "facturada"
      ? ventaConfirmada.id
      : null;

  useEffect(() => {
    if (!veFiscal) return undefined;
    setComprobante(null);
    setErrorComprobante("");
    if (!idFacturada) return undefined;

    let cancelado = false;
    api
      .get(`/ventas/${idFacturada}/comprobante`)
      .then((datos) => {
        if (!cancelado) setComprobante(datos);
      })
      .catch((err) => {
        if (!cancelado) setErrorComprobante(err.message);
      });
    return () => {
      cancelado = true;
    };
  }, [veFiscal, idFacturada]);

  // Vendedor: no recibe el estado interno, así que en vez de esperar a que
  // cambie, intenta pedir directamente el comprobante (imprimible) cada 2
  // segundos; un 409 significa "todavía no", y se reintenta sin mostrarlo
  // como error hasta agotar el tiempo.
  const medioSeFactura = Boolean(
    ventaConfirmada && configuracion?.[`facturar_${ventaConfirmada.medio_pago}`]
  );

  useEffect(() => {
    if (veFiscal) return undefined;
    setComprobante(null);
    setErrorComprobante("");
    setComprobanteAgotado(false);
    if (!ventaConfirmada || !medioSeFactura) return undefined;

    let cancelado = false;
    let temporizador;

    async function intentar(intento) {
      try {
        const datos = await api.get(`/ventas/${ventaConfirmada.id}/comprobante`);
        if (!cancelado) setComprobante(datos);
        return;
      } catch (err) {
        if (cancelado) return;
        if (intento >= INTENTOS_MAXIMOS) {
          if (err.status === 409) {
            setComprobanteAgotado(true);
          } else {
            setErrorComprobante(err.message);
          }
          return;
        }
        temporizador = setTimeout(() => intentar(intento + 1), INTERVALO_SONDEO_MS);
      }
    }

    intentar(1);
    return () => {
      cancelado = true;
      clearTimeout(temporizador);
    };
  }, [veFiscal, ventaConfirmada, medioSeFactura]);

  // Mientras haya una venta recién cobrada y sin anular, se reevalúa cada 15
  // segundos si sigue dentro de la ventana para poder anularla.
  useEffect(() => {
    if (!ventaConfirmada || ventaAnulada) return undefined;
    const id = setInterval(() => setAhora(Date.now()), 15000);
    return () => clearInterval(id);
  }, [ventaConfirmada, ventaAnulada]);

  const dentroDeLaVentanaDeAnulacion =
    ventaConfirmada != null &&
    ahora - new Date(ventaConfirmada.fecha_hora).getTime() < MINUTOS_ANULACION * 60 * 1000;
  // Si el admin ve que todavía se está facturando, ni le mostramos el botón:
  // el pedido fallaría seguro. El vendedor no tiene ese dato, así que para él
  // se deja intentar y, si corresponde, el mensaje claro lo pone la API.
  const puedeMostrarBotonAnular =
    dentroDeLaVentanaDeAnulacion && !(veFiscal && ventaConfirmada?.estado_arca === "pendiente");

  const tarjetaElegida = tarjetaId != null ? tarjetas?.find((t) => t.id === tarjetaId) : null;

  // Vista previa del recargo automático: en efectivo el precio queda igual;
  // en tarjeta depende de cuál se haya elegido, en transferencia es un único
  // %. Es solo para mostrarlo antes de cobrar: el monto que vale es el que
  // devuelve la API.
  function calcularDesglose() {
    const subtotalCent = aCentavos(subtotal);
    if (subtotalCent === null || subtotalCent <= 0) return null;

    const porcentajeMedio =
      medioPago === "tarjeta"
        ? Number(tarjetaElegida?.recargo_porcentaje ?? 0)
        : medioPago === "transferencia"
          ? Number(configuracion?.recargo_transferencia_porcentaje ?? 0)
          : 0;
    const montoMedioCent = porcentajeMedio > 0 ? Math.round((subtotalCent * porcentajeMedio) / 100) : 0;
    const totalCent = subtotalCent + montoMedioCent;

    return { subtotalCent, montoMedioCent, porcentajeMedio, totalCent };
  }

  const desglose = totalValido(subtotal) ? calcularDesglose() : null;

  function empezarVentaNueva() {
    setIdCliente(crypto.randomUUID());
    setSubtotal("");
    setMedioPago("efectivo");
    setTarjetaId(null);
    setRubroId(null);
    setErrorSubtotal("");
    setErrorEnvio("");
    setVentaConfirmada(null);
    setEstadoFiscal(null);
    setComprobanteAgotado(false);
    setMostrarAnular(false);
    setMotivoAnular("");
    setErrorAnular("");
    setVentaAnulada(false);
    setAhora(Date.now());
  }

  async function confirmarAnulacion(evento) {
    evento.preventDefault();
    setErrorAnular("");
    setAnulando(true);
    try {
      await api.post(`/ventas/${ventaConfirmada.id}/anular`, { motivo: motivoAnular });
      setVentaAnulada(true);
      setMostrarAnular(false);
      setRecientes((lista) =>
        lista.map((v) => (v.id === ventaConfirmada.id ? { ...v, anulada: true } : v))
      );
    } catch (err) {
      setErrorAnular(err.message);
    } finally {
      setAnulando(false);
    }
  }

  useEffect(() => {
    if (!ventaConfirmada && !cargandoConfig) refSubtotal.current?.focus();
  }, [ventaConfirmada, cargandoConfig]);

  async function enviarVenta(idClienteAEnviar) {
    setEnviando(true);
    setErrorEnvio("");
    try {
      const cuerpo = {
        subtotal,
        medio_pago: medioPago,
        rubro_id: rubroId,
        id_cliente: idClienteAEnviar,
      };
      if (medioPago === "tarjeta") cuerpo.tarjeta_id = tarjetaId;
      const venta = await api.post("/ventas", cuerpo);
      setVentaConfirmada(venta);
      setRecientes((lista) =>
        [venta, ...lista.filter((v) => v.id !== venta.id)].slice(0, VENTAS_RECIENTES)
      );
    } catch (err) {
      setErrorEnvio(err.message);
    } finally {
      setEnviando(false);
    }
  }

  function alEnviar(evento) {
    evento.preventDefault();
    if (!totalValido(subtotal)) {
      setErrorSubtotal("Ingresá un monto mayor a 0, con hasta 2 decimales.");
      return;
    }
    if (medioPago === "tarjeta" && !tarjetaId) return;
    if (!rubroId) return;
    setErrorSubtotal("");
    // Se reintenta siempre con el mismo id_cliente: si la venta ya se había
    // registrado (por un corte de red, por ejemplo), el servidor la devuelve
    // en vez de cobrarla dos veces.
    enviarVenta(idCliente);
  }

  function alTeclear(tecla) {
    setErrorSubtotal("");
    setSubtotal((actual) => teclearMonto(actual, tecla));
    refSubtotal.current?.focus();
  }

  function alEscribir(evento) {
    const valor = normalizarMonto(evento.target.value);
    if (valor !== null) {
      setErrorSubtotal("");
      setSubtotal(valor);
    }
  }

  const montoListo = totalValido(subtotal);

  return (
    <div className="caja">
      <header className="caja-encabezado">
        <div className="caja-marca">
          <img src="/logo-192.png" alt="" className="caja-marca-logo" />
          <span className="caja-marca-nombre">Hipercarnicería</span>
          <span className="caja-marca-seccion">
            <span className="caja-marca-punto" aria-hidden="true" />
            Caja
          </span>
        </div>
        <div className="caja-encabezado-acciones">
          {usuario?.rol === "admin" && (
            <>
              <Link to="/admin/cierre-caja" className="caja-enlace-panel">
                <IconoCierreCaja tamanio={18} />
                Cerrar caja
              </Link>
              <Link to="/admin" className="caja-enlace-panel">
                <IconoEngranaje tamanio={18} />
                Panel de administración
              </Link>
            </>
          )}
          <span className="caja-usuario">
            <span className="caja-avatar" aria-hidden="true">
              {usuario?.nombre?.[0]?.toUpperCase()}
            </span>
            {usuario?.nombre}
          </span>
          <button type="button" className="caja-boton-salir" onClick={cerrarSesion}>
            <IconoSalir tamanio={18} />
            Cerrar sesión
          </button>
        </div>
      </header>

      <main className="caja-contenido">
        {cargandoConfig && <Cargando texto="Cargando configuración…" />}
        {!cargandoConfig && errorConfig && (
          <MensajeError mensaje={errorConfig} onReintentar={cargarConfig} />
        )}

        {!cargandoConfig && !errorConfig && !ventaConfirmada && (
          <form className="caja-cobro" onSubmit={alEnviar}>
            <section className="caja-panel caja-pantalla">
              <EtiquetaSeccion as="label" htmlFor="caja-subtotal" Icono={IconoBilletes}>
                Total del ticket
              </EtiquetaSeccion>
              <div className="caja-monto">
                <span className="caja-monto-signo" aria-hidden="true">
                  $
                </span>
                <input
                  id="caja-subtotal"
                  ref={refSubtotal}
                  type="text"
                  inputMode="none"
                  autoComplete="off"
                  placeholder="0,00"
                  value={subtotal}
                  onChange={alEscribir}
                  disabled={enviando}
                  aria-describedby="caja-monto-ayuda"
                  className="caja-monto-entrada"
                />
              </div>
              <p id="caja-monto-ayuda" className="caja-monto-vista">
                {errorSubtotal ? (
                  <span className="caja-error-campo">{errorSubtotal}</span>
                ) : montoListo ? (
                  formatearDinero(subtotal)
                ) : (
                  "Escribí el total o usá el teclado."
                )}
              </p>

              <div className="caja-teclado">
                {TECLAS.map((tecla) => (
                  <button
                    key={tecla}
                    type="button"
                    className={`caja-tecla ${tecla === "borrar" ? "caja-tecla-borrar" : ""}`}
                    onClick={() => alTeclear(tecla)}
                    disabled={enviando}
                    aria-label={tecla === "borrar" ? "Borrar" : tecla === "." ? "Coma decimal" : tecla}
                  >
                    {tecla === "borrar" ? <IconoBorrar tamanio={24} /> : tecla === "." ? "," : tecla}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="caja-limpiar"
                onClick={() => alTeclear("limpiar")}
                disabled={enviando || subtotal === ""}
              >
                <IconoPapelera tamanio={16} />
                Limpiar
              </button>

              {desglose && desglose.montoMedioCent > 0 && (
                <div className="caja-desglose">
                  <div className="caja-desglose-fila">
                    <span>Subtotal</span>
                    <span>{formatearDinero(deCentavos(desglose.subtotalCent))}</span>
                  </div>
                  <div className="caja-desglose-fila">
                    <span>
                      Recargo {medioPago === "tarjeta" ? tarjetaElegida?.nombre : ETIQUETA_MEDIO[medioPago]} (
                      {desglose.porcentajeMedio}%)
                    </span>
                    <span>+{formatearDinero(deCentavos(desglose.montoMedioCent))}</span>
                  </div>
                  <div className="caja-desglose-fila caja-desglose-total">
                    <span>Total</span>
                    <span>{formatearDinero(deCentavos(desglose.totalCent))}</span>
                  </div>
                </div>
              )}
            </section>

            <div className="caja-columna">
              <section className="caja-panel">
                <EtiquetaSeccion id="caja-rubro-titulo" Icono={IconoCategorias}>
                  Rubro
                </EtiquetaSeccion>
                {rubros && rubros.length === 0 && (
                  <p className="caja-error-campo">
                    No hay rubros activos:{" "}
                    {veFiscal ? "creá uno en Configuración." : "avisale a un administrador."}
                  </p>
                )}
                <div className="caja-rubros-opciones" role="radiogroup" aria-labelledby="caja-rubro-titulo">
                  {(rubros ?? []).map((r) => (
                    <button
                      key={r.id}
                      type="button"
                      role="radio"
                      aria-checked={rubroId === r.id}
                      className={`caja-rubro-opcion ${rubroId === r.id ? "caja-rubro-opcion-elegida" : ""}`}
                      onClick={() => setRubroId(r.id)}
                      disabled={enviando}
                    >
                      {r.nombre}
                    </button>
                  ))}
                </div>
              </section>

              <section className="caja-panel">
                <EtiquetaSeccion id="caja-medio-titulo" Icono={IconoTarjeta}>
                  Medio de pago
                </EtiquetaSeccion>
                <div className="caja-medios" role="radiogroup" aria-labelledby="caja-medio-titulo">
                  {MEDIOS_DE_PAGO.map(({ valor, Icono }) => {
                    const seFactura = configuracion?.[`facturar_${valor}`];
                    const elegido = medioPago === valor;
                    return (
                      <button
                        key={valor}
                        type="button"
                        role="radio"
                        aria-checked={elegido}
                        className={`caja-medio caja-medio-${valor} ${elegido ? "caja-medio-elegido" : ""}`}
                        onClick={() => setMedioPago(valor)}
                        disabled={enviando}
                      >
                        {elegido && (
                          <span className="caja-medio-check" aria-hidden="true">
                            <IconoCheck tamanio={12} />
                          </span>
                        )}
                        <span className="caja-medio-icono">
                          <Icono tamanio={26} />
                        </span>
                        <span className="caja-medio-nombre">{ETIQUETA_MEDIO[valor]}</span>
                        {veFiscal && (
                          <span
                            className={`caja-medio-factura ${seFactura ? "caja-medio-factura-si" : ""}`}
                          >
                            {seFactura ? "Se factura" : "Sin factura"}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>

                {medioPago === "tarjeta" && (
                  <div className="caja-tarjetas">
                    <EtiquetaSeccion id="caja-tarjeta-titulo" Icono={IconoTarjeta}>
                      Tarjeta
                    </EtiquetaSeccion>
                    {tarjetas && tarjetas.length === 0 && (
                      <p className="caja-error-campo">
                        No hay tarjetas activas:{" "}
                        {veFiscal ? "creá una en Configuración." : "avisale a un administrador."}
                      </p>
                    )}
                    <div className="caja-tarjetas-opciones" role="radiogroup" aria-labelledby="caja-tarjeta-titulo">
                      {(tarjetas ?? []).map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          role="radio"
                          aria-checked={tarjetaId === t.id}
                          className={`caja-tarjeta-opcion ${tarjetaId === t.id ? "caja-tarjeta-opcion-elegida" : ""}`}
                          onClick={() => setTarjetaId(t.id)}
                          disabled={enviando}
                        >
                          {t.nombre}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <MensajeError mensaje={errorEnvio} onReintentar={() => enviarVenta(idCliente)} />

                <button
                  type="submit"
                  className="caja-cobrar"
                  disabled={enviando || !montoListo || !rubroId || (medioPago === "tarjeta" && !tarjetaId)}
                >
                  {enviando ? (
                    "Cobrando…"
                  ) : (
                    <>
                      <IconoTarjeta tamanio={22} />
                      <span className="caja-cobrar-texto">
                        <span className="caja-cobrar-titulo">
                          {desglose ? `Cobrar ${formatearDinero(deCentavos(desglose.totalCent))}` : "Cobrar"}
                        </span>
                        <span className="caja-cobrar-subtitulo">Confirmar operación</span>
                      </span>
                    </>
                  )}
                </button>
              </section>

              <VentasRecientes ventas={recientes} veFiscal={veFiscal} />
            </div>
          </form>
        )}

        {ventaConfirmada && (
          <div className="caja-resultado">
            <section className="caja-panel caja-confirmacion">
              <span className="caja-confirmacion-check">
                <IconoCheck tamanio={34} />
              </span>
              <p className="caja-confirmacion-titulo">Venta cobrada</p>
              <p className="caja-confirmacion-monto">{formatearDinero(ventaConfirmada.total)}</p>
              {ventaConfirmada.ajuste_detalle && (
                <p className="caja-confirmacion-ajuste">
                  Subtotal {formatearDinero(ventaConfirmada.subtotal)} · {ventaConfirmada.ajuste_detalle}
                </p>
              )}
              <p className="caja-confirmacion-medio">
                {ETIQUETA_MEDIO[ventaConfirmada.medio_pago]}
                {ventaConfirmada.rubro_nombre ? ` · ${ventaConfirmada.rubro_nombre}` : ""}
              </p>

              {veFiscal && (
                <EstadoFiscalVenta estado={estadoFiscal ?? { estado_arca: ventaConfirmada.estado_arca }} />
              )}
              {!veFiscal && !comprobante && (
                <EstadoComprobanteVendedor
                  seFactura={medioSeFactura}
                  agotado={comprobanteAgotado}
                  error={errorComprobante}
                />
              )}

              {comprobante && (
                <>
                  <button type="button" className="caja-imprimir" onClick={() => window.print()}>
                    <IconoImpresora tamanio={20} />
                    Imprimir ticket
                  </button>
                  <TicketComprobante comprobante={comprobante} soloImpresion />
                </>
              )}
              {veFiscal && errorComprobante && (
                <p className="caja-fiscal caja-fiscal-error">
                  No se pudo preparar el comprobante: {errorComprobante}
                </p>
              )}

              {ventaAnulada && <p className="caja-fiscal caja-fiscal-ok">Venta anulada.</p>}

              {!ventaAnulada && puedeMostrarBotonAnular && !mostrarAnular && (
                <button type="button" className="caja-boton-anular" onClick={() => setMostrarAnular(true)}>
                  Anular última venta
                </button>
              )}

              {!ventaAnulada && mostrarAnular && (
                <form className="caja-form-anular" onSubmit={confirmarAnulacion}>
                  <MensajeError mensaje={errorAnular} />
                  <p className="alerta alerta-aviso">
                    {veFiscal && ventaConfirmada.estado_arca === "facturada"
                      ? "Se va a emitir una nota de crédito en ARCA. Esta operación no se puede deshacer."
                      : "Si la venta ya se facturó, esto va a generar una nota de crédito en ARCA. No se puede deshacer."}
                  </p>
                  <label htmlFor="caja-motivo-anular">Motivo</label>
                  <input
                    id="caja-motivo-anular"
                    type="text"
                    value={motivoAnular}
                    onChange={(e) => setMotivoAnular(e.target.value)}
                    disabled={anulando}
                    autoFocus
                    required
                  />
                  <div className="caja-form-anular-botones">
                    <button type="submit" disabled={anulando || motivoAnular.trim().length === 0}>
                      {anulando ? "Anulando…" : "Confirmar anulación"}
                    </button>
                    <button
                      type="button"
                      className="caja-boton-secundario"
                      onClick={() => {
                        setMostrarAnular(false);
                        setMotivoAnular("");
                        setErrorAnular("");
                      }}
                      disabled={anulando}
                    >
                      Cancelar
                    </button>
                  </div>
                </form>
              )}

              <button type="button" className="caja-cobrar" onClick={empezarVentaNueva} autoFocus>
                Cobrar otra venta
              </button>
            </section>

            <VentasRecientes ventas={recientes} veFiscal={veFiscal} />
          </div>
        )}
      </main>
    </div>
  );
}

function VentasRecientes({ ventas, veFiscal }) {
  if (ventas.length === 0) return null;
  return (
    <section className="caja-panel caja-recientes">
      <EtiquetaSeccion Icono={IconoReloj}>Últimas ventas</EtiquetaSeccion>
      <ul>
        {ventas.map((venta) => {
          const Icono = ICONO_MEDIO[venta.medio_pago];
          return (
            <li key={venta.id}>
              <span className={`caja-reciente-icono caja-medio-${venta.medio_pago}`}>
                <Icono tamanio={18} />
              </span>
              <span className="caja-reciente-datos">
                <span className="caja-reciente-monto">{formatearDinero(venta.total)}</span>
                <span className="caja-reciente-detalle">
                  {ETIQUETA_MEDIO[venta.medio_pago]} · {formatearHora(venta.fecha_hora)}
                </span>
              </span>
              {venta.anulada ? (
                <span className="caja-insignia caja-insignia-anulada">Anulada</span>
              ) : (
                veFiscal && (
                  <span className={`caja-insignia caja-insignia-${venta.estado_arca}`}>
                    {ETIQUETA_ESTADO[venta.estado_arca]}
                  </span>
                )
              )}
              {!venta.anulada && venta.estado_arca === "facturada" && (
                <Link to={`/comprobante/${venta.id}`} className="caja-reciente-enlace">
                  Reimprimir
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function EstadoFiscalVenta({ estado }) {
  if (estado.estado_arca === "no_aplica") {
    return <p className="caja-fiscal caja-fiscal-nota">Este medio no se factura.</p>;
  }

  if (estado.estado_arca === "facturada") {
    return (
      <div className="caja-fiscal caja-fiscal-ok">
        <p>
          Comprobante {estado.tipo_comprobante}-
          {formatearNumeroComprobante(estado.punto_venta, estado.numero_comprobante)}
        </p>
        <p>CAE {estado.cae}</p>
      </div>
    );
  }

  if (estado.estado_arca === "fallo") {
    return (
      <p className="caja-fiscal caja-fiscal-error">No se pudo facturar: {estado.error_detalle}</p>
    );
  }

  // "pendiente"
  if (estado.agotado) {
    return (
      <p className="caja-fiscal caja-fiscal-nota">
        Está tardando más de lo normal en facturarse. El administrador lo puede revisar en "Facturas con
        error".
      </p>
    );
  }
  return <p className="caja-fiscal caja-fiscal-nota caja-fiscal-emitiendo">Emitiendo comprobante…</p>;
}

// Lo que ve el vendedor mientras espera el comprobante: nunca el estado
// interno de facturación, solo si ya puede imprimir o no.
function EstadoComprobanteVendedor({ seFactura, agotado, error }) {
  if (!seFactura) {
    return <p className="caja-fiscal caja-fiscal-nota">Este medio no se factura.</p>;
  }
  if (error) {
    return (
      <p className="caja-fiscal caja-fiscal-error">
        No se pudo preparar el comprobante. Avisá a un administrador.
      </p>
    );
  }
  if (agotado) {
    return (
      <p className="caja-fiscal caja-fiscal-nota">
        Está tardando más de lo normal. Avisá a un administrador si no aparece.
      </p>
    );
  }
  return <p className="caja-fiscal caja-fiscal-nota caja-fiscal-emitiendo">Emitiendo comprobante…</p>;
}
