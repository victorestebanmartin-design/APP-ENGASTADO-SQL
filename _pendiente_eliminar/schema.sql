-- =====================================================
-- SCHEMA SQL SERVER - SISTEMA ENGASTADO AUTOMÁTICO
-- =====================================================
-- Versión: 1.0
-- Fecha: 2026-02-16
-- Descripción: Base de datos normalizada para reemplazar persistencia JSON
-- =====================================================

USE master;
GO

-- Crear base de datos si no existe
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'EngastadoDB')
BEGIN
    CREATE DATABASE EngastadoDB;
END
GO

USE EngastadoDB;
GO

-- =====================================================
-- TABLA: proyectos
-- Descripción: Proyectos cargados desde archivos Excel
-- =====================================================
IF OBJECT_ID('dbo.proyectos', 'U') IS NOT NULL DROP TABLE dbo.proyectos;
GO

CREATE TABLE dbo.proyectos (
    id INT PRIMARY KEY IDENTITY(1,1),
    nombre NVARCHAR(200) NOT NULL,
    archivo NVARCHAR(500) NOT NULL,
    fecha_carga DATETIME2 NOT NULL DEFAULT GETDATE(),
    carro_asignado INT NULL,
    progreso DECIMAL(5,2) DEFAULT 0.0,
    estado NVARCHAR(50) NOT NULL DEFAULT 'activo',
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_by NVARCHAR(100) NULL,
    
    CONSTRAINT chk_proyectos_progreso CHECK (progreso >= 0 AND progreso <= 100),
    CONSTRAINT chk_proyectos_estado CHECK (estado IN ('activo', 'completado', 'pausado', 'cancelado'))
);
GO

CREATE INDEX idx_proyectos_estado ON dbo.proyectos(estado);
CREATE INDEX idx_proyectos_carro ON dbo.proyectos(carro_asignado) WHERE carro_asignado IS NOT NULL;
GO

-- =====================================================
-- TABLA: proyectos_terminales_completados
-- Descripción: Terminales completados por proyecto (antes era array JSON)
-- =====================================================
IF OBJECT_ID('dbo.proyectos_terminales_completados', 'U') IS NOT NULL DROP TABLE dbo.proyectos_terminales_completados;
GO

CREATE TABLE dbo.proyectos_terminales_completados (
    id INT PRIMARY KEY IDENTITY(1,1),
    proyecto_id INT NOT NULL,
    terminal_codigo NVARCHAR(100) NOT NULL,
    fecha_completado DATETIME2 NOT NULL DEFAULT GETDATE(),
    
    CONSTRAINT fk_terminales_proyecto FOREIGN KEY (proyecto_id) REFERENCES dbo.proyectos(id) ON DELETE CASCADE
);
GO

CREATE UNIQUE INDEX idx_proyecto_terminal ON dbo.proyectos_terminales_completados(proyecto_id, terminal_codigo);
GO

-- =====================================================
-- TABLA: bonos
-- Descripción: Bonos de producción (antes en proyectos_carros.json)
-- =====================================================
IF OBJECT_ID('dbo.bonos', 'U') IS NOT NULL DROP TABLE dbo.bonos;
GO

CREATE TABLE dbo.bonos (
    id NVARCHAR(50) PRIMARY KEY, -- Formato: 20251222_2
    fecha_creacion DATETIME2 NOT NULL DEFAULT GETDATE(),
    estado NVARCHAR(50) NOT NULL DEFAULT 'activo',
    total_ordenes INT DEFAULT 0,
    ordenes_completadas INT DEFAULT 0,
    progreso_general DECIMAL(5,2) DEFAULT 0.0,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    
    CONSTRAINT chk_bonos_progreso CHECK (progreso_general >= 0 AND progreso_general <= 100),
    CONSTRAINT chk_bonos_estado CHECK (estado IN ('activo', 'completado', 'pausado'))
);
GO

