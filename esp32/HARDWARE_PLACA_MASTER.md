# Placa MASTER y placa ESCLAVA del Pick-To-Light

Plano de montaje de las dos placas que reparten el pick-to-light de un puesto:
una **MASTER**, que es la que habla con el lector RFID y con la fuente, y tantas
**ESCLAVAS** como bancos de 16 gavetas haya detrás.

Dos planos imprimibles, cada uno en 1 página A4:

- **Montaje y conexiones:** [esquema_master_A4.html](schematics/esquema_master_A4.html)
- **Trazado de pistas, agujero a agujero:** [esquema_master_pistas_A4.html](schematics/esquema_master_pistas_A4.html)

Documentos hermanos:
- [HARDWARE_ESQUEMA_PUESTO.md](HARDWARE_ESQUEMA_PUESTO.md) — la caja del lector y el DB9.
- [HARDWARE_EXPANSORES_MCP23017.md](HARDWARE_EXPANSORES_MCP23017.md) — direcciones I2C.

---

## 0. Lo primero: esto no toca el firmware

`esp32/lib/gavetas.py` escanea el bus I2C al arrancar, ordena los expansores de
`0x20` a `0x27` y calcula `n_gavetas = 16 × nº de expansores`. **No hay que
subir `FW_VERSION` ni tocar código para añadir una esclava**: se enchufa, se
reinicia el lector y la pantalla de reposo pasa a poner `PTL 2xMCP 32GAV`.

Dos consecuencias prácticas:

- **El orden lo manda la dirección I2C, no el cable.** La placa con `0x20` es
  siempre la gaveta 1–16. Si te equivocas de strap, se renumera el puesto
  entero.
- **Una placa a medio cablear no molesta.** El servidor manda la lista de LEDs
  con terminal de verdad detrás (`validas`), y los canales sin
  microinterruptor no disparan la alarma de "gaveta robada". Puedes montar la
  placa entera y cablear 10 de las 16 gavetas.

---

## 1. Reparto: qué hace cada placa

| | MASTER | ESCLAVA |
|:--|:--|:--|
| MCP23017 | 1 (`0x20`) | 1 (`0x21`…`0x27`) |
| Micros de gaveta | 16 | 16 |
| Pull-ups I2C 4k7 | **Sí** (únicas del bus) | **No** |
| Entrada 5 V de la fuente | **Sí** (J0) | No — le llega por J1 |
| Entrada 3V3 / I2C / datos | Del DB9 del lector (J1) | De la placa anterior (J1) |
| Salida a la placa siguiente | J4 | J4 |
| Tira LED | 16 LEDs (J2 sale, J3 vuelve) | 16 LEDs (J2 sale, J3 vuelve) |
| Fusible PTC y C3 de la fuente | **Sí** (F1 + C3 en J0) | No |
| C3 en la cabeza de su tira | Sí (J2) | **Sí** (J2) |
| Adaptador de nivel 74AHCT125 | Opcional, **fuera de la placa** (punto JP1) | No hace falta |

> La ESCLAVA es **la misma placa con menos componentes**. Mismo taladrado, misma
> serigrafía, misma tabla de pads. Solo cambia la lista de montaje y los straps
> de dirección. Monta todas iguales y decide al final cuál es la master.

---

## 2. La placa: rejilla 20 × 14 y 24 pads laterales

Rejilla de paso 2,54 mm, **20 columnas (C1…C20) × 14 filas (F1…F14)** ≈ 51 × 36 mm.
**12 pads de soldadura en cada lateral** (L1…L12 a la izquierda, R1…R12 a la
derecha), para soldar el hilo pelado directamente, sin conector.

El MCP23017 en DIP-28 mide 0,6" de ancho (6 pasos) y 14 pines por lado: **puesto
en vertical ocupa exactamente las 14 filas**, en las columnas **C7 y C13**, con
la muesca hacia arriba. Es lo que hace que este plano funcione: los 16 canales
de gaveta quedan en las filas F1…F8 de las dos columnas, mirando cada uno a su
lateral, y los hilos de los micros van rectos y cortos.

