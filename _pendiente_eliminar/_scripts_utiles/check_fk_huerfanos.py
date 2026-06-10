"""
Comprueba la integridad referencial de la base de datos SQLite.

Ejecuta PRAGMA foreign_key_check sobre data/engastado.db y muestra
los registros huérfanos encontrados de forma legible.

NO modifica ni borra nada: solo informa.
"""
import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data',
    'engastado.db'
)


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: no se encuentra la base de datos en {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        # PRAGMA foreign_key_check devuelve filas:
        #   (tabla, rowid, tabla_referenciada, indice_fk)
        rows = cursor.execute("PRAGMA foreign_key_check").fetchall()

        if not rows:
            print("OK: sin registros huérfanos")
            return

        print(f"Se encontraron {len(rows)} registro(s) huérfano(s):\n")
        print(f"{'Tabla':<25} {'rowid':<12} {'Tabla referenciada':<25}")
        print("-" * 62)
        for tabla, rowid, tabla_ref, fk_index in rows:
            rowid_str = str(rowid) if rowid is not None else "(sin rowid)"
            print(f"{tabla:<25} {rowid_str:<12} {str(tabla_ref):<25}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
