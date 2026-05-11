import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

# Ver tablas
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print('Tablas existentes:')
for t in tables:
    print(f'  - {t[0]}')

# Contar registros en cada tabla
print('\nRegistros por tabla:')
for table in tables:
    try:
        cursor.execute(f'SELECT COUNT(*) FROM {table[0]}')
        count = cursor.fetchone()[0]
        print(f'  {table[0]}: {count}')
    except:
        print(f'  {table[0]}: ERROR')

conn.close()