```
          C1 C2 C3 C4 C5 C6  C7   C8..C12   C13  C14 C15 C16 C17 C18 C19 C20
        ┌──────────────────────────────────────────────────────────────────┐
 L1 ●───┤  ·  ·  ·  ·  ·  · [ 1 GPA0]        [GPB7 28] ·  ·  ·  ·  ·  ·  · ├───● R1  (gav 16)
 L2 ●───┤                   [ 2 GPA1]        [GPB6 27]                     ├───● R2
 L3 ●───┤                   [ 3 GPA2]        [GPB5 26]                  J2 ├───● R3
 L4 ●───┤                   [ 4 GPA3]        [GPB4 25]                     ├───● R4
 L5 ●───┤                   [ 5 GPA4]  bajo  [GPB3 24]        R3        J3 ├───● R5
 L6 ●───┤                   [ 6 GPA5]   el   [GPB2 23]                     ├───● R6
 L7 ●───┤                   [ 7 GPA6] zócalo [GPB1 22]                     ├───● R7
 L8 ●───┤                   [ 8 GPA7]        [GPB0 21]       JP1           ├───● R8  (gav 9)
        ├───────────────────────────────────────────────────────────────── │
 L9 ●───┤  ·  R1 ·  R2  ·  ═[ 9 VDD ]════════ INTA 20 ══════════════════ · ├───● R9
L10 ●───┤ C3  ·  ·  ·  ·  ═[10 VSS ]════════ INTB 19 ══════════════════ · ├───● R10
L11 ●───┤  ·  ·  ·  ·  ·  ══ 11 NC  ═════════ RESET 18 ═════ DATA_IN ══╗   ├───● R11
L12 ●───┤ F1  ·  ·  ·  ·  ═[12 SCL ]════════ A2   17 ═══════════════════ · ├───● R12
        │  ·  ·  ·  ·  ·  ═[13 SDA ]════════ A1   16 ══════════════════ ·  │
        │ J0  ·  ·  ·  ·  ══ 14 NC  ═════════ A0   15 ═══════════ DATA_RET │
        └──────────────────────────────────────────────────────────────────┘
           J1 (C2, F9→F14)                                  J4 (C20, F9→F14)

  ═══  pista horizontal de hilo estañado      [ ]  se suelda en ese pin
  ══   pista que SALTA ese pin sin tocarlo     ·   agujero libre
```

### 2.1 Pads laterales — los 16 micros

| Pad | Señal | Pin MCP | Pad | Señal | Pin MCP |
|:---:|:---|:---:|:---:|:---|:---:|
| **L1** | Micro gaveta **1** | 1 (GPA0) | **R1** | Micro gaveta **16** | 28 (GPB7) |
| **L2** | Micro gaveta **2** | 2 (GPA1) | **R2** | Micro gaveta **15** | 27 (GPB6) |
| **L3** | Micro gaveta **3** | 3 (GPA2) | **R3** | Micro gaveta **14** | 26 (GPB5) |
| **L4** | Micro gaveta **4** | 4 (GPA3) | **R4** | Micro gaveta **13** | 25 (GPB4) |
| **L5** | Micro gaveta **5** | 5 (GPA4) | **R5** | Micro gaveta **12** | 24 (GPB3) |
| **L6** | Micro gaveta **6** | 6 (GPA5) | **R6** | Micro gaveta **11** | 23 (GPB2) |
| **L7** | Micro gaveta **7** | 7 (GPA6) | **R7** | Micro gaveta **10** | 22 (GPB1) |
| **L8** | Micro gaveta **8** | 8 (GPA7) | **R8** | Micro gaveta **9** | 21 (GPB0) |
| **L9…L12** | **GND** común | 10 (VSS) | **R9…R12** | **GND** común | 10 (VSS) |

> ⚠️ **El lateral derecho va al revés a propósito: R1 = gaveta 16, R8 = gaveta 9.**
> No es una errata. El MCP numera GPB de abajo arriba, y respetarlo es lo que
> deja los ocho hilos rectos y sin cruces. **Rotula la placa**, porque a los
> seis meses nadie se acuerda y el síntoma —la gaveta 9 enciende y suena la 16—
> parece un fallo de software.

Cada micro lleva **un solo hilo** al pad que le toca; el retorno es la masa
común de L9…L12 / R9…R12. El firmware activa los pull-up internos de 100 kΩ del
MCP23017, así que el microinterruptor va **directo entre el pad y GND**, sin
resistencia.

- Contacto **cerrado** a GND = nivel `0` = **gaveta dentro**.
- Contacto **abierto** = nivel `1` = **gaveta fuera**.

### 2.2 Conectores de la rejilla

Todos son pads de la propia rejilla: suelda tira de pines o el hilo directo.
**Los cinco van en las columnas de los bordes (C1, C2 y C20)**, así todos los
cables salen por los laterales y el centro queda libre.

