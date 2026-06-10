"""
Repositorio de Órdenes de Producción
"""
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy import text
from .base_repository import BaseRepository


class OrdenRepository(BaseRepository):
    """Repositorio para gestión de órdenes de producción"""
    
    def crear_orden(self, codigo_corte: str, numero: str, descripcion: str,
                    cantidad: int = 1, fecha_entrega: Optional[str] = None,
                    prioridad: str = 'normal', archivo_excel: Optional[str] = None,
                    proyecto: Optional[str] = None) -> str:
        """
        Crear nueva orden de producción
        
        Args:
            codigo_corte: Código de corte/barras
            numero: Número de orden
            descripcion: Descripción de la orden
            cantidad: Cantidad a producir
            fecha_entrega: Fecha de entrega (formato ISO)
            prioridad: Prioridad ('baja', 'normal', 'alta', 'urgente')
            archivo_excel: Nombre del archivo Excel asociado
            proyecto: Nombre del proyecto
        
        Returns:
            ID de la orden creada (UUID)
        """
        import uuid
        orden_id = str(uuid.uuid4())
        
        query = """
            INSERT INTO ordenes_produccion 
            (id, codigo_corte, numero, proyecto, descripcion, cantidad, 
             fecha_entrega, prioridad, estado, archivo_excel)
            VALUES 
            (:id, :codigo_corte, :numero, :proyecto, :descripcion, :cantidad,
             :fecha_entrega, :prioridad, 'pendiente', :archivo_excel)
        """
        params = {
            'id': orden_id,
            'codigo_corte': codigo_corte,
            'numero': numero,
            'proyecto': proyecto,
            'descripcion': descripcion,
            'cantidad': cantidad,
            'fecha_entrega': fecha_entrega,
            'prioridad': prioridad,
            'archivo_excel': archivo_excel
        }
        self.execute_insert(query, params)
        return orden_id
    
    def obtener_orden(self, orden_id: str) -> Optional[Dict]:
        """Obtener orden por ID"""
        query = "SELECT * FROM ordenes_produccion WHERE id = :id"
        resultados = self.execute_select(query, {'id': orden_id})
        return resultados[0] if resultados else None
    
    def obtener_ordenes_por_estado(self, estado: str) -> List[Dict]:
        """
        Obtener órdenes por estado
        
        Args:
            estado: Estado ('pendiente', 'en_bono', 'en_proceso', 'completado', 'cancelado')
        
        Returns:
            Lista de órdenes
        """
        query = """
            SELECT * FROM ordenes_produccion 
            WHERE estado = :estado
            ORDER BY fecha_creacion DESC
        """
        return self.execute_select(query, {'estado': estado})
    
    def obtener_ordenes_por_bono(self, bono_id: str) -> List[Dict]:
        """Obtener órdenes de un bono específico"""
        query = """
            SELECT * FROM ordenes_produccion 
            WHERE bono_id = :bono_id
            ORDER BY fecha_creacion
        """
        return self.execute_select(query, {'bono_id': bono_id})
    
    def obtener_ordenes_pendientes(self) -> List[Dict]:
        """Obtener todas las órdenes pendientes"""
        return self.obtener_ordenes_por_estado('pendiente')
    
    def asignar_a_bono(self, orden_id: str, bono_id: str) -> bool:
        """
        Asignar orden a un bono
        
        Args:
            orden_id: ID de la orden
            bono_id: ID del bono
        
        Returns:
            True si se asignó correctamente
        """
        query = """
            UPDATE ordenes_produccion 
            SET bono_id = :bono_id,
                estado = 'en_bono',
                fecha_inicio_bono = datetime('now')
            WHERE id = :orden_id
        """
        params = {'orden_id': orden_id, 'bono_id': bono_id}
        rows = self.execute_update(query, params)
        return rows > 0
    
    def asignar_a_bono_por_numero(self, numero_orden: str, bono_id: str, conn=None) -> bool:
        """
        Asignar orden a un bono usando el número de orden
        
        Args:
            numero_orden: Número de orden (ej: "60245848")
            bono_id: ID del bono
            conn: Conexión/transacción existente (opcional). Si se pasa, la
                  query se ejecuta sobre ella SIN commit ni conexión propia.
        
        Returns:
            True si se asignó correctamente
        """
        query = """
            UPDATE ordenes_produccion 
            SET bono_id = :bono_id,
                estado = 'en_bono',
                fecha_inicio_bono = datetime('now')
            WHERE numero = :numero_orden
        """
        params = {'numero_orden': numero_orden, 'bono_id': bono_id}
        if conn is not None:
            result = conn.execute(text(query), params)
            return result.rowcount > 0
        rows = self.execute_update(query, params)
        return rows > 0
    
    def asignar_a_carro(self, orden_id: str, carro_numero: int) -> bool:
        """Asignar orden a un carro"""
        query = """
            UPDATE ordenes_produccion 
            SET carro_numero = :carro_numero,
                estado = 'en_proceso'
            WHERE id = :orden_id
        """
        params = {'orden_id': orden_id, 'carro_numero': carro_numero}
        rows = self.execute_update(query, params)
        return rows > 0
    
    def completar_orden(self, orden_id: str) -> bool:
        """Marcar orden como completada"""
        query = """
            UPDATE ordenes_produccion 
            SET estado = 'completado',
                fecha_completado = datetime('now')
            WHERE id = :orden_id
        """
        rows = self.execute_update(query, {'orden_id': orden_id})
        return rows > 0
    
    def cambiar_estado(self, orden_id: str, estado: str, conn=None) -> bool:
        """Cambiar estado de una orden"""
        query = """
            UPDATE ordenes_produccion 
            SET estado = :estado
            WHERE id = :orden_id
        """
        params = {'orden_id': orden_id, 'estado': estado}
        if conn is not None:
            result = conn.execute(text(query), params)
            return result.rowcount > 0
        rows = self.execute_update(query, params)
        return rows > 0
    
    def obtener_estadisticas_por_estado(self) -> Dict[str, int]:
        """Obtener conteo de órdenes por estado"""
        query = """
            SELECT estado, COUNT(*) as total
            FROM ordenes_produccion
            GROUP BY estado
        """
        resultados = self.execute_select(query)
        return {r['estado']: r['total'] for r in resultados}
    
    def buscar_por_codigo_corte(self, codigo_corte: str) -> List[Dict]:
        """Buscar órdenes por código de corte"""
        query = """
            SELECT * FROM ordenes_produccion 
            WHERE codigo_corte = :codigo_corte
            ORDER BY fecha_creacion DESC
        """
        return self.execute_select(query, {'codigo_corte': codigo_corte})
    
    def obtener_todas_ordenes(self) -> List[Dict]:
        """Obtener todas las órdenes sin filtro"""
        query = """
            SELECT * FROM ordenes_produccion 
            ORDER BY fecha_creacion DESC
        """
        return self.execute_select(query)
    
    def eliminar_orden(self, orden_id: str) -> bool:
        """
        Eliminar una orden de producción
        
        Args:
            orden_id: ID de la orden
        
        Returns:
            True si se eliminó correctamente
        """
        query = "DELETE FROM ordenes_produccion WHERE id = :orden_id"
        rows = self.execute_update(query, {'orden_id': orden_id})
        return rows > 0
    
    def actualizar_orden(self, orden_id: str, codigo_corte: Optional[str] = None, 
                        numero: Optional[str] = None, descripcion: Optional[str] = None,
                        cantidad: Optional[int] = None, fecha_entrega: Optional[str] = None,
                        prioridad: Optional[str] = None, proyecto: Optional[str] = None) -> bool:
        """
        Actualizar campos de una orden
        
        Args:
            orden_id: ID de la orden
            codigo_corte: Nuevo código de corte (opcional)
            numero: Nuevo número de orden (opcional)
            descripcion: Nueva descripción (opcional)
            cantidad: Nueva cantidad (opcional)
            fecha_entrega: Nueva fecha de entrega (opcional)
            prioridad: Nueva prioridad (opcional)
            proyecto: Nuevo proyecto (opcional)
        
        Returns:
            True si se actualizó correctamente
        """
        # Construir query dinámicamente solo con campos que no son None
        campos = []
        params = {'orden_id': orden_id}
        
        if codigo_corte is not None:
            campos.append("codigo_corte = :codigo_corte")
            params['codigo_corte'] = codigo_corte
        if numero is not None:
            campos.append("numero = :numero")
            params['numero'] = numero
        if descripcion is not None:
            campos.append("descripcion = :descripcion")
            params['descripcion'] = descripcion
        if cantidad is not None:
            campos.append("cantidad = :cantidad")
            params['cantidad'] = cantidad
        if fecha_entrega is not None:
            campos.append("fecha_entrega = :fecha_entrega")
            params['fecha_entrega'] = fecha_entrega
        if prioridad is not None:
            campos.append("prioridad = :prioridad")
            params['prioridad'] = prioridad
        if proyecto is not None:
            campos.append("proyecto = :proyecto")
            params['proyecto'] = proyecto
        
        if not campos:
            return False  # Nada que actualizar
        
        query = f"""
            UPDATE ordenes_produccion 
            SET {', '.join(campos)}
            WHERE id = :orden_id
        """
        rows = self.execute_update(query, params)
        return rows > 0

