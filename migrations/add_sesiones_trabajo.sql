-- =====================================================
-- MIGRACIÓN: Sistema de bloqueo de paquetes concurrente
-- Fecha: 2026-03-13
-- Descripción: Tabla para gestionar sesiones de trabajo activas.
--   Cuando un operario carga un terminal y empieza a trabajar en un
--   carro, se registra una sesión con los paquetes que tiene asignados.
--   Esto impide que otros puestos que compartan esos mismos elementos
--   los procesen a la vez.
-- =====================================================

PRAGMA foreign_keys = ON;

-- Tabla principal de sesiones activas
CREATE TABLE IF NOT EXISTS sesiones_trabajo (
    id TEXT PRIMARY KEY,                          -- UUID generado en Python
    maquina_id TEXT NOT NULL,                     -- Máquina (puesto) que inició la sesión
    terminal_codigo TEXT NOT NULL,                -- Terminal que se está engastando
    archivo_excel TEXT NOT NULL,                  -- Archivo Excel del carro
    carro_numero TEXT,                            -- Número de carro
    paquetes_json TEXT NOT NULL DEFAULT '[]',     -- JSON: [{cod_cable, elemento}, ...]
    timestamp_inicio TEXT NOT NULL DEFAULT (datetime('now')),
    activo INTEGER NOT NULL DEFAULT 1,            -- 1 = activa, 0 = liberada

    FOREIGN KEY (maquina_id) REFERENCES maquinas(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sesiones_maquina
    ON sesiones_trabajo(maquina_id);

CREATE INDEX IF NOT EXISTS idx_sesiones_activas
    ON sesiones_trabajo(activo);

CREATE INDEX IF NOT EXISTS idx_sesiones_terminal
    ON sesiones_trabajo(terminal_codigo);
