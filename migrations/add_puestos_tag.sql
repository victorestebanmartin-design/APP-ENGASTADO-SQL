-- =====================================================
-- MIGRACIÓN: Tarjeta NFC por puesto
-- Fecha: 2026-08-11
-- Descripción: Alternativa (o complemento) al botón de la pantalla del carro.
--   Cada puesto puede tener una tarjeta NFC; el operario la pasa por el lector
--   del carro y la pantalla le muestra sus paquetes, igual que con su botón.
--   Se guarda el UID en hexadecimal, en mayúsculas y sin separadores.
--   El botón 8 (OK) sigue siendo quien confirma.
-- =====================================================

ALTER TABLE puestos ADD COLUMN tag_uid TEXT;

-- Una tarjeta solo puede pertenecer a un puesto activo
CREATE UNIQUE INDEX IF NOT EXISTS idx_puestos_tag ON puestos(tag_uid)
    WHERE tag_uid IS NOT NULL AND activo = 1;
