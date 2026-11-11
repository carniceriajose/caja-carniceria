import { Navigate, Route, Routes } from "react-router-dom";
import RutaProtegida from "./componentes/RutaProtegida";
import ReautenticarModal from "./componentes/ReautenticarModal";
import Login from "./paginas/Login/Login";
import Venta from "./paginas/Venta/Venta";
import Dashboard from "./paginas/Dashboard/Dashboard";
import Gastos from "./paginas/Gastos/Gastos";
import Compras from "./paginas/Compras/Compras";
import Usuarios from "./paginas/Usuarios/Usuarios";
import FacturasConError from "./paginas/FacturasConError/FacturasConError";
import Auditoria from "./paginas/Auditoria/Auditoria";
import Anulaciones from "./paginas/Anulaciones/Anulaciones";
import CierreCaja from "./paginas/CierreCaja/CierreCaja";
import Configuracion from "./paginas/Configuracion/Configuracion";
import Ventas from "./paginas/Ventas/Ventas";
import VentaDetalle from "./paginas/Ventas/VentaDetalle";
import Comprobante from "./paginas/Comprobante/Comprobante";
import LayoutAdmin from "./paginas/Layout/LayoutAdmin";

export default function App() {
  return (
    <>
      <ReautenticarModal />
      <Routes>
        <Route path="/" element={<Login />} />

        <Route
          path="/venta"
          element={
            <RutaProtegida rolesPermitidos={["vendedor", "admin"]}>
              <Venta />
            </RutaProtegida>
          }
        />

        <Route
          path="/comprobante/:id"
          element={
            <RutaProtegida rolesPermitidos={["vendedor", "admin"]}>
              <Comprobante />
            </RutaProtegida>
          }
        />

        <Route
          path="/admin"
          element={
            <RutaProtegida rolesPermitidos={["admin"]}>
              <LayoutAdmin />
            </RutaProtegida>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="ventas" element={<Ventas />} />
          <Route path="ventas/:id" element={<VentaDetalle />} />
          <Route path="gastos" element={<Gastos />} />
          <Route path="compras" element={<Compras />} />
          <Route path="usuarios" element={<Usuarios />} />
          <Route path="facturas-con-error" element={<FacturasConError />} />
          <Route path="anulaciones" element={<Anulaciones />} />
          <Route path="cierre-caja" element={<CierreCaja />} />
          <Route path="configuracion" element={<Configuracion />} />
          <Route path="auditoria" element={<Auditoria />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
