# Plan de escalado — app + placas ESP32 en red local

Objetivo: que la app aguante el escenario real de planta **sin degradarse**:

- ~8 pantallas de carro (ESP32-P4) sondeando `/api/esp32/current`.
- ~10 lectores RFID + pick-to-light sondeando `/api/esp32/rfid/gaveta/orden`.
- 10 PCs cliente con la web abierta y gente usándola.
- La app **a tope de datos** (Excels grandes, informes).

## Decisiones ya tomadas (2026-09-11)

- **El servidor va en la LAN de planta** (mini-PC/NUC con `run.bat`). PythonAnywhere
  ("paw") queda **solo para pruebas**. Esto habilita: HTTP plano, disco local,
  workers sin límite, y que el servidor **empuje** a la placa (puerto 80) en vez
  de depender del sondeo.
- **waitress en un solo proceso** (así es hoy en local): un `threading.Lock` a
  nivel de módulo **sí** serializa de verdad el acceso a un fichero. No hace falta
  migrar el estado a SQLite para que sea correcto; basta lock + escritura atómica.
- Los lectores RFID **podrían pasar a USB** contra el PC cliente (que ya va
  cableado); hoy van por WiFi por comodidad. A **evaluar** en Fase 4, no bloquea
  nada.

## Diagnóstico (resumen)

Carga de sondeo en reposo, sin que nadie toque nada: **~45-55 req/s**.
La mayoría **leen y reescriben ficheros JSON en disco sin candado ni escritura
atómica** → *lost updates* entre placas y lecturas de un JSON a medio escribir
(el LED parpadea, el puesto "desaparece" un instante). Además:

- `FW_VERSION` se lee del `.py` fuente + regex en **cada** poll.
- `_expirar_logins_fantasma` hace un `UPDATE` en **cada** `GET /api/operarios/logins`.
- Frecuencias fijas agresivas (carro 1 s, gaveta 750 ms aunque no haya LED).
- 3-4 timers de sondeo por PC en el navegador.
- `waitress threads=8` para ~50 req/s.

El patrón atómico correcto **ya existe** en el repo (`_esp32_write_channel` /
`_obtener_lock_canal` en `sistema.py`, y `tempfile`+`os.replace` en
`progreso.py`); solo hay que generalizarlo.

---

## Fases

### Fase 1 — Correctitud del estado compartido  ·  HECHA (2026-09-11)

Lo más crítico (corrige bugs de datos) y de riesgo bajo (contenido, mecánico).

- [x] **1.1** `app/estado_json.py`: `cargar(path, def)`, `guardar(path, datos)`
      (temporal + `os.replace` + `fsync`), `actualizar(path, def, fn)`
      (read-modify-write bajo un `RLock` por ruta). Smoke test de concurrencia:
      8 hilos × 200 incrementos atómicos = 1600 exactos, sin *lost update*.
- [x] **1.2** Repuntados a esos helpers todos los pares load/save de estado
      compartido en `sistema.py`, `pick_to_light.py`, `operarios.py`. Ya no
      queda `open('w')+json.dump` suelto para estado vivo (salvo `esp32_ip.txt`,
      un `.txt` de un solo valor y camino frío).
- [x] **1.3** Convertidos a `actualizar()` los read-modify-write del camino
      caliente: `api_esp32_current`, `_rfid_registrar_dispositivo`,
      `/rfid/firmware/version` (cierre de OTA), `_esp32_registrar_evento`,
      confirmaciones, `_pc_registrar`, `_test_encolar`, y todos los
      `_estado_*` del pick-to-light (`orden`, `encender`, `apagar`, `verificar`,
      aviso de gaveta, prueba LED remota). El de `orden` además solo escribe si
      algo cambió de verdad.
- [x] **1.4** `FW_VERSION` (app y RFID) cacheada por `mtime` (`_fw_version_de`);
      se acabó leer + regex de un `.py` de 1600 líneas en cada poll.
- [x] Extra: `.gitignore` cubre ahora todo el estado vivo de `data/*.json`
      (antes solo algunos; el resto se colaba al repo).

*Verificado:* `create_app` OK (218 rutas); `/api/esp32/current`,
`/api/esp32/rfid/gaveta/orden`, `/api/esp32/rfid/firmware/version`,
`/api/esp32/evento`, `/api/rfid/entrada/estado` responden 200 y dejan los JSON
de `data/` válidos. Falta la prueba en planta con varias placas reales.

### Fase 2 — Bajar la carga de sondeo  ·  HECHA (2026-09-11)

- [x] **2.1** `_expirar_logins_fantasma` con freno: se ejecuta como mucho cada
      30 s (`_EXPIRACION_CADA_S`) en el camino sondeado; `forzar=True` en login
      manual y entrada por tarjeta, donde el resultado tiene que ser inmediato.
      Antes: un `UPDATE` (escritor SQLite) por cada GET `/api/operarios/logins`
      (cada 750 ms/PC).
- [x] **2.2** `/api/esp32/current`: `last_seen` con granularidad de minuto y se
      salta la escritura entera si nada cambió (fw/nfc/ip/minuto). De ~8
      writes+fsync/s (8 carros) a ~8/min. El OTA pendiente y la asignación de
      carro se resuelven leyendo, sin escribir. (El `304` con `?ts=` de la placa
      queda para cuando se toque ese firmware; el ahorro grande ya está.)
