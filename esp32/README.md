# ESP32 RFID Reader - Engastado V3 Entry System

Placa lectora RFID (ESP32 DevKit V1 Type-C + RC522) para identificar operarios
a la entrada del puesto de Engastado V3. Confirma con un zumbador y manda la
lectura al backend (la misma app Flask/SQLite -- COJOsw -- que ya usa el resto
del sistema, desplegada en PythonAnywhere).

Incluye **actualizacion por WiFi (OTA)**: una vez instalada la placa, para
cambiar su codigo basta con editar `esp32/main.py` en este repo, desplegar
como siempre (`deploy.py`) y la placa se actualiza sola en su siguiente
comprobacion -- sin volver a tocar el cable USB. Esto es lo que resuelve el
problema de gestionarla desde un PC corporativo sin permisos de driver ni
salida a puertos no estandar: todo el trafico (lectura RFID y OTA) va por
HTTPS 443 hacia PythonAnywhere, que es lo unico que ese PC ya tiene garantizado.

## Arquitectura: que se actualiza por USB y que por OTA

| Fichero | Como se instala | Por que |
|---|---|---|
| `boot.py` | **USB, una vez** | Conecta el WiFi y dispara el OTA. Si un OTA rompiera este fichero, la placa no podria ni comprobar actualizaciones -- por eso nunca se toca por WiFi. |
| `ota_update.py` | **USB, una vez** | El propio mecanismo de OTA. Mismo motivo que `boot.py`. |
| `http_client.py` | **USB, una vez** | Cliente HTTPS del que dependen `main.py` y `ota_update.py`. |
| `wifi_config.py` | **USB, una vez** | Credenciales WiFi/WebREPL y configuracion del backend. Contiene secretos: no se sube por OTA ni se commitea con valores reales. |
| `lib/mfrc522.py` | USB inicialmente, **actualizable por OTA** despues | Driver del lector. Se incluye en el manifiesto OTA por si hiciera falta un fix sin pasar por USB. |
| `main.py` | USB inicialmente, **actualizable por OTA** despues | La logica de la placa (leer RFID, avisar con el zumbador, mandar la lectura). Esto es lo que cambiaras normalmente. |

El patron (descargar y verificar TODO antes de tocar nada, con copia de
seguridad y rollback automatico si el nuevo `main.py` no arranca) es el mismo
que ya usa la pantalla del carro (`esp32/micropython/main_wifi.py`), asi que
esta ya probado en produccion.

## Registro y asignacion a puesto (Admin -> Lectores RFID)

Cada lector se registra solo en el servidor -- sin ningun paso manual -- la
primera vez que comprueba si hay firmware nuevo (llamada que ya hace sola,
por defecto cada minuto: ver `OTA_CHECK_INTERVAL_MS` en `wifi_config.py`).
Esa misma llamada sirve de "estoy vivo": Admin -> Lectores RFID lo marca
🟢 en linea mientras siga llegando.

Desde ahi se le puede:
- Poner un **nombre** (para identificarlo en la lista; por defecto solo se ve
  el ID, los ultimos 4 caracteres de su MAC).
- **Asignar un puesto**. Un lector sin puesto asignado sigue funcionando
  igual que antes (identifica al operario y el PC le pide el puesto a mano).
  Un lector **con** puesto asignado hace que, al pasar la tarjeta, el PC
  reciba tambien ese puesto y se salte el paso de elegirlo -- va directo a
  pedir el bono y abrir el puesto. Esto es lo pensado para cuando haya un
  lector fisico en cada puesto: cada uno solo identifica al operario Y dice
  automaticamente donde esta.

Esto no requiere ningun cambio en `esp32/main.py`: el lector manda su
`device_id` (la MAC del chip) en cada lectura y el servidor resuelve el
puesto por su cuenta a partir de la asignacion guardada en Admin. Si el
lector no esta asignado a ningun puesto, la respuesta simplemente no trae
puesto y el PC sigue el flujo manual de siempre.

## Hardware Setup

### Wiring Diagram

**RC522 RFID Reader -> ESP32 DevKit V1 Type-C**

```
RC522 Pin    ESP32 Pin    GPIO    Purpose
VCC          3.3V (pin 3)         Power
GND          GND (pin 1)          Ground
SDA          GPIO 5               SPI Chip Select (CS)
SCK          GPIO 18              SPI Clock (CLK)
MOSI         GPIO 23              SPI Master Out Slave In (MOSI)
MISO         GPIO 19              SPI Master In Slave Out (MISO)
RST          GPIO 22              Reset
IRQ          (no se usa)
```

**Buzzer (activo)**

```
Buzzer Pin   ESP32 Pin    Purpose
+ (Red)      GPIO 26      Senal (con resistencia de 100ohm si es de 5V)
- (Black)    GND          Ground
```

### Componentes necesarios

