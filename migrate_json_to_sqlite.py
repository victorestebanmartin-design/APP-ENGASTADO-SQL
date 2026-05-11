"""
Script para migrar datos desde archivos JSON a SQLite

Uso:
    python migrate_json_to_sqlite.py
    
O desde el proyecto original:
    python migrate_json_to_sqlite.py --source ../PROYECTO-ENGASTADO1git/data
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from sqlalchemy import text

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(__file__))

from repositories import db as DB
from repositories.proyecto_repository import ProyectoRepository
from repositories.orden_repository import OrdenRepository
from repositories.codigo_corte_repository import CodigoCorteRepository
from repositories.bono_repository import BonoRepository, CarroRepository
from repositories.puesto_repository import PuestoRepository
from repositories.maquina_repository import MaquinaRepository


def cargar_json(filepath):
    """Cargar archivo JSON"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️  Archivo no encontrado: {filepath}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error leyendo JSON {filepath}: {e}")
        return None


def migrar_proyectos(db, source_dir):
    """Migrar proyectos desde proyectos_carros.json"""
    print("\n📦 Migrando proyectos...")
    
    filepath = os.path.join(source_dir, 'proyectos_carros.json')
    data = cargar_json(filepath)
    
    if not data:
        return 0
    
    proyecto_repo = ProyectoRepository(db)
    count = 0
    
    for proyecto_json in data.get('proyectos', []):
        try:
            # Crear proyecto
            proyecto_id = proyecto_repo.crear_proyecto(
                nombre=proyecto_json['nombre'],
                archivo=proyecto_json['archivo'],
                carro_asignado=proyecto_json.get('carro_asignado')
            )
            
            # Actualizar estado y progreso
            if proyecto_json.get('estado') != 'activo':
                proyecto_repo.cambiar_estado(proyecto_id, proyecto_json['estado'])
            
            if proyecto_json.get('progreso', 0) > 0:
                proyecto_repo.actualizar_progreso(proyecto_id, proyecto_json['progreso'])
            
            # Agregar terminales completados
            for terminal in proyecto_json.get('terminales_completados', []):
                proyecto_repo.agregar_terminal_completado(proyecto_id, terminal)
            
            count += 1
            print(f"   ✓ Proyecto {proyecto_json['nombre']} (ID: {proyecto_id})")
            
        except Exception as e:
            print(f"   ❌ Error migrando proyecto {proyecto_json.get('nombre', '?')}: {e}")
    
    print(f"   Total: {count} proyectos migrados")
    return count


def migrar_carros(db, source_dir):
    """Migrar información de carros desde proyectos_carros.json"""
    print("\n🚂 Migrando carros...")
    
    filepath = os.path.join(source_dir, 'proyectos_carros.json')
    data = cargar_json(filepath)
    
    if not data:
        # Si no hay archivo, crear carros por defecto
        data = {}
    
    carro_repo = CarroRepository(db)
    count = 0
    
    carros_json = data.get('carros', {})
    
    # Si no hay carros en el JSON, crear los 6 por defecto
    if not carros_json:
        for i in range(1, 7):
            if carro_repo.crear_carro(i):
                count += 1
                print(f"   ✓ Carro {i} creado")
    else:
        # Migrar carros desde JSON
        for carro_num, carro_data in carros_json.items():
            try:
                carro_numero = int(carro_num)
                # carro_data puede ser un dict o un valor primitivo
                nombre = f'Carro {carro_numero}'
                if isinstance(carro_data, dict):
                    nombre = carro_data.get('nombre', nombre)
                if carro_repo.crear_carro(numero=carro_numero):
                    count += 1
                    print(f"   ✓ Carro {carro_numero}")
            except Exception as e:
                print(f"   ❌ Error migrando carro {carro_num}: {e}")
    
    print(f"   Total: {count} carros migrados")
    return count


def migrar_codigos_cortes(db, source_dir):
    """Migrar códigos de cortes desde codigos_cortes.json"""
    print("\n🔖 Migrando códigos de cortes...")
    
    filepath = os.path.join(source_dir, 'codigos_cortes.json')
    data = cargar_json(filepath)
    
    if not data:
        return 0
    
    codigo_repo = CodigoCorteRepository(db)
    count = 0
    
    for corte in data.get('cortes', []):
        try:
            if codigo_repo.agregar_codigo(
                codigo=corte['codigo_barras'],
                archivo_excel=corte['archivo'],
                proyecto_nombre=corte.get('proyecto')
            ):
                count += 1
                print(f"   ✓ Código {corte['codigo_barras']} → {corte['archivo']}")
        except Exception as e:
            print(f"   ❌ Error migrando código {corte.get('codigo_barras', '?')}: {e}")
    
    print(f"   Total: {count} códigos migrados")
    return count


