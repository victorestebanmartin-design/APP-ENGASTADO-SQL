import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

print("=== VERIFICANDO UBICACIÓN DE ÓRDENES ===\n")

# Verificar dónde están las órdenes 6021456 y 60124834
ordenes_buscar = ["6021456", "60124834"]

for numero in ordenes_buscar:
    cursor.execute("""
        SELECT o.numero, o.codigo_corte, o.bono_id, b.nombre as bono_nombre
        FROM ordenes_produccion o
        LEFT JOIN bonos b ON o.bono_id = b.id
        WHERE o.numero = ?
    """, (numero,))
    
    resultado = cursor.fetchone()
    if resultado:
        print(f"📋 Orden {resultado[0]} ({resultado[1]}):")
        print(f"   Bono ID: {resultado[2]}")
        print(f"   Bono Nombre: {resultado[3]}")
    else:
        print(f"❌ Orden {numero} no encontrada")

print("\n=== LISTA COMPLETA DE BONOS ===\n")
cursor.execute("SELECT id, nombre FROM bonos ORDER BY nombre")
bonos = cursor.fetchall()
for bono in bonos:
    print(f"   {bono[1]}: {bono[0]}")

conn.close()
