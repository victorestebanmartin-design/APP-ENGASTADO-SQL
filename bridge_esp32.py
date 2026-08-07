#!/usr/bin/env python3
"""
Puente ESP32 — lee estadísticas de órdenes de la BD y las envía por serial (COM4).

Uso:
    python bridge_esp32.py              # COM4 por defecto
    python bridge_esp32.py COM5         # otro puerto
    python bridge_esp32.py --dry-run    # sin hardware (prueba de lectura)

Requiere pyserial:
    pip install pyserial
"""

import sys
import json
import time
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path

# ── Configuración ──────────────────────────────────────────────────────────────
PORT       = "COM5"
BAUD       = 115200
INTERVAL   = 30        # segundos entre actualizaciones
DB_PATH    = Path(__file__).parent / "data" / "engastado.db"
# ──────────────────────────────────────────────────────────────────────────────


def leer_stats_ordenes() -> dict:
    """Lee conteo de órdenes por estado directamente de la BD SQLite."""
    if not DB_PATH.exists():
        print(f"[WARN] BD no encontrada en {DB_PATH}")
        return {"p": 0, "e": 0, "t": 0}

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT estado, COUNT(*) FROM ordenes_produccion GROUP BY estado")
    rows = cur.fetchall()
    con.close()

    mapa = {row[0]: row[1] for row in rows}
    return {
        "p": mapa.get("pendiente", 0),
        "e": mapa.get("en_proceso", 0),
        "t": mapa.get("terminada",  0),
    }


def construir_payload() -> str:
    """Construye la línea JSON que se envía al ESP32."""
    stats = leer_stats_ordenes()
    ahora = datetime.now()
    payload = {
        **stats,
        "hora":  ahora.strftime("%H:%M"),
        "fecha": ahora.strftime("%d/%m"),
    }
    return json.dumps(payload, separators=(',', ':')) + "\n"


def ejecutar_dry_run():
    print("=== DRY RUN (sin puerto serial) ===")
    for _ in range(3):
        linea = construir_payload()
        print(f"[{datetime.now():%H:%M:%S}] → {linea.strip()}")
        time.sleep(2)
    print("Fin del dry-run.")


def ejecutar_serial(puerto: str):
    try:
        import serial
    except ImportError:
        print("ERROR: pyserial no instalado. Ejecuta:  pip install pyserial")
        sys.exit(1)

    print(f"Conectando a {puerto} a {BAUD} bps…")
    try:
        ser = serial.Serial(puerto, BAUD, timeout=2)
    except serial.SerialException as e:
        print(f"Error abriendo {puerto}: {e}")
        sys.exit(1)

    # Esperar al reset del ESP32 tras abrir el puerto
    time.sleep(2)
    print(f"Conectado. Enviando cada {INTERVAL} s. Ctrl+C para salir.\n")

    try:
        while True:
            linea = construir_payload()
            ser.write(linea.encode("ascii"))
            print(f"[{datetime.now():%H:%M:%S}] → {linea.strip()}")
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\nDetenido.")
    finally:
        ser.close()


def main():
    parser = argparse.ArgumentParser(description="Puente serial ESP32 — Engastado")
    parser.add_argument("puerto", nargs="?", default=PORT,
                        help=f"Puerto serial (defecto: {PORT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Modo prueba sin hardware")
    args = parser.parse_args()

    if args.dry_run:
        ejecutar_dry_run()
    else:
        ejecutar_serial(args.puerto)


if __name__ == "__main__":
    main()
