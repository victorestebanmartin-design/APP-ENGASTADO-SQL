# flash_esp32.ps1 — Flashea MicroPython en el 4D Systems gen4-ESP32-24 (ESP32-S3)
#
# NOTA: esto ya se puede hacer desde la propia aplicación, sin PowerShell:
#   Admin -> Display Carro -> "Grabar MicroPython (placa nueva)"
# Allí se elige puerto y firmware desde el navegador, se comprueba que el .bin
# corresponde al chip de la placa y se instala también el driver USB si hace
# falta. Este script se mantiene como alternativa para uso desde terminal.
#
# Uso:
#   .\flash_esp32.ps1                       # busca el .bin en esp32\firmware
#   .\flash_esp32.ps1 -Puerto COM5          # otro puerto
#   .\flash_esp32.ps1 -SoloSubir            # solo sube main.py (ya tiene MicroPython)
#
# Los firmwares viven en esp32\firmware\. Si falta el de tu placa, descárgalo de:
#   https://micropython.org/download/ESP32_GENERIC_S3/
#   Busca el fichero: ESP32_GENERIC_S3-SPIRAM_OCT-XXXXXXXX-vX.XX.X.bin
#
# ⚠ ADVERTENCIA: El flash BORRA el firmware 4D Systems original.

param(
    [string]$Puerto   = "COM5",
    [switch]$SoloSubir
)

$Python  = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$Esptool = "$Python -m esptool"
$Mpremote= "$Python -m mpremote"
$MainPy  = Join-Path $PSScriptRoot "esp32\micropython\main.py"

# ── Verificaciones ────────────────────────────────────────────────────────────
if (-not (Test-Path $Python)) {
    Write-Error "No se encontró el venv en $Python. Ejecuta desde la raíz del proyecto."
    exit 1
}

if (-not (Test-Path $MainPy)) {
    Write-Error "No se encontró $MainPy"
    exit 1
}

Write-Host ""
Write-Host "=== ESP32-S3 Flash Tool ===" -ForegroundColor Cyan
Write-Host "Puerto : $Puerto"
Write-Host "main.py: $MainPy"
Write-Host ""

# ── FLASH MICROPYTHON ─────────────────────────────────────────────────────────
if (-not $SoloSubir) {
    # Buscar firmware .bin (en esp32\firmware y, por compatibilidad, en la raíz)
    $DirFirmware = Join-Path $PSScriptRoot "esp32\firmware"
    $Bin = @($DirFirmware, $PSScriptRoot) |
           Where-Object { Test-Path $_ } |
           ForEach-Object { Get-ChildItem -Path $_ -Filter "ESP32_GENERIC_S3-SPIRAM_OCT-*.bin" -ErrorAction SilentlyContinue } |
           Sort-Object LastWriteTime -Descending | Select-Object -First 1

    if (-not $Bin) {
        Write-Host "No se encontró el firmware .bin." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Descárgalo de:" -ForegroundColor Yellow
        Write-Host "  https://micropython.org/download/ESP32_GENERIC_S3/" -ForegroundColor White
        Write-Host "  Busca: ESP32_GENERIC_S3-SPIRAM_OCT-*.bin" -ForegroundColor White
        Write-Host "  Cópialo a: $DirFirmware" -ForegroundColor White
        Write-Host ""
        Write-Host "O hazlo desde la aplicación: Admin -> Display Carro -> Grabar MicroPython" -ForegroundColor Cyan
        exit 0
    }

    Write-Host "Firmware encontrado: $($Bin.Name)" -ForegroundColor Green
    Write-Host ""
    Write-Host "PASO 1: Borrando flash del ESP32-S3..." -ForegroundColor Yellow
    & $Python -m esptool -p $Puerto --chip esp32s3 erase-flash
    if ($LASTEXITCODE -ne 0) { Write-Error "Error al borrar flash"; exit 1 }

    Write-Host ""
    Write-Host "PASO 2: Flasheando MicroPython..." -ForegroundColor Yellow
    & $Python -m esptool -p $Puerto --chip esp32s3 --baud 460800 write-flash -z 0x0 $Bin.FullName
    if ($LASTEXITCODE -ne 0) { Write-Error "Error al flashear firmware"; exit 1 }

    Write-Host ""
    Write-Host "MicroPython instalado. Esperando que el puerto reenumere..." -ForegroundColor Green
    Start-Sleep -Seconds 8
}

# ── SUBIR main.py (con reintentos por si el puerto USB tarda en aparecer) ──────
Write-Host "PASO 3: Subiendo main.py al ESP32-S3..." -ForegroundColor Yellow
$ok = $false
for ($i = 1; $i -le 5; $i++) {
    & $Python -m mpremote connect $Puerto cp $MainPy ":main.py" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $ok = $true; break }
    Write-Host "  Intento $i/5 fallido, reintentando en 3 s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}
if (-not $ok) { Write-Error "No se pudo acceder a $Puerto tras 5 intentos. Comprueba el puerto con: [System.IO.Ports.SerialPort]::GetPortNames()"; exit 1 }

Write-Host ""
Write-Host "Reiniciando placa..." -ForegroundColor Yellow
& $Python -m mpremote connect $Puerto reset

Write-Host ""
Write-Host "LISTO. El panel arranca en la pantalla." -ForegroundColor Green
Write-Host "Ahora en otro terminal ejecuta:" -ForegroundColor Cyan
Write-Host "  .\venv\Scripts\python.exe bridge_esp32.py" -ForegroundColor White
Write-Host ""
