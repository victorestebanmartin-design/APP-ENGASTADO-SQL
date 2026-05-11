import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

print("=== REESTRUCTURANDO BONO CON DATOS REALES ===\n")

# 1. Ver todas las órdenes disponibles
cursor.execute("""
    SELECT numero, codigo_corte, archivo_excel, estado, bono_id
    FROM ordenes_produccion
    ORDER BY fecha_creacion
""")
ordenes = cursor.fetchall()

print(f"📦 Órdenes disponibles ({len(ordenes)}):")
for orden in ordenes:
    print(f"   {orden[0]} | {orden[1]} | {orden[2] or 'SIN ARCHIVO'} | {orden[3]} | Bono: {orden[4][:8] if orden[4] else 'ninguno'}...")

# 2. Obtener ID del bono 17022026_1
cursor.execute("SELECT id FROM bonos WHERE nombre = '17022026_1'")
bono = cursor.fetchone()
bono_id = bono[0]

print(f"\n🎫 Bono objetivo: 17022026_1 (ID: {bono_id[:8]}...)")

# 3. Seleccionar 2 órdenes con archivos Excel para el bono
# Usar las órdenes que tienen archivo_excel no nulo
cursor.execute("""
    SELECT numero 
    FROM ordenes_produccion 
    WHERE archivo_excel IS NOT NULL 
    ORDER BY fecha_creacion 
    LIMIT 2
""")
ordenes_seleccionadas = cursor.fetchall()

print(f"\n✏️  Asignando {len(ordenes_seleccionadas)} órdenes al bono:")

for orden in ordenes_seleccionadas:
    numero = orden[0]
    cursor.execute("""
        UPDATE ordenes_produccion 
        SET bono_id = ?, estado = 'en_bono' 
        WHERE numero = ?
    """, (bono_id, numero))
    print(f"   ✓ {numero}")

# 4. Actualizar contador
cursor.execute("""
    UPDATE bonos 
    SET total_ordenes = ? 
    WHERE id = ?
""", (len(ordenes_seleccionadas), bono_id))

conn.commit()

# 5. Verificación final
cursor.execute("""
    SELECT o.numero, o.codigo_corte, o.archivo_excel
    FROM ordenes_produccion o
    WHERE o.bono_id = ?
""", (bono_id,))
ordenes_bono = cursor.fetchall()

print(f"\n✅ BONO ACTUALIZADO:")
print(f"   Nombre: 17022026_1")
print(f"   Total órdenes: {len(ordenes_bono)}")
print(f"\n   Órdenes incluidas:")
for orden in ordenes_bono:
    print(f"      • {orden[0]} | {orden[1]} | {orden[2]}")

cursor.execute("SELECT COUNT(*) FROM puestos WHERE activo = 1")
puestos = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM maquinas WHERE activo = 1")
maquinas = cursor.fetchone()[0]

print(f"\n📊 Sistema:")
print(f"   Puestos activos: {puestos}")
print(f"   Máquinas activas: {maquinas}")

conn.close()

print("\n=== COMPLETADO ===")
print("Recarga http://localhost:5001/v3 con Ctrl+F5")
