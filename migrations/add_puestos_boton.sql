-- =====================================================
-- MIGRACIÓN: Botón de puesto en la pantalla del carro
-- Fecha: 2026-08-11
-- Descripción: La pantalla del carro tiene 8 pulsadores. Los botones 1-7
--   identifican un PUESTO: el operario que llega al carro pulsa el botón de
--   su puesto y la pantalla le muestra sus paquetes. El botón 8 es OK
--   (confirma la recogida o la devolución).
--   Como nunca hay dos operarios en el mismo puesto, el botón identifica sin
--   ambigüedad quién está delante del carro.
-- =====================================================

ALTER TABLE puestos ADD COLUMN boton INTEGER;

-- Un botón solo puede pertenecer a un puesto activo
CREATE UNIQUE INDEX IF NOT EXISTS idx_puestos_boton ON puestos(boton)
    WHERE boton IS NOT NULL AND activo = 1;
