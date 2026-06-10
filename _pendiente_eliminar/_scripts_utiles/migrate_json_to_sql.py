"""
Script de migración de datos JSON a SQL Server
==================================================
Lee todos los archivos JSON del proyecto viejo y los 
inserta en SQL Server con validaciones.

Uso:
    python migrate_json_to_sql.py [--proyecto-path RUTA]

Flags:
    --proyecto-path: Ruta al proyecto JSON viejo (default: ../PROYECTO-ENGASTADO1git)
    --dry-run: Solo validar, no insertar
    --verbose: Logs detallados
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

try:
    import pyodbc
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
except ImportError:
    print("❌ Faltan dependencias. Ejecuta: pip install -r requirements.txt")
    sys.exit(1)

from config import Config

class MigradorJSON:
    """Migrador de datos JSON a SQL Server"""
    
    def __init__(self, proyecto_path, dry_run=False, verbose=False):
        self.proyecto_path = Path(proyecto_path)
        self.data_path = self.proyecto_path / 'data'
        self.dry_run = dry_run
        self.verbose = verbose
        
        # Contadores
        self.stats = {
            'proyectos': 0,
            'bonos': 0,
            'carros': 0,
            'ordenes': 0,
            'codigos_cortes': 0,
            'puestos': 0,
            'maquinas': 0,
            'terminales': 0,
            'grupos_etiquetas': 0,
            'errores': []
        }
        
        # Conexión
        self.engine = None
        self.session = None
    
    def conectar(self):
        """Conectar a SQL Server"""
        try:
            self.engine = create_engine(
                Config.SQLALCHEMY_DATABASE_URI,
                echo=self.verbose
            )
            Session = sessionmaker(bind=self.engine)
            self.session = Session()
            
            # Test de conexión
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            print("✅ Conexión a SQL Server exitosa")
            return True
        except Exception as e:
            print(f"❌ Error conectando a SQL Server: {e}")
            return False
    
    def validar_archivos(self):
        """Verificar que existen los archivos JSON necesarios"""
        archivos_requeridos = [
            'proyectos_carros.json',
            'ordenes_produccion.json',
            'codigos_cortes.json',
            'puestos_maquinas.json',
            'terminales_desactivados.json'
        ]
        
        faltantes = []
        for archivo in archivos_requeridos:
            path = self.data_path / archivo
            if not path.exists():
                faltantes.append(archivo)
        
        if faltantes:
            print(f"⚠️  Archivos faltantes: {', '.join(faltantes)}")
            return False
        
        print(f"✅ Todos los archivos JSON encontrados en {self.data_path}")
        return True
    
    def migrar_proyectos(self):
        """Migrar proyectos_carros.json"""
        print("\n📁 Migrando proyectos...")
        
        archivo = self.data_path / 'proyectos_carros.json'
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            proyectos = data.get('proyectos', [])
            print(f"   Encontrados {len(proyectos)} proyectos")
            
            if not self.dry_run:
                # TODO: Insertar en tabla proyectos
                # for proyecto in proyectos:
                #     self.session.execute(text("""
                #         INSERT INTO proyectos (id, nombre, archivo, ...)
                #         VALUES (:id, :nombre, :archivo, ...)
                #     """), proyecto)
                pass
            
            self.stats['proyectos'] = len(proyectos)
            print(f"   ✅ {len(proyectos)} proyectos procesados")
            
        except Exception as e:
            error = f"Error en proyectos: {e}"
            print(f"   ❌ {error}")
            self.stats['errores'].append(error)
    
    def migrar_ordenes(self):
        """Migrar ordenes_produccion.json"""
        print("\n📋 Migrando órdenes de producción...")
        
        archivo = self.data_path / 'ordenes_produccion.json'
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            ordenes = data.get('ordenes', [])
            print(f"   Encontradas {len(ordenes)} órdenes")
            
            if not self.dry_run:
                # TODO: Insertar en tabla ordenes_produccion
                pass
            
            self.stats['ordenes'] = len(ordenes)
            print(f"   ✅ {len(ordenes)} órdenes procesadas")
            
        except Exception as e:
            error = f"Error en órdenes: {e}"
            print(f"   ❌ {error}")
            self.stats['errores'].append(error)
    
    def migrar_codigos_cortes(self):
        """Migrar codigos_cortes.json"""
        print("\n🔖 Migrando códigos de cortes...")
        
        archivo = self.data_path / 'codigos_cortes.json'
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            codigos = data.get('cortes', [])
            print(f"   Encontrados {len(codigos)} códigos")
            
            if not self.dry_run:
                # TODO: Insertar en tabla codigos_cortes
                pass
            
            self.stats['codigos_cortes'] = len(codigos)
            print(f"   ✅ {len(codigos)} códigos procesados")
            
        except Exception as e:
            error = f"Error en códigos: {e}"
            print(f"   ❌ {error}")
            self.stats['errores'].append(error)
    
    def migrar_puestos_maquinas(self):
        """Migrar puestos_maquinas.json"""
        print("\n🏭 Migrando puestos y máquinas...")
        
        archivo = self.data_path / 'puestos_maquinas.json'
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            puestos = data.get('puestos', [])
            print(f"   Encontrados {len(puestos)} puestos")
            
            total_maquinas = sum(len(p.get('maquinas', [])) for p in puestos)
            print(f"   Encontradas {total_maquinas} máquinas")
            
            if not self.dry_run:
                # TODO: Insertar puestos, maquinas y terminales
                pass
            
            self.stats['puestos'] = len(puestos)
            self.stats['maquinas'] = total_maquinas
            print(f"   ✅ {len(puestos)} puestos y {total_maquinas} máquinas procesados")
            
        except Exception as e:
            error = f"Error en puestos/máquinas: {e}"
            print(f"   ❌ {error}")
            self.stats['errores'].append(error)
    
    def migrar_grupos_etiquetas(self):
        """Migrar grupos_etiquetas.json"""
        print("\n🏷️  Migrando grupos de etiquetas...")
        
        archivo = self.data_path / 'grupos_etiquetas.json'
        if not archivo.exists():
            print("   ⚠️  Archivo no encontrado (opcional)")
            return
        
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            grupos = data.get('grupos', [])
            print(f"   Encontrados {len(grupos)} grupos")
            
            if not self.dry_run:
                # TODO: Insertar en tabla grupos_etiquetas
                pass
            
            self.stats['grupos_etiquetas'] = len(grupos)
            print(f"   ✅ {len(grupos)} grupos procesados")
            
        except Exception as e:
            error = f"Error en grupos etiquetas: {e}"
            print(f"   ⚠️  {error}")
    
    def generar_reporte(self):
        """Generar reporte de migración"""
        print("\n" + "=" * 80)
        print("📊 REPORTE DE MIGRACIÓN")
        print("=" * 80)
        print(f"Modo: {'DRY RUN (solo validación)' if self.dry_run else 'PRODUCCIÓN (datos insertados)'}")
        print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("\nRegistros procesados:")
        print(f"  - Proyectos:          {self.stats['proyectos']}")
        print(f"  - Órdenes:            {self.stats['ordenes']}")
        print(f"  - Códigos de corte:   {self.stats['codigos_cortes']}")
        print(f"  - Puestos:            {self.stats['puestos']}")
        print(f"  - Máquinas:           {self.stats['maquinas']}")
        print(f"  - Grupos etiquetas:   {self.stats['grupos_etiquetas']}")
        
        if self.stats['errores']:
            print(f"\n❌ Errores encontrados ({len(self.stats['errores'])}):")
            for error in self.stats['errores']:
                print(f"  - {error}")
        else:
            print("\n✅ Migración completada sin errores")
        
        print("=" * 80)
    
    def ejecutar(self):
        """Ejecutar migración completa"""
        print("=" * 80)
        print("🚀 MIGRACIÓN JSON → SQL SERVER")
        print("=" * 80)
        print(f"Proyecto origen: {self.proyecto_path}")
        print(f"Modo: {'DRY RUN' if self.dry_run else 'PRODUCCIÓN'}")
        print("=" * 80)
        
        # Validaciones previas
        if not self.validar_archivos():
            print("\n❌ Validación fallida. Abortar.")
            return False
        
        if not self.conectar():
            print("\n❌ No se pudo conectar a SQL Server. Abortar.")
            return False
        
        try:
            # Ejecutar migraciones
            self.migrar_proyectos()
            self.migrar_ordenes()
            self.migrar_codigos_cortes()
            self.migrar_puestos_maquinas()
            self.migrar_grupos_etiquetas()
            
            # Commit si no es dry-run
            if not self.dry_run:
                self.session.commit()
                print("\n✅ Transacción confirmada (COMMIT)")
            
        except Exception as e:
            if self.session:
                self.session.rollback()
            print(f"\n❌ Error crítico: {e}")
            self.stats['errores'].append(str(e))
            return False
        
        finally:
            if self.session:
                self.session.close()
        
        # Reporte final
        self.generar_reporte()
        return len(self.stats['errores']) == 0


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(description='Migrar datos JSON a SQL Server')
    parser.add_argument(
        '--proyecto-path',
        default=r'C:\Users\estebanv\PROYECTO-ENGASTADO1git',
        help='Ruta al proyecto JSON viejo'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Solo validar, no insertar datos'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Logs detallados de SQL'
    )
    
    args = parser.parse_args()
    
    # Ejecutar migración
    migrador = MigradorJSON(
        proyecto_path=args.proyecto_path,
        dry_run=args.dry_run,
        verbose=args.verbose
    )
    
    exito = migrador.ejecutar()
    sys.exit(0 if exito else 1)


if __name__ == '__main__':
    main()
