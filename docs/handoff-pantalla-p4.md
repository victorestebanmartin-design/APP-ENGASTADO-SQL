# Panel ESP32-P4 del carro — referencia de trabajo

Doc vivo para retomar el trabajo en la pantalla grande del carro. Recoge cómo
está montado, qué decisiones hay tomadas y las trampas que ya costaron tiempo.

---

## 1. Qué es

Pantalla auxiliar grande montada en el carro de fábrica, al lado de la ESP32-S3
pequeña (el lector RFID / pick-to-light).

- **Hardware:** 4D Systems **ESP32-P4-101CT-CLB**, 10,1", panel MIPI-DSI.
  Framebuffer nativo **800×1280** (retrato). Táctil capacitivo **GT911**.
- **Interfaz:** LVGL **9.5.0**, en **apaisado 1280×800**, tema oscuro a juego con
  el carro. El giro retrato→apaisado lo hace el firmware a mano (ver §5.1).
- **Qué muestra:**
  - **Lista** (`sel` vacío): una fila por puesto con trabajo — nº de botón,
    nombre, fase, nº de paquetes. No enseña paquetes (con 2-3 puestos sería un lío).
  - **Detalle** (`sel` = clave de puesto): ese puesto con sus paquetes en un grid
    de 5 (3 arriba + 2 abajo), fondo de celda = color de la etiqueta (el mismo
    que pinta el modal del SW web), nº de etiqueta enorme, nombre del elemento,
    contadores cables / term.
- **Firmware:** `esp32/pantalla_p4_101/pantalla_p4_101.ino` (un solo archivo).
  Recibe del carro por UART una trama JSON por línea; no tiene lógica de negocio.

---

## 2. Estado actual — todo funciona (firmware v12)

Banner de arranque en serie: `P4 pantalla_p4_101 v12 (LVGL) ready`.

| Cosa | Estado |
|------|--------|
| Vista lista / vista detalle / grid 3+2 / colores | OK, visto bueno del usuario |
| Nº de etiqueta en Montserrat Bold **128 px** (`lv_font_num128.c`) | **tamaño y fuente definitivos** |
| **Rayas negras** en la pantalla | **resueltas** (cache msync, §5.2) |
| **Botón OK táctil** (barra CONFIRMAR) | **funciona en el carro** (§5.4) |
| **Táctil** (no respondía) | **resuelto** — lectura sin la compuerta INT + calibración afín (§3, §5.3) |
| Recuperación sola tras reflash | el carro reenvía la instantánea cada 5 s |

**Git:** todo en `main`.
- `21b6285` — táctil operativo + calibración afín persistente (v12).
- `daf24a3` — rayas negras (cache msync) + botón OK táctil (v8); también subió el
  carro a `FW_VERSION = 2026-09-10c` y el payload de paquetes de la web.

**Despliegue:** el usuario ya desplegó PythonAnywhere ("PAW"). Tras desplegar el
servidor, el carro coge el OTA `2026-09-10c` solo en el siguiente poll — conviene
verificar el cambio de versión en **Admin → Lectores RFID**.

---

## 3. Calibración táctil

### Cómo funciona

El táctil de la librería 4D no cuadra con el giro manual del framebuffer (ver
§5.3). En vez de deducir la fórmula, la placa **se calibra sola**:

1. Al arrancar, `calibrar()` enseña 5 cruces, una a una, en
   `(120,120) · (1160,120) · (1160,680) · (120,680) · (640,400)` (coords LVGL).
2. Con los 5 pares `(toque_crudo → posición_real)` resuelve por **mínimos
   cuadrados** un mapa **afín**:
   `lx = ax·rawx + bx·rawy + cx` ; `ly = ay·rawx + by·rawy + cy`
   (`cal_resolver3()` = Gauss 3×3 sobre las ecuaciones normales). Un afín absorbe
   cualquier giro / espejo / escala, así que no hace falta saber qué hace la
   librería por dentro.
