import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

# Crear los 6 carros
for i in range(1, 7):
    try:
        cursor.execute('''
            INSERT INTO carros (numero, estado, progreso, ordenes_totales, ordenes_completadas)
            VALUES (?, 'disponible', 0.0, 0, 0)
        ''', (i,))
        print(f'✓ Carro {i} creado')
    except Exception as e:
        print(f'❌ Error creando carro {i}: {e}')

conn.commit()
conn.close()
print('\n✓ Carros creados exitosamente')
