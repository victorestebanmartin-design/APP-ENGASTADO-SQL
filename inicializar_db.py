"""
inicializar_db.py
-----------------
Crea data/engastado.db desde cero usando:
  1. schema_sqlite.sql  — estructura de tablas
  2. data/config_inicial.sql  — configuración (puestos, máquinas, etc.)
                                exportada desde el PC principal

Se ejecuta automáticamente por DESCARGAR_E_INSTALAR.bat cuando no
existe la base de datos.  También se puede ejecutar manualmente.

Uso:
    python inicializar_db.py
"""
import sqlite3
import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH     = os.path.join(BASE_DIR, 'data', 'engastado.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema_sqlite.sql')
CONFIG_PATH = os.path.join(BASE_DIR, 'data', 'config_inicial.sql')


def ejecutar_sql(con, ruta, descripcion):
    """Lee y ejecuta un fichero SQL completo."""
    with open(ruta, 'r', encoding='utf-8') as f:
        sql = f.read()
    try:
        con.executescript(sql)
        print(f"  OK  {descripcion}")
        return True
    except sqlite3.Error as e:
        print(f"  [ERROR] {descripcion}: {e}")
        return False


def main():
    # Crear carpeta data si no existe
    os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)

    if not os.path.exists(SCHEMA_PATH):
        print(f"[ERROR] No se encuentra schema_sqlite.sql en:\n  {SCHEMA_PATH}")
        sys.exit(1)

    ya_existia = os.path.exists(DB_PATH)
    if ya_existia:
        respuesta = input(
            f"\nLa base de datos ya existe en:\n  {DB_PATH}\n"
            "¿Sobreescribirla? Se perderán todos los datos. (s/N): "
        ).strip().lower()
        if respuesta != 's':
            print("Operación cancelada.")
            sys.exit(0)
        os.remove(DB_PATH)
        print()

    print("Creando base de datos...")
    con = sqlite3.connect(DB_PATH)
    try:
        # 1. Aplicar schema
        ejecutar_sql(con, SCHEMA_PATH, 'Schema (tablas e índices)')

        # 2. Aplicar configuración inicial si existe
        if os.path.exists(CONFIG_PATH):
            ejecutar_sql(con, CONFIG_PATH, 'Configuración inicial (puestos, máquinas, carros)')
        else:
            print("  --  data/config_inicial.sql no encontrado — BD vacía")
            print("      (ejecuta exportar_config.py en el PC principal para generarlo)")

        con.commit()
    finally:
        con.close()

    # Habilitar WAL mode (mejor concurrencia)
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
    finally:
        con.close()

    print(f"\n Base de datos creada correctamente en:\n  {DB_PATH}\n")


if __name__ == '__main__':
    main()
