-- Compras: seguimiento de lo que José le compra a cada comercio/proveedor,
-- con la foto del comprobante como respaldo. No tiene nada que ver con
-- "gastos" (que llevan el monto para el resumen financiero): esto es solo
-- un registro por comercio, sin montos.

create table compras (
    id              bigint generated always as identity primary key,
    fecha           date not null,
    nombre_comercio text not null,
    descripcion     text,
    imagen          text not null,
    imagen_tipo     text not null check (imagen_tipo in ('image/jpeg', 'image/png', 'image/webp')),
    creado_por      bigint not null references usuarios(id),
    creado_en       timestamptz not null default now()
);

create index compras_fecha_idx on compras (fecha);
create index compras_comercio_idx on compras (lower(nombre_comercio), fecha);
