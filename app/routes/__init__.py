"""
Rutas de la aplicación, organizadas en módulos por dominio.

Todos los módulos registran sus rutas sobre el blueprint compartido 'main'
(definido en app/routes/base.py), así que las URLs y los url_for('main.x')
de las plantillas no cambian respecto al antiguo routes.py monolítico.
"""
from app.routes.base import bp, set_db


def init_routes(app):
    """Inicializar rutas con la instancia de DB"""
    set_db(app.extensions['db'])

    # Importar los módulos registra sus rutas en el blueprint compartido
    from app.routes import (  # noqa: F401
        paginas,
        manguitos,
        proyectos,
        ordenes,
        bonos,
        carros,
        archivos,
        puestos,
        cable_colores,
        operarios,
        reports,
        trabajo_v3,
        sistema,
        etiquetas,
        progreso,
    )

    app.register_blueprint(bp)
