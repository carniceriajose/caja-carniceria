# Caja de la carnicería — Backend

API del sistema de caja. **Fase 1:** estructura base, conexión a la base de datos y login con roles.
**Fase 2:** ventas, gastos, resumen y configuración de qué medios se facturan.
**Fase 3:** facturación electrónica en ARCA (WSAA + WSFE), con reintento automático y una pantalla para las facturas con error.

- **Roles:** `vendedor` (solo carga y cobra) y `admin` (resumen, gastos, usuarios, configuración).
- **Stack:** FastAPI, SQLAlchemy 2.0, psycopg 3, argon2 para las contraseñas y JWT (HS256) para las sesiones.
- **Base de datos:** SQLite en desarrollo, PostgreSQL (Supabase) en producción.

## Requisitos

- Windows 11 y Python 3.12.

## Instalación en Windows (PowerShell)

Todos los comandos se corren desde la carpeta del proyecto.

```powershell
# 1. Entorno virtual e instalación de dependencias
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Si PowerShell no deja activar el entorno, correr una vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y volver a intentar.

```powershell
# 2. Configuración
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Abrir `.env` y pegar el valor generado en `JWT_SECRET` (es obligatorio y tiene que tener al menos 32 caracteres).

```powershell
# 3. Crear el primer administrador (pide nombre, usuario y contraseña; la contraseña no se muestra)
python -m scripts.crear_admin

# 4. Levantar la API
uvicorn app.main:app --reload
```

La API queda en <http://127.0.0.1:8000>. En desarrollo, la documentación interactiva está en
<http://127.0.0.1:8000/docs>.

```powershell
# 5. Tests
pytest
```

## Variables de entorno (`.env`)

| Variable | Descripción | Valor por defecto |
| --- | --- | --- |
| `DATABASE_URL` | Base de datos. Si empieza con `postgresql://` se convierte sola para psycopg 3. | `sqlite:///./dev.db` |
| `JWT_SECRET` | Clave para firmar los tokens. **Obligatoria**, mínimo 32 caracteres. | — |
| `JWT_MINUTOS_ADMIN` | Duración del token en minutos, para admin. | `120` |
| `JWT_MINUTOS_VENDEDOR` | Duración del token en minutos, para vendedor. | `720` |
| `ANULACION_MINUTOS_VENDEDOR` | Minutos en que el vendedor puede anular su última venta. | `10` |
| `CORS_ORIGENES` | Orígenes permitidos del frontend, separados por coma. | `http://localhost:5173` |
| `ENTORNO` | `desarrollo` o `produccion`. | `desarrollo` |
| `ARCA_ENTORNO` | `homologacion` o `produccion`. Define las URLs de WSAA y WSFE. | `homologacion` |
| `ARCA_CUIT` | CUIT con el que se factura. | — |
| `ARCA_CERT` / `ARCA_KEY` | Rutas al certificado y la clave del WSASS de ARCA. Nunca se suben al repositorio. | — |
| `ARCA_CERT_BASE64` / `ARCA_KEY_BASE64` | Alternativa a los archivos: el contenido de cada uno en base64. Si están presentes, tienen prioridad. Pensado para producción (variables de entorno, sin tocar el disco). | — |
| `ARCA_RAZON_SOCIAL`, `ARCA_DOMICILIO`, `ARCA_CONDICION_IVA`, `ARCA_INICIO_ACTIVIDADES`, `ARCA_INGRESOS_BRUTOS` | Datos del emisor que salen impresos en el ticket. Tienen que coincidir con la constancia de inscripción en ARCA. | vacío |
| `ARCA_PUNTO_VENTA` | Punto de venta habilitado para facturar. | `1` |
| `ARCA_TIPO_COMPROBANTE` | `11` = Factura C, `6` = Factura B. | `11` |
| `ARCA_ALICUOTA_IVA` | Alícuota de IVA (solo se usa con Factura B). | `21` |
| `ARCA_TAREAS_DE_FONDO` | Prende el reintento automático de facturas pendientes cada 1 minuto. Se apaga solo en los tests. | `true` |

