# setup_wifi.ps1 — Configura main_wifi.py con las credenciales WiFi y sube al ESP32
# Uso: .\setup_wifi.ps1
# Requisito: estar conectado al WiFi que va a usar el ESP32

param([string]$Puerto = "COM5")

Write-Host ""
Write-Host "=== Configuracion WiFi ESP32 ===" -ForegroundColor Cyan
Write-Host "Asegurate de estar conectado al mismo WiFi que usara el ESP32." -ForegroundColor Yellow
Write-Host ""

$ssid = Read-Host "Nombre de la red WiFi (SSID)"
$passSecure = Read-Host "Contrasena del WiFi" -AsSecureString
$pass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passSecure))

# Detectar IP del PC en la red actual
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object {
           $_.InterfaceAlias -notlike "*Loopback*" -and
           $_.IPAddress -notlike "169.*" -and
           $_.IPAddress -notlike "127.*" -and
           $_.PrefixOrigin -eq "Dhcp"
       } | Sort-Object InterfaceMetric | Select-Object -First 1).IPAddress

if (-not $ip) {
    Write-Host "No se detecto IP via DHCP. Introduce la IP del PC manualmente:" -ForegroundColor Yellow
    $ip = Read-Host "IP del PC en esa red"
}

Write-Host ""
Write-Host "Configurando con:" -ForegroundColor Green
Write-Host "  SSID   : $ssid"
Write-Host "  HOST IP: $ip"
Write-Host "  Puerto : $Puerto"
Write-Host ""

# Actualizar main_wifi.py
$file = "esp32\micropython\main_wifi.py"
$content = Get-Content $file -Raw -Encoding utf8

$content = $content -replace 'SSID\s*=\s*"[^"]*"',     "SSID     = `"$ssid`""
$content = $content -replace 'PASSWORD\s*=\s*"[^"]*"',  "PASSWORD = `"$pass`""
$content = $content -replace 'HOST_IP\s*=\s*"[^"]*"',   "HOST_IP  = `"$ip`""

$content | Out-File -FilePath $file -Encoding utf8 -NoNewline
Write-Host "Archivo actualizado." -ForegroundColor Green

# Subir al ESP32
Write-Host "Subiendo main_wifi.py al ESP32 como main.py..."
.\venv\Scripts\python.exe -m mpremote connect $Puerto cp $file :main.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error al subir. Reintentando..." -ForegroundColor Yellow
    Start-Sleep 3
    .\venv\Scripts\python.exe -m mpremote connect $Puerto cp $file :main.py
}

Write-Host "Reiniciando ESP32..."
Start-Sleep 1
.\venv\Scripts\python.exe -m mpremote connect $Puerto reset

Write-Host ""
Write-Host "LISTO. El ESP32 se conectara al WiFi '$ssid' y mostrara el panel." -ForegroundColor Green
Write-Host "Asegurate de que la app Flask esta corriendo en este PC." -ForegroundColor Cyan
Write-Host "URL que consultara el ESP32: http://$ip`:5001/api/display" -ForegroundColor White
Write-Host ""
