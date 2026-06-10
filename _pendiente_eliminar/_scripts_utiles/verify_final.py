import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

print("=== ESTADO FINAL DEL SISTEMA ===\n")

# Bono
cursor.execute("SELECT id, nombre, total_ordenes FROM bonos WHERE nombre = '17022026_1'")
bono = cursor.fetchone()
print(f"✅ Bono: {bono[1]} | Órdenes: {bono[2]}")

# Órdenes del bono
cursor.execute("SELECT numero, archivo_excel FROM ordenes_produccion WHERE bono_id = ?", (bono[0],))
ordenes = cursor.fetchall()
print(f"\n📦 Órdenes del bono ({len(ordenes)}):")
for orden in ordenes:
    print(f"   - {orden[0]} | Archivo: {orden[1] or 'NO HAY ARCHIVO ❌'}")

# Puestos
cursor.execute("SELECT COUNT(*) FROM puestos WHERE activo = 1")
print(f"\n🏭 Puestos activos: {cursor.fetchone()[0]}")

# Máquinas
cursor.execute("SELECT COUNT(*) FROM maquinas WHERE activo = 1")
print(f"🔧 Máquinas activas: {cursor.fetchone()[0]}")

# Terminales
cursor.execute("SELECT COUNT(*) FROM maquinas_terminales")
print(f"📌 Terminales asignados: {cursor.fetchone()[0]}")

conn.close()

print("\n=== LISTO PARA USAR ===")
print("Recarga http://localhost:5001/v3 y carga el bono '17022026_1'")
