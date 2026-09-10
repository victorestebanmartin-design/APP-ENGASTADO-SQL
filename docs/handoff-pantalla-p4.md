# Handoff — Panel ESP32-P4 del carro

## 1. CONTEXTO GENERAL
Pantalla auxiliar grande (4D Systems ESP32-P4-101CT-CLB, 10,1" MIPI 800x1280) montada en el
carro de fábrica junto a la ESP32-S3 pequeña. Muestra qué puestos tienen trabajo y su fase;
en detalle, los paquetes de un puesto. Firmware: `esp32/pantalla_p4_101/pantalla_p4_101.ino` (LVGL 9.5, apaisado 1280x800, tema oscuro).

## 2. ESTADO ACTUAL
- **Funciona y confirmado por el usuario:** vista lista; vista detalle con grid de 5 paquetes
  (3 arriba + 2 abajo), fondo de celda = color de la etiqueta. "Reparto y tamaños perfecto".
- **Flasheado, sin confirmar visualmente aún (commit `af387be`):** nº de etiqueta en Montserrat
  Bold 128 px (fuente propia `lv_font_num128.c`); nombre 36, contadores 18; fix de "rayas negras"
  en bordes (prefill del framebuffer + cabecera 96→100 + guardas en `flush_cb` + invalidate total).
- **Web (commit en `main`, NO desplegado a PythonAnywhere):** `_payloadESP32()` en
  `static/js/v3/v3-paquetes-modal.js` añade `color`/`tcolor`/`cables`/`term` por paquete.
  Hasta que se despliegue, la P4 pinta celdas en gris `#2B3550` y contadores a 0.

## 3. DECISIONES TOMADAS
- Toolchain: `arduino-cli` (Arduino IDE) vía `compilar.sh`, NO PlatformIO.
- Rotación 90° a mano en `flush_cb` (`lv_display_set_rotation` no rota).
- Modo PARTIAL + buffers en PSRAM.
- Detalle solo si hay operario identificado (campo `sel`); en lista no se ven paquetes (con 2-3 puestos sería un caos).
- Carro reenvía la instantánea cada 5 s → la P4 se recupera sola tras reflash sin apagar el carro.
- Colores de etiqueta se calculan en el SW web (`getCodCableColor`) y se mandan como hex; NO se portan al firmware.
- Nº grande: fuente Bold propia. Descartado `transform_scale` (no engorda el trazo, se ve blando).
- Rotación 180° del panel se deja así ("pruebas en la mesa").

## 4. SIGUIENTE PASO CONCRETO
1. Esperar el visto bueno del usuario a `af387be` (tamaño del número, rayas negras).
   Si el 128 no cuadra: regenerar la fuente con otro `--size`, renombrar, recompilar (~1-2 min, sin rebuild de LVGL).
2. Desplegar el SW web: consola Bash de PythonAnywhere →
   `cd ~/APP-ENGASTADO-SQL && git pull && touch /var/www/*_wsgi.py`
   (`deploy.py` no va: falta `DEPLOY_SECRET` en `.env`).

## 5. RIESGOS / RESTRICCIONES
- Tocar `lv_conf.h` fuerza recompilar LVGL entero (~7 min). Añadir un `.c` de fuente al sketch, no.
- UART carro→P4 con ruido en reposo (falta masa común corta); el firmware filtra acumulando desde `{`.
- `Serial` de la P4 NO sale por USB por defecto (`cdc_on_boot=0`); variante debug: FQBN + `,USBMode=hwcdc,CDCOnBoot=cdc`.
- Firmware del carro = sensible: OTA, `FW_VERSION` (hoy `2026-09-10b`), hay que desplegar servidor y verificar en Admin → Lectores RFID.
- Windows server: todo `open()`/`print()` de texto con `encoding='utf-8'` (lo vigilan tests).
- El botón físico de OK del carro NO se toca ni se sustituye (vías degradadas siempre operativas).

## 6. PENDIENTE DE DECIDIR
- Botón "OK" táctil en la P4 (el usuario lo preguntó, dijo "no hagas nada"). Es viable: el táctil ya
  funciona y `DisplayUart.leer()` ya existe en `uart_display.py` pero `main_wifi.py` no lo llama.
  Abierto: a qué puesto apunta el OK si `sel` está vacío; si el OK físico es por-puesto o global;
  esquema de fiabilidad (mandar 2-3× o ACK, porque una pulsación perdida importa).
- Si Bold 128 es el tamaño definitivo del número.

## 7. REFERENCIAS
- Firmware P4: `esp32/pantalla_p4_101/pantalla_p4_101.ino`. Funciones: `pump()`, `flush_cb()`,
  `touch_cb()`, `celdaPaquete()`, `ui_detalle()`, `ui_lista()`, `procesarLinea()`, `huellaActual()` (FNV).
- Otros del sketch: `lv_conf.h`, `lv_font_num128.c`, `compilar.sh`, `README.md`.
- Build/flash: `./esp32/pantalla_p4_101/compilar.sh COM6` (placa en COM6).
- FQBN: `esp32:esp32:esp32p4_4ds_mipi:PartitionScheme=app5M_fat24M_32MB,DisplayModel=esp32p4_101ct_clb`
- Regenerar fuente: `npx lv_font_conv@latest --font ~/Documents/Arduino/libraries/lvgl/tests/src/test_files/fonts/Montserrat-Bold.ttf --size N --bpp 4 --format lvgl --symbols "0123456789-" --no-compress --force-fast-kern-format --lv-include lvgl.h -o lv_font_numN.c`
- Carro: `esp32/micropython/main_wifi.py` (`_enviar_display(ops, carro, fw, sel='')`, ~L453);
  `esp32/micropython/lib/uart_display.py` (`DisplayUart.enviar()` / `.leer()`).
- Web: `static/js/v3/v3-paquetes-modal.js` (`_payloadESP32()`, ~L385); `static/js/cable-colors.js` (`getCodCableColor()`).
- UART: P4 GPIO52 RX / GPIO50 TX ↔ carro GPIO45 TX / GPIO46 RX, 115200 8N1. Panel nativo 800x1280, LVGL 1280x800.
- Captura serie desde Claude: PowerShell `System.IO.Ports.SerialPort` con `DtrEnable`/`RtsEnable` a true.
- Commits recientes: `9ffbac8` (grid 3+2), `af387be` (Bold 128 + rayas negras). Memoria: `esp32-p4-panel-build.md`.
