import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

print("=== MOVIENDO ÓRDENES AL BONO CORRECTO ===\n")

bono_1_id = "7dc2feff-f66d-47ac-876c-1f77f98e0fb6"  # 17022026_1
bono_2_id = "1e34335c-c618-4ec0-8fc4-a2d1d97428fb"  # 17022026_2

# Mover las 2 últimas órdenes de bono_1 a bono_2
ordenes_a_mover = ["6021456", "60124834"]

print("🔄 Moviendo órdenes:")
for numero in ordenes_a_mover:
    cursor.execute("""
        UPDATE ordenes_produccion 
        SET bono_id = ?
        WHERE numero = ? AND bono_id = ?
    """, (bono_2_id, numero, bono_1_id))
    
    if cursor.rowcount > 0:
        print(f"   ✅ {numero} movida a bono 17022026_2")
    else:
        print(f"   ⚠️  {numero} no se pudo mover (no encontrada o ya movida)")

conn.commit()

# Actualizar contadores
print("\n📊 Actualizando contadores...")
cursor.execute("""
    UPDATE bonos 
    SET total_ordenes = (
        SELECT COUNT(*) 
        FROM ordenes_produccion 
        WHERE bono_id = bonos.id
    )
""")
conn.commit()

# Verificar resultado
print("\n✅ Estado final:")
for bono_id, nombre in [(bono_1_id, '17022026_1'), (bono_2_id, '17022026_2')]:
    cursor.execute("""
        SELECT COUNT(*), GROUP_CONCAT(numero)
        FROM ordenes_produccion 
        WHERE bono_id = ?
    """, (bono_id,))
    count, numeros = cursor.fetchone()
    cursor.execute("SELECT total_ordenes FROM bonos WHERE id = ?", (bono_id,))
    total_campo = cursor.fetchone()[0]
    print(f"   {nombre}:")
    print(f"      Órdenes asociadas: {count}")
    print(f"      Números: {numeros}")
    print(f"      Campo total_ordenes: {total_campo}")

conn.close()
print("\n✅ Corrección completada - ahora el bono 17022026_2 tendrá 2 órdenes")
