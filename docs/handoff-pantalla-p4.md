# Handoff — Panel ESP32-P4 del carro

## 1. CONTEXTO GENERAL
Pantalla auxiliar grande (4D Systems ESP32-P4-101CT-CLB, 10,1" MIPI 800x1280) montada en el
carro de fábrica junto a la ESP32-S3 pequeña. Muestra qué puestos tienen trabajo y su fase;
en detalle, los paquetes de un puesto. Firmware: `esp32/pantalla_p4_101/pantalla_p4_101.ino` (LVGL 9.5, apaisado 1280x800, tema oscuro).

## 2. ESTADO ACTUAL
- **Funciona y confirmado por el usuario:** vista lista; vista detalle con grid de 5 paquetes
  (3 arriba + 2 abajo), fondo de celda = color de la etiqueta. "Reparto y tamaños perfecto".
  Nº de etiqueta en Montserrat Bold 128 px (`lv_font_num128.c`): **la fuente le vale, es
  definitiva**. Web ya desplegada en PythonAnywhere: las celdas salen con su color real.
- **Rayas negras — CAUSA REAL encontrada y arreglada (sin flashear aún):** el framebuffer DPI
  vive en PSRAM y lo lee por DMA el MIPI-DSI; `flush_cb` escribía directo en `fb` y **nunca
  volcaba la caché de la CPU** → el DSI veía filas a medio escribir como bandas negras del ancho
  de una línea de caché (64 B = 32 px). Los intentos de `af387be` (prefill, cabecera, guardas)
  no tocaban la causa. Fix: `esp_cache_msync(...C2M|UNALIGNED)` al final de `flush_cb` sobre las
  filas nativas escritas, y una vez tras el prefill de `setup()`. La librería GFX4d hace ese
  mismo msync tras cada dibujo (`EndWrite()`, `gfx4desp32_mipi_panel.cpp:654`). **Compila
  limpio.** Falta flashear (`./compilar.sh COM6`) y confirmar que se fueron.
- **Botón OK táctil en la P4 — flasheado (v10), pendiente validar en el carro:**
  - Aparece SOLO cuando el carro manda `"ok":true` en la instantánea (`_pide_accion` del puesto
    en `sel`). Barra `CONFIRMAR` full-width abajo, 96 px, verde, **parpadea** (`lv_anim` de opacidad).
  - El toque se recoge con un **velo transparente sobre toda la zona inferior** (340 px, ancho
    completo) = tecla Enter, más el `ok_click_cb` de la propia barra. Al tocar: la P4 manda
    `{"tipo":"ok","carro","sel","id":<millis>}` al carro por la misma UART (TX GPIO50 → carro
    RX GPIO46) y **reintenta 3× cada 200 ms hasta recibir `{"tipo":"ack","id":N}`**. Antirrebote
    1,5 s + "OK" verde fugaz de feedback.
  - Carro (`main_wifi.py`): lee `display_uart.leer()` cada vuelta del loop, ACKea siempre (aunque
    sea repetido), deduplica por `id` (ventana 5 s) y si `sel` coincide con `sel_clave` en
    `vista=='detalle'` llama al **mismo `confirmar_ok()`** que el pulsador 8. `FW_VERSION`
    subida a `2026-09-10c`. `lib/uart_display.py`: `rxbuf=512`, `timeout=0`.
- **Táctil — RESUELTO (v12), funciona en el carro:**
  - **Causa 1:** `touch_Update()` de la librería 4D tiene una compuerta sobre el pin INT
    (GPIO5) que en esta placa la dejaba muda (nunca detectaba la pulsación). **Fix:** leer el
    GT911 por I2C directo con `gfx.touch_GetTouchPoints()` (misma consulta, sin la compuerta).
    Helper `touch_raw()`; se usa en `touch_cb`, `cal_leer_punto()` y `cal_pedir_recalibrado()`.
  - **Causa 2:** sin `gfx.Orientation()` los ejes del táctil no cuadran con la rotación manual
    de `flush_cb`. **Fix:** `calibrar()` pide **5 toques sobre cruces** y ajusta por mínimos
    cuadrados un **afín** `lx=ax·rawx+bx·rawy+cx`, `ly=ay·rawx+by·rawy+cy` (absorbe
    giro/espejo/escala). Se guarda en **NVS** (`Preferences`, namespace `p4touch`) → **permanente,
    sobrevive apagones**. `touch_cb` aplica el afín si `cal_valida`.
  - 1ª vez (NVS vacía): calibra obligatorio. Después: ventana de 2,5 s al arrancar
    ("toca para repetir la calibración"); si no tocas, carga la de NVS y sigue.
  - Sonda I2C al arrancar → `cal_i2c` (`0x5D=OK/no 0x14=OK/no`), se enseña si la calibración
    no recibe toques (distingue "sin masa/cable" de "coordenadas raras").
  - `#define TOUCH_DEBUG 0` (rótulo de diagnóstico apagado; `1` para volver a verlo).

## 3. DECISIONES TOMADAS
- Toolchain: `arduino-cli` (Arduino IDE) vía `compilar.sh`, NO PlatformIO.
- Rotación 90° a mano en `flush_cb` (`lv_display_set_rotation` no rota).
- Modo PARTIAL + buffers en PSRAM.
- Detalle solo si hay operario identificado (campo `sel`); en lista no se ven paquetes (con 2-3 puestos sería un caos).
- Carro reenvía la instantánea cada 5 s → la P4 se recupera sola tras reflash sin apagar el carro.
- Colores de etiqueta se calculan en el SW web (`getCodCableColor`) y se mandan como hex; NO se portan al firmware.
- Nº grande: fuente Bold propia. Descartado `transform_scale` (no engorda el trazo, se ve blando).
  **128 px es el tamaño definitivo** (visto bueno del usuario).
- Rotación 180° del panel se deja así ("pruebas en la mesa").
- Rayas negras = falta de `esp_cache_msync` tras escribir el framebuffer PSRAM (no era la UI).
- Botón OK en la P4: **visible solo cuando el carro lo pide** (`ok:true`), no siempre.
  Fiabilidad por **ACK + reintento** (no por triple envío). El OK táctil = pulsador 8, apunta
  al puesto de `sel`; en vista lista no hay botón.

## 4. SIGUIENTE PASO CONCRETO
1. **Subir a `main`** el firmware de la P4 (`esp32/pantalla_p4_101/pantalla_p4_101.ino`, v12):
   rayas negras + OK táctil + calibración funcionan y confirmados en el carro. En `main` está
   solo hasta `daf24a3` (v8, sin táctil). El resto del árbol (carro `2026-09-10c`, web) ya
   está en `main` desde `daf24a3`.
2. **Desplegar el carro:** desplegar el servidor primero (ver paso 3), luego el OTA del carro
   se sirve solo — la placa coge `2026-09-10c` en el siguiente poll. Verificar en
   Admin → Lectores RFID / estado del carro que cambió de versión.
3. **Desplegar el SW web** (lleva `FW_VERSION` nuevo del carro + payload de paquetes ya en `main`):
   consola Bash de PythonAnywhere → `cd ~/APP-ENGASTADO-SQL && git pull && touch /var/www/*_wsgi.py`
   (`deploy.py` no va: falta `DEPLOY_SECRET` en `.env`).

## 5. RIESGOS / RESTRICCIONES
- Tocar `lv_conf.h` fuerza recompilar LVGL entero (~7 min). Añadir un `.c` de fuente al sketch, no.
- UART carro→P4 con ruido en reposo (falta masa común corta); el firmware filtra acumulando desde `{`.
- `Serial` de la P4 NO sale por USB por defecto (`cdc_on_boot=0`); variante debug: FQBN + `,USBMode=hwcdc,CDCOnBoot=cdc`.
- Firmware del carro = sensible: OTA, `FW_VERSION` (ahora `2026-09-10c`), hay que desplegar servidor y verificar en Admin → Lectores RFID.
- Windows server: todo `open()`/`print()` de texto con `encoding='utf-8'` (lo vigilan tests).
- El botón físico de OK del carro NO se toca ni se sustituye (vías degradadas siempre operativas).
- El OK táctil de la P4 es un extra: si la UART P4→carro falla, el pulsador 8 sigue confirmando.
- `pump()` de la P4 solo guarda UNA línea pendiente: si un `estado` y un `ack` llegan pegados,
  una se pierde. Da igual: el `estado` se reenvía en ~3 s y el `ack` lo cubre el reintento 3×.
- `tests/` no cubre el contrato JSON del display ni el valor de `FW_VERSION`. `pytest` no está
  instalado en el entorno de esta sesión; la suite no se pudo correr aquí (los cambios son
  MicroPython/Arduino, no CPython).

## 6. PENDIENTE DE DECIDIR
- (nada abierto ahora mismo) — el botón OK y el tamaño del número están cerrados.
  Si al probar el OK táctil el parpadeo molesta o el toque es poco fiable, ajustar
  `lv_anim_set_duration` / el nº de reintentos en `ok_tx_paso()`.

## 7. REFERENCIAS
- Firmware P4: `esp32/pantalla_p4_101/pantalla_p4_101.ino`. Funciones: `pump()`, `flush_cb()`
  (ahora con `esp_cache_msync`), `touch_cb()`, `celdaPaquete()`, `ui_detalle()` (barra `CONFIRMAR`),
  `ui_lista()`, `procesarLinea()` (rama `ack`), `huellaActual()` (FNV),
  `ok_tx_iniciar/paso()` + `ok_click_cb()` (OK táctil → carro).
- Otros del sketch: `lv_conf.h`, `lv_font_num128.c`, `compilar.sh`, `README.md`.
- Contrato UART P4→carro: `{"v":1,"tipo":"ok","carro":..,"sel":..,"id":<millis>}` → carro responde
  `{"v":1,"tipo":"ack","id":<mismo>}`. Carro→P4 lleva ahora `"ok":true/false` en la trama `estado`.
- Msync de referencia en la librería: `gfx4desp32_mipi_panel.cpp:654` (`EndWrite()`).
- Build/flash: `./esp32/pantalla_p4_101/compilar.sh COM6` (placa en COM6).
- FQBN: `esp32:esp32:esp32p4_4ds_mipi:PartitionScheme=app5M_fat24M_32MB,DisplayModel=esp32p4_101ct_clb`
- Regenerar fuente: `npx lv_font_conv@latest --font ~/Documents/Arduino/libraries/lvgl/tests/src/test_files/fonts/Montserrat-Bold.ttf --size N --bpp 4 --format lvgl --symbols "0123456789-" --no-compress --force-fast-kern-format --lv-include lvgl.h -o lv_font_numN.c`
- Carro: `esp32/micropython/main_wifi.py` (`_enviar_display(ops, carro, fw, sel='', pide_ok=False)`,
  ~L454; lectura del OK táctil en el loop, ~L1421); `esp32/micropython/lib/uart_display.py`
  (`DisplayUart.enviar()` / `.leer()`).
- Web: `static/js/v3/v3-paquetes-modal.js` (`_payloadESP32()`, ~L385); `static/js/cable-colors.js` (`getCodCableColor()`).
- UART: P4 GPIO52 RX / GPIO50 TX ↔ carro GPIO45 TX / GPIO46 RX, 115200 8N1. Panel nativo 800x1280, LVGL 1280x800.
- Captura serie desde Claude: PowerShell `System.IO.Ports.SerialPort` con `DtrEnable`/`RtsEnable` a true.
- Commits recientes: `9ffbac8` (grid 3+2), `af387be` (Bold 128 + intento rayas negras),
  este (msync rayas negras + OK táctil). Memoria: `esp32-p4-panel-build.md`.
