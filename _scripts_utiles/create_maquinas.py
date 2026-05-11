import sqlite3
import uuid

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

print("=== CREANDO MÁQUINAS Y TERMINALES ===\n")

# Obtener puestos
cursor.execute("SELECT id, nombre FROM puestos WHERE activo = 1")
puestos = cursor.fetchall()

print(f"📍 Puestos encontrados: {len(puestos)}\n")

# Configuración de máquinas por puesto
config_maquinas = {
    'CABLEAR': [
        ('Máquina Cablear 1', ['T1', 'T2', 'T3']),
        ('Máquina Cablear 2', ['T4', 'T5', 'T6'])
    ],
    'ENGASTADO': [
        ('Máquina Engastar 1', ['T1', 'T2', 'T3']),
        ('Máquina Engastar 2', ['T4', 'T5', 'T6'])
    ],
    'REVISAR': [
        ('Máquina Revisar 1', ['T1', 'T2', 'T3'])
    ]
}

for puesto_id, puesto_nombre in puestos:
    print(f"🔧 Puesto: {puesto_nombre}")
    
    if puesto_nombre in config_maquinas:
        for maquina_nombre, terminales in config_maquinas[puesto_nombre]:
            # Crear máquina
            maquina_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO maquinas (id, puesto_id, nombre, activo)
                VALUES (?, ?, ?, 1)
            """, (maquina_id, puesto_id, maquina_nombre))
            
            print(f"   ✓ {maquina_nombre}")
            
            # Asignar terminales
            for terminal in terminales:
                cursor.execute("""
                    INSERT INTO maquinas_terminales (maquina_id, terminal_codigo)
                    VALUES (?, ?)
                """, (maquina_id, terminal))
            
            print(f"      Terminales: {', '.join(terminales)}")

conn.commit()
conn.close()

print(f"\n=== COMPLETADO ===")
print("Máquinas y terminales creados correctamente.")
