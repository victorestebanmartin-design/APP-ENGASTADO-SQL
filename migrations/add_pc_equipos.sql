-- Identidad del PC por modulo (mangueras y manguitos dejan de necesitar puestos)
--
-- NOTA: la app aplica esto sola al arrancar (ver app/__init__.py:_apply_migrations).
-- Este fichero es solo la referencia para aplicarlo a mano si hiciera falta.

-- A que modulo esta dedicado cada equipo de planta. La red no tiene DHCP, asi
-- que la IP fija identifica al PC mejor que una cookie: sobrevive a borrar la
-- cache del navegador. Se rellena sola al configurar el equipo desde el.
-- modulo = engastado | mangueras | manguitos
-- puesto_id solo aplica a engastado (mangueras y manguitos no tienen puestos).
CREATE TABLE IF NOT EXISTS pc_equipos (
    ip         TEXT PRIMARY KEY,
    modulo     TEXT NOT NULL DEFAULT 'engastado',
    puesto_id  TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Un lector RFID puede estar asignado a un PUESTO (engastado) o a un MODULO
-- completo (mangueras/manguitos). Se guarda en el login para que cada PC sepa
-- que logins son suyos al sondear /api/operarios/logins.
ALTER TABLE operario_logins ADD COLUMN modulo TEXT;
