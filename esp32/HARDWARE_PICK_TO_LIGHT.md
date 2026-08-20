# Hardware: pick-to-light de gavetas

Esquema eléctrico del sistema que enciende la gaveta del terminal que el operario acaba
de elegir en engastado, y detecta con un micro-interruptor que la ha sacado.

No lleva placa nueva: todo cuelga de la **ESP32 del lector RFID que ya está en el puesto**
(`esp32/main.py`, ESP32 DevKit V1 + RC522 + zumbador). Esa placa ya tiene IP fija, latido
cada 60 s y OTA desde Admin → Lectores RFID, así que el pick-to-light hereda todo eso.

El firmware está en `esp32/lib/gavetas.py` y se activa **solo si detecta expansores en el
bus I2C**. Una placa sin nada soldado sigue funcionando exactamente igual que antes.

## Componentes

| Cant. (10 gav.) | Cant. (60 gav.) | Componente |
|---|---|---|
| 1 | 1 | ESP32 DevKit V1 con RC522 y zumbador (el que ya está en el puesto) |
| 10 px | 60 px | Tira WS2813 (el paso según la anchura de las gavetas) |
| 1 | 1 | Fuente 5 V — 2 A / 4 A |
| 1 | 1 | Condensador electrolítico 1000 µF / 10 V |
| 1 | 1 | Elevador de nivel 3,3 → 5 V: TXS0108E, o 74AHCT125 / 74HCT245 (ver abajo) |
| 1 | 4 | MCP23017-E/SP (PDIP-28), expansor I2C de 16 canales |
| 10 | 60 | Micro-interruptor / final de carrera, uno por gaveta |
| 1 | 4 | Condensador 100 nF (desacoplo de cada MCP23017) |
| — | 1 | Resistencia 330 Ω en la línea de datos — **opcional**, ver "Las dos resistencias" |
| — | 2 | Resistencias 4,7 kΩ de pull-up I2C — **opcional**, ver "Las dos resistencias" |

Con cables largos hasta los micros, además: 100 nF en paralelo con cada micro y 10 kΩ de
cada canal a 3,3 V.

## Vista general

```
                    ┌──────────────────┐
                    │   FUENTE 5 V     │  2 A (10 LEDs) / 4 A (60 LEDs)
                    └──┬────────────┬──┘
                    +5V│            │GND
        ┌──────────────┼────────────┼──────────────┬─────────────────┐
        │              │            │              │                 │
        v              v            v              v                 v
  ┌───────────┐  ┌──────────┐  ┌─────────┐  ┌────────────┐   ┌──────────────┐
  │ ESP32     │  │TXS0108E  │  │  TIRA   │  │ 1000 uF    │   │ MCP23017-E/SP│
  │ DevKit V1 │  │ elevador │  │ WS2813  │  │ (en la     │   │ (VDD <- 3V3  │
  │ +RC522    │  │ 3,3->5 V │  │ 10 LEDs │  │  entrada   │   │  del ESP32,  │
  │ +zumbador │  │ 8 canales│  │         │  │  de tira)  │   │  NO 5 V)     │
  └─────┬─────┘  └────┬─────┘  └────^────┘  └────────────┘   └──────┬───────┘
        │ D13         │ B1          │ DI+BI                         │ GPA/GPB
        └───> A1 ─────┼──[330 Ω]────┘                               │
        │ D21 = SDA                                                 │
        │ D26 = SCL ────────────────────────────────────────────────┘
                                                        10 micro-interruptores
                                                        (el otro extremo a GND)
```

## 1. Alimentación — masa en estrella desde el borne de la fuente

```
FUENTE +5 V ──┬─────────────────────────> ESP32       VIN
              ├─────────────────────────> TXS0108E    VB
              └──┬──────────────────────> TIRA WS2813 +5V
                 │
              ┌──┴──┐  1000 uF / 10 V   (pegado al primer LED;
              │  +  │                    la banda marcada es el −)
              └──┬──┘
FUENTE GND ───┬──┴──────────────────────> TIRA WS2813 GND
              ├─────────────────────────> ESP32       GND
              ├─────────────────────────> TXS0108E    GND
              ├─────────────────────────> MCP23017    pin 10 (VSS)
              └─────────────────────────> común de los micros

ESP32 3V3 ────┬─────────────────────────> TXS0108E    VA
              ├─────────────────────────> TXS0108E    OE   <- sin esto no sale nada
              ├─────────────────────────> MCP23017    pin 9  (VDD)
              ├─────────────────────────> MCP23017    pin 18 (RESET)
              ├──[4,7 kΩ]───────────────> línea SDA   ┐ opcionales,
              └──[4,7 kΩ]───────────────> línea SCL   ┘ ver más abajo
```

