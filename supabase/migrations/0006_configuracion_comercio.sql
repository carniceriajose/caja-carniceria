-- Pantalla de Configuración: datos del comercio, facturación y operación,
-- todo lo que antes vivía en variables de entorno y ahora es editable por el
-- admin sin reiniciar el servidor.
--
-- Los valores por default de acá son solo un placeholder para que la columna
-- pueda ser "not null": la aplicación completa los valores reales (los que
-- ya estaban en el .env) la primera vez que alguien lee la configuración
-- después de esta migración (ver app/configuracion.py).

alter table configuracion
    add column razon_social               text        not null default '',
    add column domicilio                  text        not null default '',
    add column condicion_iva              text        not null default '',
    add column inicio_actividades         date        not null default '2020-01-01',
    add column ingresos_brutos            text,
    add column tipo_comprobante           integer     not null default 11,
    add column alicuota_iva               numeric(5,2) not null default 21,
    add column punto_venta                integer     not null default 1,
    add column descripcion_item           text        not null default 'Venta de mercadería',
    add column anulacion_minutos_vendedor integer     not null default 10;

-- La alícuota con la que se facturó de verdad, congelada en cada comprobante:
-- si la configuración cambia después, no tiene que alterar uno ya emitido.
alter table ventas      add column alicuota_iva numeric(5,2);
alter table anulaciones add column alicuota_iva numeric(5,2);
