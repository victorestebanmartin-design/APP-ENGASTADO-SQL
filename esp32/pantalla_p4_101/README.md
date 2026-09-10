# Panel de producción ESP32-P4-101CT-CLB

Pantalla grande (10,1") que va en el carro y muestra, sin que nadie la toque,
qué puestos tienen trabajo ahora mismo y en qué fase están.

## Qué hace

El carro (`esp32/micropython/main_wifi.py`) manda por UART una instantánea JSON
cada vez que cambia algo:

```json
{"v":1,"tipo":"estado","carro":"1","fw":"2026-09-10b","wifi":true,"sel":"puesto_3",
 "ops":[{"operario":"puesto_3","data":{"puesto_nombre":"MONTAJE 3","puesto_id":"puesto_3",
   "fase":"recoger","lote":"L-2231","boton":1,
   "paquetes":[{"etiqueta":"12","elem":"...","cod":"...","bloqueado":false}]}}]}
```

`fase` es `recoger` | `trabajando` | `devolver` | `fin`. Interfaz **apaisada**
(1280x800), **estilo oscuro a juego con la pantalla pequeña del carro**: fondo
negro, mismos acentos (verde recoger, ámbar en proceso, rojo devolver). La
cabecera lleva `COJO sw` + `ENGASTADO`, `CARRO N` centrado, la pastilla de WiFi
y la versión de firmware del carro.

**Refresco silencioso.** Se pinta a un frame buffer oculto y se vuelca de golpe
(`DrawToframebuffer(1)` → `DrawFrameBuffer(1)`), y solo cuando cambia el
contenido: se compara una huella (FNV) de lo que se va a mostrar con la
anterior. El carro reenvía la instantánea cada 5 s aunque no cambie nada
(para que una P4 recién reiniciada se recupere sola); esas tramas iguales no
repintan nada.

**Dos vistas, según `sel`** (la clave del puesto que se está mirando en detalle
en el carro; vacío = nadie identificado):

- **Lista** (`sel` vacío): una fila por puesto con trabajo — distintivo del
  botón, nombre, fase en pastilla de color y `N paq`. **No se ven los
  paquetes**: con dos o tres puestos activos a la vez sería un caos. Hasta 7
  filas; el resto se cuenta en el pie.
- **Detalle** (`sel` = clave de un puesto, tras pasar tarjeta o pulsar el botón
  en el carro): solo ese puesto, a pantalla completa, con un **mosaico de hasta
  5 paquetes** (etiqueta grande + elemento + código; franja roja si está
  bloqueado; `+N` si tiene más de 5). El carro pasa los paquetes de uno en uno
  por su pantalla pequeña; aquí se ven los cinco. Cuando el carro vuelve solo a
  la lista (a los `VOLVER_LISTA_S`), la P4 también.

Pie: `Conectado` (punto verde) mientras llegan tramas; si pasan 90 s sin
ninguna, `SIN DATOS DEL CARRO` en rojo con una línea de diagnóstico (bytes
recibidos por la UART y último error de parseo).

No confirma acciones: es un espejo. La confirmación sigue en los botones del
carro. El táctil de momento solo imprime coordenadas por el monitor serie.

## Hardware confirmado

- Placa: 4D Systems ESP32-P4 MIPI / ESP32-P4-101CT-CLB.
- Panel: 800 x 1280 nativo, se usa en apaisado (1280 x 800). LCD JD9365B (2 lanes
  MIPI-DSI), táctil GT911.
- UART de datos: P4 GPIO52 RX y GPIO50 TX.
  Carro GPIO45 TX -> P4 GPIO52 RX; carro GPIO46 RX <- P4 GPIO50 TX.
- Masa: P4 pin 3 o 4 a GND del carro. Los 5 V **no** se unen (cada placa con su
  fuente; la P4 por USB-PWR).
- Detalle completo del conector de 30 pines en `../HARDWARE_PANTALLA_P4_101.md`.

## Compilar y subir

No usa PlatformIO. `compilar.sh` llama al `arduino-cli` que trae el Arduino IDE
(mismo motor, misma config: core `esp32 3.3.7` y las librerías de
`~/Documents/Arduino/libraries`).

```bash
./compilar.sh          # solo compila
./compilar.sh COM6     # compila y sube (la P4 aparece como COM6)
```

Equivale, en el Arduino IDE, a seleccionar la placa **4D Systems ESP32-P4 MIPI
Displays**, Display Model **ESP32-P4-101CT-CLB** y Partition Scheme
**32M Flash (4.8MB APP / 24MB FATFS)**.

### Librerías necesarias

Ya instaladas en `~/Documents/Arduino/libraries`:

- `GFX4dESP32P4` — driver de 4D Systems (no está en registros; se copia a mano
  o se instala desde el Arduino IDE). https://github.com/4dsystems/GFX4dESP32P4
- `ArduinoJson` (>= 7) — parser de las tramas del carro.

## Primera carga

1. Desconectar los tres cables UART del carro durante la carga.
2. Conectar la P4 por USB y comprobar el puerto (COM6).
3. `./compilar.sh COM6`.
4. Monitor serie de UART0 a 115200: debe salir
   `P4 pantalla_p4_101 v6 (oscuro, refresco silencioso) ready` y la
   pantalla `Esperando al carro`.
5. Con ambas placas apagadas, conectar primero GND, luego el TX del carro al RX
   de la P4, y por último el TX de la P4 al RX del carro. Al llegar la primera
   instantánea la pantalla pasa a mostrar la lista de puestos.

## Si pone «SIN DATOS DEL CARRO»

El pie enseña `... N B ... <motivo>`:

- **`0 B`**: no entra nada por la UART. El carro no está enviando (sin WiFi no
  hace el poll al servidor y no manda nada; míralo en su propia pantalla), o el
  cable de su TX (GPIO45) al RX de la P4 (GPIO52) / la masa común está mal.
- **`N B` con `JSON err`**: llegan bytes pero no son una trama válida. Casi
  siempre baudios (los dos extremos a 115200) o masa flotante. El monitor serie
  de UART0 imprime `raw:` con los primeros bytes en hexadecimal.
- **`N B` con `OK …` pero el pie sigue en rojo**: llegó una trama buena pero
  hace más de 90 s que no llega otra (el carro reenvía cada 5 s, así que esto
  significa que ha dejado de emitir).

### Ruido en la línea RX

En reposo la línea RX de la P4 recoge basura (masa larga, cable sin apantallar):
antes de cada trama buena entran unos bytes sueltos. El firmware lo lleva —
solo empieza a acumular al ver la `{` que abre el JSON y descarta cualquier
parcial que se quede quieto más de 150 ms— así que la pantalla funciona igual.
Pero el arreglo de verdad es eléctrico: **masa común corta y directa entre las
dos placas**, cable de datos corto y, si aún así hay fallos sueltos, bajar la
UART a 57600 o 38400 en los dos extremos. Un byte de ruido colado en mitad de
una trama sí la tira (hasta la siguiente).

### Serie por USB para depurar

Con la config normal, `Serial` sale por los pines de UART0, no por el USB. Para
ver los logs en el COM del PC hay que compilar una vez con
`USBMode=hwcdc,CDCOnBoot=cdc` añadido al FQBN (menús *USB Mode → Hardware CDC and
JTAG* y *CDC On Boot → Enabled* en el Arduino IDE). `compilar.sh` usa la config
normal, así que al reflashear con él vuelve a quedar sin consola USB.