CREATE INDEX idx_bonos_estado ON dbo.bonos(estado);
CREATE INDEX idx_bonos_fecha ON dbo.bonos(fecha_creacion DESC);
GO

-- =====================================================
-- TABLA: carros
-- Descripción: Carros de producción (antes solo en memoria/JSON)
-- =====================================================
IF OBJECT_ID('dbo.carros', 'U') IS NOT NULL DROP TABLE dbo.carros;
GO

CREATE TABLE dbo.carros (
    numero INT PRIMARY KEY CHECK (numero BETWEEN 1 AND 6),
    bono_id NVARCHAR(50) NULL,
    estado NVARCHAR(50) NOT NULL DEFAULT 'disponible',
    fecha_inicio DATETIME2 NULL,
    fecha_fin DATETIME2 NULL,
    progreso DECIMAL(5,2) DEFAULT 0.0,
    ordenes_totales INT DEFAULT 0,
    ordenes_completadas INT DEFAULT 0,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    
    CONSTRAINT fk_carro_bono FOREIGN KEY (bono_id) REFERENCES dbo.bonos(id) ON DELETE SET NULL,
    CONSTRAINT chk_carros_estado CHECK (estado IN ('disponible', 'en_proceso', 'completado')),
    CONSTRAINT chk_carros_progreso CHECK (progreso >= 0 AND progreso <= 100)
);
GO

CREATE INDEX idx_carros_bono ON dbo.carros(bono_id) WHERE bono_id IS NOT NULL;
CREATE INDEX idx_carros_estado ON dbo.carros(estado);
GO

-- =====================================================
-- TABLA: ordenes_produccion
-- Descripción: Órdenes de producción escaneadas
-- =====================================================
IF OBJECT_ID('dbo.ordenes_produccion', 'U') IS NOT NULL DROP TABLE dbo.ordenes_produccion;
GO

CREATE TABLE dbo.ordenes_produccion (
    id NVARCHAR(50) PRIMARY KEY, -- UUID
    codigo_corte NVARCHAR(100) NOT NULL,
    numero NVARCHAR(100) NOT NULL,
    proyecto NVARCHAR(200) NULL,
    descripcion NVARCHAR(500) NULL,
    cantidad INT DEFAULT 1,
    fecha_entrega DATE NULL,
    prioridad NVARCHAR(50) DEFAULT 'normal',
    estado NVARCHAR(50) NOT NULL DEFAULT 'pendiente',
    archivo_excel NVARCHAR(500) NULL,
    bono_id NVARCHAR(50) NULL,
    carro_numero INT NULL,
    fecha_creacion DATETIME2 NOT NULL DEFAULT GETDATE(),
    fecha_inicio_bono DATETIME2 NULL,
    fecha_completado DATETIME2 NULL,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_by NVARCHAR(100) NULL,
    
    CONSTRAINT fk_orden_bono FOREIGN KEY (bono_id) REFERENCES dbo.bonos(id) ON DELETE SET NULL,
    CONSTRAINT fk_orden_carro FOREIGN KEY (carro_numero) REFERENCES dbo.carros(numero) ON DELETE SET NULL,
    CONSTRAINT chk_ordenes_prioridad CHECK (prioridad IN ('baja', 'normal', 'alta', 'urgente')),
    CONSTRAINT chk_ordenes_estado CHECK (estado IN ('pendiente', 'en_bono', 'en_proceso', 'completado', 'cancelado'))
);
GO

CREATE INDEX idx_ordenes_bono ON dbo.ordenes_produccion(bono_id) WHERE bono_id IS NOT NULL;
CREATE INDEX idx_ordenes_carro ON dbo.ordenes_produccion(carro_numero) WHERE carro_numero IS NOT NULL;
CREATE INDEX idx_ordenes_estado ON dbo.ordenes_produccion(estado);
CREATE INDEX idx_ordenes_codigo ON dbo.ordenes_produccion(codigo_corte);
CREATE INDEX idx_ordenes_fecha_entrega ON dbo.ordenes_produccion(fecha_entrega) WHERE fecha_entrega IS NOT NULL;
GO