3. Guarda los 6 coeficientes en **NVS** (`Preferences`, namespace `"p4touch"`,
   claves `ax bx cx ay by cy` como `double` + `ok` como `bool`).
4. Enseña "Calibración guardada · error medio N px" y arranca la UI normal.

`touch_cb()` aplica ese afín a cada toque **si `cal_valida`**. Si la calibración
sale con error medio < 45 px el texto va en verde; ámbar si algún toque quedó
torcido → conviene repetir.

### Permanencia y cómo rehacerla

- **Es permanente.** Sobrevive apagones, desenchufar el carro, todo. **No se
  recalibra sola nunca.**
- Se vuelve a pedir solo si:
  - La NVS está vacía (flash recién grabada) → calibración **obligatoria**.
  - Tocas la pantalla durante la **ventana de 2,5 s** al arrancar
    ("toca la pantalla ahora para repetir la calibración"). Si no tocas, carga la
    de NVS y sigue.
- **Forzar recalibración permanente** (p. ej. si se cambia el panel): borrar la
  NVS del namespace. Rápido: añadir temporalmente `prefs.begin("p4touch", false);
  prefs.clear(); prefs.end();` en `setup()`, flashear una vez y quitarlo. O
  `esptool erase_flash` (borra todo).

### Diagnóstico

- `#define TOUCH_DEBUG` (línea ~124 del `.ino`): `0` = apagado (producción).
  Con `1`: rótulo abajo-izquierda con `cal / raw(x,y) / map(x,y) / clk`
  (clicks de LVGL) y `Serial.printf` en cada flanco de toque.
- **Sonda I2C al arrancar** → variable `cal_i2c` (`"0x5D=OK 0x14=no"` etc.).
  Si la calibración no recibe toques, la pantalla roja de error la enseña:
  distingue "el GT911 no contesta / falta masa común" de "contesta pero da
  coordenadas raras".

---

## 4. Compilar y flashear

Toolchain: **`arduino-cli`** (el que trae el Arduino IDE), vía el script.
**NO** PlatformIO.

```bash
cd esp32/pantalla_p4_101
./compilar.sh            # solo compila
./compilar.sh COM6       # compila y sube (placa en COM6) + abre monitor UART0 115200
```

- **FQBN:** `esp32:esp32:esp32p4_4ds_mipi:PartitionScheme=app5M_fat24M_32MB,DisplayModel=esp32p4_101ct_clb`
- La placa coge ~26 % de flash. Compila limpio (sin warnings).
- Tras flashear, el carro reenvía la instantánea en ~5 s → la P4 se recupera sola
  sin apagar el carro.
- **`Serial` NO sale por USB** (`cdc_on_boot=0`). El monitor es **UART0** (lo abre
  `compilar.sh` al subir). Para ver `Serial` por USB: FQBN + `,USBMode=hwcdc,CDCOnBoot=cdc`.
- **`lv_conf.h`** de esta carpeta es la config de LVGL. Tocarlo fuerza recompilar
  **todo LVGL** (~7 min). Añadir un `.c` de fuente al sketch, no.

---

## 5. Arquitectura del firmware

Estructura del `.ino` (un archivo, ~1150 líneas): constantes y paleta → estado
global → `touch_raw()` → helpers UART/JSON/huella → helpers LVGL (`card` `chip`
`txt`) → sección **OK táctil** → sección **calibración** → **vistas** (`ui_*`) →
`flush_cb` / `touch_cb` / `tick_cb` → `procesarLinea` → `ui_build` → `setup` / `loop`.

### 5.1. Giro apaisado a mano (`flush_cb`)

El framebuffer es retrato 800×1280; la UI es apaisada 1280×800.
`lv_display_set_rotation` **no** rota el contenido, así que `flush_cb` copia píxel
a píxel girando 90°:
`nx = (NAT_W-1) - ly ; ny = lx` (con `NAT_W = 800`).
Modo **`LV_DISPLAY_RENDER_MODE_PARTIAL`**, dos buffers de `1280×240` en PSRAM.

