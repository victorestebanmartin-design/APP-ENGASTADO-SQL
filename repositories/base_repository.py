"""
Base Repository - Clase abstracta para operaciones comunes
"""
from sqlalchemy import text
from typing import Optional, List, Dict, Any


class BaseRepository:
    """Repositorio base con operaciones CRUD comunes.

    Los errores de SQLAlchemy se propagan con su tipo original
    (p.ej. IntegrityError) para que las rutas puedan distinguirlos;
    aquí no se envuelven ni se transforman.
    """

    def __init__(self, db):
        """
        Args:
            db: Instancia de base de datos de repositories/__init__.py
        """
        self.db = db

    def execute_query(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Ejecutar query SQL con parámetros

        Args:
            query: Query SQL con placeholders :param
            params: Diccionario de parámetros

        Returns:
            ResultProxy de SQLAlchemy
        """
        with self.db.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            conn.commit()
            return result

    def execute_select(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Ejecutar SELECT y retornar resultados como lista de diccionarios

        Args:
            query: Query SELECT
            params: Parámetros

        Returns:
            Lista de diccionarios con resultados
        """
        with self.db.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]

    def execute_insert(self, query: str, params: Dict) -> int:
        """
        Ejecutar INSERT y retornar ID del registro insertado

        Args:
            query: Query INSERT
            params: Parámetros

        Returns:
            ID del último registro insertado
        """
        with self.db.engine.connect() as conn:
            result = conn.execute(text(query), params)
            conn.commit()
            return result.lastrowid

    def execute_update(self, query: str, params: Dict) -> int:
        """
        Ejecutar UPDATE y retornar número de filas afectadas

        Args:
            query: Query UPDATE
            params: Parámetros

        Returns:
            Número de filas actualizadas
        """
        with self.db.engine.connect() as conn:
            result = conn.execute(text(query), params)
            conn.commit()
            return result.rowcount

    def execute_delete(self, query: str, params: Dict) -> int:
        """
        Ejecutar DELETE y retornar número de filas eliminadas

        Args:
            query: Query DELETE
            params: Parámetros

        Returns:
            Número de filas eliminadas
        """
        with self.db.engine.connect() as conn:
            result = conn.execute(text(query), params)
            conn.commit()
            return result.rowcount
