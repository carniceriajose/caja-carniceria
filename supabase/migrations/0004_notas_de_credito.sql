-- Anulación de ventas facturadas con nota de crédito ante ARCA.
--
-- La 0003 había agregado ventas.anulada_motivo: se reemplaza por la tabla
-- "anulaciones" (motivo + todo el detalle de la nota de crédito, si aplica).

alter table ventas
    drop column if exists anulada_motivo;

-- ---------------------------------------------------------------
-- anulaciones: una por venta (no se puede anular dos veces). Si la venta ya
-- tenía CAE, acá queda el resultado de la nota de crédito ante ARCA; si no,
-- queda "sin_comprobante" de una, sin tocar ARCA.
-- ---------------------------------------------------------------
create table anulaciones (
    id               bigint generated always as identity primary key,
    venta_id         bigint      not null references ventas (id),
    motivo           text        not null,
    usuario_id       bigint      not null references usuarios (id),
    fecha_hora       timestamptz not null default now(),
    estado           text        not null default 'pendiente'
                     check (estado in ('pendiente', 'emitida', 'fallo', 'sin_comprobante')),

    -- Nota de crédito: mismo significado que los campos análogos de ventas,
    -- pero acá (la venta original nunca se toca).
    tipo             integer,
    punto_venta      integer,
    numero           bigint,
    cae              text,
    cae_vencimiento  date,
    error_detalle    text,
    respuesta_fiscal jsonb
);
create unique index anulaciones_venta_id_uq on anulaciones (venta_id);
create index anulaciones_pendientes_idx on anulaciones (estado) where estado in ('pendiente', 'fallo');

alter table anulaciones enable row level security;
revoke all on anulaciones from anon, authenticated;