| Ref | Agujeros | Señales | Va a |
|:---|:---|:---|:---|
| **J0** | C1/F14, C1/F10 | `+5V`, `GND` | Bornes de la **fuente de 5 V**. Solo en la MASTER. |
| **J1** | C2, F9→F14 | `+3V3`, `GND`, `DATA_IN`, `SCL`, `SDA`, `+5V` | **MASTER:** el DB9 del lector. **ESCLAVA:** el J4 de la placa anterior. |
| **J2** | C20, F1→F3 | `+5V`, `GND`, `DATA_OUT` | Cabeza de la tira WS2813 de **esta** placa (16 LEDs). |
| **J3** | C20, F5→F6 | `DATA_RET`, `GND` | Cola de la tira de esta placa (el `DO` del último LED). |
| **J4** | C20, F9→F14 | `+3V3`, `GND`, `DATA_RET`, `SCL`, `SDA`, `+5V` | El **J1 de la placa siguiente**. |

**El orden de J1 y J4 no es arbitrario: cada señal está en la fila de la pista
que le corresponde** (F9 = +3V3, F10 = GND, F11 = datos, F12 = SCL, F13 = SDA,
F14 = +5V). Por eso los dos conectores llevan el mismo orden, el cable entre
placas es recto pin a pin, y ninguna señal necesita cambiar de fila dentro de la
placa. Ver §2.3.

El mapeo de J1 en la MASTER contra el DB9 que ya está documentado:

| Pad J1 | Fila | Señal | Pin DB9 | Color |
|:---:|:---:|:---|:---:|:---|
| 1 | F9 | +3,3 V (**entra**, del lector) | 3 | Amarillo |
| 2 | F10 | GND | 1 | Blanco 0,25 |
| 3 | F11 | Datos WS2813 (GPIO17) | 2 | Naranja |
| 4 | F12 | I2C SCL (GPIO48) | 5 | Azul |
| 5 | F13 | I2C SDA (GPIO47) | 6 | Violeta |
| 6 | F14 | +5 V (**sale**, hacia el lector) | 9 | Blanco 0,5 |

### 2.3 Las pistas

Plano completo agujero a agujero:
[esquema_master_pistas_A4.html](schematics/esquema_master_pistas_A4.html).

Dos tipos de hilo, y no se mezclan:

- **Hilo estañado desnudo** — solo las **6 pistas horizontales** de las filas
  F9…F14. Se tienden rectas por la cara de cobre y se sueldan agujero a
  agujero. Son la estructura de la placa.
- **Hilo aislado** (kynar, AWG26) — todo lo demás: los 16 micros, los saltos,
  los straps y las salidas de LED. Pasa por encima de las pistas desnudas sin
  tocarlas. **Nunca tiendas desnudo nada que cruce otra pista.**

| Fila | Net | Tramos | Suelda en el zócalo |
|:---:|:---|:---|:---|
| **F9** | `+3V3` | C2–C12 · salto · C14–C20 | **C7 = pin 9 (VDD)** |
| **F10** | `GND` | C2–C12 · salto · C14–C20 | **C7 = pin 10 (VSS)** |
| **F11** | `DATA_IN` | C2–C6 · salto · C8–C12 · salto · C14–C16 | ninguno |
| **F11** | `DATA_RET` | C17–C20 — **tramo aparte, no toca el anterior** | ninguno |
| **F12** | `SCL` | C2–C12 · salto · C14–C20 | **C7 = pin 12 (SCL)** |
| **F13** | `SDA` | C2–C12 · salto · C14–C20 | **C7 = pin 13 (SDA)** |
| **F14** | `+5V` | C2–C6 · salto · C8–C12 · salto · C14–C20 | ninguno |

**«Salto» = la pista pasa por encima de la columna del pin (C7 o C13) con hilo
aislado y NO se suelda en ese agujero.** Los cinco saltos sobre C13 son
obligatorios: ahí están RESET y los tres straps de dirección. El de F14 es el
crítico — soldarlo pondría **+5 V en A0**, que está fuera de especificación
(máximo VDD = 3,3 V) y se lleva el chip.

Las columnas **C8…C12 quedan bajo el cuerpo del zócalo y no tienen pines**: por
ahí pasan los saltos, sin estorbar a nada.

#### Puentes de hilo aislado

