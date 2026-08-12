# wifi_config.py -- Credenciales y configuracion de red de la placa lectora
# RFID (Engastado V3). NO se toca por OTA: se sube una vez por USB y punto.
#
# IMPORTANTE: rellena SSID, PASSWORD y WEBREPL_PASSWORD con los valores REALES
# en tu copia local antes de subirla a la placa, pero NO subas ese cambio a
# git con las credenciales reales dentro (este fichero se versiona con
# valores de ejemplo a proposito).

SSID = "YOUR_SSID"                # Nombre de tu red WiFi
PASSWORD = "YOUR_PASSWORD"        # Contrasena de tu red WiFi
WEBREPL_PASSWORD = "YOUR_WEBREPL_PASSWORD"  # Contrasena de WebREPL (puerto 8266)

# Backend: la misma app Flask/SQLite (COJOsw) que ya usan la pantalla del
# carro y el resto del sistema, servida por PythonAnywhere sobre HTTPS
# estandar (443). Todo el trafico de esta placa -- lectura RFID y OTA -- pasa
# por aqui, así que funciona igual desde cualquier red (incluida la
# corporativa, que solo permite saliente el 443).
BACKEND_HOST = "viktor85.pythonanywhere.com"
BACKEND_PORT = 443
BACKEND_USE_SSL = True

# GPIO Configuration
BUZZER_PIN = 26    # GPIO pin para el zumbador
LED_PIN = 2        # GPIO pin del LED de estado (opcional)

# SPI Configuration (lector RC522) -- el driver crea su propio SPI interno,
# solo hacen falta los numeros de pin.
SPI_CS_PIN = 5            # SDA/CS  = GPIO 5
SPI_CLK_PIN = 18          # SCK     = GPIO 18
SPI_MOSI_PIN = 23         # MOSI    = GPIO 23
SPI_MISO_PIN = 19         # MISO    = GPIO 19
SPI_RST_PIN = 22          # RST     = GPIO 22

# Debounce entre lecturas de tarjeta (milisegundos)
DEBOUNCE_MS = 2000

# Cada cuanto main.py vuelve a comprobar si hay firmware nuevo, ademas de la
# comprobacion automatica al arrancar (milisegundos). None = solo al arrancar.
OTA_CHECK_INTERVAL_MS = 60 * 60 * 1000  # 1 hora