- ESP32 DevKit V1 Type-C
- Modulo RC522
- Zumbador activo (5V o 3.3V)
- Resistencia de 100ohm (solo si el zumbador es de 5V)
- Cable USB Type-C (para el primer flasheo y subida de ficheros)
- Red WiFi con salida a internet (para llegar a PythonAnywhere por HTTPS)

## Instalacion (pasos manuales, una unica vez)

Todo esto se hace **en un PC libre** con acceso USB a la placa (no en el PC
corporativo, que tiene el driver CP210x bloqueado).

### 1. Flashear MicroPython

```bash
pip install esptool
# Descarga la version estable para ESP32 generico desde
# https://micropython.org/download/esp32/
esptool.py erase_flash
esptool.py write_flash -z 0x1000 esp32-XXXXXXXX-vX.XX.X.bin
```

### 2. Rellenar `wifi_config.py` con tus credenciales reales

Copia `esp32/wifi_config.py` de este repo a tu maquina y edita **tu copia
local** (no la subas a git con los valores reales):

```python
SSID = "TuRedWiFi"
PASSWORD = "TuContrasenaWiFi"
WEBREPL_PASSWORD = "TuContrasenaWebREPL"   # 4-9 caracteres, la que ya usabas
```

`BACKEND_HOST`/`BACKEND_PORT`/`BACKEND_USE_SSL` ya apuntan a
`viktor85.pythonanywhere.com:443` -- no hace falta tocarlos salvo que cambie
el dominio de PAW.

### 3. Subir los ficheros base por USB

Con `mpremote` (o Thonny, si lo prefieres):

```bash
pip install mpremote

mpremote connect COM5 cp esp32/boot.py :boot.py
mpremote connect COM5 cp esp32/ota_update.py :ota_update.py
mpremote connect COM5 cp esp32/http_client.py :http_client.py
mpremote connect COM5 cp wifi_config_con_tus_credenciales.py :wifi_config.py
mpremote connect COM5 mkdir :lib
mpremote connect COM5 cp esp32/lib/mfrc522.py :lib/mfrc522.py
mpremote connect COM5 cp esp32/main.py :main.py
mpremote connect COM5 reset
```

(Cambia `COM5` por el puerto que te asigne Windows, o `/dev/ttyUSB0` en
Linux/Mac.)

### 4. Verificar en el monitor serie

Abre un monitor serie a 115200 baudios (Thonny, `mpremote connect COM5`, o
`screen`/`putty`) y deberias ver algo asi:

```
Conectando WiFi...
WiFi OK: ('192.168.1.50', '255.255.255.0', '192.168.1.1', '8.8.8.8')
OTA: version nueva disponible: 2026-08-12a (actual: ninguna)
OTA: actualizado a 2026-08-12a - reiniciando
...
Placa RFID Engastado V3 - version 2026-08-12a
Esperando lectura de tarjeta...
```

La primera vez es normal ver un OTA nada mas arrancar: la placa aun no tiene
version local guardada, asi que se "actualiza" a la version publicada
(aunque sea la misma que le subiste por USB) para fijar `version.txt`.

## Publicar una actualizacion (desde entonces, ya no hace falta USB)

1. Edita `esp32/main.py` en este repo (o `esp32/lib/mfrc522.py` si tocara el
   driver).
2. **Sube `FW_VERSION`** al principio de `esp32/main.py` (p.ej.
   `"2026-08-13a"`). Es la unica senal que usa la placa para saber que hay
   algo nuevo -- si no cambias esta linea, el OTA no se dispara.
3. Commit + push + despliegue habitual (`deploy.py`, igual que siempre).
4. La placa se actualiza sola:
   - En su siguiente arranque (corte de luz, reset manual), o
   - En la siguiente comprobacion periodica (cada
     `OTA_CHECK_INTERVAL_MS` de `wifi_config.py`, 1 hora por defecto).

No hace falta tocar la placa fisicamente para nada de esto.

## Registro de tarjetas RFID de operarios

Antes de que un operario pueda usar la placa, su tarjeta debe tener el UID
guardado en `operarios.tag_uid` (columna que ya existe en el sistema, la
misma que usa el login por NFC del carro).

### Averiguar el UID de una tarjeta

Con la placa conectada por USB y el monitor serie abierto, apoya la tarjeta:
el log muestra `Tarjeta detectada: A1B2C3D4`.

### Darla de alta

Desde Admin -> Operarios (si el panel lo permite), o directamente en la base
de datos:

```sql
UPDATE operarios SET tag_uid = 'A1B2C3D4' WHERE nombre = 'Juan Perez';
```

## Comportamiento del firmware

### Funcionamiento normal

1. El operario pasa su tarjeta por el lector.
2. La placa lee el UID y hace `POST /api/puestos/engastado_v3/entrada` con el
   UID y su propio `device_id` (la MAC del chip).
