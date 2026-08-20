-- =====================================================
-- SCHEMA SQLite - SISTEMA ENGASTADO AUTOMÁTICO
-- =====================================================
-- Versión: 1.0 SQLite
-- Fecha: 2026-02-16
-- Descripción: Base de datos SQLite normalizada (alternativa sin permisos admin)
-- =====================================================

-- SQLite: Habilitar claves foráneas
PRAGMA foreign_keys = ON;

-- SQLite: Habilitar WAL mode para mejor concurrencia
PRAGMA journal_mode = WAL;

-- SQLite: Configuración de performance
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = 10000;
PRAGMA temp_store = MEMORY;

-- =====================================================
-- TABLA: proyectos
-- Descripción: Proyectos cargados desde archivos Excel
-- =====================================================
DROP TABLE IF EXISTS proyectos;

CREATE TABLE proyectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    archivo TEXT NOT NULL,
    fecha_carga TEXT NOT NULL DEFAULT (datetime('now')),
    carro_asignado INTEGER,
    progreso REAL DEFAULT 0.0,
    estado TEXT NOT NULL DEFAULT 'activo',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by TEXT,
    
    CHECK (progreso >= 0 AND progreso <= 100),
    CHECK (estado IN ('activo', 'completado', 'pausado', 'cancelado'))
);

CREATE INDEX idx_proyectos_estado ON proyectos(estado);
CREATE INDEX idx_proyectos_carro ON proyectos(carro_asignado) WHERE carro_asignado IS NOT NULL;

-- =====================================================
-- TABLA: proyectos_terminales_completados
-- =====================================================
DROP TABLE IF EXISTS proyectos_terminales_completados;

CREATE TABLE proyectos_terminales_completados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    terminal_codigo TEXT NOT NULL,
    fecha_completado TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE,
    UNIQUE(proyecto_id, terminal_codigo)
);

CREATE INDEX idx_proyecto_terminal ON proyectos_terminales_completados(proyecto_id, terminal_codigo);

-- =====================================================
-- TABLA: bonos
-- =====================================================
DROP TABLE IF EXISTS bonos;

CREATE TABLE bonos (
    id TEXT PRIMARY KEY, -- UUID generado
    nombre TEXT NOT NULL UNIQUE, -- Nombre del bono (ej: 17022026_1)
    descripcion TEXT, -- Descripción opcional
    fecha_creacion TEXT NOT NULL DEFAULT (datetime('now')),
    estado TEXT NOT NULL DEFAULT 'activo',
    total_ordenes INTEGER DEFAULT 0,
    ordenes_completadas INTEGER DEFAULT 0,
    progreso_general REAL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    CHECK (progreso_general >= 0 AND progreso_general <= 100),
    CHECK (estado IN ('activo', 'completado', 'pausado'))
);

CREATE INDEX idx_bonos_estado ON bonos(estado);
CREATE INDEX idx_bonos_fecha ON bonos(fecha_creacion DESC);

-- =====================================================
-- TABLA: carros
-- =====================================================
DROP TABLE IF EXISTS carros;

CREATE TABLE carros (
    numero INTEGER PRIMARY KEY CHECK (numero BETWEEN 1 AND 6),
    bono_id TEXT,
    estado TEXT NOT NULL DEFAULT 'disponible',
    fecha_inicio TEXT,
    fecha_fin TEXT,
    progreso REAL DEFAULT 0.0,
    ordenes_totales INTEGER DEFAULT 0,
    ordenes_completadas INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (bono_id) REFERENCES bonos(id) ON DELETE SET NULL,
    CHECK (estado IN ('disponible', 'en_proceso', 'completado')),
    CHECK (progreso >= 0 AND progreso <= 100)
);

CREATE INDEX idx_carros_bono ON carros(bono_id) WHERE bono_id IS NOT NULL;
CREATE INDEX idx_carros_estado ON carros(estado);

-- =====================================================
-- TABLA: ordenes_produccion
-- =====================================================
DROP TABLE IF EXISTS ordenes_produccion;

