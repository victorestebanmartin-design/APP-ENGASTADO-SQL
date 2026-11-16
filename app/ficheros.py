"""Sustituir un fichero que alguien puede estar leyendo."""
import os
import time


def reemplazar_con_reintento(tmp: str, path: str, intentos: int = 20, espera: float = 0.05) -> None:
    """os.replace que aguanta a un lector en Windows.

    Allí no se puede sustituir un fichero que otro hilo o proceso tiene abierto
    (un GET del progreso, la lectura del Excel, la copia automática, el
    antivirus): falla con PermissionError. El lector lo suelta en milisegundos,
    así que basta con volver a intentarlo; sin esto se perdía el carro que se
    estaba guardando, o al jefe le salía un error al aprobar o revertir una
    propuesta. Cualquier otro error no se reintenta: sale a la primera.
    """
    for intento in range(intentos):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if intento == intentos - 1:
                raise
            time.sleep(espera)
