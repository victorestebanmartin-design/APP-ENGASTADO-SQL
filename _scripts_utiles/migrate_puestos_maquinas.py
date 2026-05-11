"""
Script para migrar puestos y máquinas desde JSON a SQLite
"""
import json
import sqlite3
import os
from pathlib import Path

# Rutas
BASE_DIR = Path(__file__).parent
OLD_JSON = BASE_DIR.parent / 'PROYECTO-ENGASTADO1git' / 'data' / 'puestos_maquinas.json'
DB_PATH = BASE_DIR / 'data' / 'engastado.db'


def migrar_puestos_maquinas():
    """Migrar puestos y máquinas desde JSON a SQLite"""
    
    if not OLD_JSON.exists():
        print(f"❌ No se encontró {OLD_JSON}")
        return
    
    if not DB_PATH.exists():
        print(f"❌ No se encontró base de datos {DB_PATH}")
        return
    
    # Leer JSON
    print(f"📖 Leyendo {OLD_JSON}...")
    with open(OLD_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    puestos = data.get('puestos', [])
    print(f"   Encontrados {len(puestos)} puestos")
    
    # Conectar a SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Estadísticas
        puestos_migrados = 0
        maquinas_migradas = 0
        terminales_asignados = 0
        
        for puesto in puestos:
            puesto_id = puesto['id']
            nombre = puesto['nombre']
            descripcion = puesto.get('descripcion', '')
            activo = 1 if puesto.get('activo', True) else 0
            
            # Insertar puesto
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO puestos (id, nombre, descripcion, activo)
                    VALUES (?, ?, ?, ?)
                """, (puesto_id, nombre, descripcion, activo))
                puestos_migrados += 1
                print(f"   ✓ Puesto: {nombre} (ID: {puesto_id})")
            except Exception as e:
                print(f"   ✗ Error en puesto {puesto_id}: {e}")
                continue
            
            # Migrar máquinas del puesto
            maquinas = puesto.get('maquinas', [])
            for maquina in maquinas:
                maquina_id = maquina['id']
                maq_nombre = maquina['nombre']
                modelo = maquina.get('modelo', '')
                maq_desc = maquina.get('descripcion', '')
                maq_activa = 1 if maquina.get('activo', True) else 0
                
                # Insertar máquina
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO maquinas (id, puesto_id, nombre, modelo, descripcion, activo)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (maquina_id, puesto_id, maq_nombre, modelo, maq_desc, maq_activa))
                    maquinas_migradas += 1
                    print(f"      ✓ Máquina: {maq_nombre} (ID: {maquina_id})")
                except Exception as e:
                    print(f"      ✗ Error en máquina {maquina_id}: {e}")
                    continue
                
                # Asignar terminales
                terminales = maquina.get('terminales_asignados', [])
                for terminal in terminales:
                    try:
                        cursor.execute("""
                            INSERT OR IGNORE INTO maquinas_terminales (maquina_id, terminal_codigo, activo)
                            VALUES (?, ?, 1)
                        """, (maquina_id, terminal))
                        terminales_asignados += 1
                    except Exception as e:
                        print(f"         ✗ Error asignando terminal {terminal}: {e}")
        
        # Commit
        conn.commit()
        
        print("\n" + "="*60)
        print("✅ MIGRACIÓN DE PUESTOS Y MÁQUINAS COMPLETADA")
        print("="*60)
        print(f"   Puestos migrados: {puestos_migrados}")
        print(f"   Máquinas migradas: {maquinas_migradas}")
        print(f"   Terminales asignados: {terminales_asignados}")
        print("="*60)
        
        # Verificar
        cursor.execute("SELECT COUNT(*) FROM puestos")
        total_puestos = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM maquinas")
        total_maquinas = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM maquinas_terminales")
        total_terminales = cursor.fetchone()[0]
        
        print(f"\n📊 Estado actual de la base de datos:")
        print(f"   Total puestos: {total_puestos}")
        print(f"   Total máquinas: {total_maquinas}")
        print(f"   Total asignaciones: {total_terminales}")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR durante la migración: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    print("="*60)
    print("MIGRACIÓN DE PUESTOS Y MÁQUINAS")
    print("="*60)
    migrar_puestos_maquinas()