## Endpoints

| Método | Ruta | Quién | Descripción |
| --- | --- | --- | --- |
| `GET` | `/salud` | Público | Verifica que la API y la base responden. |
| `POST` | `/auth/login` | Público | Entra con `usuario` y `password`. Devuelve `token` y los datos del usuario. |
| `GET` | `/auth/yo` | Logueado | Datos del usuario que hizo el pedido. |
| `GET` | `/usuarios` | Admin | Lista los usuarios. |
| `POST` | `/usuarios` | Admin | Crea un usuario (`nombre`, `usuario`, `password`, `rol`). |
| `PATCH` | `/usuarios/{id}` | Admin | Cambia `nombre`, `rol` y/o `activo`. |
| `PUT` | `/usuarios/{id}/password` | Admin | Resetea la contraseña de un usuario. |
| `GET` | `/configuracion` | Logueado | Qué medios de pago se facturan. |
| `PUT` | `/configuracion` | Admin | Cambia qué medios se facturan (`facturar_efectivo`, `facturar_tarjeta`, `facturar_transferencia`). |
| `POST` | `/ventas` | Vendedor y admin | Registra una venta (`total`, `medio_pago`, `id_cliente`). |
| `GET` | `/ventas` | Admin | Lista ventas. Filtros `desde`, `hasta`, `medio_pago`, `estado_arca`, `vendedor_id`; paginado (`pagina`, `por_pagina`). |
| `GET` | `/ventas/{id}` | Admin | Detalle de una venta. |
| `GET` | `/categorias-gasto` | Admin | Lista las categorías de gasto. |
| `POST` | `/categorias-gasto` | Admin | Crea una categoría; si ya existe (sin distinguir mayúsculas) devuelve la existente. |
| `GET` | `/gastos` | Admin | Lista gastos. Filtros `desde`, `hasta`, `categoria_id`; paginado. |
| `POST` | `/gastos` | Admin | Carga un gasto (`monto`, `categoria_id`, `fecha` opcional, `descripcion` opcional). |
| `PUT` | `/gastos/{id}` | Admin | Reemplaza un gasto. |
| `DELETE` | `/gastos/{id}` | Admin | Borra un gasto. |
| `GET` | `/resumen?desde=AAAA-MM-DD&hasta=AAAA-MM-DD` | Admin | Totales, desglose por medio de pago y estado fiscal, gastos, resultado y serie por día o por mes. |
| `GET` | `/ventas/{id}/fiscal` | Vendedor (solo la suya) y admin | Estado fiscal de una venta: para que la pantalla de cobro lo sondee hasta tener el CAE. |
| `GET` | `/ventas/{id}/comprobante` | Vendedor (solo la suya) y admin | Todo lo que lleva el ticket, incluida la URL del QR de ARCA. `409` si la venta todavía no está facturada. |
| `GET` | `/facturas/con-error` | Admin | Lista las ventas con `estado_arca = fallo`, paginado. |
| `POST` | `/ventas/{id}/reintentar-factura` | Admin | Vuelve a intentar facturar una venta `pendiente` o `fallo`. |
| `GET` | `/arca/estado` | Admin | Si hay certificado configurado y si ARCA está en línea (`FEDummy`). |

Los pedidos autenticados llevan la cabecera `Authorization: Bearer <token>`.

Códigos de error: `400` pedido inválido (por ejemplo `desde` posterior a `hasta`), `401` sin sesión válida,
`403` sin permiso, `404` no existe, `409` usuario repetido o `id_cliente` reutilizado con otros datos,
`422` datos inválidos, `429` demasiados intentos de login.

## Reglas de las ventas y del resumen

