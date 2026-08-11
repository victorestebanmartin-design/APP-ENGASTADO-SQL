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
| 2, 4, 5, 6, 7, 8, 9 | GPIO17, 16, 15, 48, 47, 38, 39 | Pulsadores 1–7 (a GND, `INPUT_PULLUP`) — cada uno identifica un **puesto** (`BTN_PUESTO_PINS`) |
| 10 | GPIO40 | Pulsador 8 — **OK / confirmar** (`BTN_OK_PIN`) |
| 3 | GPIO18 | Zumbador (`BUZZER_PIN` en el firmware; verificar si activo/pasivo — si activo, usar transistor NPN) |
| 11, 12 | GPIO6, GPIO5 | Lector NFC PN532 por I2C: SDA y SCL (`NFC_SDA_PIN`, `NFC_SCL_PIN`) |
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

## Los 8 pulsadores

Montados y en uso. Los botones **1–7 identifican un puesto** (en Admin →
Puestos se asigna a cada puesto su número) y el **8 es OK/confirmar**.

| Pulsador | Pad | GPIO | Función |
|---|---|---|---|
| 1 | 2 | GPIO17 | Puesto con botón 1 |
| 2 | 4 | GPIO16 | Puesto con botón 2 |
| 3 | 5 | GPIO15 | Puesto con botón 3 |
| 4 | 6 | GPIO48 | Puesto con botón 4 |
| 5 | 7 | GPIO47 | Puesto con botón 5 |
| 6 | 8 | GPIO38 | Puesto con botón 6 |
| 7 | 9 | GPIO39 | Puesto con botón 7 |
| 8 | 10 | GPIO40 | **OK** — confirma recogida o devolución |

Los pads 11 y 12 los ocupa ahora el lector NFC (ver más abajo). Quedan como
último recurso los pads 13, 14 y 15 (GPIO3, GPIO45, GPIO46), por ser de
strapping.

## Lector NFC (PN532 "NFC MODULE V3")

Alternativa cómoda al botón de puesto: cada puesto puede tener una tarjeta
asignada en Admin → Puestos, y pasarla por el lector hace lo mismo que pulsar
su botón. **El botón 8 (OK) sigue siendo quien confirma.** Los dos caminos
conviven: un puesto puede tener botón, tarjeta o ambos.

El módulo va en **modo I2C** — los dos micro-interruptores según la tabla que
viene serigrafiada en la propia placa (trae impresas las combinaciones
I2C / SPI / HSU).

| Señal PN532 | Pad | GPIO |
|---|---|---|
| SDA | 11 | GPIO6 |
| SCL | 12 | GPIO5 |
| VCC | 20 (3.3V) | — |
| GND | 21, 25 o 30 | — |

El lector es **opcional en el firmware**: si no está conectado o no responde, se
registra por consola y todo lo demás funciona igual (misma filosofía que el
zumbador). Con lector, la pantalla de lista dice `PASA TU TARJETA` en vez de
`PULSA TU PUESTO`.

Tres avisos de montaje:

- **Alimentación.** El PN532 pega picos de ~100 mA al levantar el campo RF y el
  pad 20 está recomendado hasta 100–200 mA. Si la pantalla se reinicia al leer,
  alimentar VCC desde los 5V del USB en lugar del pad 20 (el módulo V3 lleva su
  propio regulador y admite 3.3–5V).
- **El carro es metálico.** Una antena NFC pegada a chapa pierde casi todo el
  alcance. Montar el módulo sobre un separador de plástico de 1–2 cm, o con una
  lámina de ferrita entre antena y metal.
- **Separar de la pantalla.** Dejar unos centímetros entre la antena y el TFT.

### Alta de tarjetas

No hay que escribir nada en la tarjeta: se usa su UID de fábrica. En
Admin → Puestos, al editar un puesto, pulsa **Capturar**, acerca la tarjeta al
lector de cualquier carro y el UID aparece solo (la pantalla manda al servidor
las tarjetas que no reconoce, y Admin sondea `/api/esp32/ultimo-tag`). Solo se
aceptan lecturas de los últimos 30 segundos, para no asignar por error una
tarjeta que alguien pasó antes.

