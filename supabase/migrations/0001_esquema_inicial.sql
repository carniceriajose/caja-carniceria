    -- Esquema inicial de la carnicería.
    -- Montos siempre en numeric (nunca float) para que la plata sea exacta.
    -- Fechas en timestamptz; los "días" se calculan en hora de Argentina.

    -- ---------------------------------------------------------------
    -- usuarios: quién entra al sistema
    -- ---------------------------------------------------------------
    create table usuarios (
        id            bigint generated always as identity primary key,
        nombre        text        not null,
        usuario       text        not null,
        password_hash text        not null,          -- nunca la contraseña en claro
        rol           text        not null,
        activo        boolean     not null default true,   -- no se borran, se desactivan
        -- Se incrementa al cambiar contraseña, rol o desactivar: invalida los tokens ya emitidos.
        token_version integer     not null default 0,
        creado_en     timestamptz not null default now(),

        constraint usuarios_rol_check          check (rol in ('vendedor', 'admin')),
        constraint usuarios_usuario_minusculas check (usuario = lower(usuario))
    );
    create unique index usuarios_usuario_uq on usuarios (lower(usuario));

    -- ---------------------------------------------------------------
    -- ventas: una fila por venta. Se guardan TODAS, también las de efectivo.
    -- Qué medio se factura lo decide el backend según la configuración.
    -- ---------------------------------------------------------------
    create table ventas (
        id                 bigint generated always as identity primary key,
        -- Lo genera el frontend al empezar la venta: si el pedido se repite (doble clic,
        -- reintento por mala conexión) no se crea una segunda venta.
        id_cliente         uuid          not null,
        fecha_hora         timestamptz   not null default now(),
        total              numeric(12,2) not null check (total > 0),
        medio_pago         text          not null
                        check (medio_pago in ('efectivo', 'tarjeta', 'transferencia')),
        vendedor_id        bigint        not null references usuarios (id),

        -- Datos fiscales (controlador fiscal o web service, según cómo se termine emitiendo)
        estado_arca        text          not null default 'no_aplica'
                        check (estado_arca in ('no_aplica', 'pendiente', 'facturada', 'fallo')),
        tipo_comprobante   text,
        punto_venta        integer,
        numero_comprobante bigint,
        cae                text,          -- opcional: el controlador fiscal puede no devolverlo
        cae_vencimiento    date,
        error_detalle      text,          -- motivo cuando estado_arca = 'fallo'
        respuesta_fiscal   jsonb,         -- todo lo que devolvió el equipo o ARCA, también si falló

        -- Una venta facturada tiene que traer al menos su número de comprobante.
        constraint ventas_facturada_completa check (
            estado_arca <> 'facturada' or numero_comprobante is not null
        ),
        -- Una venta que falló tiene que decir por qué.
        constraint ventas_fallo_con_detalle check (
            estado_arca <> 'fallo' or error_detalle is not null
        )
    );
    create unique index ventas_id_cliente_uq on ventas (id_cliente);
    create index ventas_fecha_hora_idx on ventas (fecha_hora);
    create index ventas_medio_pago_idx on ventas (medio_pago, fecha_hora);
    create index ventas_estado_idx     on ventas (estado_arca) where estado_arca in ('pendiente', 'fallo');
    create index ventas_vendedor_idx   on ventas (vendedor_id);

    -- ---------------------------------------------------------------
    -- categorias_gasto: las crea el admin libremente
    -- ---------------------------------------------------------------
    create table categorias_gasto (
        id        bigint generated always as identity primary key,
        nombre    text        not null,
        creado_en timestamptz not null default now()
    );
    create unique index categorias_gasto_nombre_uq on categorias_gasto (lower(nombre));

    -- ---------------------------------------------------------------
    -- gastos: los carga el admin
    -- ---------------------------------------------------------------
    create table gastos (
        id           bigint generated always as identity primary key,
        fecha        date          not null
                    default (now() at time zone 'America/Argentina/Buenos_Aires')::date,
        monto        numeric(12,2) not null check (monto > 0),
        categoria_id bigint        not null references categorias_gasto (id),
        descripcion  text,
        creado_por   bigint        not null references usuarios (id),
        creado_en    timestamptz   not null default now()
    );
    create index gastos_fecha_idx     on gastos (fecha);
    create index gastos_categoria_idx on gastos (categoria_id, fecha);

    -- ---------------------------------------------------------------
    -- tickets_acceso: token + sign de WSAA (ARCA). Se guarda en la base y no
    -- solo en memoria porque el servidor se reinicia. Un registro por servicio.
    -- ---------------------------------------------------------------
    create table tickets_acceso (
        id          bigint generated always as identity primary key,
        servicio    text        not null,
        token       text        not null,
        sign        text        not null,
        generado_en timestamptz not null default now(),
        vence_en    timestamptz not null
    );
    create unique index tickets_acceso_servicio_uq on tickets_acceso (servicio);

    -- ---------------------------------------------------------------
    -- configuracion: una sola fila con qué medios de pago se facturan
    -- ---------------------------------------------------------------
    create table configuracion (
        id                     smallint primary key default 1,
        facturar_efectivo      boolean not null default false,
        facturar_tarjeta       boolean not null default true,
        facturar_transferencia boolean not null default true,

        constraint configuracion_una_sola_fila check (id = 1)
    );
    insert into configuracion (id) values (1);

    -- ---------------------------------------------------------------
    -- Seguridad: RLS activado y sin políticas, y sin permisos para los roles
    -- públicos. Solo el backend (FastAPI) accede, con la service key.
    -- ---------------------------------------------------------------
    alter table usuarios         enable row level security;
    alter table ventas           enable row level security;
    alter table categorias_gasto enable row level security;
    alter table gastos           enable row level security;
    alter table configuracion    enable row level security;
    alter table tickets_acceso   enable row level security;

    revoke all on usuarios, ventas, categorias_gasto, gastos, configuracion, tickets_acceso from anon, authenticated;
