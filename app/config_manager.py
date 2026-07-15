"""
config_manager.py
-----------------
Exportación e importación de configuración de la app (y opcionalmente datos de producción).

Permite:
  - Exportar config pura (puestos, máquinas, terminales, etc.) o completa (+ órdenes, bonos)
  - Importar con opción MERGE (actualiza existentes) o REPLACE (borra y recrea)
  - Transportar config entre equipos sin perder datos de producción
"""
import json
import os
import zipfile as _zipfile
import io
from datetime import datetime
from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError

# Tablas de configuración pura (no tienen datos operacionales)
TABLAS_CONFIG = [
    'puestos',
    'maquinas',
    'maquinas_terminales',
    'terminales_desactivados',
    'terminales_imagenes',
    'terminales_gavetas',
    'cable_colores',
    'operarios',
    'codigos_cortes',
]

# Tablas de producción (órdenes, bonos, progreso)
TABLAS_PRODUCCION = [
    'bonos',
    'carros',
    'proyectos',
    'ordenes_produccion',
    'proyectos_terminales_completados',
    'grupos_etiquetas',
    'etiquetas_elementos',
    'sesiones_trabajo',
]


class ConfigManager:
    """Gestor de exportación/importación de configuración."""
    
    def __init__(self, db):
        """
        Args:
            db: SQLAlchemy database instance
        """
        self.db = db
    
    def _tabla_a_json(self, tabla):
        """
        Convierte una tabla completa a lista de dicts (JSON-serializable).
        
        Args:
            tabla (str): Nombre de la tabla
            
        Returns:
            list: Lista de dicts con los registros
        """
        try:
            result = self.db.session.execute(text(f"SELECT * FROM {tabla}"))
            cols = [d[0] for d in result.keys()]
            rows = []
            for row in result:
                fila = {}
                for i, col in enumerate(cols):
                    val = row[i]
                    # Convertir tipos especiales a JSON-compatible
                    if val is None:
                        fila[col] = None
                    elif isinstance(val, (int, float, str, bool)):
                        fila[col] = val
                    else:
                        fila[col] = str(val)
                rows.append(fila)
            return rows
        except Exception as e:
            print(f"[AVISO] No se pudo exportar tabla {tabla}: {e}")
            return []
    
    def _json_a_tabla(self, tabla, datos, merge=True):
        """
        Carga datos JSON a una tabla.
        
        Args:
            tabla (str): Nombre de la tabla
            datos (list): Lista de dicts
            merge (bool): Si True, merge (INSERT OR REPLACE); si False, borra antes
            
        Returns:
            dict: {'éxito': n_insertados, 'errores': n_errores, 'detalles': []}
        """
        result = {'éxito': 0, 'errores': 0, 'detalles': []}
        
        if not merge:
            # REPLACE: borrar tabla antes
            try:
                self.db.session.execute(text(f"DELETE FROM {tabla}"))
                self.db.session.commit()
            except Exception as e:
                result['detalles'].append(f"No se pudo vaciar {tabla}: {e}")
        
        # Insertar datos
        for fila in datos:
            try:
                cols = ', '.join(fila.keys())
                placeholders = ', '.join([f":{k}" for k in fila.keys()])
                query = f"INSERT OR REPLACE INTO {tabla} ({cols}) VALUES ({placeholders})"
                self.db.session.execute(text(query), fila)
                result['éxito'] += 1
            except Exception as e:
                result['errores'] += 1
                result['detalles'].append(f"Error insertando en {tabla}: {e}")
        
        try:
            self.db.session.commit()
        except Exception as e:
            result['detalles'].append(f"Error committing {tabla}: {e}")
            self.db.session.rollback()
        
        return result
    
    def exportar(self, incluir_produccion=False):
        """
        Exporta configuración a un archivo ZIP en memoria.
        
        Args:
            incluir_produccion (bool): Si True, incluye también órdenes, bonos, etc.
            
        Returns:
            (bytes, str): (contenido ZIP, nombre_archivo)
        """
        zip_buffer = io.BytesIO()
        
        with _zipfile.ZipFile(zip_buffer, 'w', _zipfile.ZIP_DEFLATED) as zf:
            # Metadatos
            metadata = {
                'version': '1.0',
                'fecha_exportacion': datetime.now().isoformat(),
                'incluye_produccion': incluir_produccion,
            }
            zf.writestr('metadata.json', json.dumps(metadata, indent=2, ensure_ascii=False))
            
            # Tablas de configuración
            config_data = {}
            for tabla in TABLAS_CONFIG:
                datos = self._tabla_a_json(tabla)
                if datos:
                    config_data[tabla] = datos
            
            zf.writestr('config.json', json.dumps(config_data, indent=2, ensure_ascii=False))
            
            # Tablas de producción (si está habilitado)
            if incluir_produccion:
                produccion_data = {}
                for tabla in TABLAS_PRODUCCION:
                    datos = self._tabla_a_json(tabla)
                    if datos:
                        produccion_data[tabla] = datos
                
                zf.writestr('produccion.json', json.dumps(produccion_data, indent=2, ensure_ascii=False))
        
        zip_buffer.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        tipo = 'completa' if incluir_produccion else 'config'
        nombre_archivo = f"engastado_export_{tipo}_{timestamp}.zip"
        
        return zip_buffer.getvalue(), nombre_archivo
    
    def importar(self, contenido_zip, merge=True, incluir_produccion=False):
        """
        Importa configuración desde un archivo ZIP.
        
        Args:
            contenido_zip (bytes): Contenido del ZIP
            merge (bool): Si True, MERGE; si False, REPLACE
            incluir_produccion (bool): Si True, importa también datos de producción
            
        Returns:
            dict: {'éxito': True/False, 'resumen': {...}, 'detalles': [...]}
        """
        resultado = {
            'éxito': False,
            'resumen': {},
            'detalles': [],
            'modo': 'MERGE' if merge else 'REPLACE',
        }
        
        try:
            zip_buffer = io.BytesIO(contenido_zip)
            
            with _zipfile.ZipFile(zip_buffer, 'r') as zf:
                # Leer metadata
                try:
                    metadata_json = zf.read('metadata.json').decode('utf-8')
                    metadata = json.loads(metadata_json)
                    resultado['metadata'] = metadata
                except Exception as e:
                    resultado['detalles'].append(f"Aviso: no hay metadata: {e}")
                
                # Importar config
                try:
                    config_json = zf.read('config.json').decode('utf-8')
                    config_data = json.loads(config_json)
                    
                    for tabla, datos in config_data.items():
                        res = self._json_a_tabla(tabla, datos, merge=merge)
                        resultado['resumen'][tabla] = res
                        if res['detalles']:
                            resultado['detalles'].extend(res['detalles'])
                except Exception as e:
                    resultado['detalles'].append(f"Error importando config: {e}")
                    return resultado
                
                # Importar producción (si aplica)
                if incluir_produccion:
                    try:
                        produccion_json = zf.read('produccion.json').decode('utf-8')
                        produccion_data = json.loads(produccion_json)
                        
                        for tabla, datos in produccion_data.items():
                            res = self._json_a_tabla(tabla, datos, merge=merge)
                            resultado['resumen'][tabla] = res
                            if res['detalles']:
                                resultado['detalles'].extend(res['detalles'])
                    except KeyError:
                        resultado['detalles'].append("Aviso: archivo no contiene datos de producción")
                    except Exception as e:
                        resultado['detalles'].append(f"Error importando producción: {e}")
        
        except Exception as e:
            resultado['detalles'].append(f"Error leyendo ZIP: {e}")
            return resultado
        
        resultado['éxito'] = True
        return resultado