Con la tira conectada, alimentar por la fuente **o** por USB, nunca las dos a la vez.

## 2. Línea de datos de la tira (TXS0108E)

El módulo tiene `VA A1 A2 … A8 OE` en un lado y `GND B8 B7 … B1 VB` en el otro. `A` es el
lado de 3,3 V y `B` el de 5 V. Se usa **un solo canal**, el 1:

```
ESP32 3V3     ─────────> TXS0108E  VA
ESP32 D13     ─────────> TXS0108E  A1     (D13 = GPIO13)
                         TXS0108E  B1 ──[330 Ω]──┬──> TIRA  DI
                                     (opcional)  └──> TIRA  BI
+5 V         ──────────> TXS0108E  VB
3V3          ──────────> TXS0108E  OE     (lleva pull-down de 10 kΩ:
GND          ──────────> TXS0108E  GND     si lo dejas al aire, sale apagado)
A2..A8 y B2..B8: al aire
```

`DI` y `BI` van **juntos**. Así funciona la redundancia del WS2813: cada píxel recibe por
`DI` del anterior y por `BI` del anteanterior, de modo que si uno se muere el resto de la
tira sigue encendiendo. Dejar `BI` al aire tira esa ventaja por la borda.

### Si la tira parpadea o saca colores aleatorios: es el elevador

El TXS0108E es bidireccional, detecta la dirección solo y acelera los flancos. Con la
señal de 800 kHz de los WS2813 a veces se confunde. Que funcione o no depende del módulo
y de la longitud del cable, no de cómo esté soldado. Dos salidas:

- **La definitiva (~1 €): 74AHCT125 o 74HCT245.** Unidireccional y con entradas TTL, así
  que 3,3 V ya le vale como '1'. Sustituye al TXS0108E sin tocar nada más:
  `1OE` → GND, `1A` ← GPIO13, `1Y` → 330 Ω → DI+BI, pin 14 → +5 V, pin 7 → GND, y 100 nF
  entre los pines 14 y 7.
- **Sin comprar nada: quitar el elevador y bajar el 5 V del PRIMER píxel.** Un **1N4148**
  en serie con el +5 V de ese píxel deja su VDD en ~4,35 V, con lo que su umbral baja a
  ~3,05 V y el GPIO13 lo ataca directo (GPIO13 → 330 Ω → DI+BI). El resto de la tira sigue
  a 5 V y a partir del primer píxel la señal ya va a 4,35 V, de sobra para todos.
  En una tira de 10 se puede poner el diodo al +5 V de la tira entera, pero entonces tiene
  que ser un **1N5817 o 1N4001** (el 1N4148 solo aguanta 200 mA). Para 60 gavetas, solo el
  primer píxel.

## 3. Las dos resistencias: para qué son y cuándo hacen falta

Ninguna de las dos es imprescindible para un montaje de 10 gavetas en el banco.

**330 Ω en la línea de datos.** Solo amortigua: mata las reflexiones del cable y protege la
entrada del primer LED de los picos al enchufar. Con cables cortos no se nota; puente
directo y listo. Cuando se ponga, cualquier valor entre 100 Ω y 500 Ω sirve.

**4,7 kΩ en SDA y SCL.** El I2C es *open-drain*: los chips solo saben tirar la línea a 0,
quien la sube a 1 es la resistencia. Sin ninguna, el bus no funciona — pero el ESP32 lleva
pull-ups internos de ~45 kΩ que MicroPython activa al crear el I2C. Son flojas:

| Montaje | ¿Externas? |
|---|---|
| 1 expansor, cables cortos | No hacen falta |
| 2–4 expansores o varios metros de cable | Sí: los flancos de subida se vuelven lentos y el bus empieza a fallar |

Cualquier valor entre 2,2 kΩ y 10 kΩ vale: una de SDA a 3V3 y otra de SCL a 3V3, **un solo
juego en todo el bus**, no una por expansor.

## 4. Bus I2C y micro-interruptores

```
ESP32 D21 ───────────────> MCP23017 pin 13 (SDA)   (D21 = GPIO21)
ESP32 D26 ───────────────> MCP23017 pin 12 (SCL)   (D26 = GPIO26,
                                                     NO el pin marcado SCL)

MCP23017 pin 15 (A0) ──> GND ┐
MCP23017 pin 16 (A1) ──> GND ├── dirección 0x20 = gavetas 1-16
MCP23017 pin 17 (A2) ──> GND ┘

Micro de la gaveta n:   MCP23017 GPxn ────o/ o──── GND
                        gaveta PUESTA = contacto cerrado = 0
                        gaveta FUERA  = abierto = 1 (pull-up interno del MCP23017)
```

