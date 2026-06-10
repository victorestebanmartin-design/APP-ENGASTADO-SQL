import json
import sqlite3

print("🔧 Creando terminales desde puestos_maquinas.json...")

# Leer puestos y máquinas
with open('c:/Users/estebanv/PROYECTO-ENGASTADO1git/data/puestos_maquinas.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

# Obtener IDs de máquinas por nombre
cursor.execute('SELECT id, nombre FROM maquinas')
maquinas_db = {nombre: id for id, nombre in cursor.fetchall()}

total_terminales = 0

# Recorrer puestos y máquinas
for puesto in data['puestos']:
    puesto_nombre = puesto['nombre']
    
    if 'maquinas' in puesto:
        for maquina in puesto['maquinas']:
            maquina_nombre = maquina['nombre']
            
            # Buscar ID de máquina en BD
            if maquina_nombre not in maquinas_db:
                print(f"⚠️ Máquina '{maquina_nombre}' no encontrada en BD")
                continue
            
            maquina_id = maquinas_db[maquina_nombre]
            
            # Obtener terminales asignados
            terminales_asignados = maquina.get('terminales_asignados', [])
            
            if terminales_asignados:
                print(f"\n  📦 {maquina_nombre}: {len(terminales_asignados)} terminales")
                
                for terminal_codigo in terminales_asignados:
                    try:
                        cursor.execute('''
                            INSERT OR IGNORE INTO maquinas_terminales
                            (maquina_id, terminal_codigo, activo)
                            VALUES (?, ?, 1)
                        ''', (maquina_id, terminal_codigo))
                        
                        if cursor.rowcount > 0:
                            total_terminales += 1
                            print(f"    ✓ {terminal_codigo}")
                    except Exception as e:
                        print(f"    ❌ Error insertando {terminal_codigo}: {e}")

conn.commit()

# Verificar total
cursor.execute('SELECT COUNT(*) FROM maquinas_terminales')
count_term = cursor.fetchone()[0]

print(f"\n✅ Total terminales creados: {count_term}")

# Mostrar resumen por máquina
print("\n📊 Resumen por máquina:")
cursor.execute('''
    SELECT m.nombre, COUNT(mt.terminal_codigo)
    FROM maquinas m
    LEFT JOIN maquinas_terminales mt ON m.id = mt.maquina_id
    GROUP BY m.id, m.nombre
    ORDER BY COUNT(mt.terminal_codigo) DESC
''')

for nombre, count in cursor.fetchall():
    if count > 0:
        print(f"  - {nombre}: {count} terminales")

conn.close()