El panel va montado **girado 180°** respecto a lo que asume `flush_cb` — se dejó
así ("pruebas en la mesa"). Si en el carro se monta al derecho y se ve invertida:
ajustar el giro en `flush_cb` **y volver a calibrar el táctil** (el afín está
atado a la orientación actual).

### 5.2. Rayas negras = falta de cache msync (`flush_cb`, `setup`)

El framebuffer DPI vive en PSRAM y lo lee por DMA el controlador MIPI-DSI. Si la
caché de la CPU no se vuelca a memoria, el DSI ve filas a medio escribir →
**bandas negras del ancho de una línea de caché (64 B = 32 px)**. No era la UI
(el intento de `af387be` con prefill/cabecera/guardas no tocaba la causa).

**Fix:** `esp_cache_msync(fb + fila*NAT_W*2, largo, ESP_CACHE_MSYNC_FLAG_DIR_C2M |
ESP_CACHE_MSYNC_FLAG_UNALIGNED)` al final de `flush_cb` sobre el rango de filas
nativas escritas, y una vez tras el prefill de fondo en `setup()`. Es lo mismo
que hace la librería GFX4d tras cada dibujo (`EndWrite()`,
`gfx4desp32_mipi_panel.cpp:654`).

### 5.3. Táctil sin la compuerta del pin INT (`touch_raw`)

`touch_Update()` de la librería 4D tiene, al principio, una **compuerta sobre el
pin INT (GPIO5)**: si ese pin no está en el nivel que espera, sale sin leer nada
y `touch_GetPen()` se queda en "no hay dedo" para siempre. En esta placa esa
compuerta dejaba el táctil mudo.

**Fix:** helper `touch_raw(int *x, int *y)` que lee el GT911 por I2C **directo**
con `gfx.touch_GetTouchPoints(tx, ty)` — la misma consulta que la librería hace
por dentro, pero sin la compuerta. Se usa en `touch_cb()`, `cal_leer_punto()` y
`cal_pedir_recalibrado()`. Ya no se llama a `touch_Update` / `touch_GetPen` /
`touch_GetX/Y` en ningún sitio.

- GT911 en el bus I2C **GPIO7/8**, direcciones **0x5D** o **0x14**.
- `touch_GetTouchPoints` devuelve el crudo ya con la transformación interna de la
  librería (rotación `rotation=2`, `__width=800`); da igual, el afín de la
  calibración lo absorbe.

### 5.4. Botón OK táctil (sección "OK táctil" + "calibración" + `ui_detalle`)

- **Aparece solo** cuando el carro manda `"ok":true` en la trama `estado`
  (calculado de `_pide_accion` del puesto en `sel`). En vista lista no hay botón.
- Visual: barra **`CONFIRMAR`** verde, ancho completo, 96 px, al fondo de la
  tarjeta de detalle, **parpadea** (`lv_anim` de opacidad 40 ↔ cover, 450 ms).
- Zona de toque: **velo transparente sobre los 340 px inferiores**, ancho completo
  (`ok_overlay`, se crea sobre la pantalla activa cuando `pide_ok` y se quita
  cuando no) + el `ok_click_cb` de la propia barra. = "tecla Enter en toda la
  zona inferior".
- Al tocar: antirrebote 1,5 s → "OK" verde fugaz (`lv_obj_delete_delayed` 700 ms)
  → `ok_tx_iniciar()`. `ok_tx_paso()` (cada vuelta del `loop`) manda
  `{"v":1,"tipo":"ok","carro":..,"sel":..,"id":<millis>}` y **reintenta 3× cada
  200 ms** hasta recibir `{"tipo":"ack","id":N}` (rama `ack` en `procesarLinea`).
- Si el carro deja de pedir OK (`ok:false`) o cambia de puesto, se corta cualquier
  reintento vivo.
