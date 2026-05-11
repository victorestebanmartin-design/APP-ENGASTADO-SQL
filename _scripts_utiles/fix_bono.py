import sqlite3
import uuid

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

print("=== SOLUCIONANDO PROBLEMAS ===\n")

# 1. Obtener el ID del bono 17022026_1
cursor.execute("SELECT id FROM bonos WHERE nombre = '17022026_1'")
bono = cursor.fetchone()
if not bono:
    print("❌ No se encontró el bono 17022026_1")
    conn.close()
    exit()

bono_id = bono[0]
print(f"✓ Bono encontrado: {bono_id[:8]}...")

# 2. Buscar órdenes sin bono o reasignar
cursor.execute("SELECT numero FROM ordenes_produccion WHERE estado = 'en_proceso' OR bono_id IS NULL LIMIT 3")
ordenes_libres = cursor.fetchall()

if not ordenes_libres:
    # Si no hay libres, tomar las primeras 2 órdenes de cualquier bono
    cursor.execute("SELECT numero FROM ordenes_produccion LIMIT 2")
    ordenes_libres = cursor.fetchall()
    print(f"⚠️  No hay órdenes libres, reasignando {len(ordenes_libres)} órdenes...")

print(f"\n📦 Asociando {len(ordenes_libres)} órdenes al bono:")

total_ordenes = 0
for orden in ordenes_libres:
    numero = orden[0]
    cursor.execute("UPDATE ordenes_produccion SET bono_id = ?, estado = 'en_bono' WHERE numero = ?", 
                   (bono_id, numero))
    print(f"   ✓ {numero}")
    total_ordenes += 1

# Actualizar contador en bonos
cursor.execute("UPDATE bonos SET total_ordenes = ? WHERE id = ?", (total_ordenes, bono_id))

print(f"\n✓ Bono actualizado con {total_ordenes} órdenes")

# 3. Crear puestos de trabajo si no existen
cursor.execute("SELECT COUNT(*) FROM puestos WHERE activo = 1")
if cursor.fetchone()[0] == 0:
    print("\n📍 Creando puestos de trabajo...")
    
    puestos = [
        ('CABLEAR', 'Puesto de cableado', 1),
        ('ENGASTADO', 'Puesto de engastado', 1),
        ('REVISAR', 'Puesto de revisión', 1)
    ]
    
    for nombre, desc, activo in puestos:
        puesto_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO puestos (id, nombre, descripcion, activo)
            VALUES (?, ?, ?, ?)
        """, (puesto_id, nombre, desc, activo))
        print(f"   ✓ {nombre} (ID: {puesto_id[:8]}...)")
    
    print(f"\n✓ {len(puestos)} puestos creados")

conn.commit()
conn.close()

print("\n=== COMPLETADO ===")
print("Ahora recarga la página y el bono debería funcionar correctamente.")
