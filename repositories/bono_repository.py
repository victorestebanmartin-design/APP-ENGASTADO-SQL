"""
Repositorio de Bonos y Carros
"""
from typing import List, Dict, Optional
from .base_repository import BaseRepository


class BonoRepository(BaseRepository):
    """Repositorio para gestión de bonos"""
    
    def crear_bono(self, nombre: str, ordenes_ids: List[str], 
                   descripcion: Optional[str] = None) -> str:
        """
        Crear nuevo bono con órdenes
        
        Args:
            nombre: Nombre del bono
            ordenes_ids: Lista de IDs de órdenes a incluir
            descripcion: Descripción del bono (opcional)
        
        Returns:
            ID del bono creado (UUID)
        """
        import uuid
        bono_id = str(uuid.uuid4())
        
        # Insertar bono
        query_bono = """
            INSERT INTO bonos (id, nombre, descripcion, estado)
            VALUES (:id, :nombre, :descripcion, 'activo')
        """
        params_bono = {
            'id': bono_id,
            'nombre': nombre,
            'descripcion': descripcion
        }
        self.execute_insert(query_bono, params_bono)
        
        # Asignar órdenes al bono
        from .orden_repository import OrdenRepository
        orden_repo = OrdenRepository(self.db)
        for numero_orden in ordenes_ids:
            # Usar asignar_a_bono_por_numero ya que ordenes_ids contiene números de orden
            orden_repo.asignar_a_bono_por_numero(numero_orden, bono_id)
        
        return bono_id
    
    def obtener_bono(self, bono_id: str) -> Optional[Dict]:
        """Obtener bono por ID"""
        query = "SELECT * FROM bonos WHERE id = :id"
        resultados = self.execute_select(query, {'id': bono_id})
        return resultados[0] if resultados else None
    
    def obtener_bono_por_nombre(self, nombre: str) -> Optional[Dict]:
        """Obtener bono por nombre"""
        query = "SELECT * FROM bonos WHERE nombre = :nombre"
        resultados = self.execute_select(query, {'nombre': nombre})
        return resultados[0] if resultados else None
    
    def obtener_bono_con_ordenes(self, bono_id: str) -> Optional[Dict]:
        """Obtener bono con sus órdenes (usando vista)"""
        query = "SELECT * FROM vw_bonos_con_carros WHERE bono_id = :bono_id"
        resultados = self.execute_select(query, {'bono_id': bono_id})
        
        if not resultados:
            return None
        
        # Agrupar órdenes
        bono_info = {
            'id': resultados[0]['bono_id'],
            'nombre': resultados[0]['bono_nombre'],
            'estado': resultados[0]['bono_estado'],
            'carro_numero': resultados[0]['carro_numero'],
            'fecha_creacion': resultados[0]['bono_fecha_creacion'],
            'ordenes': []
        }
        
        for row in resultados:
            if row['orden_id']:
                bono_info['ordenes'].append({
                    'id': row['orden_id'],
                    'codigo_corte': row['orden_codigo_corte'],
                    'numero': row['orden_numero'],
                    'descripcion': row['orden_descripcion'],
                    'cantidad': row['orden_cantidad'],
                    'estado': row['orden_estado']
                })
        
        return bono_info
    
    def obtener_todos_bonos(self, estado: Optional[str] = None) -> List[Dict]:
        """
        Obtener todos los bonos
        
        Args:
            estado: Filtrar por estado ('activo', 'completado', 'cancelado')
        
        Returns:
            Lista de bonos
        """
        if estado:
            query = "SELECT * FROM bonos WHERE estado = :estado ORDER BY fecha_creacion DESC"
            return self.execute_select(query, {'estado': estado})
        else:
            query = "SELECT * FROM bonos ORDER BY fecha_creacion DESC"
            return self.execute_select(query)
    
    def asignar_a_carro(self, bono_id: str, carro_numero: int) -> bool:
        """
        Asignar bono a un carro
        
        Args:
            bono_id: ID del bono
            carro_numero: Número de carro (1-6)
        
        Returns:
            True si se asignó correctamente
        """
        query = """
            UPDATE bonos 
            SET carro_numero = :carro_numero
            WHERE id = :bono_id
        """
        params = {'bono_id': bono_id, 'carro_numero': carro_numero}
        rows = self.execute_update(query, params)
        
        # También actualizar las órdenes del bono
        if rows > 0:
            query_ordenes = """
                UPDATE ordenes_produccion
                SET carro_numero = :carro_numero,
                    estado = 'en_proceso'
                WHERE bono_id = :bono_id
            """
            self.execute_update(query_ordenes, params)
        
        return rows > 0
    
    def completar_bono(self, bono_id: str) -> bool:
        """Marcar bono como completado"""
        query = """
            UPDATE bonos 
            SET estado = 'completado',
                fecha_completado = datetime('now')
            WHERE id = :bono_id
        """
        rows = self.execute_update(query, {'bono_id': bono_id})
        
        # Completar también las órdenes
        if rows > 0:
            query_ordenes = """
                UPDATE ordenes_produccion
                SET estado = 'completado',
                    fecha_completado = datetime('now')
                WHERE bono_id = :bono_id AND estado != 'completado'
            """
            self.execute_update(query_ordenes, {'bono_id': bono_id})
        
        return rows > 0
    
    def cambiar_estado(self, bono_id: str, estado: str) -> bool:
        """Cambiar estado de un bono"""
        query = """
            UPDATE bonos 
            SET estado = :estado
            WHERE id = :bono_id
        """
        params = {'bono_id': bono_id, 'estado': estado}
        rows = self.execute_update(query, params)
        return rows > 0