| Desde → hasta | Qué es |
|:---|:---|
| L1…L8 → C7/F1…F8 | Micros de las gavetas 1–8 |
| R1…R8 → C13/F1…F8 | Micros de las gavetas **16…9** (al revés, ver §2.1) |
| L9-L10-L11-L12 encadenados → C3/F10 | Masa de los micros del lado izquierdo |
| R9-R10-R11-R12 encadenados → C19/F10 | Masa de los micros del lado derecho |
| **C14/F9 → C13/F11** | **RESET a +3,3 V. Imprescindible.** |
| C13/F12, C13/F13, C13/F14 → C14/F10 | Straps A2, A1, A0. MASTER = todos a GND (`0x20`). Para una esclava, los que toquen van a **C14/F9** (+3V3). |
| C1/F12 → C2/F14 · C1/F10 → C2/F10 | Entrada de la fuente a los raíles |
| C16/F5 → C20/F3 | Datos a la tira, después de R3 |
| C19/F14 → C20/F1 | +5 V de la tira |
| C19/F10 → C20/F2 · C19/F10 → C20/F6 | Masa de la tira, ida y vuelta |
| C20/F5 → C17/F11 | Retorno de la tira hacia J4 |

#### Dónde va cada componente

| Ref | Agujeros | Nota |
|:---|:---|:---|
| **Zócalo DIP-28** | C7 y C13, F1…F14 | Muesca **arriba**. |
| **F1** PTC 2 A | C1/F14 → C1/F12 | Radial, 5,08 mm = 2 agujeros. Solo MASTER. |
| **C3** 1000 µF / 10 V | C1/F12 (+) → C1/F10 (−) | Detrás del PTC. Solo MASTER. |
| **R1** 4k7 | C3/F13 (SDA) → C3/F9 (3V3) | Solo MASTER. |
| **R2** 4k7 | C5/F12 (SCL) → C5/F9 (3V3) | Solo MASTER. |
| **Cd** 100 nF | C7/F9 → C7/F10 | Justo entre los pines 9 y 10 del zócalo: 2,54 mm, clavado. En **todas** las placas. |
| **JP1** | C16/F11 → C16/F8 | Puente de hilo. Quítalo para intercalar un buffer externo. |
| **R3** 330 Ω | C16/F8 → C16/F5 | En todas las placas. |

> El 74AHCT125 **no cabe** en esta placa junto con todo lo demás. Si hace falta
> (ver §5), va en una plaquita aparte intercalada en JP1: quitas el puente y
> sacas esos dos puntos al buffer. Con eso la placa sigue siendo la misma.

> Ojo al sentido de los 5 V: el **+3,3 V entra** en la placa (lo genera el
> regulador del lector) y los **+5 V salen** de la placa hacia el lector. La
> MASTER es la que reparte la fuente, el lector no.

---

## 3. Lista de montaje

### MASTER

| Ref | Componente | Dónde | Por qué |
|:---|:---|:---|:---|
| **U1** | MCP23017-E/SP (DIP-28) + zócalo | C7/C13, F1…F14, muesca arriba | Los 16 canales. **Zócalo siempre**: un MCP muerto se cambia sin desoldar 24 hilos. |
| **R1, R2** | 4,7 kΩ | SDA→3V3 y SCL→3V3 | Pull-ups **del bus entero**. Van solo aquí. |
| **R3** | 330 Ω | C16/F8 → C16/F5 | Protege la primera entrada de la tira y redondea el flanco. |
| **Cd** | 100 nF cerámico | C7/F9 → C7/F10 | Desacoplo, clavado entre los pines 9 y 10. Sin él, el I2C da lecturas fantasma. |
| **C3** | 1000 µF / 10 V electrolítico | C1/F12 (+) → C1/F10 (−) | Golpe de corriente al encender la tira. Es el condensador que se salta todo el mundo y luego el primer LED sale de color raro. |
| **F1** | PTC rearmable 2 A | C1/F14 → C1/F12 | Un pelo de la tira tocando masa no puede fundir la fuente ni recocer la pista. |
| **JP1** | Puente de hilo | C16/F11 → C16/F8 | Punto de corte para intercalar un buffer, ver §5. |

### ESCLAVA

Lo mismo **quitando** R1, R2, F1 y J0. Se queda en: U1 + zócalo, Cd, R3, JP1,
las 6 pistas horizontales y los cuatro conectores (J1, J2, J3, J4). Los straps
A0/A1/A2 según la tabla de §4.

