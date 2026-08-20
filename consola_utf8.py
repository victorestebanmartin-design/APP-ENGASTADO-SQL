"""La salida del servidor, en UTF-8 pase lo que pase.

En Windows, cuando run.bat manda la salida a un fichero de log
(`python run_sql.py >> servidor.log`), Python ya no habla con la consola y
usa para stdout la codificacion regional del sistema: cp1252. Ahi no cabe
ningun emoji, asi que un simple print("Generando etiquetas...") con un
icono delante lanza UnicodeEncodeError.

Perder una linea de log seria lo de menos. El problema es que
UnicodeEncodeError hereda de ValueError: cualquier `except ValueError` de la
ruta que estuviera imprimiendo se lo traga y lo convierte en un fallo de la
peticion. Asi es como "Regenerar etiquetas" acabo contestandole al navegador
"'charmap' codec can't encode characters in position 0-1", y como elegir un
terminal en engastado dejo de encontrar paquetes: el Excel se cargaba bien y
lo que reventaba era el print de despues.

forzar_utf8() se llama al arrancar (run_sql.py, wsgi.py) y deja stdout y
stderr en UTF-8 con errors='replace'. A partir de ahi ningun print -nuestro
o de una libreria- puede tumbar una peticion.

Sin dependencias a proposito: se importa antes incluso de comprobar que
flask y sqlalchemy estan instalados.
"""
import sys


def forzar_utf8():
    """Deja stdout y stderr en UTF-8 tolerante.

    Es idempotente y no hace nada en Linux (donde ya son UTF-8). Si el flujo
    no admite reconfiguracion (pytest lo sustituye por un buffer propio), se
    deja como esta: alli la codificacion no es la del sistema.
    """
    for flujo in (sys.stdout, sys.stderr):
        reconfigure = getattr(flujo, 'reconfigure', None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding='utf-8', errors='replace')
        except (ValueError, OSError, LookupError):
            # Flujo ya cerrado o sin soporte: no es motivo para no arrancar.
            pass