class CarroRepository(BaseRepository):
    """Repositorio para gestión de carros"""
    
    def obtener_carro(self, carro_numero: int) -> Optional[Dict]:
        """Obtener información de un carro"""
        query = "SELECT * FROM carros WHERE numero = :numero"
        resultados = self.execute_select(query, {'numero': carro_numero})
        return resultados[0] if resultados else None
    
    def obtener_todos_carros(self) -> List[Dict]:
        """Obtener todos los carros"""
        query = "SELECT * FROM carros ORDER BY numero"
        return self.execute_select(query)
    
    def crear_carro(self, numero: int) -> bool:
        """Crear nuevo carro"""
        query = """
            INSERT OR IGNORE INTO carros (numero, estado)
            VALUES (:numero, 'disponible')
        """
        try:
            self.execute_insert(query, {'numero': numero})
            return True
        except Exception:
            return False
    
    def marcar_disponible(self, carro_numero: int, disponible: bool = True) -> bool:
        """Marcar carro como disponible/ocupado"""
        query = """
            UPDATE carros 
            SET estado = :estado
            WHERE numero = :numero
        """
        params = {
            'numero': carro_numero,
            'estado': 'disponible' if disponible else 'en_proceso'
        }
        rows = self.execute_update(query, params)
        return rows > 0
    
    def obtener_carros_disponibles(self) -> List[Dict]:
        """Obtener carros disponibles"""
        query = "SELECT * FROM carros WHERE estado = 'disponible' ORDER BY numero"
        return self.execute_select(query)
    
    def obtener_proyectos_activos_en_carro(self, carro_numero: int) -> List[Dict]:
        """Obtener proyectos activos asignados a un carro"""
        query = """
            SELECT * FROM proyectos
            WHERE carro_asignado = :carro_numero AND estado = 'activo'
            ORDER BY fecha_carga DESC
        """
        return self.execute_select(query, {'carro_numero': carro_numero})
    
    def obtener_bonos_en_carro(self, carro_numero: int) -> List[Dict]:
        """Obtener bonos asignados a un carro"""
        query = """
            SELECT * FROM bonos
            WHERE carro_numero = :carro_numero AND estado = 'activo'
            ORDER BY fecha_creacion DESC
        """
        return self.execute_select(query, {'carro_numero': carro_numero})
