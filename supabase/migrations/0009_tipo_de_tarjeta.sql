-- Tipo de tarjeta (crédito o débito): permite diferenciarlas en los
-- resúmenes, además del desglose que ya existía por tarjeta puntual.

alter table tarjetas add column if not exists tipo text;

-- Las tarjetas ya cargadas se clasifican por su nombre: "Débito" es la única
-- sembrada como débito (ver migración 0007), el resto son de crédito.
update tarjetas set tipo = case when lower(nombre) like '%d%bito%' then 'debito' else 'credito' end
    where tipo is null;

alter table tarjetas alter column tipo set not null;
alter table tarjetas drop constraint if exists tarjetas_tipo_check;
alter table tarjetas add constraint tarjetas_tipo_check check (tipo in ('credito', 'debito'));

-- Igual que nombre y recargo, el tipo queda congelado en la venta: un cambio
-- posterior en la tarjeta nunca altera una venta ya cobrada.
alter table ventas add column if not exists tarjeta_tipo text;
update ventas set tarjeta_tipo = t.tipo
    from tarjetas t
    where t.id = ventas.tarjeta_id and ventas.tarjeta_tipo is null;
