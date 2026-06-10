"""Exporta puestos, máquinas y terminales de la BD local como SQL INSERT."""
import sqlite3, sys, os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'engastado.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Ver tablas disponibles
tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
print("Tablas en BD local:", tables)
print()

# Detectar nombres reales de tablas relevantes
target_tables = []
for t in tables:
    tl = t.lower()
    if any(x in tl for x in ['puesto', 'maquina', 'terminal', 'carro']):
        target_tables.append(t)

print("Tablas de config encontradas:", target_tables)
print()

lines = []
for table in target_tables:
    rows = cur.execute(f"SELECT * FROM {table}").fetchall()
    print(f"=== {table} === ({len(rows)} filas)")
    for r in rows:
        print(" ", dict(r))
    print()
    
    if rows:
        cols = list(rows[0].keys())
        lines.append(f"\n-- {table}")
        for r in rows:
            vals = []
            for c in cols:
                v = r[c]
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    vals.append("'" + str(v).replace("'", "''") + "'")
            lines.append(f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({','.join(vals)});")

sql_out = os.path.join(os.path.dirname(__file__), '_config_pa.sql')
with open(sql_out, 'w', encoding='utf-8') as f:
    f.write("-- Configuración exportada de BD local\n")
    f.write("-- Ejecutar en PythonAnywhere para sincronizar puestos/máquinas\n\n")
    f.write("\n".join(lines))

print(f"SQL guardado en: {sql_out}")
conn.close()
