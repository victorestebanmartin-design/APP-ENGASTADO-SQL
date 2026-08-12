# WiFi Configuration Template
# Edit these values with your actual network credentials

SSID = "YOUR_SSID"           # Your WiFi network name
PASSWORD = "YOUR_PASSWORD"   # Your WiFi password

# Backend server address
# Use the IP of your PC running app-engastado-sql
# Example: "http://192.168.1.100:5001"
BACKEND_URL = "http://192.168.1.100:5001"

# GPIO Configuration
BUZZER_PIN = 26    # GPIO pin for buzzer
LED_PIN = 2        # GPIO pin for status LED (optional)

# SPI Configuration (RC522 RFID reader)
SPI_BAUDRATE = 1000000  # 1MHz for RC522
SPI_CS_PIN = 5          # Chip select = GPIO 5
SPI_CLK_PIN = 18        # Clock = GPIO 18
SPI_MOSI_PIN = 23       # MOSI = GPIO 23
SPI_MISO_PIN = 19       # MISO = GPIO 19

# Debounce time (milliseconds) between card reads
DEBOUNCE_MS = 2000

# Request timeout (seconds)
REQUEST_TIMEOUT = 5