**La esclava sí lleva su propio C3.** Cada placa inyecta los 5 V de su tramo de
tira y necesita su depósito. Va soldado **entre C20/F1 (+5V) y C20/F2 (GND)**,
que son los dos pines de J2: 2,54 mm, justo en el punto de inyección, que es
además el mejor sitio eléctrico. En la MASTER puedes ponerlo ahí también, además
del de J0.

---

## 4. Dirección I2C: los straps A0 / A1 / A2

Pines 15 (A0), 16 (A1) y 17 (A2), cada uno a **GND** o a **+3,3 V** — nunca al
aire. En la MASTER van los tres a GND (`0x20`). En las esclavas, según el banco
de gavetas que lleven:

| Placa | Gavetas | Dirección | A2 (17) | A1 (16) | A0 (15) |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **MASTER** | 1 – 16 | `0x20` | GND | GND | GND |
| ESCLAVA 1 | 17 – 32 | `0x21` | GND | GND | **3V3** |
| ESCLAVA 2 | 33 – 48 | `0x22` | GND | **3V3** | GND |
| ESCLAVA 3 | 49 – 64 | `0x23` | GND | **3V3** | **3V3** |
| ESCLAVA 4 | 65 – 80 | `0x24` | **3V3** | GND | GND |
| ESCLAVA 5 | 81 – 96 | `0x25` | **3V3** | GND | **3V3** |
| ESCLAVA 6 | 97 – 112 | `0x26` | **3V3** | **3V3** | GND |
| ESCLAVA 7 | 113 – 128 | `0x27` | **3V3** | **3V3** | **3V3** |

**`RESET` (pin 18) va SIEMPRE a +3,3 V.** Si queda flotando, el chip se
reinicia solo y el puesto pierde gavetas al azar. `INTA` (20) e `INTB` (19) se
dejan al aire: el firmware sondea, no usa interrupciones.

---

## 5. Los datos de la tira: 3,3 V o 74AHCT125

El WS2813 quiere un `1` lógico por encima de 0,7 × VDD = **3,5 V**, y el ESP32
da 3,3 V. Los puestos que ya están montados funcionan así, con la resistencia de
330 Ω y punto — pero funcionan **de milagro y por poco**, y el síntoma de que no
llega es siempre el mismo: el primer LED de la tira parpadea de colores
aleatorios y los demás van bien.

**El 74AHCT125 no cabe en esta placa.** Un DIP-14 más el 1000 µF más cinco
conectores en 20 × 14 agujeros es demasiado optimista, y forzarlo estropearía el
trazado limpio de las 6 pistas. En vez de eso, la placa deja **el punto de
corte**:

| JP1 (C16/F11 ↔ C16/F8) | Camino de los datos |
|:---|:---|
| **Puente de hilo puesto** | `DATA_IN` → R3 330 Ω → J2. Igual que los puestos ya montados. |
| **Puente quitado** | Esos dos agujeros salen a un buffer externo: `C16/F11` es la entrada, `C16/F8` la salida ya a 5 V, y R3 sigue haciendo su trabajo detrás. |

Móntala **con el puente** si el cable a la tira es corto. Quítalo y pon el buffer
si la tira queda a más de un metro o si ves el primer LED tonteando. El
74AHCT125 tiene cuatro buffers: usa uno, aliméntalo a 5 V y **ata las entradas
de los otros tres a GND**, que si no oscilan y calientan.

**La esclava nunca necesita adaptador.** Los datos que le llegan por J1 vienen
del `DO` del último LED de la tira anterior, que ya son 5 V regenerados.

---

## 6. Alimentación: dónde va la corriente gorda

```
  FUENTE 5 V ──► J0 (C1/F14) ──► F1 PTC 2A ──► C1/F12 ──► PISTA F14 (+5V)
                                                                │
                                      ┌─────────────────────────┼──────────────┐
                                      ▼                         ▼              ▼
                              J1/F14 ──► DB9-9          C19/F14 ──► J2      J4/F14
                              (lector)                   (tira 16 LED)     (ESCLAVA)

  FUENTE GND ──► J0 (C1/F10) ──► PISTA F10 (GND) ──► MASA COMÚN de la placa
                                 (fuente + lector + micros + tira)
```

- **La masa tiene que ser una sola.** El `GND` de la fuente, el `GND` que viene
  del lector por el DB9 y el retorno de los micros se juntan **en la MASTER y
  en ningún otro sitio**. Sin masa común, la señal de datos no tiene contra qué
  medirse y la tira hace cosas que parecen un fallo de firmware.
