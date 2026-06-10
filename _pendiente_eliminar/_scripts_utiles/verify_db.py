import sqlite3

conn = sqlite3.connect(r'C:\Users\estebanv\APP-ENGASTADO-SQL\data\engastado.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tablas = cursor.fetchall()

print('✅ Tablas creadas en la base de datos (' + str(len(tablas)) + '):')
for tabla in tablas:
    print(f'  - {tabla[0]}')

# Verificar WAL mode
cursor.execute("PRAGMA journal_mode")
wal_mode = cursor.fetchone()[0]
print(f'\n✅ WAL mode: {wal_mode}')

# Verificar datos iniciales en app_state
cursor.execute("SELECT clave, valor FROM app_state")
estados = cursor.fetchall()
print(f'\n✅ Datos iniciales en app_state:')
for estado in estados:
    print(f'  - {estado[0]}: {estado[1]}')

conn.close()
print('\n✅ Verificación completada exitosamente')