Una tarjeta sin asignar leída en un carro muestra `TARJETA SIN TRABAJO AQUI` con
su UID en pantalla — que es justo lo que hay que copiar si se prefiere teclearlo
a mano.

### Ficheros del firmware

El driver vive en `esp32/micropython/lib/pn532_i2c.py` y se sube a la raíz del
sistema de ficheros de la pantalla. El flasheo desde Admin (`/api/esp32/flash_usb`)
copia automáticamente todos los `.py` de esa carpeta **antes** de `main.py`. A
mano sería:

```
mpremote connect COM5 cp esp32/micropython/lib/pn532_i2c.py :
mpremote connect COM5 cp esp32/micropython/main_wifi.py :main.py
mpremote connect COM5 reset
```

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
| `BTN_PUESTO_PINS` | 17, 16, 15, 48, 47, 38, 39 | Pads 2, 4, 5, 6, 7, 8, 9 — botones 1 a 7, uno por puesto |
| `BTN_OK_PIN` | GPIO40 | Pad 10 — botón 8, OK/confirmar |
| `BUZZER_PIN` | GPIO18 | Pad 3 — zumbador (`BUZZER_PASIVO = False` → activo de 3.3V) |

### Ciclo de recogida y devolución

El botón identifica el **puesto**, no al operario: como nunca hay dos operarios
en el mismo puesto, no hay ambigüedad posible. Cada puesto recibe su número en
Admin → Puestos.

1. En el PC se elige terminal y carro; el modal muestra el grupo con el botón
   **"Tengo estos N, empezar" bloqueado**.
2. La pantalla del carro lista quién tiene algo pendiente
   (`[3] AMP-02 · RECOGER 5`) y avisa con un sonido cada 25 s.
3. El operario **pasa su tarjeta** por el lector (o pulsa el **botón de su
   puesto**) → ve sus paquetes. Los coge y pulsa **OK** → la pantalla manda
   `GET /api/esp32/evento?tipo=confirmacion&fase=recoger&carro=…&puesto=…&lote=…`.
4. El PC, que sondea `/api/esp32/estado-carro` cada 2 s, desbloquea el botón y
   el operario trabaja el grupo.
5. Al terminar el grupo (o el carro) el PC pide **DEVOLVER** y no avanza: la
   pantalla vuelve a listar ese puesto en rojo.
6. El operario pulsa su botón, deja los paquetes y pulsa **OK**
   (`fase=devolver`). El PC continúa con el grupo siguiente; si era la última
   devolución del carro, la pantalla remata con `CARRO FINALIZADO`.

Reglas de la interacción, para que no haya confirmaciones ciegas:

- **OK solo vale después de identificarse** (tarjeta o botón). Si se pulsa OK
  desde la lista, la pantalla responde `PULSA ANTES TU PUESTO` y no confirma
  nada: cada confirmación lleva detrás la identidad de un puesto.
- **Al confirmar, los paquetes desaparecen** de la pantalla y vuelve a la lista
  (el operario ya se los ha llevado, o los ha dejado).
- Si el puesto mostrado no tiene nada que confirmar, dice `NADA QUE CONFIRMAR`.
- Al salir del modal en el PC, cambiar de puesto o cerrar la pestaña, ese
  puesto **se libera** de la pantalla y deja de aparecer en su lista.

### Cómo se liberan los puestos colgados

Un puesto ocupa un hueco en la pantalla del carro solo mientras su PC da
señales de vida. Hay tres redes de seguridad, de la más suave a la más bruta:

1. **Salida limpia.** Cancelar el modal, volver a puestos, terminar el carro o
   cerrar la pestaña liberan el puesto al instante.
2. **Caducidad automática.** El navegador re-envía su estado cada 60 s como
   latido (`ESP32_KEEPALIVE_S`). Si deja de hacerlo — PC apagado de golpe, sin
   red, pestaña muerta — el servidor descarta esa entrada a los **4 minutos**
   (`ESP32_TTL_S`) y desaparece sola de la pantalla.
