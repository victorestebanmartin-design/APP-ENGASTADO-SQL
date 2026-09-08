# Esquema Eléctrico y Guía de Montaje: ESP32 Lector Puesto + Pick-To-Light (PTL)

Ficheros del esquema de montaje listos para imprimir en **1 página A4**:
- 📄 **HTML Imprimible (Ctrl+P / PDF):** [esp32/schematics/esquema_puesto_A4.html](esp32/schematics/esquema_puesto_A4.html)
- 🖼️ **Gráfico Vectorial SVG:** [esp32/schematics/esquema_puesto_A4.svg](esp32/schematics/esquema_puesto_A4.svg)

---

## ⚡ 1. Alimentación y Protección de la Caja
El Lector de Puesto Gen4 admite dos opciones de alimentación:
1. **USB-C Directo:** Para programación y pruebas en banco.
2. **Fuente Externa 5V Pick-To-Light:** Mediante el conector **DB9 Pin 9 (+5V)** y **DB9 Pin 1 (GND)**.

```
Fuente Externa PTL (+5V)
    ──► Fusible PTC 1A ──► Diodo SS14 ──► DB9 Pin 9 ──► Breakout Pad 26 (5V IN)

Fuente Externa PTL (GND)
    ──────────────────────────────────────► DB9 Pin 1 ──► Breakout Pad 25 (GND)
```

> ⚠️ **REGLA ABSOLUTA:**  
> **NUNCA conectar USB-C y los 5V del DB9 al mismo tiempo.**  
> La fuente externa de 5V alimenta el lector y la tira de LEDs WS2813. La corriente pesada de la tira de LEDs se conecta **directamente** a los bornes de la fuente de 5V, **nunca** haciéndola circular a través de la caja del lector ni del DB9.

---

## 🔌 2. Mapado Completo del Conector DB9 Hembra y Breakout 30 Vías

| Pin DB9 | Color Hilo | Pad Breakout / GPIO | Función / Destino MUX 1 |
|:---:|:---:|:---:|:---|
| **1** | Blanco (0.25 mm²) | **Pad 25 (GND)** | Masa común del bus y retorno de fuente |
| **2** | Naranja | **Pad 2 (GPIO17)** | Datos WS2813 (330 Ω en serie a DIN+BI) |
| **3** | Amarillo | **Pad 20 (+3.3V)** | **3.3V VDD & RESET del MCP23017** |
| **4** | Verde | Pad 5 (GPIO15) | *Libre* (GPIO dañado por 5V anterior, aislar) |
| **5** | Azul | **Pad 6 (GPIO48)** | **I2C SCL (3.3V)** para MCP23017 |
| **6** | Violeta | **Pad 7 (GPIO47)** | **I2C SDA (3.3V)** para MCP23017 |
| **7** | Gris | Pad 8 (GPIO38) | Reserva / Aislar |
| **8** | — | — | Sin cable |
| **9** | Blanco (0.5 mm²) | **Pad 26 (5V IN)** | Entrada +5V protegida por PTC 1A y SS14 |

> ⚠️ **ADVERTENCIA CRÍTICA DE CABLEADO DB9-3:**  
> En montajes antiguos DB9-3 iba al Pad 4 (GPIO16). **Actualmente DB9-3 lleva +3.3V directos del Pad 20** para alimentar la lógica de los MCP23017.  
> **Verificar que el Pad 4 NO está unido a DB9-3.** Dejar unidos Pad 4 y Pad 20 quemará la patilla del microcontrolador.

---

## 🛠️ 3. Conexiones Periféricas

### A. Lector RFID PN532 (Modo I2C)
- **Modo I2C:** Microswitch interno del módulo PN532 en **DIP 1 = ON, DIP 2 = OFF**.
- **Conexiones:**
  - **SDA:** Pad 11 (GPIO6) - Cable Naranja.
  - **SCL:** Pad 12 (GPIO5) - Cable Amarillo.
  - **VCC:** Pad 20 (+3.3V) - Cable Rojo.
  - **GND:** Pad 21 (GND) - Cable Marrón.
- **Condensadores Anti-Reinicio:** 100 µF (electrolítico) + 100 nF (cerámico) soldados en paralelo directamente en las patillas VCC y GND del módulo PN532.

### B. Zumbador Acústico de Puesto (3.3V)
- **Positivo (+):** Pad 3 (GPIO18).
- **Negativo (-):** Pad 1 / 21 / 25 (GND).
- Emite pitidos de lectura correcta (1 bep), rechazado (2 beps) o error de comunicación (3 beps).

### C. Expansores I2C Multiplexor (MCP23017)
- **Alimentación Lógica:** **SIEMPRE a 3.3V** desde DB9-3 (Pad 20) y GND desde DB9-1 (Pad 25).
- **Bus I2C:** SCL a DB9-5 (GPIO48) y SDA a DB9-6 (GPIO47).
- **Pull-Ups:** Colocar dos resistencias de **4.7 kΩ** entre SDA y 3.3V, y entre SCL y 3.3V en el primer expansor.
- **Codificación de Direcciones I2C (Pines A2, A1, A0):** Ver documento completo en [esp32/HARDWARE_EXPANSORES_MCP23017.md](esp32/HARDWARE_EXPANSORES_MCP23017.md).

| Nº Expansor | Rango Gavetas | Dirección Hex | A2 (Pin 17) | A1 (Pin 16) | A0 (Pin 15) |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **MUX 1** | Gavetas 1 – 16 | `0x20` | GND | GND | GND |
| **MUX 2** | Gavetas 17 – 32 | `0x21` | GND | GND | **+3.3V** |
| **MUX 3** | Gavetas 33 – 48 | `0x22` | GND | **+3.3V** | GND |
| **MUX 4** | Gavetas 49 – 64 | `0x23` | GND | **+3.3V** | **+3.3V** |
| **MUX 5** | Gavetas 65 – 80 | `0x24` | **+3.3V** | GND | GND |
| **MUX 6** | Gavetas 81 – 96 | `0x25` | **+3.3V** | GND | **+3.3V** |
| **MUX 7** | Gavetas 97 – 112 | `0x26` | **+3.3V** | **+3.3V** | GND |
| **MUX 8** | Gavetas 113 – 128 | `0x27` | **+3.3V** | **+3.3V** | **+3.3V** |

---

## 📄 Impresión a 1 Página A4
Para imprimir en taller:
1. Abre [esp32/schematics/esquema_puesto_A4.html](esp32/schematics/esquema_puesto_A4.html) en el navegador.
2. Presiona el botón **"Imprimir / Guardar en PDF"** (`Ctrl + P`).
3. Selecciona orientación **Vertical (A4)**.
