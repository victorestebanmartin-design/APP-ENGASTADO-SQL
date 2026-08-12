# ESP32 RFID Reader - Engastado V3 Entry System

Firmware for ESP32 DevKit V1 Type-C with RC522 RFID reader to identify operarios at Engastado V3 workstation entrance.

## Hardware Setup

### Wiring Diagram

**RC522 RFID Reader → ESP32 DevKit V1 Type-C**

```
RC522 Pin    ESP32 Pin    GPIO    Purpose
VCC          3.3V (pin 3)         Power
GND          GND (pin 1)          Ground
SDA          GPIO 5               SPI Chip Select (CS)
SCK          GPIO 18              SPI Clock (CLK)
MOSI         GPIO 23              SPI Master Out Slave In (MOSI)
MISO         GPIO 19              SPI Master In Slave Out (MISO)
IRQ          (not used)           Interrupt
```

**Buzzer (Active/Passive)**

```
Buzzer Pin   ESP32 Pin    Purpose
+ (Red)      GPIO 26      Signal (via 100Ω resistor if 5V buzzer)
- (Black)    GND          Ground
```

### Components Needed

- ESP32 DevKit V1 Type-C
- RC522 RFID Module
- Active Buzzer (5V or 3.3V)
- 100Ω resistor (if using 5V buzzer with 3.3V GPIO)
- USB Type-C cable (for programming)
- WiFi network with intranet access to your PC

## Software Setup

### 1. Flash MicroPython to ESP32

On your **PC libre** with USB access to ESP32:

```bash
# Install esptool
pip install esptool

# Download MicroPython for ESP32 generic
# From: https://micropython.org/download/esp32/
# Or use stable version:
wget https://micropython.org/resources/firmware/esp32-20240222-v1.22.2.bin

# Erase ESP32 flash
esptool.py erase_flash

# Flash MicroPython
esptool.py write_flash -z 0x1000 esp32-20240222-v1.22.2.bin

# Verify
esptool.py chip_id  # Should return chip_id
```

### 2. Upload MicroPython Files

Use **mpremote** or **ampy** to upload files to ESP32:

```bash
# Install mpremote
pip install mpremote

# Connect and upload files
mpremote mount .
mpremote cp main.py :/main.py
mpremote cp wifi_config.py :/wifi_config.py
mpremote cp mfrc522.py :/mfrc522.py
```

Or use **Thonny IDE** (graphical):
- Download: https://thonny.org
- File → Open → Open esp32/main.py
- Configure interpreter: Options → Interpreter → MicroPython (ESP32) with USB port
- Upload to device (Ctrl+Shift+S)

### 3. Configure WiFi & Backend URL

Edit `wifi_config.py` on the ESP32 with your network credentials:

```python
SSID = "YourWiFiNetwork"
PASSWORD = "YourWiFiPassword"
BACKEND_URL = "http://192.168.1.100:5001"  # Change to your PC's IP
```

**To find your PC's IP:**

Linux/Mac:
```bash
ifconfig | grep "inet "
```

Windows:
```
ipconfig
```

Look for the IP on the same subnet as your ESP32 (e.g., 192.168.x.x).

### 4. Test Connection

On ESP32, open serial monitor (115200 baud) and watch for:

```
ESP32 RFID Reader - Engastado V3
==================================================
Connecting to WiFi...
WiFi connected: ('192.168.1.50', '255.255.255.0', '192.168.1.1', '8.8.8.8')

Waiting for RFID card scan...
```

If you see connection errors, verify:
- WiFi SSID and password are correct
- Backend URL is reachable from ESP32 (test with curl on your PC)
- ESP32 is on same network as PC (no firewall blocking port 5001)

## RFID Card Registration

Before operarios can use the system, their RFID card UIDs must be registered in the database.

### Get Card UID

1. Connect ESP32 and place RFID card on reader
2. Serial monitor will show: `Card detected: A1B2C3D4`
3. Note the hex code (e.g., "A1B2C3D4")

### Register in Database

On your PC running app-engastado-sql:

**Via admin panel (if available):**
- Admin → Operarios → Edit operario → Scan RFID → Save

**Via direct SQL:**
```sql
UPDATE operarios SET tag_uid = 'A1B2C3D4' WHERE nombre = 'Juan Pérez';
```

**Via Python shell:**
```python
import sqlite3
conn = sqlite3.connect('data/engastado.db')
conn.execute("UPDATE operarios SET tag_uid = 'A1B2C3D4' WHERE nombre = 'Juan Pérez'")
conn.commit()
```

## Firmware Behavior

### Normal Operation

1. Operario scans RFID card at puesto entrance
2. ESP32 reads 4-byte card UID
3. Sends HTTP POST to `/api/puestos/engastado_v3/entrada`
4. **On success (200):** Buzzer beeps 2x, LED blinks (operario logged in)
5. **On card not found (404):** Buzzer beeps 1x (invalid card)
6. **On network error:** Buzzer beeps 5x, retries after 5 seconds

### Debounce

Minimum 2 seconds between reads to prevent double-scans. Operario can scan again after buzzer confirms.

## Troubleshooting

### "Card detected" but no HTTP request

- Check `BACKEND_URL` in wifi_config.py is correct
- Verify firewall on PC allows port 5001
- Test connectivity: `ping 192.168.1.100` from another device on network

### Buzzer not working

- Check GPIO 26 is connected to buzzer
- Verify buzzer + lead goes to GPIO 26, - lead to GND
- Test with: `from machine import Pin; Pin(26, Pin.OUT).on()`

### ESP32 won't connect to WiFi

- Verify SSID and password in wifi_config.py
- Check if WiFi requires special characters (edit with care)
- Try 2.4GHz network (some ESP32 have issues with 5GHz)

### RFID reader not detected

- Check SPI wiring: CS=5, CLK=18, MOSI=23, MISO=19
- Verify 3.3V power to RC522
- Try different RFID cards (some cards don't work)

## Files

- `main.py` - Main firmware loop
- `wifi_config.py` - WiFi & backend configuration
- `mfrc522.py` - RFID library (must be uploaded to ESP32)

## Backend Integration

The firmware expects this endpoint to exist:

```
POST /api/puestos/engastado_v3/entrada
Request:  { "tag_uid": "A1B2C3D4" }
Response: 200 OK { "success": true, "operario_nombre": "Juan Pérez", "login_id": "..." }
Response: 404 Not Found { "success": false, "error": "Tarjeta RFID no registrada" }
```

See backend implementation in `app/routes/operarios.py`.

## References

- MicroPython documentation: https://docs.micropython.org
- RC522 RFID library: https://github.com/mfrc522/micropython-mfrc522
- ESP32 pinout: https://randomnerdtutorials.com/esp32-pinout-reference-gpios/
