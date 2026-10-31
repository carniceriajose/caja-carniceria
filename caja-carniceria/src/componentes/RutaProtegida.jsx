import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Cargando from "./Cargando";

export default function RutaProtegida({ rolesPermitidos, children }) {
  const { usuario, cargando } = useAuth();

  if (cargando) return <Cargando texto="Verificando sesión…" />;
  if (!usuario) return <Navigate to="/" replace />;
  if (rolesPermitidos && !rolesPermitidos.includes(usuario.rol)) {
    return <Navigate to={usuario.rol === "admin" ? "/admin" : "/venta"} replace />;
  }
  return children;
}