-- =====================================================
-- TABLA: codigos_cortes
-- Descripción: Mapeo de códigos de barras a archivos Excel
-- =====================================================
IF OBJECT_ID('dbo.codigos_cortes', 'U') IS NOT NULL DROP TABLE dbo.codigos_cortes;
GO

CREATE TABLE dbo.codigos_cortes (
    codigo NVARCHAR(100) PRIMARY KEY,
    archivo_excel NVARCHAR(500) NOT NULL,
    proyecto_nombre NVARCHAR(200) NULL,
    fecha_carga DATETIME2 NOT NULL DEFAULT GETDATE(),
    activo BIT DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE()
);
GO

CREATE INDEX idx_codigos_archivo ON dbo.codigos_cortes(archivo_excel);
CREATE INDEX idx_codigos_activo ON dbo.codigos_cortes(activo) WHERE activo = 1;
GO

-- =====================================================
-- TABLA: puestos
-- Descripción: Puestos de trabajo en planta
-- =====================================================
IF OBJECT_ID('dbo.puestos', 'U') IS NOT NULL DROP TABLE dbo.puestos;
GO

CREATE TABLE dbo.puestos (
    id NVARCHAR(50) PRIMARY KEY,
    nombre NVARCHAR(200) NOT NULL,
    descripcion NVARCHAR(500) NULL,
    activo BIT DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE()
);
GO

CREATE INDEX idx_puestos_activo ON dbo.puestos(activo) WHERE activo = 1;
GO

-- =====================================================
-- TABLA: maquinas
-- Descripción: Máquinas dentro de cada puesto
-- =====================================================
IF OBJECT_ID('dbo.maquinas', 'U') IS NOT NULL DROP TABLE dbo.maquinas;
GO

CREATE TABLE dbo.maquinas (
    id NVARCHAR(50) PRIMARY KEY,
    puesto_id NVARCHAR(50) NOT NULL,
    nombre NVARCHAR(200) NOT NULL,
    modelo NVARCHAR(200) NULL,
    descripcion NVARCHAR(500) NULL,
    activo BIT DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    
    CONSTRAINT fk_maquina_puesto FOREIGN KEY (puesto_id) REFERENCES dbo.puestos(id) ON DELETE CASCADE
);
GO

CREATE INDEX idx_maquinas_puesto ON dbo.maquinas(puesto_id);
CREATE INDEX idx_maquinas_activo ON dbo.maquinas(activo) WHERE activo = 1;
GO

-- =====================================================
-- TABLA: maquinas_terminales
-- Descripción: Terminales asignados a cada máquina (antes array JSON)
-- =====================================================
IF OBJECT_ID('dbo.maquinas_terminales', 'U') IS NOT NULL DROP TABLE dbo.maquinas_terminales;
GO

CREATE TABLE dbo.maquinas_terminales (
    id INT PRIMARY KEY IDENTITY(1,1),
    maquina_id NVARCHAR(50) NOT NULL,
    terminal_codigo NVARCHAR(100) NOT NULL,
    activo BIT DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    
    CONSTRAINT fk_terminal_maquina FOREIGN KEY (maquina_id) REFERENCES dbo.maquinas(id) ON DELETE CASCADE
);
GO

CREATE UNIQUE INDEX idx_maquina_terminal ON dbo.maquinas_terminales(maquina_id, terminal_codigo);
CREATE INDEX idx_terminal_codigo ON dbo.maquinas_terminales(terminal_codigo);
GO

-- =====================================================
-- TABLA: terminales_desactivados
-- Descripción: Lista de terminales desactivados temporalmente
-- =====================================================
IF OBJECT_ID('dbo.terminales_desactivados', 'U') IS NOT NULL DROP TABLE dbo.terminales_desactivados;
GO

