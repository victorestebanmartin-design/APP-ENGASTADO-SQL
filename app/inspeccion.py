"""
Inspección periódica de las máquinas (como la ITV): hasta cuándo vale.

La fecha está en maquinas.inspeccion_valida_hasta, y es válida todo ese día:
  - NULL             -> sin anotar: ni avisa ni bloquea (desplegar no para la planta)
  - faltan > 2 meses -> nada
  - faltan <= 2 meses -> aviso cada vez que se usa, sin parar a nadie
  - ya ha pasado     -> no se puede usar hasta anotar la nueva en la ficha

Como en los ensayos, el bloqueo lo pone el servidor (datos_trabajo_v3); la
pantalla (v3-maquina-rfid.js) es la cara amable.
"""
import calendar
from datetime import date, datetime

from sqlalchemy import text

try:
    from zoneinfo import ZoneInfo
    _TZ_LOCAL = ZoneInfo('Europe/Madrid')
except Exception:
    _TZ_LOCAL = None

MESES_AVISO = 2

CONSEJO_CADUCADA = ('Elige otra máquina y avisa al responsable. Cuando pase la inspección, '
                    'hay que anotar la nueva fecha en Gestión de Puestos → Máquinas.')
CONSEJO_AVISO = 'Avisa al responsable para que programe la inspección.'


def _hoy():
    return datetime.now(_TZ_LOCAL).date() if _TZ_LOCAL else date.today()


def _sumar_meses(dia, meses):
    """Mismo día N meses después; si ese mes es más corto, su último día."""
    total = dia.month - 1 + meses
    anio, mes = dia.year + total // 12, total % 12 + 1
    return date(anio, mes, min(dia.day, calendar.monthrange(anio, mes)[1]))


def calcular(hasta, hoy=None):
    """Situación de una fecha: {estado, bloquea, hasta, dias, motivo, consejo}.

    'estado' es 'sin_anotar', 'vigente', 'aviso' o 'caducada'.
    """
    hoy = hoy or _hoy()
    resultado = {'estado': 'sin_anotar', 'bloquea': False, 'hasta': hasta or None,
                 'dias': None, 'motivo': None, 'consejo': None}
    try:
        fecha = datetime.strptime(hasta or '', '%Y-%m-%d').date()
    except ValueError:
        return resultado

    dias = (fecha - hoy).days
    resultado['dias'] = dias
    texto = fecha.strftime('%d/%m/%Y')
    if dias < 0:
        resultado.update(estado='caducada', bloquea=True,
                         motivo=f'La inspección de esta máquina caducó el {texto}',
                         consejo=CONSEJO_CADUCADA)
    elif fecha <= _sumar_meses(hoy, MESES_AVISO):
        cuando = 'hoy' if dias == 0 else ('mañana' if dias == 1 else f'en {dias} días')
        resultado.update(estado='aviso',
                         motivo=f'La inspección de esta máquina caduca {cuando} ({texto})',
                         consejo=CONSEJO_AVISO)
    else:
        resultado['estado'] = 'vigente'
    return resultado


def estado_maquina(conn, maquina_id, hoy=None):
    """Situación de la inspección de una máquina activa, con la fecha de ahora."""
    hasta = conn.execute(text(
        "SELECT inspeccion_valida_hasta FROM maquinas WHERE id = :id AND activo = 1"
    ), {'id': maquina_id}).scalar()
    return calcular(hasta, hoy)
