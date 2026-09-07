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

El arnes que sale de la caja hacia el primer multiplexor lleva un **DB9 macho**
en su extremo. Mirando la cara de acoplamiento del macho, los numeros son los
mismos; por su cara de soldadura vuelve a quedar en espejo. Soldar cada hilo
con el mismo numero en ambos conectores: pin 1 con pin 1, pin 2 con pin 2,
hasta pin 9 con pin 9. Etiquetar ambos extremos como `LECTOR PUESTO / MUX 1`.

| DB9 | Cable a breakout | Funcion | Soldadura dentro de la caja |
|---:|---|---|---|
| 1 | Pad 25, GND | Retorno 5 V | Cable negro de fuente externa |
| 2 | Pad 2, GPIO17 | Datos WS2813, 3.3 V | 330 Ω en serie, luego DIN+BI del primer pixel |
| 3 | Pad 4, GPIO16 | **Libre** (reservar, no conectar) | Sin conectar — ver nota abajo |
| 4 | Pad 5, GPIO15 | **Libre** (reservar, no conectar) | Sin conectar — ver nota abajo |
| 5 | Pad 6, GPIO48 | **I2C SCL, 3.3 V** | Bus de MCP23017 |
| 6 | Pad 7, GPIO47 | **I2C SDA, 3.3 V** | Bus de MCP23017 |
| 7 | Pad 8, GPIO38 | Reserva | Sin conectar |
| 8 | Pad 9, GPIO39 | Reserva | Sin conectar |
| 9 | Pad 26, 5V IN | Entrada +5 V | Desde PTC + SS14, ver arriba |

> **Por que DB9-3/4 quedan libres:** GPIO16 y GPIO15 solo toleran 3.3 V. Si el
> MCP23017 se alimenta accidentalmente a 5 V, su I2C sube a 5 V y dana esos GPIO
> de forma permanente. Usando GPIO47/GPIO48 (DB9-5/6) el riesgo queda aislado a
> esos pines de reserva. En la placa que sufriera ese fallo, soldar un cable de
> DB9-3 a DB9-6 y otro de DB9-4 a DB9-5 en el arnes basta para recuperarla.

Los pines 2-8 son logica de **3.3 V**, no RS-232, no RS-485 y no toleran 5 V.
No conectar cargas, bobinas, LEDs, finales de carrera ni salidas de otro
microcontrolador directamente. Los pines 5 y 6 son I2C: necesitan sus
resistencias de pull-up de 4.7 k a 3.3 V en el modulo de MCP23017, no a 5 V.

Las lineas quedan como entradas de alta impedancia en el firmware hasta que se
defina el protocolo del multiplexor. Se pueden encadenar fisicamente varios
multiplexores con arneses DB9, pero **solo** si las siete entradas de todos los
multiplexores son de alta impedancia. Nunca unir dos salidas entre si. Cuando
se elija el modelo de multiplexor se asignara la funcion de MUX-1 a MUX-7
(direccion, datos, reloj, habilitacion, etc.) y, si hace falta una red larga,
se sustituira por RS-485/CAN sin cambiar PN532 ni la pantalla.

## Arnes DB9 macho hacia el primer multiplexor

Soldar el DB9 macho con este mismo orden. En el otro extremo del arnes, llevar
los hilos a los bornes del **primer multiplexor** que correspondan a la tabla.
El numero de borne concreto depende del modelo del multiplexor: anotarlo y
casarlo antes de energizar, no se debe inventar.

| DB9 macho | Color recomendado | Destino en MUX 1 | Funcion |
|---:|---|---|---|
| 1 | Negro | `GND / 0V` | Retorno comun de fuente y referencia logica |
| 2 | Blanco | `330 Ω` -> DIN+BI del primer WS2813 | Datos hacia primer WS2813 |
| 3 | Marron | Dejar aislado | Libre — reserva (no conectar) |
| 4 | Rojo fino | Dejar aislado | Libre — reserva (no conectar) |
| 5 | Naranja | `SCL` de MCP23017 | I2C a 3.3 V |
| 6 | Amarillo | `SDA` de MCP23017 | I2C a 3.3 V |
| 7 | Verde | Reserva | Dejar aislado y etiquetado |
| 8 | Azul | Reserva | Dejar aislado y etiquetado |
| 9 | Rojo grueso | `+5V IN` | Salida protegida de fuente pick-to-light |

El rojo grueso y negro son el par de alimentacion. Salen de los bornes de la
**fuente de 5 V del pick-to-light** hacia el DB9 macho; el PTC y SS14 quedan
dentro de la caja del lector, antes del pad 26. Repartir desde la fuente en
estrella, no desde el DB9:

