-- Comentarios por comercio: notas que José va agregando con el tiempo sobre
-- cada proveedor (no están atadas a una compra puntual, son del comercio en
-- general). Se agrupan por el mismo texto de "nombre_comercio" que ya usa
-- "compras" (sin distinguir mayúsculas), sin necesitar una tabla de
-- comercios aparte.

create table comentarios_comercio (
    id              bigint generated always as identity primary key,
    nombre_comercio text not null,
    comentario      text not null,
    creado_por      bigint not null references usuarios(id),
    creado_en       timestamptz not null default now()
);

create index comentarios_comercio_nombre_idx on comentarios_comercio (lower(nombre_comercio), creado_en desc);
