import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import {
  IconoAnular,
  IconoCarrito,
  IconoCerrarX,
  IconoCierreCaja,
  IconoDinero,
  IconoDocumento,
  IconoEngranaje,
  IconoInicio,
  IconoMenu,
  IconoSalir,
  IconoUsuarios,
} from "../../componentes/Iconos";
import "./LayoutAdmin.css";

const ENLACES = [
  { ruta: "/admin", texto: "Resumen", Icono: IconoInicio, exacto: true },
  { ruta: "/admin/ventas", texto: "Ventas", Icono: IconoCarrito },
  { ruta: "/admin/gastos", texto: "Gastos", Icono: IconoDinero },
  { ruta: "/admin/facturas-con-error", texto: "Facturas con error", Icono: IconoDocumento },
  { ruta: "/admin/anulaciones", texto: "Anulaciones", Icono: IconoAnular },
  { ruta: "/admin/cierre-caja", texto: "Cierre de caja", Icono: IconoCierreCaja },
  { ruta: "/admin/usuarios", texto: "Usuarios", Icono: IconoUsuarios },
  { ruta: "/admin/configuracion", texto: "Configuración", Icono: IconoEngranaje },
];

export default function LayoutAdmin() {
  const { usuario, cerrarSesion } = useAuth();
  const [menuAbierto, setMenuAbierto] = useState(false);

  const cerrarMenu = () => setMenuAbierto(false);

  return (
    <div className="layout-admin">
      <aside className="layout-admin-menu">
        <div className="layout-admin-cabecera">
          <span className="layout-admin-titulo">
            <img src="/logo-192.png" alt="El Abasto de José" />
            <span className="layout-admin-titulo-texto">
              <span className="layout-admin-titulo-rubro">Hipercarnicería</span>
              <span className="layout-admin-titulo-nombre">El Abasto de José</span>
            </span>
          </span>
          <button
            type="button"
            className="layout-admin-hamburguesa"
            aria-label={menuAbierto ? "Cerrar menú" : "Abrir menú"}
            aria-expanded={menuAbierto}
            aria-controls="layout-admin-panel"
            onClick={() => setMenuAbierto((abierto) => !abierto)}
          >
            {menuAbierto ? <IconoCerrarX tamanio={22} /> : <IconoMenu tamanio={22} />}
          </button>
        </div>

        <div id="layout-admin-panel" className={`layout-admin-panel ${menuAbierto ? "abierto" : ""}`}>
          <NavLink to="/venta" className="layout-admin-caja" onClick={cerrarMenu}>
            Ir a la caja
          </NavLink>

          <nav className="layout-admin-nav">
            {ENLACES.map(({ ruta, texto, Icono, exacto }) => (
              <NavLink
                key={ruta}
                to={ruta}
                end={exacto}
                onClick={cerrarMenu}
                className={({ isActive }) => (isActive ? "layout-admin-enlace activo" : "layout-admin-enlace")}
              >
                <Icono tamanio={18} />
                <span>{texto}</span>
              </NavLink>
            ))}
          </nav>

          <div className="layout-admin-usuario">
            <div className="layout-admin-usuario-datos">
              <span className="layout-admin-usuario-avatar" aria-hidden="true">
                {usuario?.nombre?.[0]?.toUpperCase()}
              </span>
              <span className="layout-admin-usuario-texto">
                <span className="layout-admin-usuario-nombre">{usuario?.nombre}</span>
                <span className="layout-admin-usuario-rol">
                  {usuario?.rol === "admin" ? "Administrador" : "Vendedor"}
                </span>
              </span>
            </div>
            <button type="button" className="layout-admin-salir" onClick={cerrarSesion}>
              <IconoSalir tamanio={16} />
              Cerrar sesión
            </button>
          </div>
        </div>
      </aside>

      {menuAbierto && <button type="button" className="layout-admin-fondo" aria-label="Cerrar menú" onClick={cerrarMenu} />}

      <main className="layout-admin-contenido">
        <Outlet />
      </main>
    </div>
  );
}
