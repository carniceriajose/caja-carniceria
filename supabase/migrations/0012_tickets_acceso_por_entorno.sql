-- El ticket de acceso de WSAA se guardaba identificado solo por "servicio"
-- (wsfe), sin distinguir entorno ni CUIT: si se cambiaba de homologación a
-- producción (o de CUIT), el sistema podía reutilizar sin darse cuenta un
-- ticket viejo de otro entorno. Ahora se identifica por los tres juntos.

alter table tickets_acceso add column if not exists entorno text;
alter table tickets_acceso add column if not exists cuit text;

-- El/los ticket(s) que ya había quedan sin entorno/cuit asignado: se piden
-- de nuevo la próxima vez (que es lo correcto después de este cambio). No
-- toca ninguna venta ni comprobante existente.
delete from tickets_acceso;

alter table tickets_acceso alter column entorno set not null;
alter table tickets_acceso alter column cuit set not null;

drop index if exists tickets_acceso_servicio_uq;
create unique index tickets_acceso_servicio_entorno_cuit_uq on tickets_acceso (servicio, entorno, cuit);