def migrar_ordenes(db, source_dir):
    """Migrar órdenes de producción desde ordenes_produccion.json"""
    print("\n📋 Migrando órdenes de producción...")
    
    filepath = os.path.join(source_dir, 'ordenes_produccion.json')
    data = cargar_json(filepath)
    
    if not data:
        return 0
    
    orden_repo = OrdenRepository(db)
    count = 0
    
    # Mapeo de bonos (nombre → ID)
    bono_map = {}
    
    for orden_json in data.get('ordenes', []):
        try:
            # Usar el ID existente si está en formato UUID
            orden_id = orden_json.get('id')
            if not orden_id or len(orden_id) != 36:
                orden_id = str(uuid.uuid4())
            
            # Crear orden con ID específico
            with db.engine.connect() as conn:
                query = text("""
                    INSERT INTO ordenes_produccion 
                    (id, codigo_corte, numero, proyecto, descripcion, cantidad, 
                     fecha_entrega, prioridad, estado, archivo_excel)
                    VALUES 
                    (:id, :codigo_corte, :numero, :proyecto, :descripcion, :cantidad,
                     :fecha_entrega, :prioridad, :estado, :archivo_excel)
                """)
                
                conn.execute(query, {
                    'id': orden_id,
                    'codigo_corte': orden_json['codigo_corte'],
                    'numero': orden_json['numero'],
                    'proyecto': orden_json.get('proyecto', ''),
                    'descripcion': orden_json['descripcion'],
                    'cantidad': orden_json.get('cantidad', 1),
                    'fecha_entrega': orden_json.get('fecha_entrega'),
                    'prioridad': orden_json.get('prioridad', 'normal'),
                    'estado': {
                        'engastando': 'en_proceso',
                        'finalizado': 'completado',
                        'pending': 'pendiente',
                    }.get(orden_json.get('estado', 'pendiente'), orden_json.get('estado', 'pendiente')),
                    'archivo_excel': orden_json.get('archivo_excel')
                })
                conn.commit()
            
            # Si tiene bono, crear/asignar
            bono_nombre = orden_json.get('bono')
            if bono_nombre:
                # Si el bono ya existe en el mapeo, usar ese ID
                if bono_nombre in bono_map:
                    bono_id = bono_map[bono_nombre]
                else:
                    # Crear nuevo bono
                    bono_id = str(uuid.uuid4())
                    
                    with db.engine.connect() as conn:
                        query = text("""
                            INSERT INTO bonos (id, nombre, estado)
                            VALUES (:id, :nombre, 'activo')
                        """)
                        conn.execute(query, {'id': bono_id, 'nombre': bono_nombre})
                        conn.commit()
                    
                    bono_map[bono_nombre] = bono_id
                
                # Asignar orden al bono
                orden_repo.asignar_a_bono(orden_id, bono_id)
            
            # Asignar a carro si tiene
            carro_numero = orden_json.get('carro_numero')
            if carro_numero:
                orden_repo.asignar_a_carro(orden_id, carro_numero)
            
            count += 1
            print(f"   ✓ Orden {orden_json['numero']} ({orden_json['codigo_corte']})")
            
        except Exception as e:
            print(f"   ❌ Error migrando orden {orden_json.get('numero', '?')}: {e}")
    
    print(f"   Total: {count} órdenes migradas")
    print(f"   Bonos creados: {len(bono_map)}")
    return count


