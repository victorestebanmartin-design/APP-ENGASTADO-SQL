"""
Script rápido para crear los 6 carros en la base de datos
"""
import sqlite3
import sys

DB_PATH = 'data/engastado.db'

carros = [
    (1, 'disponible'),
    (2, 'disponible'),
    (3, 'disponible'),
    (4, 'disponible'),
    (5, 'disponible'),
    (6, 'disponible'),
]

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Creando carros...")
    
    for numero, estado in carros:
        cursor.execute("""
            INSERT OR IGNORE INTO carros (numero, estado)
            VALUES (?, ?)
        """, (numero, estado))
        print(f"  Carro {numero} creado")
    
    conn.commit()
    print(f"\n{len(carros)} carros creados exitosamente")
    
    # Verificar
    cursor.execute("SELECT * FROM carros ORDER BY numero")
    result = cursor.fetchall()
    print(f"\nCarros en la base de datos: {len(result)}")
    for row in result:
        print(f"  - {row}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
