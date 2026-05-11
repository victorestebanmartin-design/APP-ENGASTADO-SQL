"""Aplica la migración add_sesiones_trabajo.sql a engastado.db"""
import sqlite3

db_path = 'data/engastado.db'
sql_path = 'migrations/add_sesiones_trabajo.sql'

with open(sql_path, 'r', encoding='utf-8') as f:
    sql = f.read()

conn = sqlite3.connect(db_path)
conn.executescript(sql)
conn.commit()

query = "SELECT name FROM sqlite_master WHERE type='table' AND name='sesiones_trabajo'"
row = conn.execute(query).fetchone()
print('Tabla creada:', row)

for col in conn.execute('PRAGMA table_info(sesiones_trabajo)').fetchall():
    print(' -', col[1], col[2])

conn.close()
print('Migracion completada.')
