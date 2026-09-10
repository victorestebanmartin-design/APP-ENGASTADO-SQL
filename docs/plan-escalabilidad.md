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

### Fase 2 — Bajar la carga de sondeo

- [ ] **2.1** `_expirar_logins_fantasma`: pasar de por-petición a barrido periódico
      (hilo de fondo cada 30-60 s, o `maintenance.py`).
- [ ] **2.2** `/api/esp32/current`: no reescribir `esp32_devices.json` si
      `last_seen` no cambió de minuto; responder `304` si el `ts` que trae la
      placa ya coincide (la placa manda `?ts=`).
- [ ] **2.3** Backoff del sondeo de gaveta en la placa: 750 ms con LED encendido,
      3-5 s en reposo. (firmware `lector_puesto.py`)
- [ ] **2.4** Backoff/tope de reintento en el bucle de gaveta cuando el servidor
      no responde (hoy no lo tiene; una placa en reinicio-bucle machaca el server).
- [ ] **2.5** Subir `POLL_INTERVAL` del carro de 1 s a 2-3 s.

### Fase 3 — Servidor y navegador

- [ ] **3.1** `waitress`: `threads=24`, `channel_timeout` sensato; `busy_timeout`
      de SQLite a 5 s (fallar rápido y reintentar, no congelar un hilo 30 s).
- [ ] **3.2** Endpoint único `/api/puesto/tick?since=` que agrupe los sondeos del
      navegador (rfid entrada + logins + estado gaveta + bloqueos). Adaptar los
      timers de `static/js/v3/*` para que llamen a uno solo.
- [ ] **3.3** Copia de seguridad programada del `.db` + los JSON de `data/`
      (hoy no hay ninguna; con esta escala ya es crítico).
- [ ] **3.4** Métricas mínimas: log de peticiones lentas y contador req/s por
      endpoint, para tener datos cuando planta diga "va lento".

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
  y con candado, `FW_VERSION` cacheada, `.gitignore` al día). Siguiente: Fase 2.
