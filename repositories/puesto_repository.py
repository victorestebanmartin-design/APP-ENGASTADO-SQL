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
    
    def obtener_puesto_por_boton(self, boton: int) -> Optional[Dict]:
        """Puesto activo asociado a un botón de la pantalla del carro (1-7)."""
        query = "SELECT * FROM puestos WHERE boton = :b AND activo = 1"
        resultados = self.execute_select(query, {'b': boton})
        return resultados[0] if resultados else None

    def obtener_puesto_por_tag(self, tag_uid: str) -> Optional[Dict]:
        """Puesto activo asociado a una tarjeta NFC (UID en hex)."""
        query = "SELECT * FROM puestos WHERE tag_uid = :t AND activo = 1"
        resultados = self.execute_select(query, {'t': tag_uid})
        return resultados[0] if resultados else None

    def actualizar_puesto(self, id: str, nombre: Optional[str] = None,
                         descripcion: Optional[str] = None,
                         boton: Optional[int] = None,
                         limpiar_boton: bool = False,
                         tag_uid: Optional[str] = None,
                         limpiar_tag: bool = False) -> bool:
        """Actualizar información de un puesto.

        boton:   número de pulsador (1-7) con el que este puesto se identifica
                 en la pantalla del carro.
        tag_uid: UID de su tarjeta NFC, la otra forma de identificarse.

        En ambos casos, para quitar el valor se usa el flag limpiar_*
        (pasar None significa 'no tocar ese campo').
        """
        updates = []
        params = {'id': id}

        if nombre is not None:
            updates.append("nombre = :nombre")
            params['nombre'] = nombre

        if descripcion is not None:
            updates.append("descripcion = :descripcion")
            params['descripcion'] = descripcion

        if limpiar_boton:
            updates.append("boton = NULL")
        elif boton is not None:
            updates.append("boton = :boton")
            params['boton'] = boton

        if limpiar_tag:
            updates.append("tag_uid = NULL")
        elif tag_uid is not None:
            updates.append("tag_uid = :tag_uid")
            params['tag_uid'] = tag_uid

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