- **Fiabilidad por ACK + reintento**, no por triple envío. El OK táctil es un
  **extra**: si la UART P4→carro falla, el **pulsador físico 8 del carro sigue
  confirmando** — ese pulsador NO se toca ni se sustituye.

### 5.5. Refresco silencioso (`huellaActual`, `ui_actualizar`)

`ui_actualizar` calcula una **huella FNV** del contenido visible (puesto, fase,
paquetes, `pide_ok`, wifi…) y solo repinta si cambió. Evita parpadeos con el
reenvío cada 5 s.

### 5.6. UART y ruido (`pump`)

La línea carro→P4 tiene **ruido en reposo** (falta una masa común corta). `pump()`
drena byte a byte y solo empieza a acumular una línea cuando ve `{`; descarta lo
que no sea JSON. **Solo guarda UNA línea pendiente**: si un `estado` y un `ack`
llegan pegados, una se pierde — da igual, el `estado` se reenvía en ~3 s y el
`ack` lo cubre el reintento 3×.

---

## 6. Contrato UART P4 ↔ carro

Pines: **P4 GPIO52 RX / GPIO50 TX ↔ carro GPIO45 TX / GPIO46 RX**, 115200 8N1.
Una trama JSON por línea, terminada en `\n`.

**carro → P4** (instantánea, cada 5 s o al cambiar algo):
```json
{"v":1,"tipo":"estado","carro":"1","fw":"2026-09-10c","wifi":true,"sel":"puesto_3",
 "ok":true,
 "ops":[{"operario":"puesto_3","data":{"puesto_nombre":"...","puesto_id":"...",
    "fase":"recoger|trabajando|devolver|fin","lote":"...","boton":1,
    "grupo":1,"grupos":5,
    "paquetes":[{"etiqueta":12,"elem":"S206","cod":"...","cables":3,"term":5,
                 "color":"#2563eb","tcolor":"#ffffff","bloqueado":false}]}}]}
```
- `sel` vacío → LISTA; `sel` = clave → DETALLE de ese puesto.
- `ok` → `true` solo si el puesto de `sel` está esperando confirmación.
- **Los campos numéricos van como número JSON, no como string.** ArduinoJson v7
  `doc["x"] | 0u` / `.as<uint32_t>()` devuelve 0 para un string → no lo parsea.

**P4 → carro** (toque en CONFIRMAR):
```json
{"v":1,"tipo":"ok","carro":"1","sel":"puesto_3","id":123456}
```

**carro → P4** (acuse):
```json
{"v":1,"tipo":"ack","id":123456}
```
`id` es el mismo número (millis de la P4). El carro lo reenvía tal cual.

---

## 7. Lado carro — `esp32/micropython/main_wifi.py`

- `FW_VERSION = "2026-09-10c"`.
- `_enviar_display(ops, carro, fw, sel='', pide_ok=False)`: añade `'ok': bool(pide_ok)`
  a la trama. La instantánea se reenvía si cambia la huella, el `sel`, el `ok` o
  toca reenvío periódico.
- **Lectura del OK táctil** en el bucle principal: cada vuelta hace
  `display_uart.leer()`; si llega `{"tipo":"ok",...}`:
  - **Siempre ACKea** (aunque sea repetido → así la P4 deja de reintentar).
  - Deduplica por `id` (ventana 5 s).
  - Si `sel` coincide con `sel_clave` y `vista == 'detalle'` → llama a
    **`confirmar_ok()`**, el **mismo** camino que el pulsador físico 8.
- `esp32/micropython/lib/uart_display.py`: `UART(..., rxbuf=512, timeout=0)`;
  `DisplayUart.enviar()` / `.leer()` (una línea JSON, sin bloquear, sin tumbar el
  bucle si falla).

**Regla OTA (ver `CLAUDE.md`):** al tocar el firmware del carro, subir `FW_VERSION`
(`AAAA-MM-DDx`), desplegar el servidor (si no, sirve el firmware viejo) y
comprobar en **Admin → Lectores RFID** que la placa cogió la versión.

---