Los pines 11, 14, 19 y 20 (NC, NC, INTB, INTA) se dejan al aire: el firmware sondea por
I2C cada 40 ms, no usa la interrupción.

## 5. Numeración: gaveta → píxel → pin del expansor

El número de gaveta es el mismo en los tres sitios, y es el que se teclea en el campo
"nº de LED" de cada terminal (gestión de puestos → chip de gaveta).

| Gaveta | Píxel | Canal | Pin DIP | Gaveta | Píxel | Canal | Pin DIP |
|---|---|---|---|---|---|---|---|
| 1 | 1 | GPA0 | 21 | 9  | 9  | GPB0 | 1 |
| 2 | 2 | GPA1 | 22 | 10 | 10 | GPB1 | 2 |
| 3 | 3 | GPA2 | 23 | 11 | 11 | GPB2 | 3 |
| 4 | 4 | GPA3 | 24 | 12 | 12 | GPB3 | 4 |
| 5 | 5 | GPA4 | 25 | 13 | 13 | GPB4 | 5 |
| 6 | 6 | GPA5 | 26 | 14 | 14 | GPB5 | 6 |
| 7 | 7 | GPA6 | 27 | 15 | 15 | GPB6 | 7 |
| 8 | 8 | GPA7 | 28 | 16 | 16 | GPB7 | 8 |

Para un puesto de 60 gavetas: una tira encadenada de 60 píxeles y 4 expansores colgando
del mismo bus (4 hilos: SDA, SCL, 3V3, GND). La dirección la fijan A0/A1/A2:

| Expansor | Gavetas | A2 | A1 | A0 | Dirección |
|---|---|---|---|---|---|
| 1 | 1–16  | GND | GND | GND | 0x20 |
| 2 | 17–32 | GND | GND | 3V3 | 0x21 |
| 3 | 33–48 | GND | 3V3 | GND | 0x22 |
| 4 | 49–60 | GND | 3V3 | 3V3 | 0x23 |

El firmware escanea de 0x20 a 0x27, así que ampliar es soldar el expansor siguiente y
reiniciar: no hay que configurar nada en el servidor.

## 6. Pines del ESP32 — y cómo se llaman en la placa

**En la ESP32 DevKit V1, `D<n>` de la serigrafía ES el `GPIO<n>`.** `D13` es GPIO13,
`D26` es GPIO26, `D21` es GPIO21. No hay tabla de conversión que aprenderse, a diferencia
de las NodeMCU de ESP8266, donde `D1` es GPIO5 y todo va cambiado.

Para saber cuál tienes en la mano: si la placa lleva pines **`VP`, `VN`, `D34` y `D35`**,
es ESP32 y vale la regla de arriba. Si solo llega hasta `D8`, es una ESP8266 y este
esquema no le sirve.

### Todo lo del montaje, con el nombre que está impreso

| Señal | GPIO | En tu placa | Va a |
|---|---|---|---|
| RC522 SDA/CS | 5 | `D5` | ya soldado, no se toca |
| RC522 SCK | 18 | `D18` | ya soldado |
| RC522 MOSI | 23 | `D23` | ya soldado |
| RC522 MISO | 19 | `D19` | ya soldado |
| RC522 RST | 22 | `D22` | ya soldado — **ojo, ver el aviso de abajo** |
| Zumbador | 4 | `D4` | ya soldado |
| LED de estado | 2 | `D2` | el de la propia placa |
| **Datos WS2813** | 13 | **`D13`** | TXS0108E `A1` (o 74AHCT125 pin 2) |
| **I2C SDA** | 21 | **`D21`** | MCP23017 pin 13 |
| **I2C SCL** | 26 | **`D26`** | MCP23017 pin 12 |
| 5 V de la fuente | — | `VIN` | en algunas clónicas pone `5V` o `VV` |
| 3,3 V | — | `3V3` | alimenta el MCP23017 y `VA`/`OE` del TXS0108E |
| Masa | — | `GND` | hay tres, valen los tres |

### El aviso: no uses el pin que pone "SCL"

