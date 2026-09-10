# Panel de producción ESP32-P4-101CT-CLB

Pantalla grande (10,1") que va en el carro y muestra, sin que nadie la toque,
qué puestos tienen trabajo ahora mismo y en qué fase están.

## Qué hace

El carro (`esp32/micropython/main_wifi.py`) manda por UART una instantánea JSON
cada vez que cambia algo:

```json
{"v":1,"tipo":"estado","carro":"1","fw":"2026-09-01a","wifi":true,
 "ops":[{"operario":"clave","data":{"puesto_nombre":"MONTAJE 3","fase":"recoger",
         "lote":"L-2231","paquetes":[...]}}]}
```

`fase` es `recoger` | `trabajando` | `devolver` | `fin`. La interfaz usa la
identidad del SW web (COJO): fondo claro y cabecera azul en degradado.

- Cabecera: marca `COJO sw`, `Carro N`, pastilla de estado WiFi y versión de
  firmware del carro.
- Una tarjeta blanca por puesto (máximo 5 visibles): nombre, lote, la fase en
  una pastilla de color (ámbar recoger, azul en proceso, verde devolver, gris
  finalizado) y el número de paquetes en grande.
- Pie: `Conectado — hace N s` mientras llegan tramas (el contador se refresca
  cada segundo); si pasan 90 s sin nada, `SIN DATOS DEL CARRO` en rojo. Si el
  carro tiene más de 5 puestos, el pie indica cuántos quedan sin mostrar.

No confirma acciones: es un espejo. La confirmación sigue en los botones del
carro. El táctil de momento solo imprime coordenadas por el monitor serie.

## Hardware confirmado

- Placa: 4D Systems ESP32-P4 MIPI / ESP32-P4-101CT-CLB.
- Panel: 800 x 1280, orientación vertical. LCD JD9365B (2 lanes MIPI-DSI),
  táctil GT911.
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
4. Monitor serie de UART0 a 115200: debe salir `P4 pantalla_p4_101 v3 (UI) ready`
   y la pantalla `Esperando al carro`.
5. Con ambas placas apagadas, conectar primero GND, luego el TX del carro al RX
   de la P4, y por último el TX de la P4 al RX del carro. Al llegar la primera
   instantánea la pantalla pasa a mostrar la lista de puestos.
