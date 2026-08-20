"""
exportar_config.py
------------------
Ejecutar en el PC PRINCIPAL para exportar la configuración actual
(puestos, máquinas, terminales, carros) a data/config_inicial.sql

Este fichero se sube a GitHub y permite que los PCs nuevos arranquen
con toda la configuración ya cargada.

Uso:
    python exportar_config.py
"""
import sqlite3
import os
import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'engastado.db')
OUT_PATH = os.path.join(BASE_DIR, 'data', 'config_inicial.sql')

TABLAS_CONFIG = [
    'puestos',
    'maquinas',
    'maquinas_terminales',
    'terminales_desactivados',
    'carros',         # los 6 carros siempre deben existir
    # El kanban de stock tambien es configuracion: la gaveta y el stock de cada
    # terminal se teclean a mano y no estaban aqui, asi que las instalaciones
    # nuevas arrancaban con el kanban en blanco.
    'terminales_gavetas',
    'terminales_stock',
]


def exportar_tabla(con, tabla):
    """Genera los INSERT para una tabla completa."""
    cur = con.execute(f"SELECT * FROM {tabla}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()

    if not rows:
        return f"-- (tabla {tabla} vacía)\n"

    lines = [f"-- {tabla}: {len(rows)} fila(s)"]
    for row in rows:
        valores = []
        for v in row:
            if v is None:
                valores.append('NULL')
            elif isinstance(v, (int, float)):
                valores.append(str(v))
            else:
                # Escapar comillas simples
                valores.append("'" + str(v).replace("'", "''") + "'")
        cols_str = ', '.join(cols)
        vals_str = ', '.join(valores)
        lines.append(f"INSERT OR REPLACE INTO {tabla} ({cols_str}) VALUES ({vals_str});")
    return '\n'.join(lines) + '\n'


def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] No se encuentra la base de datos en:\n  {DB_PATH}")
        return

    con = sqlite3.connect(DB_PATH)
    try:
        ahora = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        bloques = [
            f"-- config_inicial.sql  (generado el {ahora})",
            "-- Configuración inicial exportada desde el PC principal.",
            "-- Se aplica automáticamente al crear una BD nueva en otro PC.",
            "PRAGMA foreign_keys = OFF;\n",
        ]

        for tabla in TABLAS_CONFIG:
            try:
                bloques.append(exportar_tabla(con, tabla))
            except Exception as e:
                bloques.append(f"-- [AVISO] No se pudo exportar {tabla}: {e}\n")

        bloques.append("PRAGMA foreign_keys = ON;\n")

        contenido = '\n'.join(bloques)
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            f.write(contenido)

        # Resumen
        total = sum(
            con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in TABLAS_CONFIG
            if con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)
            ).fetchone()
        )

        print(f"\n Configuración exportada a:\n  {OUT_PATH}")
        print(f"\n Tablas exportadas:")
        for t in TABLAS_CONFIG:
            try:
                n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"   - {t}: {n} filas")
            except Exception:
                print(f"   - {t}: (no existe)")
        print(f"\n Total: {total} filas exportadas")
        print("\n Ahora haz commit y push de data/config_inicial.sql para")
        print("   que los PCs nuevos descarguen la configuración.\n")

    finally:
        con.close()


if __name__ == '__main__':
    main()