El I2C de fábrica del ESP32 es SDA=GPIO21 y **SCL=GPIO22**, y bastantes placas lo llevan
serigrafiado como `SDA` y `SCL` junto a `D21` y `D22`. Aquí **`D22` está ocupado por el
RST del RC522**, así que el SCL de las gavetas va a **`D26`**, no al pin marcado `SCL`.
Es lo único de este montaje que contradice a la serigrafía; si lo cableas "como pone en la
placa", el bus no arranca y no se detecta ningún expansor.

El I2C del ESP32 se remapea a cualquier pin, así que esto no tiene ningún coste: evita
rehacer las placas ya montadas. Los tres pines nuevos se pueden cambiar en
`wifi_config.py` (`GAVETAS_LED_PIN`, `GAVETAS_SDA_PIN`, `GAVETAS_SCL_PIN`); si no están,
el firmware usa estos por defecto.

### Mapa de la placa entera (30 pines, orden habitual)

Con el USB abajo:

```
   IZQUIERDA                            DERECHA
   EN                                   D23   (GPIO23)  <- RC522 MOSI
   VP    (GPIO36, solo entrada)         D22   (GPIO22)  <- RC522 RST
   VN    (GPIO39, solo entrada)         TX0   (GPIO1)   consola serie
   D34   (GPIO34, solo entrada)         RX0   (GPIO3)   consola serie
   D35   (GPIO35, solo entrada)         D21   (GPIO21)  <- I2C SDA
   D32   (GPIO32)                       D19   (GPIO19)  <- RC522 MISO
   D33   (GPIO33)                       D18   (GPIO18)  <- RC522 SCK
   D25   (GPIO25)                       D5    (GPIO5)   <- RC522 CS
   D26   (GPIO26)  <- I2C SCL           TX2   (GPIO17)
   D27   (GPIO27)                       RX2   (GPIO16)
   D14   (GPIO14)                       D4    (GPIO4)   <- zumbador
   D12   (GPIO12)                       D2    (GPIO2)   <- LED de estado
   D13   (GPIO13)  <- datos WS2813      D15   (GPIO15)
   GND                                  GND
   VIN             <- +5 V              3V3             <- 3,3 V
```

Las clónicas cambian a veces el orden de alguna fila, pero nunca la regla: fíate del
nombre impreso, no de la posición. `VP`/`VN`, `D34` y `D35` son **solo entrada** y no
sirven para atacar la tira.

## 7. Consumo

La app enciende como mucho tres LEDs a la vez y el firmware limita el brillo al 40 %, así
que el consumo real ronda los 100 mA. El peor caso teórico —los 60 en blanco al 100 %—
son 3,6 A, y por eso la fuente se dimensiona a 4 A aunque nunca se llegue.

Si la tira pasa de ~2 m, inyectar 5 V por los dos extremos: el cobre de la tira cae
tensión y los últimos píxeles se van a verdoso.

## 8. Tres avisos que rompen cosas

1. **El MCP23017 se alimenta a 3,3 V, jamás a 5 V.** A 5 V pondría 5 V en SDA/SCL y se
   lleva por delante el ESP32.
2. **Masa común antes que el 5 V** al enchufar nada. Si la tira ve 5 V sin masa común, la
   corriente busca el retorno por la línea de datos y se lleva el GPIO.
3. **Nunca la tira colgando de un ESP32 alimentado solo por USB.** El regulador de la
   placa no da esa corriente y el puerto del PC se protege y corta.

Y el bus I2C corto (menos de 2 m), trenzado con su masa y lejos de los cables de las
engastadoras: son cargas inductivas y meten ruido.

## 9. Puesta en marcha

1. **La tira sola primero**, antes de soldar los micros: ESP32 + elevador + tira, y desde
   el REPL un barrido de colores. Si salen píxeles aleatorios, es el elevador (ver §2).
2. Soldar un expansor. Al arrancar, la placa escribe por consola las direcciones I2C que
   encuentra y cuántas gavetas queda configuradas.
3. En gestión de puestos, el chip de gaveta de cada terminal tiene un botón **Probar**:
   enciende el LED de ese número para identificar el cajón físico sin moverse del sitio.
4. Prueba de flujo completo en engastado: elegir terminal → LED verde → sacar la gaveta
   correcta → azul y pitido corto → salen los paquetes. Sacar otra → roja y zumbido
   continuo hasta devolverla.
5. **Desenchufar la placa y repetir**: engastado tiene que llegar a los paquetes igual,
   avisando de que no hay luz. Si se queda parado, es un fallo.

Al tocar el firmware, el orden importa (ver `CLAUDE.md`): subir `FW_VERSION` en
`esp32/main.py`, desplegar el servidor, y comprobar en Admin → Lectores RFID que la placa
ha cogido la versión nueva.
