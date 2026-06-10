import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

print("=== MOVIENDO ÓRDENES AL BONO CORRECTO ===\n")

# IDs correctos de bonos
bono_1_id = "7dc2feff-469b-4b8e-8651-32e91e7da5da"  # 17022026_1
bono_2_id = "1e34335c-c618-4ec0-8fc4-a2d1d97428fb"  # 17022026_2

# Mover las 2 últimas órdenes de bono_1 a bono_2
ordenes_a_mover = ["6021456", "60124834"]

print("🔄 Moviendo órdenes:")
for numero in ordenes_a_mover:
    cursor.execute("""
        UPDATE ordenes_produccion 
        SET bono_id = ?
        WHERE numero = ?
    """, (bono_2_id, numero))
    
    if cursor.rowcount > 0:
        print(f"   ✅ {numero} movida a bono 17022026_2")
    else:
        print(f"   ⚠️  {numero} no se pudo mover")

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
    total = cursor.fetchone()
    total_campo = total[0] if total else 0
    print(f"\n   📦 {nombre}:")
    print(f"      Órdenes en DB: {count}")
    print(f"      Números: {numeros}")
    print(f"      Campo total_ordenes: {total_campo}")

conn.close()
print("\n✅ ¡Completado! Ahora recarga la página /v3")
