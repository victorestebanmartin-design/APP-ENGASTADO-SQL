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
| 2 | GPIO17 | Pulsador 1 (a GND, `INPUT_PULLUP`) — operario: corta = siguiente operario, larga = deshacer entregas (`BTN_OP_PIN`) |
| 3 | GPIO18 | Zumbador (`BUZZER_PIN` en el firmware; verificar si activo/pasivo — si activo, usar transistor NPN) |
| 4 | GPIO16 | Pulsador 2 (a GND, `INPUT_PULLUP`) — entrega: corta = "me llevo los paquetes", larga = confirmar entrega-devolución (`BTN_ENT_PIN`) |
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
| `BTN_OP_PIN` | GPIO17 | Pad 2 — pulsador 1 (operario): corta = siguiente operario, larga (1s) = deshacer entregas/devoluciones |
| `BTN_ENT_PIN` | GPIO16 | Pad 4 — pulsador 2 (entrega): corta = "me llevo los paquetes" (ENTREGADO), larga (1s) = entrega-devolución (DEVUELTO + evento `/api/esp32/evento` al servidor, pendiente de vincular con la liberación de bloqueos) |
| `BUZZER_PIN` | GPIO18 | Pad 3 — zumbador (`BUZZER_PASIVO = False` → activo de 3.3V) |
| `BUTTON_PIN` | GPIO5 | Pad 12 — botón genérico opcional (sin cablear actualmente) |

## Notas de la sesión

- Pendiente de decidir/verificar: si el zumbador es activo o pasivo, para saber
  si hace falta transistor de conmutación. (El firmware asume activo:
  `BUZZER_PASIVO = False`.)
- No hay forma fiable de leer el % de batería de la power bank por software
  (es una caja cerrada); se descartó instrumentar esto.

---
*Generado a partir de la documentación oficial de 4D Systems (gen4-ESP32 Series
Datasheet R1.2) y MikroElektronika.*
