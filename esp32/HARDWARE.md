# Hardware: Display gen4-ESP32-24 (4D Systems)

Documentación de la parte física de la pantalla de producción: qué placa es,
cómo está alimentada, qué pads de la extensora están ocupados y cuáles quedan
libres para ampliar (más pulsadores, sensores, etc.).

El firmware que corre en esta placa está en `esp32/micropython/main_wifi.py`.

## Hardware

| Componente | Referencia / Modelo |
|---|---|
| Display | 4D Systems **gen4-ESP32-24** — 2.4", 240x320, IPS TFT, sin touch |
| Procesador integrado | Espressif **ESP32-S3R8** (8MB PSRAM Octal SPI + 16MB Flash Quad SPI externa) |
| Interfaz de expansión | Conector **FFC de 30 vías, paso 0.5mm**, tipo "Opposite" |
| Breakout usado | 4D Systems **gen4-Breakout** — saca las 30 señales de la faja a 30 pads (15 por lado), paso 2.54mm |
| Alimentación | Power Bank **Ansmann PB2xx, 20.000 mAh**, salida USB-A 5V/2A, con **carga pasante** (pass-through) |
| Conexión de alimentación | Power Bank → cable USB-A a USB-C → **interruptor intercalado en el hilo VBUS** → USB-C del display |
| Tensión de alimentación del display | 4.0V – 6.0V (nominal 5V), pines "5V IN" del FFC (no usados en este montaje; se alimenta por USB-C directo) |
| Consumo típico | ~149 mA (sin WiFi, contraste 15) — con WiFi activo, estimado 250-400 mA |

## Pines en uso en la gen4-Breakout

Numeración = pin de la faja FFC de 30 vías.

| Pad | Señal | Función en el proyecto |
|---|---|---|
| 1, 21, 25, 30 | GND | Masa común (pulsadores, zumbador, EN-RST) |
| 2 | GPIO17 | Pulsador 1 (a GND, `INPUT_PULLUP`) — operario: corta = siguiente operario, larga = deshacer (`BTN_OP_PIN`) |
| 3 | GPIO18 | Zumbador (`BUZZER_PIN` en el firmware; verificar si activo/pasivo — si activo, usar transistor NPN) |
| 4 | GPIO16 | Pulsador 2 (a GND, `INPUT_PULLUP`) — confirmación: larga = revelar y confirmar el grupo, corta = "me llevo los paquetes" (`BTN_ENT_PIN`) |
| 22 | EN-RST | Interruptor de apagado alternativo (a GND desactiva el ESP32-S3; no confirmado si corta retroiluminación) |
| 20 | 3.3V | Salida 3.3V disponible para el usuario (máx. recomendado 100-200mA) |

## Próximos GPIO libres disponibles

Sin función reservada de fábrica:

| Pad | GPIO | Observaciones |
|---|---|---|
| 5 | GPIO15 | Entrada analógica |
| 6 | GPIO48 | |
| 7 | GPIO47 | |
| 8 | GPIO38 | |
| 9 | GPIO39 | |
| 10 | GPIO40 | |
| 11 | GPIO6 | Entrada analógica |
| 12 | GPIO5 | Entrada analógica — ⚠️ es el `BUTTON_PIN` opcional del firmware (botón genérico); libre si no se cablea ese botón |
| 13 | GPIO3 | Entrada analógica — ⚠️ strapping del S3 (JTAG), no forzar nivel en el arranque |
| 14 | GPIO45 | ⚠️ strapping del S3 (VDD_SPI), no forzar nivel en el arranque |
| 15 | GPIO46 | ⚠️ strapping del S3 (modo boot junto a GPIO0), no forzar nivel en el arranque |

Los pines de strapping funcionan como GPIO normales una vez arrancado, pero si
algo externo los deja a un nivel fijo durante el encendido la placa puede no
arrancar o arrancar en modo raro. Para pulsadores con pull-up (reposo = 3.3V)
suelen valer; para cargas que fijan nivel, mejor usar antes 48/47/38/39/40.

