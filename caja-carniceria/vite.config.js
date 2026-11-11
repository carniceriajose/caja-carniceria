import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  define: {
    // Se usa como "número de versión" en Configuración: con esto alcanza para
    // saber qué build tiene cargado José cuando avisa que algo no anda.
    __FECHA_BUILD__: JSON.stringify(
      new Date().toLocaleString("es-AR", {
        timeZone: "America/Argentina/Buenos_Aires",
        dateStyle: "short",
        timeStyle: "short",
      })
    ),
  },
  plugins: [
    react(),
    VitePWA({
      // "prompt": el service worker nuevo se instala pero se queda esperando
      // en vez de tomar el control solo. Como la caja queda con la pestaña
      // abierta todo el día, si se actualizara sola podría cortar una venta a
      // medio cargar. En vez de eso, el aviso de ActualizacionDisponible deja
      // que decida la persona cuándo recargar.
      registerType: "prompt",
      injectRegister: false,
      includeAssets: ["favicon.png", "favicon-32.png"],
      manifest: {
        name: "El Abasto de José",
        short_name: "El Abasto",
        description: "Sistema de ventas y gestión de la carnicería.",
        start_url: "/venta",
        scope: "/",
        display: "standalone",
        theme_color: "#861f2d",
        background_color: "#f3f5f8",
        lang: "es-AR",
        icons: [
          { src: "/icono-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "/icono-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "/icono-maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
          { src: "/icono-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // El shell de la app (HTML/JS/CSS/íconos) se cachea para que abra
        // rápido y funcione aunque se corte un instante la conexión. Las
        // llamadas a la API (otro origen: el backend) nunca pasan por acá,
        // así que los datos de ventas/resumen siempre se piden en vivo.
        globPatterns: ["**/*.{js,css,html,png,svg,ico}"],
        navigateFallbackDenylist: [/^\/auth\//],
        // Borra del Cache Storage las versiones de caché de builds anteriores
        // apenas el service worker nuevo toma el control.
        cleanupOutdatedCaches: true,
        // El service worker nuevo se queda "esperando" hasta que la persona
        // confirma la actualización (ver ActualizacionDisponible.jsx), pero
        // una vez que lo confirma necesita tomar control de la pestaña ya
        // abierta de inmediato para que la recarga lo use; sin esto se
        // quedaría esperando a una pestaña nueva que, en la caja, puede no
        // llegar nunca porque la pestaña queda abierta todo el día.
        clientsClaim: true,
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
  server: {
    port: 5173,
  },
});
