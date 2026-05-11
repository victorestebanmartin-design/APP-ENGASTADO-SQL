"""
Repositorio de Puestos de Trabajo
"""
from typing import List, Dict, Optional
from .base_repository import BaseRepository


class PuestoRepository(BaseRepository):
    """Repositorio para puestos de trabajo"""
    
    def crear_puesto(self, id: str, nombre: str, descripcion: Optional[str] = None) -> bool:
        """
        Crear nuevo puesto de trabajo
        
        Args:
            id: ID único del puesto
            nombre: Nombre del puesto
            descripcion: Descripción opcional
        
        Returns:
            True si se creó correctamente
        """
        query = """
            INSERT INTO puestos (id, nombre, descripcion, activo)
            VALUES (:id, :nombre, :descripcion, 1)
        """
        params = {
            'id': id,
            'nombre': nombre,
            'descripcion': descripcion
        }
        try:
            self.execute_insert(query, params)
            return True
        except Exception:
            return False
    
    def obtener_puesto(self, id: str) -> Optional[Dict]:
        """Obtener un puesto por ID"""
        query = "SELECT * FROM puestos WHERE id = :id AND activo = 1"
        resultados = self.execute_select(query, {'id': id})
        return resultados[0] if resultados else None
    
    def obtener_todos_puestos(self, solo_activos: bool = True) -> List[Dict]:
        """
        Obtener todos los puestos
        
        Args:
            solo_activos: Si True, solo retorna puestos activos
        
        Returns:
            Lista de puestos
        """
        if solo_activos:
            query = "SELECT * FROM puestos WHERE activo = 1 ORDER BY nombre"
        else:
            query = "SELECT * FROM puestos ORDER BY nombre"
        return self.execute_select(query)
    
    def actualizar_puesto(self, id: str, nombre: Optional[str] = None, 
                         descripcion: Optional[str] = None) -> bool:
        """Actualizar información de un puesto"""
        updates = []
        params = {'id': id}
        
        if nombre is not None:
            updates.append("nombre = :nombre")
            params['nombre'] = nombre
        
        if descripcion is not None:
            updates.append("descripcion = :descripcion")
            params['descripcion'] = descripcion
        
        if not updates:
            return False
        
        updates.append("updated_at = datetime('now')")
        
        query = f"""
            UPDATE puestos 
            SET {', '.join(updates)}
            WHERE id = :id
        """
        rows = self.execute_update(query, params)
        return rows > 0
    
    def desactivar_puesto(self, id: str) -> bool:
        """Desactivar un puesto (soft delete)"""
        query = """
            UPDATE puestos 
            SET activo = 0,
                updated_at = datetime('now')
            WHERE id = :id
        """
        rows = self.execute_update(query, {'id': id})
        return rows > 0
    
    def eliminar_puesto(self, id: str) -> bool:
        """Eliminar permanentemente un puesto y sus máquinas"""
        query = "DELETE FROM puestos WHERE id = :id"
        rows = self.execute_delete(query, {'id': id})
        return rows > 0
    
    def existe_puesto(self, id: str) -> bool:
        """Verificar si existe un puesto"""
        resultado = self.obtener_puesto(id)
        return resultado is not None
