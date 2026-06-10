import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

# Ver bono
cursor.execute("SELECT id, nombre, total_ordenes FROM bonos WHERE nombre = '17022026_1'")
bono = cursor.fetchone()
print(f'Bono: ID={bono[0][:8]}..., Nombre={bono[1]}, Total Ordenes={bono[2]}')

# Ver órdenes y sus asociaciones con bonos
cursor.execute('SELECT numero, bono_id, estado FROM ordenes_produccion')
ordenes = cursor.fetchall()
print(f'\nÓrdenes en DB ({len(ordenes)}):')
for orden in ordenes:
    print(f'  - {orden[0]} | Bono: {orden[1] or "ninguno"} | Estado: {orden[2]}')

# Ver si hay puestos
cursor.execute('SELECT COUNT(*) FROM puestos WHERE activo = 1')
puestos_count = cursor.fetchone()[0]
print(f'\nPuestos activos: {puestos_count}')

conn.close()