## 8. Lado web

- `static/js/v3/v3-paquetes-modal.js` → `_payloadESP32()` (~L385): arma el payload
  de paquetes que el servidor mete en la instantánea.
- `static/js/cable-colors.js` → `getCodCableColor()`: calcula el color de la
  etiqueta. **Los colores se calculan en la web y se mandan como hex** (`color`,
  `tcolor`); NO se portan al firmware.
- Despliegue PythonAnywhere: consola Bash →
  `cd ~/APP-ENGASTADO-SQL && git pull && touch /var/www/*_wsgi.py`
  (`deploy.py` no va: falta `DEPLOY_SECRET` en `.env`).

---

## 9. Trampas / cosas que no tocar

- **Pulsador físico 8 del carro:** NO se toca ni se sustituye. Las vías degradadas
  (pick-to-light, "Continuar sin confirmar") siempre operativas.
- **`lv_conf.h`:** tocarlo = recompilar LVGL entero (~7 min).
- **`Serial` no sale por USB** por defecto (ver §4).
- **Ruido UART en reposo** (falta masa común corta): `pump()` lo filtra.
- **Números en el JSON** deben ir como número, no string (ArduinoJson v7).
- **El afín del táctil está atado a la orientación actual** de `flush_cb`. Si
  cambias el giro de la pantalla, recalibra.
- **NVS `p4touch`:** si el táctil se comporta raro tras un cambio de hardware,
  bórrala y recalibra (§3).
- `tests/` de la app NO cubre el contrato JSON del display ni `FW_VERSION`; estos
  archivos son MicroPython/Arduino y no los toca la suite CPython.
- **Windows server:** todo `open()`/`print()` de texto con `encoding='utf-8'`
  (lo vigilan tests) — no aplica a `esp32/` (MicroPython), pero sí a cualquier
  cambio en `app/` o `static/`.

---

## 10. Tareas típicas para seguir

**Cambiar el tamaño / la fuente del número de etiqueta**
Regenerar el `.c` de la fuente (solo dígitos y `-`):
```
npx lv_font_conv@latest --font ~/Documents/Arduino/libraries/lvgl/tests/src/test_files/fonts/Montserrat-Bold.ttf \
  --size N --bpp 4 --format lvgl --symbols "0123456789-" --no-compress \
  --force-fast-kern-format --lv-include lvgl.h -o lv_font_numN.c
```
Poner el `.c` en la carpeta del sketch, `extern "C" const lv_font_t lv_font_numN;`
y `#define F_HUGE &lv_font_numN`. (128 px es el definitivo hoy.)

**Añadir un campo a la trama `estado`**
Carro: meterlo en el dict de `_enviar_display` como **número o string** según toque.
P4: leerlo en `procesarLinea` con `copiaCampo` (string) o `doc["x"] | def`
(número/bool), guardarlo en `Op`/`Paq`, y si afecta a lo que se ve, meterlo en
`huellaActual()` o el refresco no se entera.

**Mover / cambiar el botón OK**
Barra visible: `ui_detalle()` (bloque final, tras el grid). Zona de toque:
`ok_overlay_poner()` (los 340 px inferiores). Envío/reintentos: `ok_tx_paso()`.
Antirrebote: `ok_toque_ms` en `ok_click_cb`.

**Depurar el táctil**
Poner `#define TOUCH_DEBUG 1`, flashear. El rótulo abajo-izquierda enseña
`raw(x,y)` (crudo del GT911) y `map(x,y)` (tras el afín). Si `map` cae lejos del
dedo → recalibrar (ventana de 2,5 s). Si `raw` no cambia al tocar → mirar
`cal_i2c` (sonda I2C); si es `0x5D=no 0x14=no` → cableado/masa del táctil.

**Depurar la UART carro→P4**
Si no llegan tramas: monitor UART0 (`compilar.sh COM6`), mirar los `hb:` cada
10 s (`rx`, `buf`, `nops`, `sel`, `diag`) y las líneas `RX (...)` / `LASTLINE`.
`ui_diag()` (pantalla roja) sale sola si llegan bytes pero no son JSON válido.

