#!/usr/bin/env bash
#
# Compila (y opcionalmente sube) el firmware del panel P4.
#
#   ./compilar.sh              -> solo compila (variante con tactil)
#   ./compilar.sh COM6         -> compila y sube al puerto indicado
#   ./compilar.sh COM6 notouch -> variante SIN GT911 (paneles sin tactil:
#                                 se salta la sonda I2C, la calibracion y la
#                                 barra CONFIRMAR; el orden del argumento da
#                                 igual, "notouch COM6" tambien vale)
#   ./compilar.sh COM6 debug   -> diagnostico: Serial por el USB, retro siempre
#                                 encendida y trama de prueba si el carro no
#                                 manda nada en 8 s (se combina con notouch).
#                                 NO dejarlo en produccion.
#
# No usa PlatformIO. Llama al arduino-cli que trae el Arduino IDE, que es el
# mismo motor que usa el IDE por dentro y ya tiene la config buena:
#   - core  esp32 3.3.7
#   - libs  ~/Documents/Arduino/libraries  (GFX4dESP32P4, ArduinoJson)
# Esa config la lee arduino-cli de ~/.arduinoIDE/arduino-cli.yaml, no hay que
# pasarle rutas.
#
set -euo pipefail

SKETCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Placa: 4D Systems ESP32-P4 MIPI, panel 10.1" 101CT-CLB, particion de 32 MB.
FQBN="esp32:esp32:esp32p4_4ds_mipi:PartitionScheme=app5M_fat24M_32MB,DisplayModel=esp32p4_101ct_clb"

# arduino-cli: primero el del PATH, si no el que instala el Arduino IDE.
if command -v arduino-cli >/dev/null 2>&1; then
    CLI="arduino-cli"
elif [ -x "/c/Program Files/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe" ]; then
    CLI="/c/Program Files/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe"
else
    echo "No encuentro arduino-cli (ni en PATH ni en el Arduino IDE)." >&2
    exit 1
fi

PORT=""
EXTRA=""
for arg in "$@"; do
    case "$arg" in
        notouch) EXTRA="$EXTRA -DHAS_TOUCH=0" ;;
        # Serial por el USB de programar (por defecto la P4 no saca log por
        # USB), retro siempre encendida y trama de prueba si el carro calla.
        debug)   FQBN="$FQBN,USBMode=hwcdc,CDCOnBoot=cdc"; EXTRA="$EXTRA -DP4_DEBUG=1" ;;
        *)       PORT="$arg" ;;
    esac
done
BUILD_PROPS=()
[ -n "$EXTRA" ] && BUILD_PROPS+=(--build-property "compiler.cpp.extra_flags=$EXTRA")

# Build-path explicito: "upload" no admite --build-property, asi que hace
# falta apuntarle al mismo directorio donde "compile" dejo el .bin (si no, se
# fia de la cache por defecto de arduino-cli, que no distingue variantes por
# build-property y podria subir el binario de la otra). Un directorio fijo por
# variante: reutiliza LVGL ya compilada (si no, ~7 min cada vez).
VARIANTE="$(printf '%s' "$FQBN$EXTRA" | md5sum | cut -c1-8)"
BUILD_DIR="${TMPDIR:-/tmp}/p4_build_$VARIANTE"
mkdir -p "$BUILD_DIR"

echo ">> Compilando  $SKETCH_DIR"
echo ">> FQBN        $FQBN"
[ -n "$EXTRA" ] && echo ">> Flags      $EXTRA"
"$CLI" compile --fqbn "$FQBN" "${BUILD_PROPS[@]}" --build-path "$BUILD_DIR" "$SKETCH_DIR"

if [ -n "$PORT" ]; then
    echo ">> Subiendo a  $PORT"
    "$CLI" upload -p "$PORT" --fqbn "$FQBN" --input-dir "$BUILD_DIR" "$SKETCH_DIR"
    echo ">> Listo. Monitor serie a 115200 (UART0)."
fi
