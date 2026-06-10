"""
Repositorio de Proyectos
"""
from typing import List, Dict, Optional
from sqlalchemy import text
from .base_repository import BaseRepository


class ProyectoRepository(BaseRepository):
    """Repositorio para gestión de proyectos"""
    
    def crear_proyecto(self, nombre: str, archivo: str, carro_asignado: Optional[int] = None) -> int:
        """
        Crear nuevo proyecto
        
        Args:
            nombre: Nombre del proyecto
            archivo: Nombre del archivo Excel
            carro_asignado: Número de carro (opcional)
        
        Returns:
            ID del proyecto creado
        """
        query = """
            INSERT INTO proyectos (nombre, archivo, carro_asignado, progreso, estado)
            VALUES (:nombre, :archivo, :carro_asignado, 0.0, 'activo')
        """
        params = {
            'nombre': nombre,
            'archivo': archivo,
            'carro_asignado': carro_asignado
        }
        return self.execute_insert(query, params)
    
    def obtener_proyecto(self, proyecto_id: int) -> Optional[Dict]:
        """Obtener proyecto por ID"""
        query = "SELECT * FROM proyectos WHERE id = :id"
        resultados = self.execute_select(query, {'id': proyecto_id})
        return resultados[0] if resultados else None
    
    def obtener_todos_proyectos(self, estado: Optional[str] = None) -> List[Dict]:
        """
        Obtener todos los proyectos, opcionalmente filtrados por estado
        
        Args:
            estado: Estado a filtrar ('activo', 'completado', 'pausado', 'cancelado')
        
        Returns:
            Lista de proyectos
        """
        if estado:
            query = "SELECT * FROM proyectos WHERE estado = :estado ORDER BY fecha_carga DESC"
            return self.execute_select(query, {'estado': estado})
        else:
            query = "SELECT * FROM proyectos ORDER BY fecha_carga DESC"
            return self.execute_select(query)
    
    def obtener_proyectos_por_carro(self, carro_numero: int) -> List[Dict]:
        """Obtener proyectos asignados a un carro específico"""
        query = """
            SELECT * FROM proyectos 
            WHERE carro_asignado = :carro_numero AND estado = 'activo'
            ORDER BY fecha_carga DESC
        """
        return self.execute_select(query, {'carro_numero': carro_numero})
    
    def asignar_carro(self, proyecto_id: int, carro_numero: int) -> bool:
        """
        Asignar proyecto a un carro
        
        Args:
            proyecto_id: ID del proyecto
            carro_numero: Número de carro (1-6)
        
        Returns:
            True si se asignó correctamente
        """
        query = """
            UPDATE proyectos 
            SET carro_asignado = :carro_numero
            WHERE id = :proyecto_id
        """
        params = {'proyecto_id': proyecto_id, 'carro_numero': carro_numero}
        rows = self.execute_update(query, params)
        return rows > 0
    
    def liberar_carro(self, proyecto_id: int, conn=None) -> bool:
        """Liberar carro de un proyecto"""
        query = """
            UPDATE proyectos 
            SET carro_asignado = NULL
            WHERE id = :proyecto_id
        """
        params = {'proyecto_id': proyecto_id}
        if conn is not None:
            result = conn.execute(text(query), params)
            return result.rowcount > 0
        rows = self.execute_update(query, params)
        return rows > 0
    
    def actualizar_progreso(self, proyecto_id: int, progreso: float) -> bool:
        """
        Actualizar progreso de un proyecto
        
        Args:
            proyecto_id: ID del proyecto
            progreso: Porcentaje de progreso (0-100)
        
        Returns:
            True si se actualizó
        """
        query = """
            UPDATE proyectos 
            SET progreso = :progreso
            WHERE id = :proyecto_id
        """
        params = {'proyecto_id': proyecto_id, 'progreso': progreso}
        rows = self.execute_update(query, params)
        return rows > 0
    
    def cambiar_estado(self, proyecto_id: int, estado: str) -> bool:
        """
        Cambiar estado de un proyecto
        
        Args:
            proyecto_id: ID del proyecto
            estado: Nuevo estado ('activo', 'completado', 'pausado', 'cancelado')
        
        Returns:
            True si se cambió
        """
        query = """
            UPDATE proyectos 
            SET estado = :estado
            WHERE id = :proyecto_id
        """
        params = {'proyecto_id': proyecto_id, 'estado': estado}
        rows = self.execute_update(query, params)
        return rows > 0
    
    def agregar_terminal_completado(self, proyecto_id: int, terminal_codigo: str) -> bool:
        """Marcar un terminal como completado en un proyecto"""
        query = """
            INSERT INTO proyectos_terminales_completados (proyecto_id, terminal_codigo)
            VALUES (:proyecto_id, :terminal_codigo)
        """
        try:
            self.execute_insert(query, {
                'proyecto_id': proyecto_id,
                'terminal_codigo': terminal_codigo
            })
            return True
        except Exception:
            return False
    
    def obtener_terminales_completados(self, proyecto_id: int) -> List[str]:
        """Obtener lista de terminales completados de un proyecto"""
        query = """
            SELECT terminal_codigo 
            FROM proyectos_terminales_completados 
            WHERE proyecto_id = :proyecto_id
            ORDER BY fecha_completado
        """
        resultados = self.execute_select(query, {'proyecto_id': proyecto_id})
        return [r['terminal_codigo'] for r in resultados]
    
    def eliminar_proyecto(self, proyecto_id: int) -> bool:
        """Eliminar un proyecto (soft delete, cambiar estado a cancelado)"""
        return self.cambiar_estado(proyecto_id, 'cancelado')
