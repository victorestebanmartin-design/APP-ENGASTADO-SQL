"""
Migrar etiquetas desde JSON a SQLite
"""
import sqlite3
import json
import os
from glob import glob

def migrar_etiquetas_principal():
    """Migrar grupos_etiquetas.json principal"""
    json_path = 'data/grupos_etiquetas.json'
    db_path = 'data/engastado.db'
    
    if not os.path.exists(json_path):
        print(f"❌ No se encontró {json_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Leer JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    archivo = data.get('archivo', 'DESCONOCIDO')
    codigo_corte = data.get('codigo_corte')
    grupos = data.get('grupos', [])
    
    print(f"\n📦 Migrando {len(grupos)} grupos desde {archivo}...")
    
    migrados = 0
    for grupo in grupos:
        try:
            cursor.execute("""
                INSERT INTO etiquetas_elementos 
                (archivo_excel, codigo_corte, numero_etiqueta, cod_cable, elemento, 
                 descripcion, seccion, longitud, de_terminal, num_cables, num_terminales)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                archivo,
                codigo_corte,
                grupo.get('numero_etiqueta'),
                grupo.get('cod_cable'),
                grupo.get('elemento'),
                grupo.get('descripcion'),
                grupo.get('seccion'),
                grupo.get('longitud'),
                grupo.get('de_terminal'),
                grupo.get('num_cables', 0),
                grupo.get('num_terminales', 0)
            ))
            migrados += 1
        except sqlite3.IntegrityError as e:
            print(f"⚠️  Etiqueta {grupo.get('numero_etiqueta')} ya existe, omitiendo...")
        except Exception as e:
            print(f"❌ Error en etiqueta {grupo.get('numero_etiqueta')}: {e}")
    
    conn.commit()
    print(f"✅ {migrados} etiquetas migradas desde archivo principal")
    
    conn.close()

def migrar_etiquetas_simuladas():
    """Migrar archivos de etiquetas_simuladas/"""
    etiquetas_dir = 'data/etiquetas_simuladas'
    db_path = 'data/engastado.db'
    
    if not os.path.exists(etiquetas_dir):
        print(f"❌ No se encontró carpeta {etiquetas_dir}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Buscar todos los archivos JSON en la carpeta
    archivos = glob(os.path.join(etiquetas_dir, '*.json'))
    
    print(f"\n📁 Encontrados {len(archivos)} archivos en etiquetas_simuladas/...")
    
    total_migrados = 0
    
    for archivo_path in archivos:
        try:
            with open(archivo_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            archivo = data.get('archivo', os.path.basename(archivo_path))
            codigo_corte = data.get('codigo_corte')
            grupos = data.get('grupos', [])
            
            if not grupos:
                continue
            
            print(f"  📄 {os.path.basename(archivo_path)}: {len(grupos)} grupos")
            
            migrados = 0
            for grupo in grupos:
                try:
                    cursor.execute("""
                        INSERT INTO etiquetas_elementos 
                        (archivo_excel, codigo_corte, numero_etiqueta, cod_cable, elemento, 
                         descripcion, seccion, longitud, de_terminal, num_cables, num_terminales)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        archivo,
                        codigo_corte,
                        grupo.get('numero_etiqueta'),
                        grupo.get('cod_cable'),
                        grupo.get('elemento'),
                        grupo.get('descripcion'),
                        grupo.get('seccion'),
                        grupo.get('longitud'),
                        grupo.get('de_terminal'),
                        grupo.get('num_cables', 0),
                        grupo.get('num_terminales', 0)
                    ))
                    migrados += 1
                except sqlite3.IntegrityError:
                    pass  # Ya existe
                except Exception as e:
                    print(f"    ❌ Error: {e}")
            
            total_migrados += migrados
            conn.commit()
            
        except Exception as e:
            print(f"  ❌ Error procesando {archivo_path}: {e}")
    
    print(f"✅ {total_migrados} etiquetas migradas desde archivos simulados")
    
    conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("MIGRACIÓN DE ETIQUETAS JSON → SQLite")
    print("=" * 60)
    
    migrar_etiquetas_principal()
    migrar_etiquetas_simuladas()
    
    # Mostrar resumen
    conn = sqlite3.connect('data/engastado.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM etiquetas_elementos")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT archivo_excel) FROM etiquetas_elementos")
    archivos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT codigo_corte) FROM etiquetas_elementos")
    codigos = cursor.fetchone()[0]
    
    print(f"\n📊 RESUMEN:")
    print(f"   Total etiquetas: {total}")
    print(f"   Archivos: {archivos}")
    print(f"   Códigos de corte: {codigos}")
    
    conn.close()
    
    print("\n✅ Migración completada")
