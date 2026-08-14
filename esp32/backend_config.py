# backend_config.py -- Host del backend para la placa lectora RFID
# (Engastado V3). A DIFERENCIA de wifi_config.py, este fichero SI se
# actualiza por OTA (va en el manifiesto junto a main.py, ver
# _rfid_firmware_files en app/routes/sistema.py): si cambia el servidor
# (p.ej. de PythonAnywhere al servidor local de planta), basta con publicar
# el cambio aqui y las placas ya desplegadas lo recogen solas en su
# siguiente comprobacion OTA, sin necesidad de USB.
#
# Por eso este fichero NUNCA debe llevar SSID/PASSWORD/WEBREPL_PASSWORD:
# esos SI tienen que quedarse en wifi_config.py (USB-only), porque hacen
# falta ANTES de tener WiFi -- no se pueden descargar por una red a la que
# la placa todavia no esta conectada.

# Servidor LOCAL (planta, sin internet): IP fija del PC servidor y puerto
# de run_sql.py (5001), sin SSL (HTTP normal en la LAN).
BACKEND_HOST = "192.168.1.20"
BACKEND_PORT = 5001
BACKEND_USE_SSL = False
# Alternativa: servidor en PythonAnywhere (requiere que la placa tenga
# salida a internet; funciona tambien desde una red corporativa que solo
# permita saliente el 443):
#   BACKEND_HOST = "viktor85.pythonanywhere.com"
#   BACKEND_PORT = 443
#   BACKEND_USE_SSL = True
