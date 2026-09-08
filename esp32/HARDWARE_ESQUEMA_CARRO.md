# Esquema Eléctrico y Guía de Montaje: ESP32 del Carro (Pantalla Gen4)

Ficheros de esquema listos para imprimir en **1 página A4**:
- 📄 **HTML Imprimible (Ctrl+P / PDF):** [esp32/schematics/esquema_carro_A4.html](esp32/schematics/esquema_carro_A4.html)
- 🖼️ **Gráfico Vectorial SVG:** [esp32/schematics/esquema_carro_A4.svg](esp32/schematics/esquema_carro_A4.svg)

---

## ⚡ 1. Sistema de Alimentación e Interruptor General

```
[ Power Bank Ansmann 20.000 mAh ]
              │ (USB-A 5V / 2A)
              ▼
    [ Hilo +5V VBUS Cable USB-C ]
              │
              ├─── [ INTERRUPTOR GENERAL ON/OFF ] ─── (Corta Hilo +5V VBUS)
              │
              ▼
   [ Conector USB-C Display gen4 ]
```

> ⚠️ **REGLA CRÍTICA DE ALIMENTACIÓN:**  
> El interruptor de encendido **DEBE** cortar el hilo **VBUS (+5V)** del cable USB-C.  
> **NO** conectar el interruptor al pin **EN-RST** (pad 22): de lo contrario, el microprocesador se resetea pero el zumbador suena a mosca y el lector PN532 se queda colgado encendido.

---

## 🔌 2. Tabla de Conexiones del Breakout FFC de 30 Vías (gen4-ESP32-24)

| Pad Breakout | Señal / GPIO | Componente Conectado | Notas de Montaje |
|:---:|:---:|:---|:---|
| **1** | **GND** | **Masa Común de Pulsadores** | Un solo cable de masa recorre los 8 botones |
| **2** | **GPIO17** | **Pulsador Puesto 1** | Entrada digital N.A., `Pin.IN, Pin.PULL_UP` |
| **3** | **GPIO18** | **Zumbador (Buzzer)** | Salida audio. Opc. Resistencia 10kΩ a GND anti-ruido |
| **4** | **GPIO16** | **Pulsador Puesto 2** | Entrada digital N.A. |
| **5** | **GPIO15** | **Pulsador Puesto 3** | Entrada digital N.A. |
| **6** | **GPIO48** | **Pulsador Puesto 4** | Entrada digital N.A. |
| **7** | **GPIO47** | **Pulsador Puesto 5** | Entrada digital N.A. |
| **8** | **GPIO38** | **Pulsador Puesto 6** | Entrada digital N.A. |
| **9** | **GPIO39** | **Pulsador Puesto 7** | Entrada digital N.A. |
| **10** | **GPIO40** | **Pulsador OK / Confirmar** | **Botón 8 (OK):** Confirma recogida o devolución |
| **11** | **GPIO6** | **PN532 SDA (I2C)** | Bus I2C de datos del lector NFC |
| **12** | **GPIO5** | **PN532 SCL (I2C)** | Bus I2C de reloj del lector NFC |
| **13, 14, 15** | GPIO3, 45, 46 | *Libres* | ⚠️ Strapping del S3. No forzar niveles al encender |
| **20** | **3.3V OUT** | Alimentación lógica 3.3V | Máx. 150 mA |
| **21, 25, 30** | **GND** | Masas adicionales | Para apantallamiento o PN532 |
| **26, 27, 28, 29** | **5V IN** | +5V Directo desde USB | Alimentación principal PN532 VCC |

---

## 🛠️ 3. Esquema de Periféricos

### A. Panel de 8 Pulsadores (Puestos 1..7 + OK)
- **Modo:** Normalmente Abiertos (N.A.) a GND.
- **Pull-Up:** Configurado por software (`Pin.PULL_UP`).
- **Antirrebote Industrial:** Recomendado colocar un condensador **100 nF (0.1 µF)** en paralelo con cada pulsador (entre pad del breakout y GND).

### B. Lector NFC PN532 (Módulo V3 I2C)
- **Microswitch I2C:** Configurar la placa PN532 en modo I2C poniendo **DIP 1 = ON** y **DIP 2 = OFF**.
- **Filtro de Alimentación Anti-Reinicios:** Conectar en paralelo pegado a los pines VCC/GND del módulo PN532:
  - Condensador Electrolítico de **100 µF** (16V).
  - Condensador Cerámico de **100 nF**.
- **Montaje Mecánico en el Carro:** El carro es metálico. **NUNCA** atornillar o pegar la antena NFC directamente contra la chapa metálica. Usar separadores de plástico de **1 a 2 cm** o colocar una lámina de ferrita detrás de la antena.

### C. Zumbador / Buzzer
- **Buzzer Activo (3.3V):** Conectar positivo (+) a Pad 3 (GPIO18) y negativo (-) a GND.
- **Resistencia Anti-Moscas:** Resistencia de **10 kΩ** conectada entre Pad 3 y GND para asegurar nivel bajo constante durante resets de la placa.

---

## 📄 Impresión a 1 Página A4
Para obtener la hoja impres en el taller:
1. Abre [esp32/schematics/esquema_carro_A4.html](esp32/schematics/esquema_carro_A4.html) en Microsoft Edge o Google Chrome.
2. Pulsa el botón **"Imprimir / Guardar en PDF"** o presiona `Ctrl + P`.
3. Selecciona la impresora o "Guardar como PDF", orientándolo a **A4 Vertical**.