**Reflashear sin apagar el carro**
`./compilar.sh COM6`. La P4 arranca, hace la ventana de calibración (2,5 s, no
toques) y en ~5 s el carro le reenvía la instantánea.

---

## 11. Referencias rápidas

| | |
|--|--|
| Firmware P4 | `esp32/pantalla_p4_101/pantalla_p4_101.ino` |
| Otros del sketch | `lv_conf.h`, `lv_font_num128.c`, `compilar.sh`, `README.md` |
| Build / flash | `cd esp32/pantalla_p4_101 && ./compilar.sh [COM6]` |
| FQBN | `esp32:esp32:esp32p4_4ds_mipi:PartitionScheme=app5M_fat24M_32MB,DisplayModel=esp32p4_101ct_clb` |
| UART | P4 GPIO52 RX / GPIO50 TX ↔ carro GPIO45 TX / GPIO46 RX · 115200 8N1 |
| Panel | nativo 800×1280 (retrato) · LVGL 1280×800 (apaisado) · giro a mano en `flush_cb` |
| Táctil | GT911 · I2C GPIO7/8 · addr 0x5D o 0x14 · INT GPIO5 (compuerta evitada) |
| Calibración | NVS `Preferences` namespace `"p4touch"` · claves `ax bx cx ay by cy ok` |
| Cache msync ref. | `gfx4desp32_mipi_panel.cpp:654` (`EndWrite()`) |
| Librería GFX4d | `~/Documents/Arduino/libraries/GFX4dESP32P4` |
| Carro | `esp32/micropython/main_wifi.py`, `esp32/micropython/lib/uart_display.py` |
| Web | `static/js/v3/v3-paquetes-modal.js`, `static/js/cable-colors.js` |
| Captura serie desde script | PowerShell `System.IO.Ports.SerialPort` con `DtrEnable`/`RtsEnable` = true |
| Memoria del proyecto | `.claude/.../memory/esp32-p4-panel-build.md` |

### Funciones clave del `.ino`

| Función | Qué hace |
|---------|----------|
| `touch_raw()` | lee el GT911 por I2C sin la compuerta INT |
| `flush_cb()` | copia+gira el buffer LVGL al framebuffer retrato + `esp_cache_msync` |
| `touch_cb()` | aplica el afín de la calibración al toque |
| `calibrar()` / `cal_resolver3()` / `cal_leer_punto()` | rutina de 5 cruces + ajuste afín |
| `cal_cargar()` / `cal_guardar()` / `cal_pedir_recalibrado()` | NVS + ventana de 2,5 s |
| `ok_tx_iniciar()` / `ok_tx_paso()` / `ok_click_cb()` / `ok_overlay_poner()` | OK táctil → carro |
| `procesarLinea()` | parser JSON de la trama del carro (ramas `estado` y `ack`) |
| `huellaActual()` | FNV del contenido visible → refresco solo si cambia |
| `ui_lista()` / `ui_detalle()` / `celdaPaquete()` / `ui_diag()` | vistas |
| `pump()` | drena la UART filtrando ruido desde `{` |

### Historial de commits del panel

- `21b6285` táctil operativo + calibración afín persistente (v12)
- `daf24a3` rayas negras (cache msync) + botón OK táctil (v8) + carro `2026-09-10c`
- `af387be` nº en Montserrat Bold 128 + primer (fallido) intento de rayas negras
- `9ffbac8` detalle en grid 3+2 con color de etiqueta de fondo
- `04ff5df` paquetes como el modal del SW (etiqueta, cables, term.)
- `812079a` rotar el apaisado a mano en `flush_cb`
- `ab18a95` reescribir la interfaz con LVGL 9
- `268dfd7` la P4 solo detalla los paquetes del puesto identificado
- `f6a933c` el carro reenvía la instantánea al display cada 5 s
