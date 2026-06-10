-- Tabla de operarios (identificación controlada)
CREATE TABLE IF NOT EXISTS operarios (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    activo INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_operarios_activo ON operarios(activo);
