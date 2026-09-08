# Codificación de Direcciones I2C para Expansores MCP23017 (Pick-To-Light)

Documentación oficial de configuración física de pines **A0, A1, A2** y direccionamiento para expansores de gavetas **MCP23017** en el sistema de Puesto.

---

## 📌 Principio de Funcionamiento

El firmware del Lector de Puesto (`esp32/micropython/lib/gavetas.py` y `mcp23017.py`) escanea el bus I2C y **ordena los expansores de menor a mayor dirección I2C (0x20 a 0x27)**.

- **Cada MCP23017 añade 16 gavetas/canales** al sistema.
- **Hasta 8 expansores en el mismo bus** (`0x20` a `0x27`), lo que permite un control total de hasta **128 gavetas** por puesto.
- La numeración de las gavetas en el sistema es consecutiva según la dirección I2C configurada físicamente en cada placa.

---

## 🎛️ Tabla de Codificación de Pines (A2, A1, A0) para 8 Expansores

Para fijar la dirección de cada expansor, se conectan sus patillas de dirección **A2, A1 y A0** a **Masa (GND)** o a **+3.3V**:

| Nº Expansor | Rango Gavetas | Dirección Hex | A2 (Pin 17) | A1 (Pin 16) | A0 (Pin 15) | Estado Lógico (A2 A1 A0) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **MUX 1** | **Gavetas 1 – 16** | `0x20` | **GND** (0V) | **GND** (0V) | **GND** (0V) | `0 0 0` |
| **MUX 2** | **Gavetas 17 – 32** | `0x21` | **GND** (0V) | **GND** (0V) | **+3.3V** | `0 0 1` |
| **MUX 3** | **Gavetas 33 – 48** | `0x22` | **GND** (0V) | **+3.3V** | **GND** (0V) | `0 1 0` |
| **MUX 4** | **Gavetas 49 – 64** | `0x23` | **GND** (0V) | **+3.3V** | **+3.3V** | `0 1 1` |
| **MUX 5** | **Gavetas 65 – 80** | `0x24` | **+3.3V** | **GND** (0V) | **GND** (0V) | `1 0 0` |
| **MUX 6** | **Gavetas 81 – 96** | `0x25` | **+3.3V** | **GND** (0V) | **+3.3V** | `1 0 1` |
| **MUX 7** | **Gavetas 97 – 112** | `0x26` | **+3.3V** | **+3.3V** | **GND** (0V) | `1 1 0` |
| **MUX 8** | **Gavetas 113 – 128** | `0x27` | **+3.3V** | **+3.3V** | **+3.3V** | `1 1 1` |

---

## 🛠️ Pinout Físico del Chip MCP23017 (Encapsulado DIP-28)

Si se realiza el montaje sobre placa de topos o diseño propio con el integrado **MCP23017-E/SP**:

```
                  ┌───┬───┐
       GPA0 (G1)  │ 1 ┊ 28│  GPB7 (G16)
       GPA1 (G2)  │ 2 ┊ 27│  GPB6 (G15)
       GPA2 (G3)  │ 3 ┊ 26│  GPB5 (G14)
       GPA3 (G4)  │ 4 ┊ 25│  GPB4 (G13)
       GPA4 (G5)  │ 5 ┊ 24│  GPB3 (G12)
       GPA5 (G6)  │ 6 ┊ 23│  GPB2 (G11)
       GPA6 (G7)  │ 7 ┊ 22│  GPB1 (G10)
       GPA7 (G8)  │ 8 ┊ 21│  GPB0 (G9)
  VDD (+3.3V) ──► │ 9 ┊ 20│  INTA
     VSS (GND) ──►│10 ┊ 19│  INTB
            NC    │11 ┊ 18│  ◄── RESET (Conectar a +3.3V Obligatorio)
    SCL (DB9-5) ─►│12 ┊ 17│  ◄── A2 (Dirección bit 2)
    SDA (DB9-6) ─►│13 ┊ 16│  ◄── A1 (Dirección bit 1)
            NC    │14 ┊ 15│  ◄── A0 (Dirección bit 0)
                  └───┴───┘
```

---

## 🔌 Conexiones de Alimentación y Bus para Todos los Módulos

### 1. Alimentación Lógica (`VDD` / `VSS`)
- **`VDD` (Pin 9):** Debe alimentar a **+3.3V estrictos** (procedente del conector **DB9-3** / Pad 20 de la gen4).
- **`VSS` (Pin 10):** Conectar a **Masa / GND** (procedente del conector **DB9-1** / Pad 25).
- **`RESET` (Pin 18):** Conectar **SIEMPRE a +3.3V**. *Si queda flotando, el chip se reinicia constantemente y se pierden datos I2C.*

> ⚠️ **NUNCA alimentar el MCP23017 a 5V.**  
> Si un MCP23017 se alimenta a 5V, sus líneas I2C (SCL/SDA) suben a 5V y queman permanentemente los GPIOs del ESP32-S3.

### 2. Bus I2C y Resistencias Pull-Up
- **`SCL` (Pin 12):** Conectar al hilo **DB9-5** (Azul, GPIO48).
- **`SDA` (Pin 13):** Conectar al hilo **DB9-6** (Violeta, GPIO47).
- **Resistencias Pull-Up:** Se requiere **un solo par de resistencias de 4.7 kΩ** entre `SDA` e `+3.3V`, y entre `SCL` e `+3.3V` en todo el bus I2C (colocadas en el primer multiplexor MUX 1). **NO añadir pull-ups en cada expansor**, ya que la resistencia equivalente en paralelo caería demasiado.

---

## 📦 Conexión de Micro-interruptores (Detección de Gavetas)

Cada canal (GPA0..GPA7, GPB0..GPB7) lee un micro-interruptor de gaveta:
- **Contacto Abierto (Gaveta fuera):** Lee nivel Alto `1`.
- **Contacto Cerrado a GND (Gaveta dentro):** Lee nivel Bajo `0`.
- El firmware activa automáticamente las resistencias Pull-Up internas de 100 kΩ del MCP23017, por lo que los micro-interruptores van conectados **directamente entre el pin del canal y GND**.
