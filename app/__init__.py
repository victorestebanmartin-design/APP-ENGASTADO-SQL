"""
Inicialización de la aplicación Flask con SQLite
"""
from flask import Flask
from config import Config
import os


def create_app(config_class=Config):
    """
    Factory de aplicación Flask
    
    Args:
        config_class: Clase de configuración a usar
    
    Returns:
        Instancia de Flask configurada
    """
    # Rutas absolutas para templates y static (están en raíz del proyecto)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')
    
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir)
    app.config.from_object(config_class)
    
    # Inicializar base de datos
    from repositories import init_db
    db = init_db(app)
    
    # Guardar extensión DB en app
    app.extensions['db'] = db
    
    # Registrar blueprints/rutas
    from app import routes
    routes.init_routes(app)
    
    return app