def migrar_puestos_maquinas_terminales(db, source_dir):
    """Migrar puestos, máquinas y terminales desde puestos_maquinas.json"""
    print("\n🏭 Migrando puestos, máquinas y terminales...")
    
    filepath = os.path.join(source_dir, 'puestos_maquinas.json')
    data = cargar_json(filepath)
    
    if not data or 'puestos' not in data:
        print("   ⚠️  No se encontró archivo puestos_maquinas.json")
        return 0
    
    puesto_repo = PuestoRepository(db)
    maquina_repo = MaquinaRepository(db)
    
    count_puestos = 0
    count_maquinas = 0
    count_terminales = 0
    
    for puesto_json in data['puestos']:
        try:
            # Crear puesto usando el ID del JSON o generar uno nuevo
            puesto_id = puesto_json.get('id', str(uuid.uuid4()))
            success = puesto_repo.crear_puesto(
                id=puesto_id,
                nombre=puesto_json['nombre'],
                descripcion=puesto_json.get('descripcion', '')
            )
            if success:
                count_puestos += 1
                print(f"   ✓ Puesto: {puesto_json['nombre']}")
            
            # Crear máquinas del puesto
            if 'maquinas' in puesto_json:
                for maquina_json in puesto_json['maquinas']:
                    try:
                        # Generar UUID para máquina
                        maquina_id = str(uuid.uuid4())
                        success = maquina_repo.crear_maquina(
                            id=maquina_id,
                            puesto_id=puesto_id,
                            nombre=maquina_json['nombre'],
                            modelo=maquina_json.get('modelo', ''),
                            descripcion=maquina_json.get('descripcion', '')
                        )
                        
                        if success:
                            count_maquinas += 1
                            print(f"     - Máquina: {maquina_json['nombre']}")
                            
                            # Asignar terminales a la máquina
                            terminales_asignados = maquina_json.get('terminales_asignados', [])
                            if terminales_asignados:
                                for terminal_codigo in terminales_asignados:
                                    try:
                                        maquina_repo.asignar_terminal(maquina_id, terminal_codigo)
                                        count_terminales += 1
                                    except Exception as e:
                                        print(f"       ⚠️  Terminal {terminal_codigo}: {e}")
                        
                    except Exception as e:
                        print(f"     ❌ Error creando máquina {maquina_json.get('nombre', '?')}: {e}")
        
        except Exception as e:
            print(f"   ❌ Error creando puesto {puesto_json.get('nombre', '?')}: {e}")
    
    print(f"   Total: {count_puestos} puestos, {count_maquinas} máquinas, {count_terminales} terminales")
    return count_puestos + count_maquinas + count_terminales


def main():
    """Función principal de migración"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrar datos JSON a SQLite')
    parser.add_argument(
        '--source',
        default='../PROYECTO-ENGASTADO1git/data',
        help='Directorio con archivos JSON (default: ../PROYECTO-ENGASTADO1git/data)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Forzar migración (eliminar datos existentes)'
    )
    
    args = parser.parse_args()
    
    # Verificar directorio source
    source_dir = Path(args.source)
    if not source_dir.exists():
        print(f"❌ Directorio no encontrado: {source_dir}")
        print(f"   Asegúrate de que la ruta sea correcta.")
        return 1
    
    print("="*60)
    print("   🔄 MIGRACIÓN JSON → SQLite")
    print("="*60)
    print(f"📂 Directorio fuente: {source_dir.absolute()}")
    
    # Confirmar migración
    if not args.force:
        respuesta = input("\n¿Continuar con la migración? (s/n): ")
        if respuesta.lower() != 's':
            print("Migración cancelada.")
            return 0
    
    # Inicializar DB manualmente
    print("\n🔧 Inicializando conexión a base de datos...")
    from config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, scoped_session
    
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, echo=False)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    
    # Crear objeto DB compatible
    class DBWrapper:
        def __init__(self, engine, session):
            self.engine = engine
            self.session = session
        
        def get_session(self):
            return self.session()
        
        def close_session(self):
            self.session.remove()
    
    db = DBWrapper(engine, Session)
    
    # Inicializar schema (crear tablas si no existen)
    schema_file = os.path.join(os.path.dirname(__file__), 'schema_sqlite.sql')
    if os.path.exists(schema_file):
        print("🔧 Inicializando schema de base de datos...")
        with engine.connect() as conn:
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            # Ejecutar cada sentencia por separado
            for statement in schema_sql.split(';'):
                stmt = statement.strip()
                if stmt:
                    try:
                        conn.execute(text(stmt))
                    except Exception:
                        pass  # Ignorar errores de tablas ya existentes
            conn.commit()
        print("✅ Schema inicializado")
    
    print("✅ Conexión establecida")
    
    # Ejecutar migraciones
    total_items = 0
    
    try:
        total_items += migrar_puestos_maquinas_terminales(db, source_dir)
        total_items += migrar_carros(db, source_dir)
        total_items += migrar_proyectos(db, source_dir)
        total_items += migrar_codigos_cortes(db, source_dir)
        total_items += migrar_ordenes(db, source_dir)
        
        print("\n" + "="*60)
        print(f"✅ MIGRACIÓN COMPLETADA - {total_items} elementos migrados")
        print("="*60)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error durante la migración: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close_session()



if __name__ == '__main__':
    sys.exit(main())
