-- Añadir IP fija y tipo de módulo a los puestos
-- ip_fija: dirección IP estática de la PC de este puesto (alternativa a la cookie)
-- modulo:  módulo al que pertenece este puesto ('engastado', 'mangueras', 'manguitos')

ALTER TABLE puestos ADD COLUMN ip_fija TEXT;
ALTER TABLE puestos ADD COLUMN modulo TEXT DEFAULT 'engastado';

-- Una IP solo puede pertenecer a un puesto activo
CREATE UNIQUE INDEX IF NOT EXISTS idx_puestos_ip
    ON puestos(ip_fija) WHERE ip_fija IS NOT NULL AND activo = 1;