- **El +3,3 V lo da el regulador del lector.** Solo alimenta los MCP23017 (un
  par de mA cada uno). No cuelgues nada más de ahí.
- ⚠️ **NUNCA alimentes el MCP23017 a 5 V.** Sus líneas SDA/SCL subirían a 5 V y
  se llevan por delante los GPIO del ESP32-S3, permanentemente.
- ⚠️ **NUNCA conectes el USB-C del lector y los 5 V del DB9 a la vez.**
- **A partir de tres placas, lleva los 5 V de la tira directos de la fuente a
  cada J0**, no encadenados por J4. Treinta y dos LEDs a tope son ~2 A y todo
  eso pasa hoy por la MASTER. La cadena de datos sigue igual; solo se reparte la
  corriente.

---

## 7. Orden de montaje y comprobación

Cada paso se comprueba antes de pasar al siguiente. Este orden existe porque los
fallos caros son los de alimentación y se detectan todos con el polímetro, antes
de enchufar nada.

1. **Primero las 6 pistas horizontales** (F9…F14), con el zócalo puesto pero
   vacío. Luego los puentes, los componentes y por último los 16 micros.
2. **Continuidad con el polímetro, sin tensión y sin el MCP:**
   - Pin 9 ↔ F9, pin 10 ↔ F10, pin 12 ↔ F12, pin 13 ↔ F13 → **deben pitar**.
   - Pin 18 (RESET) ↔ +3V3 → **debe pitar**.
   - Pines 11, 14, 15, 16, 17, 19 y 20 contra +5 V y contra GND → **todos
     abiertos**. Aquí es donde se caza un salto mal hecho sobre C13.
   - +5 V ↔ GND → **abierto**. Si pita, el C3 está del revés o hay un puente.
   - L9…L12 y R9…R12 ↔ pin 10 → deben pitar.
3. **Enchufa la fuente, todavía sin el MCP.** Mide en el zócalo: pin 9 = 3,30 V,
   pin 18 = 3,30 V, pin 10 = 0 V. Si el pin 9 marca 5 V, **para aquí**.
4. **Desenchufa, pon el MCP en el zócalo** (muesca arriba) y vuelve a dar
   tensión.
5. **Reinicia el lector RFID.** La pantalla de reposo tiene que poner
   `PTL 1xMCP 16GAV` (o `2xMCP 32GAV` con la esclava). Si sigue poniendo
   `SIN PTL`, el bus I2C no ve nada: revisa SDA/SCL, los pull-ups de 4k7 y el
   RESET.
6. **Admin → Lectores RFID → probar cableado.** Enciende LED a LED y ve
   cerrando micros: la prueba te dice qué canal lee cada uno. Aquí es donde
   salta el lateral derecho invertido si te lo has saltado.
7. **Prueba de verdad:** pide un terminal desde engastado y coge la gaveta. Dos
   toques cortos y **ascendentes** = la buena. Un zumbido **grave y machacón** =
   has abierto otra. Si suenan parecidos, el zumbador está mal o el firmware es
   anterior a `2026-09-11e`.

---

## 8. Lo que se rompe y cómo se ve

| Síntoma | Causa casi segura |
|:---|:---|
| La pantalla pone `SIN PTL` | Sin pull-ups 4k7, RESET al aire, o SDA/SCL cambiados. |
| Dice `1xMCP` habiendo dos placas | Las dos con el mismo strap de dirección. Los `0x20` duplicados se ven como uno. |
| La gaveta 9 enciende y suena la 16 | Lateral derecho cableado ascendente. Ver §2.1. |
| Gavetas que aparecen y desaparecen solas | `RESET` flotando, o falta C1 junto al MCP. |
| El primer LED hace colores raros, el resto bien | Nivel de datos justo: pasa JP1 a **AHCT**. |
| Toda la tira apagada pero los micros van | La tira sin 5 V (F1 disparado), o `DATA_OUT` sin R3. |
| Un banco entero "fuera" de golpe | Ese expansor no contesta. El firmware lo marca como `canales_error`, no como gavetas fuera: míralo en Admin. |
| El chip se calienta o no arranca | Un salto sobre C13 soldado donde no tocaba. El de F14 (+5 V en A0) es el que mata. Ver §2.3. |
| La dirección no es la que pusiste | El salto de F12 o F13 sobre C13 está soldado: SCL o SDA metidos en A2/A1. |
| Suena la alarma con todas las gavetas puestas | Canal sin micro cableado que el servidor sí tiene como válido. Revisa la lista de terminales del puesto. |