3. **A mano, desde el carro.** **Mantener pulsado 1 segundo** el botón de un
   puesto lo libera en el acto: la pantalla dice `PUESTO n LIBERADO` y avisa al
   servidor (`tipo=liberar`). Es la salida de emergencia cuando algo se queda
   colgado y no quieres esperar.

El recordatorio sonoro de "ven al carro" suena como mucho `AVISO_MAX` veces (6)
y luego se calla; el aviso sigue en pantalla. Así un estado colgado nunca deja
el zumbador pitando sin fin.

Si la pantalla no responde, el PC ofrece un enlace para confirmar manualmente
(se registra como `confirmacion_manual`): el trabajo nunca se bloquea del todo.
Tampoco se bloquea si el carro no tiene pantalla asignada o el puesto no tiene
botón. Los eventos quedan en `data/esp32_eventos.json` (últimos 100) y la última
confirmación de cada `(carro, puesto)` en `data/esp32_confirmaciones.json`.

### Sonidos del zumbador

Con un zumbador **activo** la frecuencia es fija (las notas no se distinguen),
así que cada aviso se reconoce por **ritmo y textura** (`tono` = liso,
`trino` = cortes rápidos, suena rasposo). Con un piezo pasivo
(`BUZZER_PASIVO = True`) los mismos patrones suenan además como melodías.

| Evento | Patrón |
|---|---|
| Arranque | trino corto + nota |
| Pulsas el botón de tu puesto | dos ticks rápidos |
| Contenido actualizado | tic casi imperceptible (14 ms) |
| Alguien tiene que venir al carro | tres golpes separados, se repite cada 25 s |
| OK a una recogida | fanfarria **ascendente** de tres notas |
| OK a una devolución | las mismas tres notas **descendentes** ("cerrado") |
| Llegan paquetes en reposo | melodía de cuatro notas, la llamada más larga |
| Gesto no válido (puesto sin trabajo, OK a destiempo) | dos zumbidos rasposos y graves |

## Problemas conocidos

### El zumbador "hace de mosca" con la placa apagada

Zumbido flojo y continuo cuando se apaga la pantalla con el interruptor. **No
es software**: si el ESP32-S3 está en reset, ningún programa puede tocar el
pin. Es el pin del zumbador quedándose **flotante**.

Un zumbador activo cableado GPIO18 → patilla +, GND → patilla −, se alimenta
del propio GPIO. Cuando el S3 entra en reset (interruptor en el pad 22,
**EN-RST**), el chip suelta todos sus pines y los deja en alta impedancia,
pero **la placa sigue alimentada a 5V**: la patilla del zumbador queda al aire
recogiendo fugas y ruido, y suena ese mosquito.

Para confirmar que es esto: al accionar el interruptor, **¿se queda la pantalla
encendida?** Si el retroiluminado sigue dando luz, la placa sigue alimentada y
el interruptor es el de EN-RST — entonces es exactamente este caso.

Dos arreglos, cualquiera vale:

- **Resistencia de 10 kΩ entre GPIO18 (pad 3) y GND.** Mantiene la patilla a
  masa siempre que el ESP32 no la esté empujando activamente. Es la solución
  estándar y no afecta al funcionamiento normal (el GPIO empuja de sobra
  contra 10 kΩ).
- **Mover el interruptor al hilo VBUS** del cable USB-C, para cortar la
  alimentación de verdad en vez de solo poner el chip en reset. Sin 5V el
  zumbador no puede sonar.

## Notas de la sesión

- Pendiente de decidir/verificar: si el zumbador es activo o pasivo, para saber
  si hace falta transistor de conmutación. (El firmware asume activo:
  `BUZZER_PASIVO = False`.)
- No hay forma fiable de leer el % de batería de la power bank por software
  (es una caja cerrada); se descartó instrumentar esto.

---
*Generado a partir de la documentación oficial de 4D Systems (gen4-ESP32 Series
Datasheet R1.2) y MikroElektronika.*
