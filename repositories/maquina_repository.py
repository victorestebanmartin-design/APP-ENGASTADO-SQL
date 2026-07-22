"""
Repositorio de Máquinas de Producción
"""
from typing import List, Dict, Optional
from .base_repository import BaseRepository


class MaquinaRepository(BaseRepository):
    """Repositorio para máquinas de producción"""
    
    def crear_maquina(self, id: str, puesto_id: str, nombre: str,
                      modelo: Optional[str] = None, descripcion: Optional[str] = None,
                      tipo_operacion: str = 'MANUAL') -> bool:
        """
        Crear nueva máquina
        
        Args:
            id: ID único de la máquina
            puesto_id: ID del puesto al que pertenece
            nombre: Nombre de la máquina
            modelo: Modelo de la máquina (opcional)
            descripcion: Descripción (opcional)
            tipo_operacion: MANUAL, AUTOMATICA o SEMI-AUTOMATICA
        
        Returns:
            True si se creó correctamente
        """
        query = """
            INSERT INTO maquinas (id, puesto_id, nombre, modelo, descripcion, tipo_operacion, activo)
            VALUES (:id, :puesto_id, :nombre, :modelo, :descripcion, :tipo_operacion, 1)
        """
        params = {
            'id': id,
            'puesto_id': puesto_id,
            'nombre': nombre,
            'modelo': modelo,
            'descripcion': descripcion,
            'tipo_operacion': tipo_operacion or 'MANUAL'
        }
        try:
            self.execute_insert(query, params)
            return True
        except Exception:
            return False
    
    def obtener_maquina(self, id: str) -> Optional[Dict]:
        """Obtener una máquina por ID con información del puesto"""
        query = """
            SELECT m.*, p.nombre as puesto_nombre
            FROM maquinas m
            LEFT JOIN puestos p ON m.puesto_id = p.id
            WHERE m.id = :id AND m.activo = 1
        """
        resultados = self.execute_select(query, {'id': id})
        return resultados[0] if resultados else None
    
    def obtener_todas_maquinas(self, solo_activas: bool = True) -> List[Dict]:
        """
        Obtener todas las máquinas con información del puesto
        
        Args:
            solo_activas: Si True, solo retorna máquinas activas
        
        Returns:
            Lista de máquinas con información del puesto
        """
        if solo_activas:
            query = """
                SELECT m.*, p.nombre as puesto_nombre
                FROM maquinas m
                LEFT JOIN puestos p ON m.puesto_id = p.id
                WHERE m.activo = 1
                ORDER BY p.nombre, m.nombre
            """
        else:
            query = """
                SELECT m.*, p.nombre as puesto_nombre
                FROM maquinas m
                LEFT JOIN puestos p ON m.puesto_id = p.id
                ORDER BY p.nombre, m.nombre
            """
        return self.execute_select(query)
    
    def obtener_maquinas_por_puesto(self, puesto_id: str) -> List[Dict]:
        """Obtener todas las máquinas de un puesto específico"""
        query = """
            SELECT * FROM maquinas
            WHERE puesto_id = :puesto_id AND activo = 1
            ORDER BY nombre
        """
        return self.execute_select(query, {'puesto_id': puesto_id})
    
    def actualizar_maquina(self, id: str, nombre: Optional[str] = None,
                          modelo: Optional[str] = None, descripcion: Optional[str] = None,
                          puesto_id: Optional[str] = None,
                          tipo_operacion: Optional[str] = None,
                          pdf_instrucciones: Optional[str] = None,
                          limpiar_pdf: bool = False) -> bool:
        """Actualizar información de una máquina"""
        updates = []
        params = {'id': id}
        
        if puesto_id is not None:
            updates.append("puesto_id = :puesto_id")
            params['puesto_id'] = puesto_id
        
        if nombre is not None:
            updates.append("nombre = :nombre")
            params['nombre'] = nombre
        
        if modelo is not None:
            updates.append("modelo = :modelo")
            params['modelo'] = modelo
        
        if descripcion is not None:
            updates.append("descripcion = :descripcion")
            params['descripcion'] = descripcion

        if tipo_operacion is not None:
            updates.append("tipo_operacion = :tipo_operacion")
            params['tipo_operacion'] = tipo_operacion

        if pdf_instrucciones is not None:
            updates.append("pdf_instrucciones = :pdf_instrucciones")
            params['pdf_instrucciones'] = pdf_instrucciones
        elif limpiar_pdf:
            updates.append("pdf_instrucciones = NULL")
        
        if not updates:
            return False
        
        updates.append("updated_at = datetime('now')")
        
        query = f"""
            UPDATE maquinas 
            SET {', '.join(updates)}
            WHERE id = :id
        """
        rows = self.execute_update(query, params)
        return rows > 0
    
    def desactivar_maquina(self, id: str) -> bool:
        """Desactivar una máquina (soft delete)"""
        query = """
            UPDATE maquinas 
            SET activo = 0,
                updated_at = datetime('now')
            WHERE id = :id
        """
        rows = self.execute_update(query, {'id': id})
        return rows > 0
    
    def eliminar_maquina(self, id: str) -> bool:
        """Eliminar permanentemente una máquina"""
        query = "DELETE FROM maquinas WHERE id = :id"
        rows = self.execute_delete(query, {'id': id})
        return rows > 0
    
    def asignar_terminal(self, maquina_id: str, terminal_codigo: str) -> bool:
        """
        Asignar un terminal a una máquina
        
        Args:
            maquina_id: ID de la máquina
            terminal_codigo: Código del terminal
        
        Returns:
            True si se asignó correctamente
        """
        query = """
            INSERT INTO maquinas_terminales (maquina_id, terminal_codigo, activo)
            VALUES (:maquina_id, :terminal_codigo, 1)
        """
        params = {
            'maquina_id': maquina_id,
            'terminal_codigo': terminal_codigo
        }
        try:
            self.execute_insert(query, params)
            return True
        except Exception:
            # Puede fallar si ya existe
            return False
    
    def desasignar_terminal(self, terminal_codigo: str) -> bool:
        """Desasignar un terminal de su máquina actual"""
        query = """
            DELETE FROM maquinas_terminales
            WHERE terminal_codigo = :terminal_codigo
        """
        rows = self.execute_delete(query, {'terminal_codigo': terminal_codigo})
        return rows > 0
    
    def obtener_terminales_asignados(self, maquina_id: str) -> List[str]:
        """
        Obtener lista de terminales asignados a una máquina
        
        Args:
            maquina_id: ID de la máquina
        
        Returns:
            Lista de códigos de terminales
        """
        query = """
            SELECT terminal_codigo
            FROM maquinas_terminales
            WHERE maquina_id = :maquina_id AND activo = 1
            ORDER BY terminal_codigo
        """
        resultados = self.execute_select(query, {'maquina_id': maquina_id})
        return [r['terminal_codigo'] for r in resultados]
    
    def verificar_terminal_asignado(self, terminal_codigo: str) -> Optional[Dict]:
        """
        Verificar si un terminal está asignado y a qué máquina
        
        Args:
            terminal_codigo: Código del terminal
        
        Returns:
            Dict con información de asignación, o None si no está asignado
        """
        query = """
            SELECT mt.*, m.nombre as maquina_nombre, m.puesto_id, p.nombre as puesto_nombre
            FROM maquinas_terminales mt
            JOIN maquinas m ON mt.maquina_id = m.id
            LEFT JOIN puestos p ON m.puesto_id = p.id
            WHERE mt.terminal_codigo = :terminal_codigo AND mt.activo = 1
        """
        resultados = self.execute_select(query, {'terminal_codigo': terminal_codigo})
        return resultados[0] if resultados else None