## Ampliación a 8 pulsadores (plan de cableado)

Con 2 pulsadores ya montados (pads 2 y 4) quedan 6 por soldar. Los seis pads
siguientes son GPIOs limpios (sin strapping, sin función reservada) y además
están **todos en la misma fila** del breakout que los dos ya montados
(pads 1–15 comparten lado), así que sale una tira ordenada.

| Pulsador | Pad | GPIO | Estado |
|---|---|---|---|
| 1 | 2 | GPIO17 | ✅ montado — operario |
| 2 | 4 | GPIO16 | ✅ montado — confirmación |
| 3 | 5 | GPIO15 | por soldar |
| 4 | 6 | GPIO48 | por soldar |
| 5 | 7 | GPIO47 | por soldar |
| 6 | 8 | GPIO38 | por soldar |
| 7 | 9 | GPIO39 | por soldar |
| 8 | 10 | GPIO40 | por soldar |

Quedan **libres de reserva** los pads 11 (GPIO6) y 12 (GPIO5) por si algún
pulsador da problemas o hace falta un noveno. Los pads 13, 14 y 15 (GPIO3,
GPIO45, GPIO46) se dejan como último recurso por ser de strapping.

**Cableado.** Cada pulsador va entre su pad y GND, con `Pin.IN, Pin.PULL_UP`
(reposo = 1, pulsado = 0). No hace falta resistencia externa para que funcione.
Los 8 comparten una única línea de masa: hay GND en los pads **1, 21, 25 y 30**
— el pad 1 está justo al lado de la tira, así que lo natural es sacar de ahí un
hilo común a todos los pulsadores y dejar 21/25/30 libres.

**En taller (recomendado si los cables pasan de ~30 cm o van cerca de las
engastadoras).** El pull-up interno del S3 es débil (~45 kΩ) y capta ruido de
cargas inductivas:

- Un condensador de **100 nF** en paralelo con cada pulsador (entre pad y GND)
  mata los rebotes y buena parte del ruido.
- Opcionalmente una resistencia de **4,7–10 kΩ** de cada pad a 3.3V (pad 20),
  en paralelo con el pull-up interno: baja la impedancia y hace la línea mucho
  más inmune.
- Mejor cable trenzado o con la masa acompañando a cada señal que hilos sueltos.

El firmware ya hace antirrebote por software (250 ms entre pulsaciones), así que
si los cables son cortos y limpios puedes empezar sin nada de esto y añadirlo
solo si ves pulsaciones fantasma.

## Pines a evitar (función reservada o comparten hardware)

| Pad | Señal | Motivo |
|---|---|---|
| 16, 17, 18 | GPIO20, GPIO19, GPIO11 | No conectados a la faja por defecto (USB-C nativo y reset del touch); requieren modificación de hardware (R25/R23, R26/R22, R9/R8) |
| 19 | GPIO0 | Strapping de arranque — no llevar a LOW al encender |
| 23, 24 | U0RXD, U0TX0 | UART de programación (GPIO44/43) — reservados salvo que se liberen por software |

## GPIOs internos del display (no salen a la faja)

Ocupados por el propio módulo; el firmware los reserva y no deben tocarse:

| GPIO | Función |
|---|---|
| 4 | Backlight (retroiluminación ON/OFF) |
| 7, 21 | Control del TFT (DC / CS) |
| 12, 13, 14 | SPI del TFT (MISO / MOSI / SCK) |

## Pinout completo del conector FFC de 30 vías (referencia)

