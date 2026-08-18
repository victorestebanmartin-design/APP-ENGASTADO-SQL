# wifi_config.py -- Credenciales y configuracion de red de la placa lectora
# RFID (Engastado V3). NO se toca por OTA: se sube una vez por USB y punto.
#
# IMPORTANTE: rellena SSID y PASSWORD con los valores REALES en tu copia
# local antes de subirla a la placa, pero NO subas ese cambio a git con las
# credenciales reales dentro (este fichero se versiona con valores de
# ejemplo a proposito).

SSID = "YOUR_SSID"                # Nombre de tu red WiFi
PASSWORD = "YOUR_PASSWORD"        # Contrasena de tu red WiFi

# WebREPL: consola de Python remota (puerto 8266) para depurar la placa por
# WiFi en lugar de con el cable USB. OPCIONAL y apagado por defecto: vacio =
# no se arranca (ver boot.py). Si alguna vez quieres depurar una placa en
# remoto, pon aqui una contrasena y vuelve a subir este fichero por USB.
WEBREPL_PASSWORD = ""

# --- IP fija de ESTA placa -------------------------------------------------
# La red de planta (192.168.50.0/24) no tiene DHCP: si la placa no se
# autoconfigura la IP, no conecta con nadie. STATIC_IP lo rellena el servidor
# al flashear por USB (Admin -> Lectores RFID -> "Configurar y subir por USB",
# campo "IP estatica"); vacio = pedir IP por DHCP, que solo sirve en una red
# de pruebas que si lo tenga.
#
# La mascara y la puerta de enlace son fijas para toda la instalacion
# (GATEWAY = el TL-WR802N, que hace tambien de DNS), asi que no se tocan por
# placa. Ver boot.py:_conectar_wifi().
STATIC_IP = ""                    # p.ej. "192.168.50.21"
SUBNET_MASK = "255.255.255.0"
GATEWAY = "192.168.50.5"
DNS = "192.168.50.5"

# El host del backend REAL vive en backend_config.py, que a diferencia de
# este fichero SI se actualiza por OTA (para poder migrar de servidor sin
# visitar cada placa con un cable USB). Lo de abajo es solo una RED DE
# SEGURIDAD y no se usa mientras main.py sea la version actual.
#
# Por que sigue aqui: si un main.py nuevo falla al arrancar 3 veces,
# ota_update.rollback_si_procede() restaura main_prev.py, que puede ser un
# main.py ANTERIOR al split de backend_config.py y que por tanto lee el host
# de aqui. Sin estas tres lineas ese rollback lanzaria AttributeError en cada
# arranque, el contador de fallos nunca se resetearia y la placa quedaria en
# bucle infinito -- justo lo que la red de seguridad pretende evitar. Con
# ellas, la placa arranca igual y ota_update (que si usa backend_config) puede
# volver a descargar el firmware bueno y curarse sola.
BACKEND_HOST = "192.168.50.1"
BACKEND_PORT = 5001
BACKEND_USE_SSL = False

# GPIO Configuration
BUZZER_PIN = 4     # GPIO pin para el zumbador
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
# Esta misma llamada hace de latido de presencia para Admin -> Lectores RFID
# (aparece "en linea"/"sin senal" segun cuando se vio por ultima vez), asi que
# conviene que no sea demasiado espaciada. Es un GET pequeno (unos cientos de
# bytes): 60s no supone trafico apreciable.
OTA_CHECK_INTERVAL_MS = 60 * 1000  # 1 minuto