3. **Exito (200):** 2 pitidos + LED, la interfaz V3 detecta el login solo. Si
   el lector tiene un puesto asignado (Admin -> Lectores RFID), el PC recibe
   tambien ese puesto y se salta el paso de elegirlo a mano.
4. **Tarjeta no registrada / ya dentro en otro puesto (404/409):** 1 pitido.
5. **Fallo de red:** 5 pitidos, se puede reintentar al momento (no hay estado
   que limpiar).

### Antirrebote

Minimo 2 segundos entre lecturas (`DEBOUNCE_MS` en `wifi_config.py`) para no
duplicar la misma pasada de tarjeta.

### Seguridad ante fallos de OTA

- Se descarga y verifica (tamano + sha256) TODO antes de tocar nada: un corte
  de red a mitad de la descarga deja el firmware actual intacto.
- Si el `main.py` nuevo no llega a arrancar 3 veces seguidas, `boot.py`
  restaura la version anterior solo (rollback), sin intervencion manual.
- Un corte de luz que reinicie la placa a mitad de trabajo NO cuenta como
  fallo de arranque (solo cuenta si `main.py` no llega a entrar en su bucle
  principal).

## Resolucion de problemas

### La placa no conecta a WiFi

- Revisa `SSID`/`PASSWORD` en tu copia de `wifi_config.py` (subida por USB).
- Prueba con una red de 2.4GHz (el ESP32 clasico no soporta 5GHz).

### "Tarjeta detectada" pero no llega nada al servidor

- Comprueba que la placa tiene salida a internet (no solo a la red local):
  el backend es `viktor85.pythonanywhere.com` por HTTPS, no una IP local.
- Revisa el log del monitor serie: `http_client` imprime el motivo del fallo.

### El zumbador no suena

- Revisa el cableado: `+` a GPIO 26, `-` a GND.
- Prueba a mano: `from machine import Pin; Pin(26, Pin.OUT).on()`.

### El lector RFID no responde

- Repasa el cableado SPI: CS=5, SCK=18, MOSI=23, MISO=19, RST=22.
- Alimentacion del RC522 a 3.3V, nunca a 5V (se puede danar).
- Prueba con otra tarjeta (algunos tags no son compatibles con MIFARE
  Classic, que es lo que soporta este lector).

### La placa se quedo "vieja" y no se actualiza

- Comprueba `GET https://viktor85.pythonanywhere.com/api/esp32/rfid/firmware/version`
  desde un navegador: debe devolver la `FW_VERSION` que pusiste en
  `esp32/main.py` tras el ultimo deploy.
- Por USB, revisa `version.txt` en la placa (`mpremote connect COM5 cat version.txt`)
  para ver que version cree tener instalada.

## Ficheros de este directorio

- `boot.py` -- arranque: WiFi, WebREPL, dispara el OTA. **USB, no se toca por OTA.**
- `ota_update.py` -- logica de comprobar/descargar/aplicar/revertir el OTA. **USB, no se toca por OTA.**
- `http_client.py` -- cliente HTTP/HTTPS minimo sin dependencias externas. **USB, no se toca por OTA.**
- `wifi_config.py` -- credenciales y configuracion. **USB, no se toca por OTA, no se commitea con secretos reales.**
- `lib/mfrc522.py` -- driver del lector RC522 (vendorizado, MIT license). Actualizable por OTA.
- `main.py` -- logica de la placa (RFID + zumbador + POST). **Esto es lo que se actualiza por OTA.**

## Backend (referencia)

Endpoints implicados, todos en `app/routes/`:

- `POST /api/puestos/engastado_v3/entrada` (`app/routes/operarios.py`) -- recibe la lectura RFID (+ `device_id`), resuelve el login del operario y, si el lector tiene puesto asignado, lo devuelve tambien.
- `GET /api/esp32/rfid/firmware/version` (`app/routes/sistema.py`) -- version y manifiesto disponibles; con `?id=&ip=&fw=` tambien registra/actualiza el lector (latido).
- `GET /api/esp32/rfid/firmware/file?name=X` (`app/routes/sistema.py`) -- sirve un fichero del firmware.
- `GET /api/esp32/rfid/devices` (Admin) -- lista de lectores detectados + puestos disponibles, para Admin -> Lectores RFID.
- `POST /api/esp32/rfid/devices/<device_id>` (Admin) -- asigna nombre y/o puesto a un lector.
- `DELETE /api/esp32/rfid/devices/<device_id>` (Admin) -- olvida un lector (vuelve a aparecer solo si sigue encendido).

## Referencias

- Documentacion MicroPython: https://docs.micropython.org
- Driver MFRC522 original: https://github.com/wendlers/micropython-mfrc522 (MIT License)
- Pinout ESP32: https://randomnerdtutorials.com/esp32-pinout-reference-gpios/
