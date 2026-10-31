-- Rubros de venta: cada uno con su propia alícuota de IVA (Carne 10,5%,
-- Embutidos 21%, u otros que se agreguen después). Reemplaza la alícuota
-- única que había en configuración.

create table if not exists rubros (
    id                  bigint generated always as identity primary key,
    nombre              text          not null,
    alicuota            numeric(5,2)  not null
                        check (alicuota in (0, 2.5, 5, 10.5, 21, 27)),
    descripcion_factura text          not null,
    activo              boolean       not null default true,
    orden               integer       not null,
    es_predeterminado   boolean       not null default false
);
create unique index if not exists rubros_nombre_uq on rubros (lower(nombre));
-- A lo sumo un predeterminado a la vez (la aplicación se encarga de que
-- siempre haya exactamente uno, nunca cero: ver app/rubros.py).
create unique index if not exists rubros_predeterminado_uq on rubros (es_predeterminado) where es_predeterminado;

insert into rubros (nombre, alicuota, descripcion_factura, activo, orden, es_predeterminado)
select * from (values
    ('Carne', 10.5, 'Venta de carne', true, 1, true),
    ('Embutidos', 21, 'Venta de embutidos', true, 2, false)
) as datos_iniciales(nombre, alicuota, descripcion_factura, activo, orden, es_predeterminado)
where not exists (select 1 from rubros);

alter table rubros enable row level security;
revoke all on rubros from anon, authenticated;

-- Tarjeta: nombre y recargo quedan también congelados en la venta (antes
-- solo quedaba el id), por si la tarjeta cambia de nombre o de recargo (o se
-- desactiva) más adelante.
alter table ventas
    add column if not exists tarjeta_nombre            text,
    add column if not exists tarjeta_recargo_porcentaje numeric(5,2);
update ventas set tarjeta_nombre = t.nombre, tarjeta_recargo_porcentaje = t.recargo_porcentaje
    from tarjetas t
    where t.id = ventas.tarjeta_id and ventas.tarjeta_nombre is null;

-- Rubro elegido: determina la alícuota de IVA y la descripción del ítem en
-- la factura, también congelados en la venta.
alter table ventas
    add column if not exists rubro_id            bigint references rubros (id),
    add column if not exists rubro_nombre        text,
    add column if not exists descripcion_factura text;

alter table configuracion drop column if exists alicuota_iva;
