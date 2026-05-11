import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

print("=== ESTADO DE BONOS Y ÓRDENES ===\n")

# Últimos bonos creados
cursor.execute("SELECT id, nombre, total_ordenes, descripcion FROM bonos ORDER BY fecha_creacion DESC LIMIT 3")
bonos = cursor.fetchall()
print("📦 Últimos bonos creados:")
for bono in bonos:
    print(f"   {bono[1]} | ID: {bono[0][:8]}... | Órdenes: {bono[2]} | Desc: {bono[3] or 'N/A'}")

# Ver todas las órdenes y sus asociaciones
print("\n📋 Órdenes y sus asociaciones:")
cursor.execute("SELECT numero, codigo_corte, bono_id, estado FROM ordenes_produccion ORDER BY updated_at DESC")
ordenes = cursor.fetchall()
for orden in ordenes:
    bono_ref = orden[2][:8] + "..." if orden[2] else "ninguno"
    print(f"   {orden[0]} ({orden[1]}) -> Bono: {bono_ref} | Estado: {orden[3]}")

# Ver específicamente el bono 17022026_2
print("\n🔍 Detalles del bono 17022026_2:")
cursor.execute("SELECT id, total_ordenes FROM bonos WHERE nombre = '17022026_2'")
bono_2 = cursor.fetchone()
if bono_2:
    print(f"   ID: {bono_2[0]}")
    print(f"   Total órdenes (campo): {bono_2[1]}")
    
    cursor.execute("SELECT numero, codigo_corte FROM ordenes_produccion WHERE bono_id = ?", (bono_2[0],))
    ordenes_asociadas = cursor.fetchall()
    print(f"   Órdenes asociadas (DB): {len(ordenes_asociadas)}")
    for orden in ordenes_asociadas:
        print(f"      - {orden[0]} ({orden[1]})")
else:
    print("   ❌ No existe el bono 17022026_2")

conn.close()