- **Plata:** los montos entran como número o, mejor, como texto (`"1250.50"`), con hasta 2 decimales y mayores a 0. Salen siempre como texto con 2 decimales, para que nunca pasen por un float.
- **`id_cliente`:** un UUID que genera el frontend al empezar cada venta. Si el mismo `id_cliente` llega dos veces con los mismos datos (doble clic, reintento por mala conexión) se devuelve la venta ya creada, con `200` en vez de `201`. Si llega con datos distintos, `409`.
- **Vendedor y fecha:** el vendedor sale del token y la fecha y hora las pone el servidor; si vienen en el cuerpo se ignoran.
- **Estado fiscal:** una venta nace `pendiente` si su medio de pago se factura según `/configuracion`, y `no_aplica` si no. Todas las ventas se guardan siempre. Cambiar la configuración solo afecta a las ventas nuevas.
- **Días en hora de Argentina:** `desde` y `hasta` de `/ventas`, `/gastos` y `/resumen` son fechas argentinas, inclusivas. Una venta a las 22:00 del lunes es del lunes aunque en UTC ya sea martes. Las sumas y agrupaciones las hace la base.
- **Serie del resumen:** por día; si el rango supera 62 días, por mes (el período es el primer día del mes). Los días o meses sin ventas aparecen en cero. El rango máximo es de 10 años.

## Facturación en ARCA

- **Cuándo se factura:** al crear una venta, si su medio de pago se factura según `/configuracion`, queda `pendiente` y la emisión se lanza en segundo plano — la respuesta al vendedor no espera a ARCA. Si se aprueba, pasa a `facturada` con el CAE; si ARCA la rechaza, a `fallo` con el motivo en `error_detalle`. La respuesta completa de ARCA (aprobada, rechazada o con error) siempre se guarda en `respuesta_fiscal`.
- **Reintento automático:** un proceso corre cada 1 minuto y reintenta las ventas `pendiente`. Si no logra avanzar ninguna (ARCA caído, sin certificado), espera cada vez más antes de volver a intentar, hasta un tope de 30 minutos.
- **Facturas `fallo`:** no se reintentan solas. El admin las ve en "Facturas con error" y las reintenta a mano.
- **Nunca se duplica una factura:** si ARCA no contesta a tiempo (timeout), antes de pedir otro número se consulta con `FECompConsultar` si el anterior quedó autorizado. Si quedó, se guarda ese CAE; si no, se deja la venta como estaba para el próximo ciclo.
- **Un comprobante por vez:** pedir el último número autorizado y pedir el CAE están protegidos por un lock (en el proceso, y `pg_advisory_lock` en PostgreSQL), para que dos ventas simultáneas nunca pidan el mismo número.
- **Cálculo de Factura B:** `ImpNeto = total / (1 + alícuota)` redondeado a 2 decimales, `ImpIVA = total - ImpNeto` (así siempre suman exacto el total). Factura C no discrimina IVA.
- **El ticket de acceso de WSAA** (token + sign) se guarda en la tabla `tickets_acceso` y se reutiliza mientras le falten más de 10 minutos para vencer. Si ARCA avisa que ya hay un ticket vigente, no se reintenta en loop: se espera al próximo ciclo.
- **Sin certificado:** el backend arranca igual, las ventas facturables quedan `pendiente`, y `/arca/estado` lo informa sin mostrar la ruta del archivo.

### Comprobante imprimible

- El ticket es para impresora térmica de 80 mm (`@page` a 80 mm de ancho). Se imprime desde la pantalla de cobro (una vez facturada la venta) y se reimprime desde Ventas → Ver detalle → Ver e imprimir comprobante. En el cuadro de impresión hay que elegir la impresora térmica.
- **QR:** URL `https://www.afip.gob.ar/fe/qr/?p=<base64 del JSON>` con los campos de la RG 4291 (`ver`, `fecha`, `cuit`, `ptoVta`, `tipoCmp`, `nroCmp`, `importe`, `moneda`, `ctz`, `tipoDocRec`, `nroDocRec`, `tipoCodAut`, `codAut`). El importe se arma como texto con 2 decimales, sin pasar por un float. Consumidor final sin identificar: `tipoDocRec` 99, `nroDocRec` 0.
- **Fecha del ticket:** la que ARCA registró (`CbteFch`); si no está, el día de la venta en hora de Argentina.
- **Factura B:** muestra el IVA contenido (Ley 27.743), calculado con la alícuota configurada.