CREATE TABLE ordenes_produccion (
    id TEXT PRIMARY KEY, -- UUID
    codigo_corte TEXT NOT NULL,
    numero TEXT NOT NULL,
    proyecto TEXT,
    descripcion TEXT,
    cantidad INTEGER DEFAULT 1,
    fecha_entrega TEXT,
    prioridad TEXT DEFAULT 'normal',
    estado TEXT NOT NULL DEFAULT 'pendiente',
    archivo_excel TEXT,
    bono_id TEXT,
    carro_numero INTEGER,
    fecha_creacion TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_inicio_bono TEXT,
    fecha_completado TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by TEXT,
    
    FOREIGN KEY (bono_id) REFERENCES bonos(id) ON DELETE SET NULL,
    FOREIGN KEY (carro_numero) REFERENCES carros(numero) ON DELETE SET NULL,
    CHECK (prioridad IN ('baja', 'normal', 'alta', 'urgente')),
    CHECK (estado IN ('pendiente', 'en_bono', 'en_proceso', 'completado', 'cancelado'))
);

CREATE INDEX idx_ordenes_bono ON ordenes_produccion(bono_id) WHERE bono_id IS NOT NULL;
CREATE INDEX idx_ordenes_carro ON ordenes_produccion(carro_numero) WHERE carro_numero IS NOT NULL;
CREATE INDEX idx_ordenes_estado ON ordenes_produccion(estado);
CREATE INDEX idx_ordenes_codigo ON ordenes_produccion(codigo_corte);
CREATE INDEX idx_ordenes_fecha_entrega ON ordenes_produccion(fecha_entrega) WHERE fecha_entrega IS NOT NULL;

-- =====================================================
-- TABLA: codigos_cortes
-- =====================================================
DROP TABLE IF EXISTS codigos_cortes;

