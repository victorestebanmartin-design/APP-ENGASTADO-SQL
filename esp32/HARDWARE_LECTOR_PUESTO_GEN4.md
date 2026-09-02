# Hardware: lector RFID de puesto gen4-ESP32-24

Esta caja sustituye gradualmente el lector de entrada basado en ESP32 DevKit
y RC522. Usa la pantalla 4D Systems gen4-ESP32-24, un PN532, un zumbador y un
DB9 reservado para el multiplexor. El firmware es
`esp32/micropython/lector_puesto.py`.

La pantalla funciona en horizontal a 320x240. En Admin -> Lectores RFID ->
Configurar y subir por USB se elige si la caja se monta en posicion `normal` o
`girada 180 grados`; la eleccion se graba en el firmware de esa placa. Esta
orientacion es exclusiva del lector de puesto; las pantallas de carro conservan
su firmware y formato vertical de 240x320.

No es una pantalla de carro: no lleva pulsadores ni ejecuta la seleccion,
recogida o devolucion de paquetes. Lee la tarjeta del operario, manda su UID
al servidor y muestra aceptacion, rechazo o error tecnico.

## Plano de soldadura: alimentacion

La caja admite **una sola** fuente de 5 V, elegida al montar:

1. **USB-C nativo.** Alimentar por el USB-C de la gen4. Es la opcion de banco
    y de programacion.
2. **Fuente externa del pick-to-light por DB9.** La fuente de 5 V entra por el
    DB9 y alimenta la gen4 por el pad 26 del breakout.

**No conectar USB-C y los 5 V del DB9 a la vez.** Dos fuentes de 5 V en
paralelo pueden realimentarse entre si, calentar un cable o danar el puerto
USB. El interruptor, si se instala, va en el positivo de la fuente elegida,
nunca en EN-RST.

Para alimentar desde el DB9, soldar dentro de la caja:

```
Fuente pick-to-light +5 V
   -> fusible rearmable 1 A (PTC)
   -> diodo Schottky SS14 (anodo hacia fuente, catodo hacia pantalla)
   -> DB9 pin 9
   -> breakout pad 26 (5V IN)

Fuente pick-to-light GND
   -> DB9 pin 1
   -> breakout pad 25 (GND)
```

El diodo deja aproximadamente 4.6-4.8 V en la pantalla, dentro de su rango
de 4.0-6.0 V, y evita que el USB-C pueda alimentar el cable DB9. Antes de
conectar la gen4, medir entre los pads 26 y 25: debe haber +5 V aproximados y
nunca polaridad invertida. Para el par de alimentacion usar cable de al menos
0.5 mm2 si el DB9 va varios metros hasta la fuente.

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

## Plano de soldadura: DB9 hembra e interconexion

El conector de la caja es un **DB9 hembra**. Mirando la cara de acoplamiento
del conector hembra, con la hilera de cinco arriba, sus pines son:

```
Cara de acoplamiento del DB9 hembra

  1   2   3   4   5
    6   7   8   9
```

Por la cara de soldadura el dibujo queda en espejo: comprobar siempre el
numero grabado en el plastico antes de estañar.

| DB9 | Cable a breakout | Funcion | Soldadura dentro de la caja |
|---:|---|---|---|
| 1 | Pad 25, GND | Retorno 5 V | Cable negro de fuente externa |
| 2 | Pad 2, GPIO17 | MUX-1, 3.3 V | Serie 220 ohm antes del DB9 |
| 3 | Pad 4, GPIO16 | MUX-2, 3.3 V | Serie 220 ohm antes del DB9 |
| 4 | Pad 5, GPIO15 | MUX-3, 3.3 V | Serie 220 ohm antes del DB9 |
| 5 | Pad 6, GPIO48 | MUX-4, 3.3 V | Serie 220 ohm antes del DB9 |
| 6 | Pad 7, GPIO47 | MUX-5, 3.3 V | Serie 220 ohm antes del DB9 |
| 7 | Pad 8, GPIO38 | MUX-6, 3.3 V | Serie 220 ohm antes del DB9 |
| 8 | Pad 9, GPIO39 | MUX-7, 3.3 V | Serie 220 ohm antes del DB9 |
| 9 | Pad 26, 5V IN | Entrada +5 V | Desde PTC + SS14, ver arriba |

Los pines 2-8 son logica de **3.3 V**, no RS-232, no RS-485 y no toleran 5 V.
No conectar cargas, bobinas, LEDs, finales de carrera ni salidas de otro
microcontrolador directamente. Para el tramo de 1-5 m, las siete resistencias
serie de 220 ohm son obligatorias; anadir TVS de 3.3 V a GND o un buffer de
3.3 V en la placa de interfaz si el cable pasa junto a engastadoras.

Las lineas quedan como entradas de alta impedancia en el firmware hasta que se
defina el protocolo del multiplexor. Se pueden encadenar fisicamente varios
multiplexores con arneses DB9, pero **solo** si las siete entradas de todos los
multiplexores son de alta impedancia. Nunca unir dos salidas entre si. Cuando
se elija el modelo de multiplexor se asignara la funcion de MUX-1 a MUX-7
(direccion, datos, reloj, habilitacion, etc.) y, si hace falta una red larga,
se sustituira por RS-485/CAN sin cambiar PN532 ni la pantalla.

No usar GPIO0, GPIO3, GPIO45 ni GPIO46: son pines de strapping. No usar
GPIO43/GPIO44: son el UART de programacion. GPIO40 queda libre para futura
ampliacion y no se cablea en este DB9.

## Lista de conexiones para hoy

1. PN532: SDA -> pad 11, SCL -> pad 12, VCC -> pad 20 (3.3 V), GND -> pad 21.
   Configurar sus interruptores en modo I2C. Soldar 100 uF y 100 nF entre VCC
   y GND junto al PN532.
2. Zumbador activo 3.3 V: positivo -> pad 3 (GPIO18), negativo -> pad 1 GND.
   Si es de 5 V o consume mas de 20 mA, no conectarlo directo: usar transistor
   NPN, resistencia de base de 1 k y diodo si no es piezo.
3. DB9 hembra: soldar los nueve cables exactamente segun la tabla anterior.
   Trenzar los cables de 5 V/GND y sujetar el cable con prensaestopa para que
   la faja FFC no reciba traccion.
4. Antes de enchufar: comprobar continuidad pin 1 -> GND y pin 9 -> pad 26;
   comprobar que no hay continuidad entre pin 9 y GND; con fuente externa,
   medir polaridad y tension en pads 26/25.

## Primera puesta en marcha

1. Grabar MicroPython para ESP32-S3 con PSRAM Octal en la gen4.
2. En Admin -> Lectores RFID -> Configurar y subir por USB, elegir
   `Display gen4-ESP32-24 + PN532 (nuevo)`.
3. Indicar puerto COM, SSID, contrasena, IP estatica y host del servidor.
4. Comprobar en pantalla `NFC OK`, el ID de cuatro caracteres y la IP WiFi.
5. En Admin -> Lectores RFID, asignar el ID detectado al puesto o modulo.
6. Probar una tarjeta registrada, una no registrada y la repeticion de una
   tarjeta mantenida sobre el lector.