CREATE TABLE dbo.terminales_desactivados (
    terminal_codigo NVARCHAR(100) PRIMARY KEY,
    fecha_desactivacion DATETIME2 NOT NULL DEFAULT GETDATE(),
    motivo NVARCHAR(500) NULL,
    desactivado_por NVARCHAR(100) NULL,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE()
);
GO

CREATE INDEX idx_terminales_fecha ON dbo.terminales_desactivados(fecha_desactivacion DESC);
GO

-- =====================================================
-- TABLA: grupos_etiquetas
-- Descripción: Grupos de etiquetas generadas (antes grupos_etiquetas.json)
-- =====================================================
IF OBJECT_ID('dbo.grupos_etiquetas', 'U') IS NOT NULL DROP TABLE dbo.grupos_etiquetas;
GO

CREATE TABLE dbo.grupos_etiquetas (
    id INT PRIMARY KEY IDENTITY(1,1),
    numero_grupo INT NOT NULL,
    proyecto_nombre NVARCHAR(200) NOT NULL,
    tipo_etiqueta NVARCHAR(50) NOT NULL,
    cantidad INT NOT NULL,
    bono_id NVARCHAR(50) NULL,
    carros_str NVARCHAR(100) NULL, -- "1,2,3" para múltiples carros
    timestamp DATETIME2 NOT NULL DEFAULT GETDATE(),
    contenido_zpl NVARCHAR(MAX) NULL,
    
    CONSTRAINT fk_grupo_bono FOREIGN KEY (bono_id) REFERENCES dbo.bonos(id) ON DELETE SET NULL,
    CONSTRAINT chk_grupos_tipo CHECK (tipo_etiqueta IN ('asignacion', 'asignacion_duplicado', 'reimpresion'))
);
GO

CREATE INDEX idx_grupos_bono ON dbo.grupos_etiquetas(bono_id) WHERE bono_id IS NOT NULL;
CREATE INDEX idx_grupos_timestamp ON dbo.grupos_etiquetas(timestamp DESC);
CREATE INDEX idx_grupos_numero ON dbo.grupos_etiquetas(numero_grupo);
GO

-- =====================================================
-- TABLA: etiquetas_pendientes
-- Descripción: Cola de etiquetas pendientes de impresión
-- =====================================================
IF OBJECT_ID('dbo.etiquetas_pendientes', 'U') IS NOT NULL DROP TABLE dbo.etiquetas_pendientes;
GO

CREATE TABLE dbo.etiquetas_pendientes (
    id INT PRIMARY KEY IDENTITY(1,1),
    contenido_zpl NVARCHAR(MAX) NOT NULL,
    tipo NVARCHAR(50) NOT NULL,
    proyecto NVARCHAR(200) NULL,
    carros_str NVARCHAR(100) NULL,
    intentos INT DEFAULT 0,
    max_intentos INT DEFAULT 3,
    ultimo_error NVARCHAR(MAX) NULL,
    fecha_creacion DATETIME2 NOT NULL DEFAULT GETDATE(),
    fecha_ultimo_intento DATETIME2 NULL,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    
    CONSTRAINT chk_etiquetas_tipo CHECK (tipo IN ('asignacion', 'reimpresion', 'manual', 'otro'))
);
GO

CREATE INDEX idx_etiquetas_fecha ON dbo.etiquetas_pendientes(fecha_creacion DESC);
CREATE INDEX idx_etiquetas_intentos ON dbo.etiquetas_pendientes(intentos) WHERE intentos < 3;
GO

-- =====================================================
-- TABLA: app_state
-- Descripción: Estado de la aplicación (last_loaded.json, config runtime)
-- =====================================================
IF OBJECT_ID('dbo.app_state', 'U') IS NOT NULL DROP TABLE dbo.app_state;
GO

CREATE TABLE dbo.app_state (
    clave NVARCHAR(100) PRIMARY KEY,
    valor NVARCHAR(MAX) NULL,
    tipo_dato NVARCHAR(50) DEFAULT 'string', -- string, json, int, date
    descripcion NVARCHAR(500) NULL,
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE()
);
GO