- [x] **2.3 + 2.4** `lector_puesto.py`: sondeo de `/gaveta/orden` a 750 ms solo
      con trabajo activo (LED encendido o RFID armado); en reposo `GAVETA_POLL_IDLE_MS`
      (4 s) — en la LAN el encendido llega por empuje al puerto 80. Tras fallos
      seguidos se estira hasta `GAVETA_POLL_MAX_MS` (15 s). Baja el sondeo de
      fondo de ~13 req/s a ~2. **Requiere desplegar firmware (ver nota abajo).**
- [x] **2.5** `main_wifi.py` `POLL_INTERVAL` 1 s → 2 s (con 8 carros, la mitad
      de req/s de fondo; el OK del pulsador va por UART, no por el poll).
      `FW_VERSION` → `2026-09-11a`. **Requiere desplegar firmware.**

### Fase 3 — Servidor y navegador  ·  PARCIAL (3.2 pendiente)

- [x] **3.1** `waitress`: `threads=24`, `channel_timeout=60`, `connection_limit=300`.
      `busy_timeout` de SQLite 30 s → 10 s (en `connect_args` y en el `PRAGMA`
      del listener): fallar pronto y reintentar en vez de congelar un hilo.
- [ ] **3.2** Endpoint único `/api/puesto/tick?since=` que agrupe los sondeos del
      navegador (rfid entrada + logins + estado gaveta + bloqueos). **Pendiente
      a propósito**: toca `static/js/v3/*` (UI de planta) y es mejor hacerlo con
      alguien mirando. Ganancia esperada: ~4× menos req/s de navegador.
- [x] **3.3** `app/backup_auto.py`: hilo de fondo (arrancado desde `run_sql.py`,
      no en tests/wsgi) que cada `AUTO_BACKUP_HORAS` (6) copia `engastado.db`
      (vía `sqlite3.backup()`, seguro en caliente) + los JSON de estado a
      `data/backups_auto/backup_<sello>/`, conservando los últimos
      `AUTO_BACKUP_RETENER` (20). Probado: copia + `integrity_check` OK.
- [x] **3.4** `app/observabilidad.py`: cada petición que pasa de `SLOW_REQUEST_MS`
      (1 s) va al log como `LENTA <ms> <método> <ruta> -> <código>`; contador de
      carga por endpoint (ventana 5 min) en `GET /api/sistema/carga` (admin):
      req/s por endpoint, peor tiempo visto, nº de lentas.

### Nota — desplegar el firmware de las placas

Las placas siguen con el firmware viejo hasta que se despliega; nada de esto
llega solo. Al desplegar el servidor:

- **Carro (`main_wifi.py`):** el OTA lo sirve `_esp32_firmware_files` como
  `app.py` y lee `FW_VERSION` de ese mismo fichero → subir `FW_VERSION` (hecho,
  `2026-09-11a`) + desplegar servidor + verificar en Admin → Display Carro.
- **Lector RFID (`lector_puesto.py`):** OJO, hay un desajuste heredado — el OTA
  de `sistema.py` (`_rfid_firmware_files` / `_rfid_firmware_version`) sirve
  `esp32/main.py` (que **no tiene `FW_VERSION`** y parece el panel serie viejo),
  no `lector_puesto.py`. Antes de contar con que el backoff de gaveta llegue por
  OTA hay que aclarar cómo se instala hoy `lector_puesto.py` en las placas y
  apuntar ahí el `FW_VERSION` (subido a `2026-09-11a` en el fichero, por si el
  OTA se corrige, pero puede que hoy haya que flashear por USB).

### Fase 4 — Arquitectura (cuando Fases 1-3 estén asentadas)

- [ ] **4.1** Evaluar **conexión persistente** para las P4: MQTT (mosquitto en el
      mini-PC) o long-poll con keep-alive. La app publica cambios de
      `gaveta`/`current`; las placas se suscriben. Elimina ~21 req/s de sondeo y
      hace el pick-to-light instantáneo. Retained messages = último estado al
      reconectar.
- [ ] **4.2** Evaluar lectores RFID **por USB** al PC cliente (cableado, sin
      WiFi): más fiable, quita 10 estaciones WiFi. Implica un puente local
      PC↔lector (serie) y repensar `enviar_entrada`/gaveta desde el navegador.
- [ ] **4.3** Si se sigue con WiFi: SSID/VLAN dedicada para las ESP32, 2+ APs,
      plan de canales; `PM_NONE` ya está puesto en el firmware.
- [ ] **4.4** Valorar mover el estado JSON caliente a tablas SQLite (WAL ya
      activo) si en algún momento el servidor pasa a multi-proceso.

---

## Registro de avance

- **2026-09-11** — Plan creado. **Fase 1 completada** (estado compartido atómico
  y con candado, `FW_VERSION` cacheada, `.gitignore` al día).
- **2026-09-11** — **Fase 2 completada** (freno al barrido de logins, `/current`
  sin escritura si no cambia, backoff del sondeo de gaveta y del carro).
  **Fase 3 salvo 3.2**: waitress + `busy_timeout`, backup automático,
  observabilidad de peticiones lentas y carga por endpoint.
  Pendiente: **3.2** (endpoint `tick` del navegador — necesita a alguien mirando
  la UI) y **Fase 4** (MQTT / RFID-USB / VLAN — son decisiones, no código).
  Firmware cambiado (carro + lector): NO se aplica hasta desplegar; ver la nota
  de despliegue.