```
Fuente +5 V ----+----> tira WS2813 / luces pick-to-light
                |
                +----> DB9 macho pin 9 -> lector gen4

Fuente GND -----+----> tira WS2813 / masas MUX
                |
                +----> DB9 macho pin 1 -> lector gen4
```

**No hacer pasar la corriente de la tira WS2813 por el DB9.** El DB9 alimenta
solo la gen4, PN532 y zumbador. La tira, LEDs y cargas del pick-to-light llevan
su ramal directo desde la fuente y su condensador de 1000 uF.

## Linea de datos de la tira WS2813

### Sin conversor de nivel (opcion directa)

GPIO17 a 3.3 V conectado directo al DIN de la tira funciona en la practica con
cable corto (menos de 50 cm). El umbral logico alto del WS2813 a 5 V es 0.7 x
VCC = 3.5 V, asi que 3.3 V esta en el limite, pero los chips suelen aceptarlo.

```
DB9-2 (GPIO17) -> 330 Ω -> WS2813 DIN y BI del primer pixel
```

La resistencia de 330 Ω es obligatoria: amortigua los flancos y protege el GPIO
de los picos al enchufar. Sin ella el GPIO puede verse en riesgo.

**Atencion al ruido:** con conexion directa la linea de datos actua de antena.
Fuentes de interferencia cerca (soldadores, motores, fuentes conmutadas) pueden
hacer que los LEDs cambien de color solos. Soluciones:
- Condensador de **1000 µF** entre el +5 V y GND justo en el primer pixel.
- Condensador de **100 nF** ceramico en paralelo con el anterior.
- Cable de datos lo mas corto posible y trenzado con el GND.

### Con conversor de nivel TXS0108E (opcion robusta)

Para cables largos o entornos con mucho ruido electromagnetico:

```
DB9-2 (GPIO17) -> TXS0108E A1   <- lado LV (3.3 V)
3.3 V (pad 20) -> TXS0108E VA y OE
5 V fuente     -> TXS0108E VB   <- lado HV (5 V)
GND            -> TXS0108E GND
TXS0108E B1    -> 330 Ω -> WS2813 DIN y BI del primer pixel
```

**Atencion al cableado del conversor:** el lado A es el de 3.3 V (GPIO17) y el
lado B es el de 5 V (tira). Si se conectan al reves, la salida da una tension
estatica de ~4 V en vez de la señal pulsante correcta. En caso de duda: medir
con multimetro en modo AC al enviar un comando -- debe haber tension alterna.
Si marca 0 en AC, el conversor esta al reves o mal alimentado.

Si la tira parpadea o saca colores aleatorios con el TXS0108E, sustituirlo por
un **74AHCT125** o **74HCT245** (unidireccional, mas fiable con señales de 800 kHz).

## MCP23017 y encadenar varios modulos

El arnes DB9 del lector llega solo a **MUX 1**. El MCP23017 no es un
multiplexor de siete hilos: usa SDA/SCL, y cada chip añade 16 micros de gaveta.

En MUX 1, alimentar cada MCP23017 asi:

```
Pad 20 gen4 (3.3 V) ──────────────> MCP23017 VDD (pin 9), RESET (pin 18)
DB9-1 GND --------------------------> MCP23017 VSS (pin 10)
DB9-6 (GPIO47, SDA) ----------------> MCP23017 SDA (pin 13)
DB9-5 (GPIO48, SCL) ----------------> MCP23017 SCL (pin 12)
3.3 V (pad 20) -- 4.7 k --> SDA    3.3 V (pad 20) -- 4.7 k --> SCL
```

**El MCP23017 se alimenta SIEMPRE desde el pad 20 (3.3 V) de la gen4, nunca
desde el 5 V.** Si se alimenta a 5 V, su I2C sube a 5 V y dana los GPIO del
ESP32-S3 de forma permanente. El pad 20 entrega hasta ~150 mA, suficiente para
varios MCP23017. Para armarios grandes con muchos expansores, usar un LDO o buck
externo de 3.3 V alimentado desde DB9-9 (5 V).

Para MUX 2 y posteriores:

1. Llevar 5 V y GND desde los bornes de la fuente a cada modulo en estrella.
2. Encadenar solo SDA (DB9-3) y SCL (DB9-4), con GND comun; cada MCP23017
   debe tener direccion distinta de 0x20 a 0x27 mediante A0/A1/A2.