CREATE TABLE codigos_cortes (
    codigo TEXT PRIMARY KEY,
    archivo_excel TEXT NOT NULL,
    proyecto_nombre TEXT,
    fecha_carga TEXT NOT NULL DEFAULT (datetime('now')),
    activo INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_codigos_archivo ON codigos_cortes(archivo_excel);
CREATE INDEX idx_codigos_activo ON codigos_cortes(activo) WHERE activo = 1;

-- =====================================================
-- TABLA: puestos
-- =====================================================
DROP TABLE IF EXISTS puestos;

CREATE TABLE puestos (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    activo INTEGER DEFAULT 1,
    -- Boton de la pantalla del carro (1-7) con el que el operario de este
    -- puesto se identifica al llegar. NULL = puesto sin boton asignado.
    boton INTEGER,
    -- UID (hex) de la tarjeta NFC de este puesto: alternativa al boton, el
    -- operario la pasa por el lector del carro. NULL = puesto sin tarjeta.
    tag_uid TEXT,
    -- IP estatica de la PC de este puesto: alternativa a la cookie del
    -- navegador. Si se rellena, cualquier peticion desde esa IP se
    -- identifica automaticamente como este puesto sin necesitar cookie.
    ip_fija TEXT,
    -- Legado: todos los puestos son de engastado. Mangueras y manguitos NO
    -- tienen puestos -- se asignan al PC entero (ver tabla pc_equipos).
    modulo TEXT DEFAULT 'engastado',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_puestos_activo ON puestos(activo) WHERE activo = 1;

-- Un boton solo puede pertenecer a un puesto activo
CREATE UNIQUE INDEX idx_puestos_boton ON puestos(boton)
    WHERE boton IS NOT NULL AND activo = 1;

-- Una tarjeta solo puede pertenecer a un puesto activo
CREATE UNIQUE INDEX idx_puestos_tag ON puestos(tag_uid)
    WHERE tag_uid IS NOT NULL AND activo = 1;

-- Una IP fija solo puede pertenecer a un puesto activo
CREATE UNIQUE INDEX idx_puestos_ip ON puestos(ip_fija)
    WHERE ip_fija IS NOT NULL AND activo = 1;

-- =====================================================
-- EQUIPOS (PCs de planta): a que modulo esta dedicado cada uno
-- =====================================================
-- Cada PC de planta trabaja en UN modulo. El modulo es del EQUIPO, no un
-- puesto: engastado necesita ademas saber que puesto es, mientras que
-- mangueras y manguitos entran directos (no tienen puestos).
-- La red de planta usa IPs fijas (sin DHCP), asi que la IP identifica al
-- equipo mejor que una cookie: sobrevive a borrar la cache del navegador.
-- Se rellena sola al configurar el equipo en /puesto/seleccionar.
CREATE TABLE pc_equipos (
    ip         TEXT PRIMARY KEY,
    -- 'engastado' | 'mangueras' | 'manguitos'
    modulo     TEXT NOT NULL DEFAULT 'engastado',
    -- Solo para engastado; NULL en mangueras y manguitos
    puesto_id  TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =====================================================
-- TABLA: maquinas
-- =====================================================
DROP TABLE IF EXISTS maquinas;

CREATE TABLE maquinas (
    id TEXT PRIMARY KEY,
    puesto_id TEXT NOT NULL,
    nombre TEXT NOT NULL,
    modelo TEXT,
    descripcion TEXT,
    activo INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (puesto_id) REFERENCES puestos(id) ON DELETE CASCADE
);

CREATE INDEX idx_maquinas_puesto ON maquinas(puesto_id);
CREATE INDEX idx_maquinas_activo ON maquinas(activo) WHERE activo = 1;

-- =====================================================
-- TABLA: maquinas_terminales
-- =====================================================
DROP TABLE IF EXISTS maquinas_terminales;

CREATE TABLE maquinas_terminales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maquina_id TEXT NOT NULL,
    terminal_codigo TEXT NOT NULL,
    activo INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id) ON DELETE CASCADE,
    UNIQUE(maquina_id, terminal_codigo)
);

CREATE INDEX idx_maquina_terminal ON maquinas_terminales(maquina_id, terminal_codigo);
CREATE INDEX idx_terminal_codigo ON maquinas_terminales(terminal_codigo);

-- =====================================================
-- TABLA: cable_colores (paleta de colores por código de cable)
-- Los valores iniciales se cargan desde seed_inicial.json
-- =====================================================
CREATE TABLE IF NOT EXISTS cable_colores (
    cod_cable TEXT PRIMARY KEY,
    color_hex TEXT NOT NULL,
    color_texto TEXT
);

-- =====================================================
-- TABLA: terminales_imagenes (foto/icono de cada terminal)
-- =====================================================
CREATE TABLE IF NOT EXISTS terminales_imagenes (
    terminal_codigo TEXT PRIMARY KEY,
    imagen_data     TEXT NOT NULL,        -- data URL base64
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =====================================================
-- TABLA: terminales_gavetas (ubicación física del terminal)
-- =====================================================
-- 'gaveta' es la etiqueta que lee el operario ('Estante 3-B'); 'led' es el
-- numero de gaveta en el pick-to-light del puesto (1..N, ver
-- esp32/HARDWARE_PICK_TO_LIGHT.md). NULL = gaveta sin luz: la app sigue
-- funcionando, solo que sin encender nada.
CREATE TABLE IF NOT EXISTS terminales_gavetas (
    terminal_codigo TEXT PRIMARY KEY,
    gaveta          TEXT NOT NULL,
    led             INTEGER,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =====================================================
-- TABLA: terminales_stock (kanban de stock)
-- =====================================================
-- Stock actual y minimo de cada terminal, tecleados a mano desde el kanban.
-- Tiene que estar aqui y no solo en las automigraciones: data/config_inicial.sql
-- puede traer INSERTs de esta tabla, y se aplica justo despues de este schema.
CREATE TABLE IF NOT EXISTS terminales_stock (
    terminal_codigo TEXT PRIMARY KEY,
    stock_actual    INTEGER NOT NULL DEFAULT 0,
    stock_minimo    INTEGER NOT NULL DEFAULT 0,
    notas           TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =====================================================
-- TABLA: esp32_ips (IP fija de cada placa ESP32)
-- =====================================================
-- La red de planta (192.168.50.0/24) no tiene DHCP: cada placa lleva su IP
-- grabada en el firmware. Aqui se lleva el registro de que IP tiene cada una,
-- para no repetirlas y poder reflashear sin recordarlas de memoria.
--   device_id = MAC del chip (binascii.hexlify(machine.unique_id())), el mismo
--               identificador que la placa manda en /api/esp32/*.
--   tipo      = 'display' (pantalla de carro) | 'rfid' (lector de puesto).
-- La mascara (255.255.255.0) y la puerta de enlace (192.168.50.5, el
-- TL-WR802N) son fijas para toda la instalacion y no se guardan por placa.
CREATE TABLE IF NOT EXISTS esp32_ips (
    device_id  TEXT PRIMARY KEY,
    tipo       TEXT NOT NULL DEFAULT 'display',
    nombre     TEXT,
    ip         TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_esp32_ips_ip ON esp32_ips(ip);

-- =====================================================
-- TABLA: terminales_desactivados
-- =====================================================
DROP TABLE IF EXISTS terminales_desactivados;

CREATE TABLE terminales_desactivados (
    terminal_codigo TEXT PRIMARY KEY,
    fecha_desactivacion TEXT NOT NULL DEFAULT (datetime('now')),
    motivo TEXT,
    desactivado_por TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_terminales_fecha ON terminales_desactivados(fecha_desactivacion DESC);

-- =====================================================
-- TABLA: grupos_etiquetas
-- =====================================================
DROP TABLE IF EXISTS grupos_etiquetas;

CREATE TABLE grupos_etiquetas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_grupo INTEGER NOT NULL,
    proyecto_nombre TEXT NOT NULL,
    tipo_etiqueta TEXT NOT NULL,
    cantidad INTEGER NOT NULL,
    bono_id TEXT,
    carros_str TEXT, -- "1,2,3"
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    contenido_zpl TEXT,
    
    FOREIGN KEY (bono_id) REFERENCES bonos(id) ON DELETE SET NULL,
    CHECK (tipo_etiqueta IN ('asignacion', 'asignacion_duplicado', 'reimpresion'))
);

CREATE INDEX idx_grupos_bono ON grupos_etiquetas(bono_id) WHERE bono_id IS NOT NULL;
CREATE INDEX idx_grupos_timestamp ON grupos_etiquetas(timestamp DESC);
CREATE INDEX idx_grupos_numero ON grupos_etiquetas(numero_grupo);

-- =====================================================
-- TABLA: etiquetas_elementos
-- Descripción: Grupos de etiquetas por código de cable + elemento
-- (Reemplaza el archivo grupos_etiquetas.json)
-- =====================================================
DROP TABLE IF EXISTS etiquetas_elementos;

CREATE TABLE etiquetas_elementos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archivo_excel TEXT NOT NULL,
    codigo_corte TEXT,
    orden_id TEXT,
    numero_etiqueta INTEGER NOT NULL,
    sub_numero INTEGER NOT NULL DEFAULT 0,
    es_grupo_padre INTEGER NOT NULL DEFAULT 0,
    grupo_serie TEXT,
    cod_cable TEXT NOT NULL,
    elemento TEXT NOT NULL,
    descripcion TEXT,
    seccion TEXT,
    longitud REAL,
    de_terminal TEXT,
    num_cables INTEGER DEFAULT 0,
    num_terminales INTEGER DEFAULT 0,
    fecha_generacion TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (orden_id) REFERENCES ordenes_produccion(id) ON DELETE CASCADE,
    UNIQUE(archivo_excel, numero_etiqueta, sub_numero)
);

CREATE INDEX idx_etiquetas_archivo ON etiquetas_elementos(archivo_excel);
CREATE INDEX idx_etiquetas_codigo ON etiquetas_elementos(codigo_corte);
CREATE INDEX idx_etiquetas_orden ON etiquetas_elementos(orden_id);
CREATE INDEX idx_etiquetas_numero ON etiquetas_elementos(numero_etiqueta);
CREATE INDEX idx_etiquetas_cable_elemento ON etiquetas_elementos(cod_cable, elemento);

-- =====================================================
-- TABLA: etiquetas_pendientes
-- =====================================================
DROP TABLE IF EXISTS etiquetas_pendientes;

CREATE TABLE etiquetas_pendientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contenido_zpl TEXT NOT NULL,
    tipo TEXT NOT NULL,
    proyecto TEXT,
    carros_str TEXT,
    intentos INTEGER DEFAULT 0,
    max_intentos INTEGER DEFAULT 3,
    ultimo_error TEXT,
    fecha_creacion TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_ultimo_intento TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    CHECK (tipo IN ('asignacion', 'reimpresion', 'manual', 'otro'))
);

CREATE INDEX idx_etiquetas_fecha ON etiquetas_pendientes(fecha_creacion DESC);
CREATE INDEX idx_etiquetas_intentos ON etiquetas_pendientes(intentos) WHERE intentos < 3;

-- =====================================================
-- TABLA: app_state
-- =====================================================
DROP TABLE IF EXISTS app_state;

CREATE TABLE app_state (
    clave TEXT PRIMARY KEY,
    valor TEXT,
    tipo_dato TEXT DEFAULT 'string', -- string, json, int, date
    descripcion TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Insertar valores iniciales
INSERT INTO app_state (clave, valor, tipo_dato, descripcion) VALUES
    ('last_loaded_file', NULL, 'string', 'Último archivo Excel cargado'),
    ('last_loaded_timestamp', NULL, 'date', 'Timestamp del último Excel cargado'),
    ('siguiente_numero_grupo_etiqueta', '1', 'int', 'Contador para grupos de etiquetas'),
    ('sistema_version', '2.0-SQLite', 'string', 'Versión actual del sistema');

-- =====================================================
-- TRIGGERS para updated_at automático
-- =====================================================

-- Trigger proyectos
DROP TRIGGER IF EXISTS trg_proyectos_updated_at;
CREATE TRIGGER trg_proyectos_updated_at
AFTER UPDATE ON proyectos
FOR EACH ROW
BEGIN
    UPDATE proyectos SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Trigger bonos
DROP TRIGGER IF EXISTS trg_bonos_updated_at;
CREATE TRIGGER trg_bonos_updated_at
AFTER UPDATE ON bonos
FOR EACH ROW
BEGIN
    UPDATE bonos SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Trigger carros
DROP TRIGGER IF EXISTS trg_carros_updated_at;
CREATE TRIGGER trg_carros_updated_at
AFTER UPDATE ON carros
FOR EACH ROW
BEGIN
    UPDATE carros SET updated_at = datetime('now') WHERE numero = NEW.numero;
END;

-- Trigger ordenes
DROP TRIGGER IF EXISTS trg_ordenes_updated_at;
CREATE TRIGGER trg_ordenes_updated_at
AFTER UPDATE ON ordenes_produccion
FOR EACH ROW
BEGIN
    UPDATE ordenes_produccion SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- =====================================================
-- VISTAS útiles
-- =====================================================

-- Vista: resumen de bonos con sus carros
DROP VIEW IF EXISTS vw_bonos_con_carros;
CREATE VIEW vw_bonos_con_carros AS
SELECT 
    b.id AS bono_id,
    b.estado,
    b.fecha_creacion,
    b.total_ordenes,
    b.ordenes_completadas,
    b.progreso_general,
    COUNT(c.numero) AS total_carros,
    GROUP_CONCAT(c.numero) AS carros_asignados
FROM bonos b
LEFT JOIN carros c ON c.bono_id = b.id
GROUP BY b.id;

-- Vista: órdenes agrupadas por bono
DROP VIEW IF EXISTS vw_ordenes_por_bono;
CREATE VIEW vw_ordenes_por_bono AS
SELECT 
    bono_id,
    COUNT(*) AS total_ordenes,
    SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) AS ordenes_completadas,
    SUM(CASE WHEN estado IN ('en_proceso', 'en_bono') THEN 1 ELSE 0 END) AS ordenes_en_proceso,
    SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) AS ordenes_pendientes
FROM ordenes_produccion
WHERE bono_id IS NOT NULL
GROUP BY bono_id;

-- =====================================================
-- FIN DEL SCRIPT
-- =====================================================
SELECT 'Schema SQLite creado exitosamente' AS mensaje;
SELECT 'Tablas: proyectos, bonos, carros, ordenes_produccion, codigos_cortes, puestos, maquinas, etc.' AS info;
SELECT 'Vistas: vw_bonos_con_carros, vw_ordenes_por_bono' AS vistas;
SELECT 'WAL mode habilitado para concurrencia' AS concurrencia;
SELECT 'Siguiente paso: python run_sql.py para iniciar aplicación' AS proximo_paso;
