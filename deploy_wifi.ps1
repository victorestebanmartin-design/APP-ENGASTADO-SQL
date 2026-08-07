# deploy_wifi.ps1 — Sube main_wifi.py al ESP32 por WiFi (sin cable USB)
#
# Uso:
#   .\deploy_wifi.ps1                    # usa IP y puerto por defecto
#   .\deploy_wifi.ps1 -IP 192.168.1.47  # IP especifica
#
# Requiere: WebREPL activo en el ESP32 (boot.py con webrepl.start())
# Password WebREPL: cojosw  (cambiar en boot.py si quieres)

param(
    [string]$IP       = "",
    [string]$Archivo  = "esp32\micropython\main_wifi.py",
    [string]$Destino  = "main.py"
)

# Detectar IP del ESP32 desde main_wifi.py si no se pasa
if (-not $IP) {
    $linea = Select-String -Path $Archivo -Pattern 'HOST_IP\s*=' | Select-Object -First 1 -ExpandProperty Line
    # La IP del ESP32 no es HOST_IP... buscamos en el archivo de config o pedimos
    $IP = Read-Host "IP del ESP32 (ej: 192.168.1.47)"
}

Write-Host ""
Write-Host "=== Deploy WiFi ESP32 ===" -ForegroundColor Cyan
Write-Host "Archivo : $Archivo"
Write-Host "ESP32 IP: $IP"
Write-Host ""

# Subir via WebREPL (mpremote soporta connect ws:host)
Write-Host "Subiendo $Archivo -> :$Destino por WiFi..."
.\venv\Scripts\python.exe -m mpremote connect "ws:$IP" cp $Archivo ":$Destino"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Error al subir. Comprueba que el ESP32 esta en la misma red y WebREPL esta activo."
    exit 1
}

Write-Host "Reiniciando ESP32..."
.\venv\Scripts\python.exe -m mpremote connect "ws:$IP" reset

Write-Host ""
Write-Host "Listo. ESP32 actualizado por WiFi." -ForegroundColor Green
