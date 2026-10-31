-- Cierre de caja diario: el corte que hace el admin al terminar el día.

create table cierres_caja (
    id                   bigint generated always as identity primary key,
    fecha                date        not null,
    usuario_id           bigint      not null references usuarios (id),
    fecha_hora_cierre    timestamptz not null default now(),

    total_general        numeric(12,2) not null,
    total_efectivo       numeric(12,2) not null,
    total_tarjeta        numeric(12,2) not null,
    total_transferencia  numeric(12,2) not null,
    cantidad_ventas      integer       not null,
    cantidad_anulaciones integer       not null,
    monto_anulaciones    numeric(12,2) not null,

    efectivo_contado     numeric(12,2) not null,
    diferencia           numeric(12,2) not null,
    observaciones        text,
    detalle              jsonb         not null,

    anulado              boolean     not null default false,
    anulado_motivo       text,
    anulado_por          bigint references usuarios (id),
    anulado_en           timestamptz
);

-- Un solo cierre activo por día: anulado uno, se puede cerrar de nuevo.
create unique index cierres_caja_fecha_activo_uq on cierres_caja (fecha) where not anulado;

alter table cierres_caja enable row level security;
revoke all on cierres_caja from anon, authenticated;
