"""
Repositorio de Códigos de Cortes
"""
from typing import List, Dict, Optional
from .base_repository import BaseRepository


class CodigoCorteRepository(BaseRepository):
    """Repositorio para mapeo de códigos de barras a archivos Excel"""
    
    def agregar_codigo(self, codigo: str, archivo_excel: str, proyecto_nombre: Optional[str] = None) -> bool:
        """
        Agregar o actualizar código de corte
        
        Args:
            codigo: Código de barras/corte
            archivo_excel: Nombre del archivo Excel
            proyecto_nombre: Nombre del proyecto (opcional)
        
        Returns:
            True si se agregó/actualizó correctamente
        """
        # SQLite: usar INSERT OR REPLACE
        query = """
            INSERT OR REPLACE INTO codigos_cortes (codigo, archivo_excel, proyecto_nombre, activo)
            VALUES (:codigo, :archivo_excel, :proyecto_nombre, 1)
        """
        params = {
            'codigo': codigo,
            'archivo_excel': archivo_excel,
            'proyecto_nombre': proyecto_nombre
        }
        try:
            self.execute_insert(query, params)
            return True
        except Exception:
            return False
    
    def obtener_codigo(self, codigo: str) -> Optional[Dict]:
        """Obtener información de un código de corte"""
        query = """
            SELECT * FROM codigos_cortes 
            WHERE codigo = :codigo AND activo = 1
        """
        resultados = self.execute_select(query, {'codigo': codigo})
        return resultados[0] if resultados else None
    
    def obtener_todos_codigos(self, solo_activos: bool = True) -> List[Dict]:
        """
        Obtener todos los códigos de cortes
        
        Args:
            solo_activos: Si True, solo retorna códigos activos
        
        Returns:
            Lista de códigos
        """
        if solo_activos:
            query = "SELECT * FROM codigos_cortes WHERE activo = 1 ORDER BY codigo"
        else:
            query = "SELECT * FROM codigos_cortes ORDER BY codigo"
        return self.execute_select(query)
    
    def buscar_por_archivo(self, archivo_excel: str) -> List[Dict]:
        """Obtener todos los códigos asociados a un archivo Excel"""
        query = """
            SELECT * FROM codigos_cortes 
            WHERE archivo_excel = :archivo_excel AND activo = 1
            ORDER BY codigo
        """
        return self.execute_select(query, {'archivo_excel': archivo_excel})
    
    def desactivar_codigo(self, codigo: str) -> bool:
        """Desactivar un código de corte (soft delete)"""
        query = """
            UPDATE codigos_cortes 
            SET activo = 0
            WHERE codigo = :codigo
        """
        rows = self.execute_update(query, {'codigo': codigo})
        return rows > 0
    
    def eliminar_codigo(self, codigo: str) -> bool:
        """Eliminar permanentemente un código de corte"""
        query = "DELETE FROM codigos_cortes WHERE codigo = :codigo"
        rows = self.execute_delete(query, {'codigo': codigo})
        return rows > 0
    
    def existe_codigo(self, codigo: str) -> bool:
        """Verificar si existe un código de corte"""
        resultado = self.obtener_codigo(codigo)
        return resultado is not None
