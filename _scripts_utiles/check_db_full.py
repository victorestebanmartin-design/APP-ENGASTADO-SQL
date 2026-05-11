import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

print("=== ESTADO COMPLETO DE LA BASE DE DATOS ===\n")

# Contar todos los registros
cursor.execute("SELECT COUNT(*) FROM ordenes_produccion")
total_ordenes = cursor.fetchone()[0]
print(f"📊 Total órdenes en DB: {total_ordenes}")

cursor.execute("SELECT COUNT(*) FROM bonos")
total_bonos = cursor.fetchone()[0]
print(f"📦 Total bonos en DB: {total_bonos}")

# Listar todas las órdenes
print("\n📋 Todas las órdenes:")
cursor.execute("SELECT id, numero, codigo_corte, bono_id, estado FROM ordenes_produccion")
ordenes = cursor.fetchall()
for orden in ordenes:
    print(f"   ID: {orden[0][:8]}... | Num: {orden[1]} | Código: {orden[2]} | Bono: {orden[3][:8] + '...' if orden[3] else 'NULL'} | Estado: {orden[4]}")

# Listar todos los bonos
print("\n📦 Todos los bonos:")
cursor.execute("SELECT id, nombre, total_ordenes, estado, fecha_creacion FROM bonos ORDER BY fecha_creacion DESC")
bonos = cursor.fetchall()
for bono in bonos:
    print(f"   ID: {bono[0][:8]}... | Nombre: {bono[1]} | Órdenes: {bono[2]} | Estado: {bono[3]} | Creado: {bono[4]}")

conn.close()
