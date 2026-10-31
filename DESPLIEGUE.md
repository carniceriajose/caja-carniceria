# Puesta en producción

Pasos para los puntos 2, 3, 4 y 8 de la lista de lanzamiento. Lo que requiere
tus cuentas (Railway, Netlify, Supabase, ARCA) lo hacés vos; acá te dejo
exactamente qué pegar en cada lado.

## 1. Backend en Railway

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → elegí este repositorio.
2. Railway detecta Python solo (por `requirements.txt`, `.python-version` y el `Procfile` que ya están en el repo).
3. En **Variables**, cargá estas (mismos nombres que tu `.env` local; ver `.env.example` para el detalle de cada una):

   ```
   DATABASE_URL=postgresql://...        (el de Supabase, el mismo que usás ahora)
   JWT_SECRET=                          (generar uno nuevo y distinto al de desarrollo:
                                          python -c "import secrets; print(secrets.token_urlsafe(48))")
   JWT_MINUTOS_ADMIN=120
   JWT_MINUTOS_VENDEDOR=720
   ANULACION_MINUTOS_VENDEDOR=10
   CORS_ORIGENES=https://TU-SITIO.netlify.app   (lo sabés recién después del paso 2; lo actualizás ahí)
   ENTORNO=produccion
   ARCA_ENTORNO=produccion
   ARCA_CUIT=                           (el CUIT real de la carnicería)
   ARCA_CERT_BASE64=                    (ver abajo cómo generarlo)
   ARCA_KEY_BASE64=
   ARCA_RAZON_SOCIAL=
   ARCA_DOMICILIO=
   ARCA_CONDICION_IVA=
   ARCA_INICIO_ACTIVIDADES=
   ARCA_INGRESOS_BRUTOS=
   ARCA_PUNTO_VENTA=10
   ARCA_TIPO_COMPROBANTE=6              (6 = Factura B)
   ARCA_TAREAS_DE_FONDO=true
   ```

   **Certificado y clave en base64** (una vez que tengas el certificado de
   producción de ARCA — ver más abajo), en PowerShell:

   ```powershell
   certutil -encode produccion.crt cert.b64
   certutil -encode produccion.key key.b64
   ```

   Abrí los `.b64` generados y pegá el contenido (sin las líneas
   `-----BEGIN CERTIFICATE-----`/`-----END CERTIFICATE-----`, Railway no las
   necesita) en `ARCA_CERT_BASE64` / `ARCA_KEY_BASE64`.

4. Railway te da una URL pública (`https://tu-backend.up.railway.app`). Probala:
   `https://tu-backend.up.railway.app/salud` tiene que devolver `{"estado":"ok"}`.

## 2. Frontend en Netlify

1. [netlify.com](https://netlify.com) → **Add new site** → **Import an existing project** → este repositorio.
2. Base directory: `caja-carniceria`. El `netlify.toml` ya tiene el build command (`npm run build`) y la carpeta de salida (`dist`).
3. En **Site settings → Environment variables**, agregá:

   ```
   VITE_API_URL=https://tu-backend.up.railway.app
   ```

   (la URL real de Railway del paso anterior, sin barra al final).

4. Deploy. Netlify te da una URL (`https://tu-sitio.netlify.app`).
5. Volvé a Railway y actualizá `CORS_ORIGENES` con esa URL exacta, para que el backend acepte pedidos del frontend.

## 3. Backups en Supabase

1. Entrá a tu proyecto en [supabase.com](https://supabase.com) → **Database → Backups**.
2. Activá los backups automáticos diarios (en el plan gratuito son de 7 días de
   retención; si querés más, hay que pasar a un plan pago).
3. Las migraciones ya están todas aplicadas — los backups cubren los datos,
   no hace falta tocar nada más acá.

## 4. Arranque automático en la PC del local

Con el backend y el frontend en la nube, la PC del local no necesita correr
nada — solo necesita abrir el navegador en la URL de Netlify al prender.

1. Instalá la PWA: abrí `https://tu-sitio.netlify.app` en Chrome o Edge →
   ícono de instalar en la barra de direcciones (o menú → "Instalar
   aplicación").
2. Para que abra sola al prender la PC: `Win + R` → `shell:startup` → poné ahí
   un acceso directo a la app instalada (clic derecho sobre su ícono en el
   menú de inicio → "Más" → "Abrir ubicación del archivo", copiar ese acceso
   directo a la carpeta que se abrió con `shell:startup`).

## Certificado de producción de ARCA (lo gestionás vos)

1. Entrá a [afip.gob.ar](https://www.afip.gob.ar) con la clave fiscal de la
   carnicería (nivel 3 como mínimo).
2. Buscá el servicio **"Administración de Certificados Digitales"**.
3. Generá un nuevo certificado para el CUIT de la carnicería, para el
   servicio **wsfe** (factura electrónica). AFIP te da un `.crt`; la clave
   privada (`.key`) la generás vos antes de pedirlo (con `openssl`) y nunca
   se la mandás a nadie.
4. Una vez que tengas ambos archivos, son los que vas a convertir a base64
   para Railway (paso 1 de arriba) y los que reemplazan a `homo.crt`/`homo.key`
   si seguís probando en esta PC.

Avisame cuando tengas el certificado y actualizamos `ARCA_ENTORNO=produccion`
y el CUIT real en el `.env` de acá también, para la factura de prueba del
punto 7.
