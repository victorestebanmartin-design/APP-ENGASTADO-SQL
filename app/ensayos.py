"""
Ensayos de tracción: cuándo toca ensayar y qué queda registrado.

Lo que se ensaya es la MATRIZ (aplicador) con la que se va a engastar, no el
terminal: una matriz puede engastar varios terminales y un ensayo OK la deja
cubierta para todos ellos durante el periodo. Un terminal sin matriz asignada
se ensaya a nivel de máquina (todas sus "sin matriz" comparten ensayo).

Cada máquina decide su frecuencia (maquinas.ensayo_frecuencia):
  - NULL      -> no pide ensayo (valor por defecto: desplegar no cambia nada)
  - 'diaria'  -> primer uso de cada día
  - 'mensual' -> primer uso de cada mes natural

Además:
  - Regular la máquina invalida el ensayo vigente: hay que repetirlo.
  - Un NOK bloquea hasta que un supervisor decide «repetir» o «continuar».
  - «Continuar» vale solo hasta el final de ese día, también en las mensuales.

Todo va a ensayos_traccion, que es un registro de auditoría: solo se añaden
filas (los triggers de la migración impiden UPDATE y DELETE). El estado de
una matriz se calcula recorriendo sus eventos del periodo en orden.
"""
import uuid
from datetime import datetime

from sqlalchemy import text

try:
    from zoneinfo import ZoneInfo
    _TZ_LOCAL = ZoneInfo('Europe/Madrid')
except Exception:
    _TZ_LOCAL = None

FRECUENCIAS = ('diaria', 'mensual')
DECISIONES = ('repetir', 'continuar')

# Permiso (Admin -> Operarios) de quien puede resolver un NOK. Ver MODULOS_APP.
PERMISO_SUPERVISOR = 'ensayos_supervisor'


class EnsayoError(Exception):
    """Rechazo con motivo (qué pasa) y consejo (qué hacer), como los de tarjeta."""

    def __init__(self, motivo, consejo='', status=409):
        super().__init__(motivo)
        self.motivo = motivo
        self.consejo = consejo
        self.status = status

    def como_json(self):
        return {'success': False, 'message': self.motivo,
                'motivo': self.motivo, 'consejo': self.consejo}


def ahora_local():
    """Hora de la planta. El servidor puede estar en UTC (PythonAnywhere): el
    «día» del ensayo diario tiene que ser el de Madrid, no el de Greenwich."""
    if _TZ_LOCAL is not None:
        return datetime.now(_TZ_LOCAL).replace(tzinfo=None, microsecond=0)
    return datetime.now().replace(microsecond=0)


