import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
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
