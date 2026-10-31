-- Recargo automático sobre el total de la venta: por tarjeta (según el tipo
-- de tarjeta elegido) y por transferencia (un único porcentaje). No hay
-- descuentos ni ajustes manuales. Efectivo nunca tiene recargo.

-- Limpieza de columnas de un diseño anterior (ajuste manual + un único
-- recargo de tarjeta en configuración) que se descartó antes de llegar a
-- usarse de verdad.
alter table configuracion
    drop column if exists recargo_tarjeta_porcentaje,
    drop column if exists permitir_ajuste_manual,
    drop column if exists tope_descuento_manual_porcentaje,
    drop column if exists ajuste_manual_quien;

alter table configuracion
    add column if not exists recargo_transferencia_porcentaje numeric(5,2) not null default 0;

-- ---------------------------------------------------------------
-- tarjetas: los tipos de tarjeta que se pueden elegir al cobrar, cada uno con
-- su propio recargo. No se borran (una venta vieja tiene que poder seguir
-- señalando la que usó): se desactivan con "activa" y desaparecen de la
-- pantalla de venta, pero quedan en el historial.
-- ---------------------------------------------------------------
create table if not exists tarjetas (
    id                 bigint generated always as identity primary key,
    nombre             text          not null,
    recargo_porcentaje numeric(5,2)  not null default 0 check (recargo_porcentaje >= 0 and recargo_porcentaje <= 100),
    activa             boolean       not null default true,
    orden              integer       not null
);
create unique index if not exists tarjetas_nombre_uq on tarjetas (lower(nombre));

insert into tarjetas (nombre, recargo_porcentaje, activa, orden)
select * from (values
    ('Débito', 0, true, 1),
    ('Visa 1 pago', 15, true, 2),
    ('Mastercard 1 pago', 15, true, 3),
    ('Maestro 1 pago', 15, true, 4),
    ('Naranja 1 pago', 20, true, 5)
) as datos_iniciales(nombre, recargo_porcentaje, activa, orden)
where not exists (select 1 from tarjetas);

alter table tarjetas enable row level security;
revoke all on tarjetas from anon, authenticated;

-- "subtotal" es lo que se tipeó antes de aplicar nada; "total" (ya existía)
-- pasa a ser lo que se cobra y se factura de verdad, con el recargo aplicado.
-- Para las ventas de antes de este campo, el subtotal es el mismo total.
alter table ventas add column if not exists subtotal numeric(12,2);
update ventas set subtotal = total where subtotal is null;
alter table ventas alter column subtotal set not null;

alter table ventas
    add column if not exists ajuste_tipo    text,
    add column if not exists ajuste_origen  text,
    add column if not exists ajuste_monto   numeric(12,2),
    add column if not exists ajuste_detalle text,
    -- Qué tarjeta se usó (solo cuando medio_pago = 'tarjeta'): sirve para
    -- detectar un reintento con una tarjeta distinta, igual que con el monto.
    add column if not exists tarjeta_id bigint references tarjetas (id);

alter table ventas drop constraint if exists ventas_ajuste_tipo_check;
alter table ventas add constraint ventas_ajuste_tipo_check
    check (ajuste_tipo is null or ajuste_tipo = 'recargo');

alter table ventas drop constraint if exists ventas_ajuste_origen_check;
alter table ventas add constraint ventas_ajuste_origen_check
    check (ajuste_origen is null or ajuste_origen = 'medio_pago');