### Probar contra ARCA

```powershell
python -m scripts.probar_arca
```

Hace login en WSAA, consulta `FEDummy`, pide el último comprobante autorizado y emite una factura de $100 a consumidor final. Muestra el CAE obtenido. Requiere `ARCA_CERT`/`ARCA_KEY` (o sus `_BASE64`) configurados.

## Reglas de seguridad

- Contraseñas con argon2id (mínimo 8 caracteres); se vuelven a hashear solas si cambian los parámetros.
- El login es solo con **usuario** (no mail). Si el usuario no existe o la contraseña está mal, la respuesta y el tiempo son los mismos.
- **Bloqueo:** 5 intentos fallidos de un mismo usuario lo bloquean 15 minutos, y 20 fallos desde una misma IP bloquean esa IP 15 minutos (respuesta `429`). El límite por IP es más alto porque toda la carnicería sale por la misma IP. Un login correcto reinicia el contador del usuario, no el de la IP. Los límites son las constantes `MAX_INTENTOS_USUARIO`, `MAX_INTENTOS_IP` y `VENTANA_SEGUNDOS` de `app/security.py`. El contador está en memoria, así que se reinicia al reiniciar el servidor y sirve para una sola instancia. Detrás de un proxy hay que arrancar uvicorn con `--proxy-headers` y `--forwarded-allow-ips` para que vea la IP real del cliente.
- En **cada pedido** se vuelve a leer al usuario de la base: si fue desactivado, no existe o su `token_version` cambió, se lo rechaza. Cambiar la contraseña, cambiar el rol o desactivar a un usuario invalida sus tokens al instante.
- Un admin no puede desactivarse ni quitarse el rol a sí mismo, y siempre queda al menos un admin activo.
- CORS solo para los orígenes configurados, sin credenciales. Cabeceras `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` y `Cache-Control: no-store` (más HSTS en producción).
- En producción no se publican `/docs` ni `/openapi.json`.
- Los errores de validación no devuelven el valor recibido, para no repetir contraseñas en las respuestas.
- El contenido de la clave privada de ARCA, el token y el sign nunca se loguean, imprimen ni devuelven por la API.

## Producción con Supabase

1. En el editor SQL de Supabase, ejecutar `supabase/migrations/0001_esquema_inicial.sql`. En producción la API **no** crea las tablas sola.
2. Las tablas quedan con RLS activado, sin políticas y sin permisos para `anon` y `authenticated`: solo el backend accede.
3. En `.env`: `ENTORNO=produccion` y `DATABASE_URL` con la cadena de conexión de Postgres del proyecto (Project Settings → Database). Es la cadena de la base, no la API key.
4. Servir la API solo por HTTPS.
5. Crear el primer admin con `python -m scripts.crear_admin` apuntando a esa base.

SQLite es solo para desarrollo: no guarda los `numeric` con precisión exacta. En PostgreSQL la plata es exacta.

## Estructura

```
app/
  config.py     variables de entorno
  db.py         conexión a la base
  models.py     tablas (coinciden con la migración SQL)
  schemas.py    formatos de entrada y salida
  security.py   contraseñas, tokens y bloqueo de intentos
  deps.py       usuario logueado y control de roles
  fechas.py     zona horaria de Argentina
  main.py       aplicación, CORS y cabeceras de seguridad
  routers/      auth.py, usuarios.py, ventas.py, gastos.py, resumen.py, configuracion.py, arca.py
  arca/         wsaa.py (login), wsfe.py (comprobantes), servicio.py (cálculo, numeración, lock), tareas.py (reintento cada 1 minuto)
scripts/        crear_admin.py, probar_arca.py
tests/          pruebas con pytest (SQLite en memoria; ARCA con el cliente SOAP simulado)
supabase/migrations/   SQL para PostgreSQL
```