def _fecha_txt(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def inicio_periodo(frecuencia, ahora):
    if frecuencia == 'mensual':
        return ahora.strftime('%Y-%m-01 00:00:00')
    return ahora.strftime('%Y-%m-%d 00:00:00')


def normalizar_seccion(valor):
    """'1,5', '1.50', 1.5 -> '1.5'. Lo que no sea un número se deja tal cual."""
    if valor is None:
        return ''
    crudo = str(valor).strip().replace(',', '.')
    if crudo.lower().endswith('mm2') or crudo.lower().endswith('mm²'):
        crudo = crudo[:-3].strip()
    try:
        numero = float(crudo)
    except ValueError:
        return crudo
    if numero != numero or numero <= 0:   # NaN o absurdo
        return ''
    return f'{numero:g}'


# ==================== CONTEXTO: máquina y matriz ====================

def contexto(conn, maquina_id, terminal):
    """(maquina, matriz) para ese terminal en esa máquina. matriz puede ser
    None (terminal sin matriz). maquina None si no existe o está inactiva."""
    maquina = conn.execute(text(
        "SELECT id, nombre, puesto_id, tipo_operacion, lleva_regulacion, ensayo_frecuencia "
        "FROM maquinas WHERE id = :id AND activo = 1"
    ), {'id': maquina_id}).mappings().first()
    if not maquina:
        return None, None
    matriz = None
    if terminal:
        matriz = conn.execute(text("""
            SELECT mz.id, mz.nombre, mz.codigo
            FROM maquinas_terminales mt
            JOIN matrices mz ON mz.id = mt.matriz_id AND mz.activo = 1
            WHERE mt.maquina_id = :m AND UPPER(mt.terminal_codigo) = UPPER(:t) AND mt.activo = 1
        """), {'m': maquina_id, 't': terminal}).mappings().first()
    return dict(maquina), (dict(matriz) if matriz else None)


def _ambito_texto(maquina, matriz):
    if matriz:
        return f"matriz {matriz['nombre']} de {maquina['nombre']}"
    return f"máquina {maquina['nombre']}"


# ==================== ESTADO ====================

def estado_clave(conn, maquina, matriz_id, ahora=None):
    """Recorre los eventos del periodo de esa máquina+matriz y dice en qué
    punto está. Devuelve dict con estado, motivo_ensayo, vigente y nok."""
    ahora = ahora or ahora_local()
    frecuencia = maquina.get('ensayo_frecuencia')
    if frecuencia not in FRECUENCIAS:
        return {'estado': 'sin_ensayo', 'motivo_ensayo': None, 'vigente': None, 'nok': None}

    filas = conn.execute(text("""
        SELECT * FROM ensayos_traccion
        WHERE maquina_id = :m AND fecha >= :inicio
          AND (tipo = 'regulacion' OR matriz_id IS :mz)
        ORDER BY fecha, rowid
    """), {'m': maquina['id'], 'inicio': inicio_periodo(frecuencia, ahora),
          'mz': matriz_id}).mappings().all()

    estado, motivo = 'falta', frecuencia   # 'diaria' | 'mensual'
    vigente, nok = None, None
    for ev in filas:
        if ev['tipo'] == 'ensayo':
            if ev['resultado'] == 'OK':
                estado, vigente, nok = 'ok', dict(ev), None
            else:
                estado, vigente, nok = 'nok_pendiente', None, dict(ev)
        elif ev['tipo'] == 'decision':
            if nok and ev['ref_id'] == nok['id']:
                if ev['decision'] == 'repetir':
                    estado, motivo, nok = 'falta', 'repeticion', None
                else:
                    estado, vigente, nok = 'continuar', dict(ev), None
        elif ev['tipo'] == 'regulacion':
            # Una regulación no levanta un NOK: eso solo lo hace el supervisor.
            if estado in ('ok', 'continuar'):
                estado, vigente = 'falta', None
            if estado == 'falta':
                motivo = 'regulacion'

    if estado == 'continuar' and vigente['fecha'][:10] != ahora.strftime('%Y-%m-%d'):
        estado, vigente = 'falta', None
    return {'estado': estado, 'motivo_ensayo': motivo, 'vigente': vigente, 'nok': nok}


_MOTIVOS_TEXTO = {
    'diaria': 'primer engaste del día',
    'mensual': 'primer engaste del mes',
    'regulacion': 'la máquina se ha regulado',
    'repeticion': 'el supervisor ha pedido repetir el ensayo',
}


def estado(conn, maquina_id, terminal, ahora=None):
    """Estado del ensayo para engastar ese terminal en esa máquina.

    bloquea=True significa que no se puede empezar a engastar: o falta el
    ensayo, o hay un NOK esperando al supervisor.
    """
    maquina, matriz = contexto(conn, maquina_id, terminal)
    if not maquina:
        return {'requerido': False, 'bloquea': False, 'estado': 'sin_ensayo',
                'motivo': 'Máquina no encontrada', 'consejo': ''}
    res = estado_clave(conn, maquina, matriz['id'] if matriz else None, ahora)
    ambito = _ambito_texto(maquina, matriz)
    salida = {
        'requerido': res['estado'] != 'sin_ensayo',
        'bloquea': res['estado'] in ('falta', 'nok_pendiente'),
        'estado': res['estado'],
        'frecuencia': maquina.get('ensayo_frecuencia'),
        'maquina': {'id': maquina['id'], 'nombre': maquina['nombre'],
                    'lleva_regulacion': bool(maquina.get('lleva_regulacion'))},
        'matriz': matriz,
        'ambito': ambito,
        'motivo_ensayo': res['motivo_ensayo'],
        'vigente': res['vigente'],
        'nok': res['nok'],
        'motivo': '',
        'consejo': '',
    }
    if res['estado'] == 'falta':
        salida['motivo'] = (f"Falta el ensayo de tracción de la {ambito} "
                            f"({_MOTIVOS_TEXTO.get(res['motivo_ensayo'], res['motivo_ensayo'])})")
        salida['consejo'] = 'Haz el ensayo de una probeta y anota la fuerza de rotura'
    elif res['estado'] == 'nok_pendiente':
        salida['motivo'] = (f"El último ensayo de la {ambito} no llegó al mínimo "
                            f"({res['nok']['fuerza_n']:g} N de {res['nok']['fuerza_min_n']:g} N)")
        salida['consejo'] = 'Avisa al supervisor: tiene que pasar su tarjeta y decidir'
    return salida


# ==================== ESPECIFICACIONES ====================

def especificacion(conn, terminal, seccion):
    """Fuerza mínima para ese terminal y sección: primero la propia del
    terminal, si no la genérica de la sección. None si no hay ninguna."""
    seccion = normalizar_seccion(seccion)
    if not seccion:
        return None
    fila = conn.execute(text("""
        SELECT * FROM ensayos_especificaciones
        WHERE seccion = :s AND (UPPER(terminal_codigo) = UPPER(:t) OR terminal_codigo = '')
        ORDER BY CASE WHEN terminal_codigo = '' THEN 1 ELSE 0 END
        LIMIT 1
    """), {'s': seccion, 't': terminal or ''}).mappings().first()
    return dict(fila) if fila else None


# ==================== REGISTRO ====================

def _insertar(conn, **campos):
    campos.setdefault('id', uuid.uuid4().hex)
    campos.setdefault('fecha', _fecha_txt(ahora_local()))
    columnas = ', '.join(campos)
    valores = ', '.join(f':{c}' for c in campos)
    conn.execute(text(f"INSERT INTO ensayos_traccion ({columnas}) VALUES ({valores})"), campos)
    return campos


def registrar_ensayo(conn, maquina_id, terminal, seccion, fuerza_n, operario,
                     bono=None, orden_id=None, origen='manual', comentario=None):
    """Registra un ensayo y devuelve la fila. El resultado lo decide el
    servidor con la fuerza mínima de la tabla, nunca la pantalla."""
    maquina, matriz = contexto(conn, maquina_id, terminal)
    if not maquina:
        raise EnsayoError('Máquina no encontrada', '', 404)
    if maquina.get('ensayo_frecuencia') not in FRECUENCIAS:
        raise EnsayoError(f"La máquina {maquina['nombre']} no tiene ensayo de tracción configurado",
                          'Configúralo en Ensayos tracción → Máquinas y matrices', 409)
    try:
        fuerza = float(str(fuerza_n).replace(',', '.'))
    except (TypeError, ValueError):
        raise EnsayoError('La fuerza tiene que ser un número', 'Escribe los newtons, p. ej. 162', 400)
    if not (0 < fuerza < 100000):
        raise EnsayoError('La fuerza no es válida', 'Escribe los newtons que marca el dinamómetro', 400)

    seccion = normalizar_seccion(seccion)
    spec = especificacion(conn, terminal, seccion)
    if not spec:
        raise EnsayoError(
            f'No hay fuerza mínima definida para el terminal {terminal} a {seccion or "?"} mm²',
            'Pide a calidad que la añada en Ensayos tracción → Fuerzas mínimas', 409)

    res = estado_clave(conn, maquina, matriz['id'] if matriz else None)
    if res['estado'] == 'nok_pendiente':
        raise EnsayoError('Hay un ensayo NOK pendiente de decisión del supervisor',
                          'Avisa al supervisor: tiene que pasar su tarjeta y decidir', 409)

    return _insertar(
        conn, tipo='ensayo',
        maquina_id=maquina['id'], maquina_nombre=maquina['nombre'],
        matriz_id=matriz['id'] if matriz else None,
        matriz_nombre=matriz['nombre'] if matriz else None,
        puesto_id=maquina.get('puesto_id'),
        terminal_codigo=terminal, seccion=seccion,
        operario=operario or '(sin identificar)',
        bono=bono or None, orden_id=orden_id or None,
        motivo=res['motivo_ensayo'] if res['estado'] == 'falta' else 'voluntario',
        fuerza_n=fuerza, fuerza_min_n=spec['fuerza_min_n'], norma=spec.get('norma'),
        resultado='OK' if fuerza >= spec['fuerza_min_n'] else 'NOK',
        origen=origen if origen in ('manual', 'dinamometro') else 'manual',
        comentario=(comentario or None),
    )


def registrar_regulacion(conn, maquina_id, operario, comentario=None):
    maquina, _ = contexto(conn, maquina_id, None)
    if not maquina:
        raise EnsayoError('Máquina no encontrada', '', 404)
    return _insertar(
        conn, tipo='regulacion',
        maquina_id=maquina['id'], maquina_nombre=maquina['nombre'],
        puesto_id=maquina.get('puesto_id'),
        operario=operario or '(sin identificar)', motivo='regulacion',
        comentario=(comentario or None),
    )


def obtener_evento(conn, evento_id):
    fila = conn.execute(text("SELECT * FROM ensayos_traccion WHERE id = :id"),
                        {'id': evento_id}).mappings().first()
    return dict(fila) if fila else None


def nok_pendiente(conn, nok_id):
    """La fila NOK si sigue siendo el NOK pendiente de su matriz; si no, error."""
    nok = obtener_evento(conn, nok_id)
    if not nok or nok['tipo'] != 'ensayo' or nok['resultado'] != 'NOK':
        raise EnsayoError('Ese ensayo no es un NOK', '', 404)
    maquina, _ = contexto(conn, nok['maquina_id'], None)
    if not maquina:
        raise EnsayoError('Máquina no encontrada', '', 404)
    res = estado_clave(conn, maquina, nok['matriz_id'])
    if res['estado'] != 'nok_pendiente' or res['nok']['id'] != nok['id']:
        raise EnsayoError('Ese NOK ya está resuelto', 'Vuelve a elegir el terminal', 409)
    return nok


def registrar_decision(conn, nok_id, decision, supervisor, via, comentario=None, operario=None):
    if decision not in DECISIONES:
        raise EnsayoError('Decisión no válida', 'Elige «Repetir ensayo» o «Continuar»', 400)
    comentario = (comentario or '').strip()
    if decision == 'continuar' and len(comentario) < 3:
        raise EnsayoError('Para continuar con un NOK hace falta un motivo',
                          'Escribe por qué se puede seguir engastando', 400)
    nok = nok_pendiente(conn, nok_id)
    return _insertar(
        conn, tipo='decision',
        maquina_id=nok['maquina_id'], maquina_nombre=nok['maquina_nombre'],
        matriz_id=nok['matriz_id'], matriz_nombre=nok['matriz_nombre'],
        puesto_id=nok['puesto_id'],
        terminal_codigo=nok['terminal_codigo'], seccion=nok['seccion'],
        operario=operario or nok['operario'],
        bono=nok['bono'], orden_id=nok['orden_id'],
        ref_id=nok['id'], decision=decision,
        supervisor=supervisor, supervisor_via=via,
        comentario=comentario or None,
    )