3. Encadenar la tira WS2813 por su salida de datos entre tiras, no uniendo
   salidas de dos conversores de nivel.
4. Usar **un solo juego** de pull-ups I2C de 4.7 k a 3.3 V en todo el bus. Con
   mas de 1 m de bus o cable cercano a engastadoras, I2C directo no es fiable:
   añadir extensor I2C diferencial o montar el primer MCP junto al lector.

El firmware del lector incorpora `gavetas.py` para gen4: al detectar uno o
mas MCP23017 activa el pick-to-light con `GPIO17/GPIO16/GPIO15`. Sin
expansores conectados, se desactiva solo y el lector RFID sigue funcionando
con normalidad.

En la nave, el servidor local manda la orden directamente a la IP del lector.
Con PythonAnywhere, que no puede entrar en la red privada, la placa consulta
su orden cada 750 ms; el comportamiento de luces y micros es el mismo.

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
   En el otro extremo montar DB9 macho, pin a pin, siguiendo la tabla de arnes
   hacia MUX 1. Trenzar los cables de 5 V/GND y sujetar el cable con
   prensaestopa para que la faja FFC no reciba traccion.
4. Antes de enchufar: comprobar continuidad pin 1 -> GND y pin 9 -> pad 26;
   comprobar que no hay continuidad entre pin 9 y GND; con fuente externa,
   medir polaridad y tension en pads 26/25. Comprobar tambien continuidad de
   pin 1 a pin 1, pin 2 a pin 2 y asi hasta pin 9 a pin 9 en el arnes macho.

## Primera puesta en marcha

1. Grabar MicroPython para ESP32-S3 con PSRAM Octal en la gen4.
2. En Admin -> Lectores RFID -> Configurar y subir por USB, elegir
   `Display gen4-ESP32-24 + PN532 (nuevo)`.
3. Indicar puerto COM, SSID, contrasena, IP estatica y host del servidor.
4. Comprobar en pantalla `NFC OK`, el ID de cuatro caracteres y la IP WiFi.
5. En Admin -> Lectores RFID, asignar el ID detectado al puesto o modulo.
6. Probar una tarjeta registrada, una no registrada y la repeticion de una
   tarjeta mantenida sobre el lector.

## Lecciones aprendidas en la primera instalacion

Estos errores ya se cometieron y se documentan para no repetirlos.

### MCP23017 a 5 V dana los GPIO

El MCP23017 admite hasta 5.5 V en VDD, pero si se alimenta a 5 V sus pines I2C
suben a 5 V. Los GPIO del ESP32-S3 solo toleran 3.3 V: el resultado es la
destruccion permanente de los GPIO de SDA y SCL.

**Señal de que ha pasado:** el test de micros desde Admin -> Pick-to-light no
responde aunque el cableado parezca correcto y el MCP23017 este bien conectado.

Solucion en la placa danada: cambiar SDA/SCL a otro par de GPIO libres del DB9.
El firmware usa GPIO47/GPIO48 (DB9-5/6) por este motivo.

### El conversor de nivel TXS0108E puede estar al reves

Si la salida del conversor da una tension estatica (~4 V) en vez de pulsar, el
conversor esta conectado con los lados A y B invertidos. El lado A es el de
3.3 V (GPIO17) y el lado B es el de 5 V (tira). Al reves no dana nada, pero
la tira no enciende.

**Como detectarlo sin osciloscopio:** multimetro en modo AC sobre el cable de
datos mientras se envia un comando de test. Si marca 0, no hay señal.

### Conexion directa sin conversor: funciona pero es sensible al ruido

GPIO17 a 3.3 V directo al DIN enciende la tira en la practica. Sin embargo,
la linea sin blindaje recoge interferencias de fuentes cercanas (soldadores a
220 V, motores). Los LEDs pueden cambiar de color solos al encender cargas en
la misma red. Poner 1000 µF en el +5 V del primer pixel y 330 Ω en la señal
de datos reduce el problema notablemente.

### Los 4 cables de la tira WS2813: DIN y BI van juntos

La tira WS2813 tiene VCC, GND, DIN y BI (backup input). Los dos cables de señal
(DIN y BI) se conectan **juntos** a la misma salida del conversor o GPIO. Asi
funciona la redundancia del WS2813: si un pixel muere, la cadena no se rompe.

### Los LEDs bailan con el soldador encendido: es ruido electromagnetico normal

No es un fallo del firmware ni de la placa. Un soldador de 220 V mete un pico
de ruido en la red y en el campo EM del entorno. La tira lo capta por el cable
de datos. En produccion (sin soldadores cerca) el problema desaparece.