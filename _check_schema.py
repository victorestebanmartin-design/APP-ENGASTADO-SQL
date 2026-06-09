import sqlite3
conn = sqlite3.connect('data/engastado.db')
for t in ['puestos','maquinas','maquinas_terminales','carros']:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE name='" + t + "'").fetchone()
    print("=== " + t + " ===")
    print(row[0] if row else 'NO TABLE')
    print()
conn.close()