```
1  GND        11 GPIO6(A)   21 GND
2  GPIO17(A)  12 GPIO5(A)   22 EN-RST
3  GPIO18(A)  13 GPIO3(A)   23 U0RXD (GPIO44)
4  GPIO16(A)  14 GPIO45     24 U0TX0 (GPIO43)
5  GPIO15(A)  15 GPIO46     25 GND
6  GPIO48     16 GPIO20*    26 5V IN
7  GPIO47     17 GPIO19*    27 5V IN
8  GPIO38     18 GPIO11*    28 5V IN
9  GPIO39     19 GPIO0      29 5V IN
10 GPIO40     20 3.3V       30 GND
(A) = capaz de entrada analógica
*   = requiere modificación de hardware para acceder desde la faja
```

## Correspondencia con el firmware (`main_wifi.py`)

| Constante | Valor actual | Pad de la extensora |
|---|---|---|
| `BTN_OP_PIN` | GPIO17 | Pad 2 — pulsador 1 (operario): corta = siguiente operario, larga (1s) = deshacer |
| `BTN_ENT_PIN` | GPIO16 | Pad 4 — pulsador 2 (confirmación): larga (1s) = revelar y confirmar el grupo (con barra de progreso), corta = "me llevo los paquetes" |
| `BUZZER_PIN` | GPIO18 | Pad 3 — zumbador (`BUZZER_PASIVO = False` → activo de 3.3V) |
| `BUTTON_PIN` | GPIO5 | Pad 12 — botón genérico opcional (sin cablear actualmente) |

### Confirmación física del lote

El PC no deja empezar un grupo de paquetes hasta que el operario ha estado en el
carro. El circuito completo:

1. En el PC se elige terminal y carro; el modal muestra el grupo con el botón
   **"Tengo estos N, empezar" bloqueado**.
2. La pantalla del carro avisa (sonido de atención cada 25 s) con
   `GRUPO n/N — MANTÉN EL BOTÓN`, **sin desvelar todavía los paquetes**.
3. El operario mantiene el **pulsador 2** un segundo (barra de progreso en
   pantalla). La pantalla revela los paquetes y manda
   `GET /api/esp32/evento?tipo=confirmacion&carro=…&operario=…&lote=…`.
4. El PC, que sondea `/api/esp32/estado-carro` cada 2 s, desbloquea el botón.
5. Al pulsar "Siguiente grupo" se genera un lote nuevo y se repite desde el 2.

Si la pantalla no responde, el PC ofrece un enlace para confirmar manualmente
(se registra como `confirmacion_manual`): el trabajo nunca se bloquea del todo.
Los eventos quedan en `data/esp32_eventos.json` (últimos 100) y la última
confirmación de cada `(carro, operario)` en `data/esp32_confirmaciones.json`.

### Sonidos del zumbador

Con un zumbador **activo** la frecuencia es fija (las notas no se distinguen),
así que cada aviso se reconoce por **ritmo y textura** (`tono` = liso,
`trino` = cortes rápidos, suena rasposo). Con un piezo pasivo
(`BUZZER_PASIVO = True`) los mismos patrones suenan además como melodías.

| Evento | Patrón |
|---|---|
| Arranque | trino corto + nota |
| Cambio de operario | tic seco de 22 ms |
| Contenido actualizado | tic casi imperceptible (14 ms) |
| Grupo esperando en el carro | tres golpes separados, se repite cada 25 s |
| Grupo revelado y confirmado | fanfarria ascendente de tres notas |
| "Me llevo los paquetes" | dos golpes descendentes |
| Deshacer | trino largo y grave ("rebobinar") |
| Llegan paquetes en reposo | melodía de cuatro notas, la llamada más larga |
| Gesto no válido | dos zumbidos rasposos y graves |

## Notas de la sesión

- Pendiente de decidir/verificar: si el zumbador es activo o pasivo, para saber
  si hace falta transistor de conmutación. (El firmware asume activo:
  `BUZZER_PASIVO = False`.)
- No hay forma fiable de leer el % de batería de la power bank por software
  (es una caja cerrada); se descartó instrumentar esto.

---
*Generado a partir de la documentación oficial de 4D Systems (gen4-ESP32 Series
Datasheet R1.2) y MikroElektronika.*
