-- Fase 5 de seguridad: 2FA opcional con códigos de recuperación, anulación de
-- ventas (sin nota de crédito todavía) y más detalle en la auditoría.
--
-- La migración 0002 ya había agregado totp_activado/totp_secreto/
-- totp_secreto_pendiente: se renombran los dos primeros (mismo dato, nuevo
-- nombre) y se elimina el pendiente, porque ahora el secreto viaja sin
-- guardar entre /2fa/iniciar y /2fa/activar.

alter table usuarios
    rename column totp_activado to dos_factores_activo;
alter table usuarios
    rename column totp_secreto to dos_factores_secreto;
alter table usuarios
    drop column if exists totp_secreto_pendiente;

-- ---------------------------------------------------------------
-- codigos_recuperacion_2fa: 8 códigos de un solo uso, hasheados, que se
-- muestran una única vez al activar el 2FA.
-- ---------------------------------------------------------------
create table codigos_recuperacion_2fa (
    id          bigint generated always as identity primary key,
    usuario_id  bigint      not null references usuarios (id),
    codigo_hash text        not null,
    usado_en    timestamptz,
    creado_en   timestamptz not null default now()
);
create index codigos_recuperacion_2fa_usuario_idx on codigos_recuperacion_2fa (usuario_id);

alter table codigos_recuperacion_2fa enable row level security;
revoke all on codigos_recuperacion_2fa from anon, authenticated;

-- ---------------------------------------------------------------
-- auditoria: qué entidad afectó cada acción (además del detalle libre en json)
-- ---------------------------------------------------------------
alter table auditoria
    add column entidad    text,
    add column entidad_id bigint;

-- ---------------------------------------------------------------
-- ventas: anulación (sin nota de crédito todavía: bloqueada si ya tiene CAE,
-- ver app/routers/ventas.py)
-- ---------------------------------------------------------------
alter table ventas
    add column anulada        boolean not null default false,
    add column anulada_motivo text,
    add column anulada_por    bigint references usuarios (id),
    add column anulada_en     timestamptz,
    add constraint ventas_anulada_completa check (not anulada or anulada_en is not null);
