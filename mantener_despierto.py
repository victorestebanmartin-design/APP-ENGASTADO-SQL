"""El PC servidor no se echa la siesta mientras la app esta sirviendo.

En fabrica la app corre en un PC Windows normal (`run.bat`), no en un
servidor de verdad. Y un PC normal viene configurado para suspenderse solo a
los pocos minutos sin teclado ni raton -- que es exactamente lo que hace el
PC servidor: nadie lo toca, solo sirve peticiones por red.

Cuando el equipo entra en suspension no se "ralentiza": se para. La CPU deja
de ejecutar, la tarjeta de red se apaga y el puerto 5001 deja de existir. El
sintoma en planta es que "la app se ha caido" aunque el proceso siga vivo:

  - los PCs de puesto dan "no se puede acceder a este sitio",
  - las placas ESP32 no reciben respuesta -> pitido de error tecnico,
  - y basta mover el raton del servidor para que todo vuelva solo, lo que
    despista todavia mas: nadie mira los logs de la app porque no hay nada
    que mirar (no hay error, hay un hueco).

Trafico de red NO despierta al equipo (eso seria Wake-on-LAN, que no esta
puesto y de todas formas no reanuda una sesion HTTP a medias).

La solucion es decirle a Windows que mientras este proceso viva el sistema
esta "en uso": SetThreadExecutionState con ES_CONTINUOUS | ES_SYSTEM_REQUIRED.
Se hace desde la app a proposito, en vez de solo cambiar el plan de energia a
mano en el PC:

  - No pide permisos de administrador (como el resto de la app).
  - Vale para cualquier PC servidor sin acordarse de configurarlo: si manana
    se reinstala Windows o el equipo se sustituye, sigue funcionando.
  - Sobrevive a que IT o una directiva de dominio reponga el plan de energia.
  - Solo mantiene despierto el equipo MIENTRAS el servidor esta en marcha; al
    pararlo, el PC vuelve a suspenderse como cualquier otro.

Lo que NO hace, y es deliberado: no pide ES_DISPLAY_REQUIRED. La pantalla
puede apagarse tranquilamente -- eso no para el servidor -- y tener un monitor
encendido toda la noche solo lo gasta.

Tampoco impide una suspension pedida a mano (menu Inicio -> Suspender, o
cerrar la tapa de un portatil): eso Windows lo hace igual, y es correcto que
lo haga. Aqui solo se bloquea el "dormirse por inactividad".

Sin dependencias a proposito, igual que consola_utf8: se llama al arrancar y
no puede ser el motivo de que la app no levante.
"""
import sys

# winbase.h. ES_CONTINUOUS = el estado se mantiene hasta que se cambie (no es
# un aviso puntual); ES_SYSTEM_REQUIRED = el sistema esta en uso, no lo
# suspendas por inactividad.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def mantener_despierto():
    """Pide a Windows no suspender el equipo mientras viva este hilo.

    Devuelve (aplicado, detalle) para que quien llame lo deje escrito en el
    log: si algun dia el servidor vuelve a "desaparecer" de madrugada, la
    linea del arranque dice si esta proteccion llego a aplicarse o no.

    IMPORTANTE: la peticion la guarda Windows POR HILO y se pierde cuando ese
    hilo termina. Hay que llamarla desde el hilo principal, que es el que se
    queda bloqueado sirviendo (`serve(...)` en run_sql.py) mientras la app
    esta viva. Desde un hilo que acabe enseguida no serviria de nada.

    Nunca lanza: en Linux (PythonAnywhere, tests) no hay nada que hacer, y en
    Windows un fallo de la llamada es un riesgo de siesta, no un motivo para
    dejar la planta sin app.
    """
    if not sys.platform.startswith('win'):
        return False, 'no es Windows: no hay suspension que evitar'

    try:
        import ctypes
        anterior = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
    except (AttributeError, OSError, ValueError) as e:
        return False, f'no se pudo pedir a Windows que no suspenda el equipo: {e}'

    # La API devuelve el estado anterior, o 0 si ha fallado.
    if not anterior:
        return False, ('Windows rechazo la peticion (SetThreadExecutionState '
                       'devolvio 0): configura el plan de energia a mano')

    return True, 'el equipo no se suspendera mientras el servidor este en marcha'
