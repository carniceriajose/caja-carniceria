-- Segundo factor (TOTP) para admin y tabla de auditoría.

alter table usuarios
    add column totp_activado          boolean not null default false,
    add column totp_secreto           text,
    add column totp_secreto_pendiente text;

-- ---------------------------------------------------------------
-- auditoria: quién hizo cada cosa (acciones administrativas, no lecturas)
-- ---------------------------------------------------------------
create table auditoria (
    id         bigint generated always as identity primary key,
    usuario_id bigint references usuarios (id),
    accion     text        not null,
    detalle    jsonb,
    creado_en  timestamptz not null default now()
);
create index auditoria_creado_en_idx on auditoria (creado_en desc);
create index auditoria_usuario_idx   on auditoria (usuario_id);

alter table auditoria enable row level security;
revoke all on auditoria from anon, authenticated;
