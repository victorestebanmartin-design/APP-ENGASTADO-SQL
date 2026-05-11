"""
Base Repository - Clase abstracta para operaciones comunes
"""
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, List, Dict, Any


class BaseRepository:
    """Repositorio base con operaciones CRUD comunes"""
    
    def __init__(self, db):
        """
        Args:
            db: Instancia de base de datos de repositories/__init__.py
        """
        self.db = db
        self.session = db.get_session()
    
    def execute_query(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Ejecutar query SQL con parámetros
        
        Args:
            query: Query SQL con placeholders :param
            params: Diccionario de parámetros
        
        Returns:
            ResultProxy de SQLAlchemy
        """
        try:
            with self.db.engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                conn.commit()
                return result
        except SQLAlchemyError as e:
            self.session.rollback()
            raise Exception(f"Error ejecutando query: {e}")
    
    def execute_select(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Ejecutar SELECT y retornar resultados como lista de diccionarios
        
        Args:
            query: Query SELECT
            params: Parámetros
        
        Returns:
            Lista de diccionarios con resultados
        """
        try:
            with self.db.engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
        except SQLAlchemyError as e:
            raise Exception(f"Error en SELECT: {e}")
    
    def execute_insert(self, query: str, params: Dict) -> int:
        """
        Ejecutar INSERT y retornar ID del registro insertado
        
        Args:
            query: Query INSERT
            params: Parámetros
        
        Returns:
            ID del último registro insertado
        """
        try:
            with self.db.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                return result.lastrowid
        except SQLAlchemyError as e:
            raise Exception(f"Error en INSERT: {e}")
    
    def execute_update(self, query: str, params: Dict) -> int:
        """
        Ejecutar UPDATE y retornar número de filas afectadas
        
        Args:
            query: Query UPDATE
            params: Parámetros
        
        Returns:
            Número de filas actualizadas
        """
        try:
            with self.db.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                return result.rowcount
        except SQLAlchemyError as e:
            raise Exception(f"Error en UPDATE: {e}")
    
    def execute_delete(self, query: str, params: Dict) -> int:
        """
        Ejecutar DELETE y retornar número de filas eliminadas
        
        Args:
            query: Query DELETE
            params: Parámetros
        
        Returns:
            Número de filas eliminadas
        """
        try:
            with self.db.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                return result.rowcount
        except SQLAlchemyError as e:
            raise Exception(f"Error en DELETE: {e}")
    
    def commit(self):
        """Confirmar transacción"""
        self.session.commit()
    
    def rollback(self):
        """Revertir transacción"""
        self.session.rollback()
    
    def close(self):
        """Cerrar sesión"""
        self.session.close()
