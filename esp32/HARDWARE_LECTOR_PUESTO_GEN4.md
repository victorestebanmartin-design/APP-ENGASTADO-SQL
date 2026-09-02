# Hardware: lector RFID de puesto gen4-ESP32-24

Esta caja sustituye gradualmente el lector de entrada basado en ESP32 DevKit
y RC522. Usa la pantalla 4D Systems gen4-ESP32-24, un PN532, un zumbador y un
DB9 reservado para el multiplexor. El firmware es
`esp32/micropython/lector_puesto.py`.

No es una pantalla de carro: no lleva pulsadores ni ejecuta la seleccion,
recogida o devolucion de paquetes. Lee la tarjeta del operario, manda su UID
al servidor y muestra aceptacion, rechazo o error tecnico.

## Alimentacion

Alimentar la gen4 mediante USB-C a 5 V. Intercalar el interruptor en el hilo
VBUS del cable USB-C, no en EN-RST: asi se apagan tambien el PN532 y el
zumbador. El DB9 no transporta alimentacion.

## Cableado en la gen4-Breakout

| Componente | Senal | Pad | GPIO |
|---|---|---:|---:|
| PN532 en modo I2C | SDA | 11 | GPIO6 |
| PN532 en modo I2C | SCL | 12 | GPIO5 |
| PN532 | VCC | 20 | 3.3 V |
| PN532 | GND | 21, 25 o 30 | GND |
| Zumbador activo 3.3 V | positivo | 3 | GPIO18 |
| Zumbador | negativo | 1, 21, 25 o 30 | GND |

El PN532 debe estar configurado en modo I2C. Colocar un condensador de 100 uF
en paralelo con uno ceramico de 100 nF entre VCC y GND, pegados al modulo. Si
la pantalla se reinicia al leer, alimentar el VCC del PN532 desde 5 V USB solo
si el modulo concreto confirma que incorpora regulador y admite 5 V.

Montar la antena lejos de chapa y del TFT. Sobre metal, usar separador de
plastico de 1-2 cm o una lamina de ferrita.

## DB9 de expansion para multiplexor

El DB9 es una interfaz digital de 3.3 V. No es RS-232, no es RS-485 y no lleva
5 V. Nunca conectar una carga, una fuente externa o un puerto serie RS-232
directamente a sus pines.

| DB9 | Senal gen4 | Uso reservado |
|---:|---|---|
| 1 | GND | Masa de referencia |
| 2 | GPIO17 (pad 2) | Linea 1 |
| 3 | GPIO16 (pad 4) | Linea 2 |
| 4 | GPIO15 (pad 5) | Linea 3 |
| 5 | GPIO48 (pad 6) | Linea 4 |
| 6 | GPIO47 (pad 7) | Linea 5 |
| 7 | GPIO38 (pad 8) | Linea 6 |
| 8 | GPIO39 (pad 9) | Linea 7 |
| 9 | GPIO40 (pad 10) | Linea 8 |

Para el cable previsto de 1-5 m, colocar dentro de la caja una placa de
interfaz entre cada GPIO y el DB9: resistencia serie de 100-330 ohm, proteccion
ESD/TVS hacia GND y un buffer de 3.3 V adecuado a la direccion que defina el
multiplexor. Mantener los GPIO como entradas con alta impedancia hasta definir
el protocolo, para que el DB9 no active nada durante el arranque.

No usar GPIO0, GPIO3, GPIO45 ni GPIO46: son pines de strapping. No usar
GPIO43/GPIO44: son el UART de programacion. Si el multiplexor definitivo pide
RS-232, RS-485, 5 V o mas distancia, sustituir la interfaz de DB9 por el
transceptor o bus adecuado; no alterar este cableado de la pantalla.

## Primera puesta en marcha

1. Grabar MicroPython para ESP32-S3 con PSRAM Octal en la gen4.
2. En Admin -> Lectores RFID -> Configurar y subir por USB, elegir
   `Display gen4-ESP32-24 + PN532 (nuevo)`.
3. Indicar puerto COM, SSID, contrasena, IP estatica y host del servidor.
4. Comprobar en pantalla `NFC OK`, el ID de cuatro caracteres y la IP WiFi.
5. En Admin -> Lectores RFID, asignar el ID detectado al puesto o modulo.
6. Probar una tarjeta registrada, una no registrada y la repeticion de una
   tarjeta mantenida sobre el lector.