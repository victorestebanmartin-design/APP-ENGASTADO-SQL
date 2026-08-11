-- =====================================================
-- MIGRACIÓN: Login exclusivo de operarios
-- Fecha: 2026-08-11
-- Descripción: Tabla para registrar qué operarios están
--   dentro del módulo de engastado en cada momento.
--   Al elegir operario al principio del módulo se crea un
--   login; mientras ese login esté activo, ningún otro
--   puesto puede entrar con el mismo operario.
--   El navegador manda un "latido" periódico; los logins
--   sin latido reciente se expiran automáticamente
--   (protege frente a cierres bruscos del navegador).
-- =====================================================

CREATE TABLE IF NOT EXISTS operario_logins (
    id TEXT PRIMARY KEY,                              -- UUID generado en Python
    operario_nombre TEXT NOT NULL,                    -- Nombre del operario logeado
    timestamp_login TEXT NOT NULL DEFAULT (datetime('now')),
    ultimo_latido TEXT NOT NULL DEFAULT (datetime('now')),
    activo INTEGER NOT NULL DEFAULT 1                 -- 1 = dentro del módulo, 0 = fuera
);

CREATE INDEX IF NOT EXISTS idx_operario_logins_activo
    ON operario_logins(activo);

-- Un mismo operario solo puede tener UN login activo a la vez
CREATE UNIQUE INDEX IF NOT EXISTS idx_operario_logins_nombre_activo
    ON operario_logins(operario_nombre) WHERE activo = 1;
