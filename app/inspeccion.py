"""
Inspección periódica de las máquinas (como la ITV): hasta cuándo vale.

maquinas.inspeccion_valida_hasta guarda el mes (AAAA-MM) que marca la etiqueta
de la máquina, y la inspección vale ese mes entero, hasta su último día:
  - NULL               -> sin anotar: ni avisa ni bloquea (desplegar no para la planta)
  - quedan > 2 meses   -> nada
  - quedan <= 2 meses  -> aviso cada vez que se usa, sin parar a nadie
Los meses que quedan cuentan el actual: con la etiqueta en enero, en diciembre
quedan dos (diciembre y enero) y empieza el aviso.
  - ya ha pasado el mes -> no se puede usar hasta anotar el nuevo en la ficha

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

MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
         'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')

CONSEJO_CADUCADA = ('Elige otra máquina y avisa al responsable. Cuando pase la inspección, '
                    'hay que anotar el nuevo mes en Gestión de Puestos → Máquinas.')
CONSEJO_AVISO = 'Avisa al responsable para que programe la inspección.'


def _hoy():
    return datetime.now(_TZ_LOCAL).date() if _TZ_LOCAL else date.today()


def _ultimo_dia(anio, mes):
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def calcular(hasta, hoy=None):
    """Situación de un mes de validez: {estado, bloquea, hasta, dias, motivo, consejo}.

    'estado' es 'sin_anotar', 'vigente', 'aviso' o 'caducada'. 'dias' son los
    que quedan hasta el último día del mes.
    """
    hoy = hoy or _hoy()
    resultado = {'estado': 'sin_anotar', 'bloquea': False, 'hasta': hasta or None,
                 'dias': None, 'motivo': None, 'consejo': None}
    try:
        mes = datetime.strptime((hasta or '')[:7], '%Y-%m')
    except ValueError:
        return resultado

    fin = _ultimo_dia(mes.year, mes.month)
    dias = (fin - hoy).days
    resultado['dias'] = dias
    texto = f'{MESES[mes.month - 1]} de {mes.year}'
    if dias < 0:
        resultado.update(estado='caducada', bloquea=True,
                         motivo=f'La inspección de esta máquina valía hasta {texto} y ha caducado',
                         consejo=CONSEJO_CADUCADA)
    elif (mes.year - hoy.year) * 12 + mes.month - hoy.month + 1 <= MESES_AVISO:
        cuando = 'hoy' if dias == 0 else ('mañana' if dias == 1 else f'en {dias} días')
        resultado.update(estado='aviso',
                         motivo=f'La inspección de esta máquina vale hasta {texto}: caduca {cuando}',
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