-- Insertar valores iniciales
INSERT INTO dbo.app_state (clave, valor, tipo_dato, descripcion)
VALUES 
    ('last_loaded_file', NULL, 'string', 'Último archivo Excel cargado'),
    ('last_loaded_timestamp', NULL, 'date', 'Timestamp del último Excel cargado'),
    ('siguiente_numero_grupo_etiqueta', '1', 'int', 'Contador para grupos de etiquetas'),
    ('sistema_version', '2.0-SQL', 'string', 'Versión actual del sistema');
GO

-- =====================================================
-- TRIGGERS para updated_at automático
-- =====================================================

-- Trigger proyectos
GO
CREATE OR ALTER TRIGGER trg_proyectos_updated_at
ON dbo.proyectos
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.proyectos
    SET updated_at = GETDATE()
    FROM dbo.proyectos p
    INNER JOIN inserted i ON p.id = i.id;
END;
GO

-- Trigger bonos
CREATE OR ALTER TRIGGER trg_bonos_updated_at
ON dbo.bonos
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.bonos
    SET updated_at = GETDATE()
    FROM dbo.bonos b
    INNER JOIN inserted i ON b.id = i.id;
END;
GO

-- Trigger carros
CREATE OR ALTER TRIGGER trg_carros_updated_at
ON dbo.carros
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.carros
    SET updated_at = GETDATE()
    FROM dbo.carros c
    INNER JOIN inserted i ON c.numero = i.numero;
END;
GO

-- Trigger ordenes_produccion
CREATE OR ALTER TRIGGER trg_ordenes_updated_at
ON dbo.ordenes_produccion
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.ordenes_produccion
    SET updated_at = GETDATE()
    FROM dbo.ordenes_produccion o
    INNER JOIN inserted i ON o.id = i.id;
END;
GO

-- =====================================================
-- VISTAS útiles
-- =====================================================

-- Vista: resumen de bonos con sus carros
GO
CREATE OR ALTER VIEW vw_bonos_con_carros AS
SELECT 
    b.id AS bono_id,
    b.estado,
    b.fecha_creacion,
    b.total_ordenes,
    b.ordenes_completadas,
    b.progreso_general,
    COUNT(c.numero) AS total_carros,
    STRING_AGG(CAST(c.numero AS VARCHAR), ',') AS carros_asignados
FROM dbo.bonos b
LEFT JOIN dbo.carros c ON c.bono_id = b.id
GROUP BY b.id, b.estado, b.fecha_creacion, b.total_ordenes, b.ordenes_completadas, b.progreso_general;
GO

-- Vista: órdenes agrupadas por bono
CREATE OR ALTER VIEW vw_ordenes_por_bono AS
SELECT 
    bono_id,
    COUNT(*) AS total_ordenes,
    SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) AS ordenes_completadas,
    SUM(CASE WHEN estado IN ('en_proceso', 'en_bono') THEN 1 ELSE 0 END) AS ordenes_en_proceso,
    SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) AS ordenes_pendientes
FROM dbo.ordenes_produccion
WHERE bono_id IS NOT NULL
GROUP BY bono_id;
GO

-- =====================================================
-- PERMISOS (ajustar según usuario de aplicación)
-- =====================================================
-- NOTA: Crear usuario específico para la aplicación
-- CREATE LOGIN app_engastado WITH PASSWORD = 'TuPasswordSeguro123!';
-- CREATE USER app_engastado FOR LOGIN app_engastado;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO app_engastado;
-- GO

-- =====================================================
-- FIN DEL SCRIPT
-- =====================================================
PRINT 'Schema creado exitosamente';
PRINT 'Tablas: proyectos, bonos, carros, ordenes_produccion, codigos_cortes, puestos, maquinas, etc.';
PRINT 'Vistas: vw_bonos_con_carros, vw_ordenes_por_bono';
PRINT 'Siguiente paso: Ejecutar migrate_json_to_sql.py para importar datos existentes';
GO
