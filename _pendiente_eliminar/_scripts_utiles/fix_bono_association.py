"""
Script para corregir la asociación de bonos
"""
import sqlite3
import os

# Usar path relativo correcto
db_path = "data/engastado.db"
if not os.path.exists(db_path):
    print(f"❌ Base de datos no encontrada en: {os.path.abspath(db_path)}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== CORRIGIENDO ASOCIACIONES ===\n")

# Bono IDs correctos
bono_1 = "7dc2feff-f66d-47ac-876c-1f77f98e0fb6"  # 17022026_1 (debe tener 3 órdenes)
bono_2 = "1e34335c-c618-4ec0-8fc4-a2d1d97428fb"  # 17022026_2 (debe tener 2 órdenes)

# Obtener todas las órdenes actualmente asociadas a bono_1
cursor.execute("""
    SELECT numero, codigo_corte 
    FROM ordenes_produccion 
    WHERE bono_id = ?
    ORDER BY numero
""", (bono_1,))

ordenes_bono_1 = cursor.fetchall()
print(f"📦 Bono 17022026_1 tiene {len(ordenes_bono_1)} órdenes:")
for num, cod in ordenes_bono_1:
    print(f"   • {num} ({cod})")

# Las últimas 2 deberían ir al bono_2
if len(ordenes_bono_1) > 3:
    ordenes_a_mover = ordenes_bono_1[-2:]
    print(f"\n🔄 Moviendo últimas 2 órdenes al bono 17022026_2:")
    
    for num, cod in ordenes_a_mover:
        cursor.execute("""
            UPDATE ordenes_produccion 
            SET bono_id = ?
            WHERE numero = ?
        """, (bono_2, num))
        print(f"   ✅ {num} ({cod})")
    
    conn.commit()

# Actualizar contadores
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
print("\n📊 Estado final:")
for bono_id, nombre in [(bono_1, '17022026_1'), (bono_2, '17022026_2')]:
    cursor.execute("""
        SELECT COUNT(*), GROUP_CONCAT(numero)
        FROM ordenes_produccion 
        WHERE bono_id = ?
    """, (bono_id,))
    count, numeros = cursor.fetchone()
    print(f"   {nombre}: {count} órdenes ({numeros})")

conn.close()
print("\n✅ Corrección completada")
