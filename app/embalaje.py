"""
Embalaje: en qué cajas va cada orden terminada y qué paquetes lleva cada caja.

La primera vez que se embala un código de corte, el operario dice cuántas
cajas y reparte los paquetes; ese reparto se guarda para el código de corte y
la siguiente orden de la misma referencia sale ya guiada. Los carteles de las
cajas se imprimen antes de empezar, para dejar cada caja con el suyo.

Reglas (las decidió planta, no las cambies sin preguntar):
  - Un «paquete» es una etiqueta de primer nivel del Excel: cada cable +
    elemento suelto, y cada serie entera como un solo bulto.
  - Solo se embalan órdenes con todas sus máquinas acabadas. Si alguna dejó
    paquetes pendientes, hace falta un supervisor (permiso ensayos_supervisor).
  - Rehacer un reparto ya guardado pide supervisor. Completarlo con paquetes
    nuevos (el Excel ha cambiado) no: eso no cambia lo que ya estaba decidido.
  - Si la cantidad de la orden no es la del reparto guardado, se avisa y se
    deja elegir: usarlo igual, o rehacerlo (con supervisor).
"""
import uuid

from sqlalchemy import text

PERMISO_SUPERVISOR = 'ensayos_supervisor'
MAX_CAJAS = 50


class EmbalajeError(Exception):
    """Rechazo con motivo (qué pasa) y consejo (qué hacer)."""

    def __init__(self, motivo, consejo='', status=409, **extra):
        super().__init__(motivo)
        self.motivo = motivo
        self.consejo = consejo
        self.status = status
        self.extra = extra

    def como_json(self):
        return {'success': False, 'message': self.motivo, 'motivo': self.motivo,
                'consejo': self.consejo, **self.extra}


# ==================== paquetes ====================

def clave_paquete(cod_cable, elemento):
    """Clave estable de un paquete entre órdenes del mismo código de corte.
    Una serie sale como GRUPO_SERIE|<serie>, igual que su etiqueta padre."""
    return f"{(cod_cable or '').strip()}|{(elemento or '').strip()}"


def _texto_etiqueta(numero, sub):
    return f"{numero}.{int(sub):02d}" if sub else str(numero)


def paquetes_de_archivo(conn, archivo):
    """Paquetes a embalar de un Excel, en el orden de sus etiquetas.

    Lee las etiquetas guardadas (etiquetas_elementos): las de primer nivel son
    los bultos; los hijos de una serie viajan dentro de ella.
    """
    filas = conn.execute(text("""
        SELECT numero_etiqueta, sub_numero, es_grupo_padre, grupo_serie,
               cod_cable, elemento, descripcion, seccion, num_cables
        FROM etiquetas_elementos
        WHERE archivo_excel = :a
        ORDER BY numero_etiqueta, sub_numero
    """), {'a': archivo}).mappings().all()

    paquetes, por_numero = [], {}
    for f in filas:
        if f['sub_numero']:
            padre = por_numero.get(f['numero_etiqueta'])
            if padre is not None:
                padre['contenido'].append({
                    'etiqueta': _texto_etiqueta(f['numero_etiqueta'], f['sub_numero']),
                    'cod_cable': f['cod_cable'], 'elemento': f['elemento']})
            continue
        es_serie = bool(f['es_grupo_padre'])
        paquete = {
            'clave': clave_paquete(f['cod_cable'], f['elemento']),
            'etiqueta': _texto_etiqueta(f['numero_etiqueta'], 0),
            'cod_cable': '' if f['cod_cable'] == 'GRUPO_SERIE' else (f['cod_cable'] or ''),
            'elemento': f['elemento'] or '',
            'descripcion': f['descripcion'] or '',
            'seccion': f['seccion'] or '',
            'num_cables': f['num_cables'] or 0,
            'es_serie': es_serie,
            'serie': f['grupo_serie'] or '',
            'contenido': [],
        }
        por_numero[f['numero_etiqueta']] = paquete
        paquetes.append(paquete)
    return paquetes


# ==================== estado de una orden ====================

def estado_orden_desde_progreso(terminales, progreso, carro_key, orden_cerrada, descartado=None):
    """¿Se puede embalar la orden del carro carro_key?

    terminales: los que la orden tiene que engastar (None = no se ha podido
    leer su Excel). progreso: el fichero de progreso del bono.
    Devuelve {'estado': 'completa'|'pendientes'|'incompleta', 'motivo', ...}.

    'pendientes' = todas las máquinas han pasado por el carro, pero alguna
    dejó paquetes sin hacer: se embala solo con supervisor.
    """
    descartado = descartado or (lambda t: False)
    con_pendientes = sorted(
        t for t, datos in (progreso or {}).items()
        if not descartado(t)
        and str(carro_key) in ((datos or {}).get('carros_con_pendientes') or {}))

    faltan = []
    if terminales is None:
        if not orden_cerrada:
            return {'estado': 'incompleta', 'motivo': 'No se encuentra el Excel de la orden',
                    'faltan': [], 'pendientes': con_pendientes}
    else:
        for t in sorted(terminales):
            datos = (progreso or {}).get(t) or {}
            hechos = {str(c) for c in (datos.get('carros_completados') or [])}
            if t in con_pendientes:
                continue
            if str(carro_key) in hechos or datos.get('estado') == 'completado':
                continue
            faltan.append(t)
        if not terminales and not orden_cerrada:
            return {'estado': 'incompleta', 'motivo': 'La orden no tiene terminales que engastar',
                    'faltan': [], 'pendientes': con_pendientes}

    if faltan and not orden_cerrada:
        n = len(faltan)
        return {'estado': 'incompleta',
                'motivo': f"Falta{'n' if n > 1 else ''} {n} terminal{'es' if n > 1 else ''} por engastar",
                'faltan': faltan, 'pendientes': con_pendientes}
    if con_pendientes:
        n = len(con_pendientes)
        return {'estado': 'pendientes',
                'motivo': f"{n} terminal{'es' if n > 1 else ''} con paquetes pendientes",
                'faltan': [], 'pendientes': con_pendientes}
    return {'estado': 'completa', 'motivo': '', 'faltan': [], 'pendientes': []}


# ==================== repartos ====================

def reparto_activo(conn, codigo_corte):
    """Reparto guardado para ese código de corte, o None.
    {'id', 'num_cajas', 'cantidad_ref', 'asignaciones': {clave: caja}, ...}"""
    fila = conn.execute(text("""
        SELECT id, codigo_corte, num_cajas, cantidad_ref, creado_por, supervisor, created_at
        FROM embalaje_repartos
        WHERE codigo_corte = :c AND activo = 1
        ORDER BY created_at DESC, rowid DESC LIMIT 1
    """), {'c': codigo_corte}).mappings().first()
    if not fila:
        return None
    reparto = dict(fila)
    reparto['asignaciones'] = {
        r[0]: r[1] for r in conn.execute(text(
            "SELECT clave, caja FROM embalaje_reparto_paquetes WHERE reparto_id = :r"),
            {'r': fila['id']})}
    return reparto


def _validar_asignaciones(paquetes, num_cajas, asignaciones):
    try:
        num_cajas = int(num_cajas)
    except (TypeError, ValueError):
        raise EmbalajeError('Indica cuántas cajas', 'Elige un número de cajas', 400)
    if num_cajas < 1 or num_cajas > MAX_CAJAS:
        raise EmbalajeError(f'El número de cajas tiene que estar entre 1 y {MAX_CAJAS}', '', 400)
    if not isinstance(asignaciones, dict):
        raise EmbalajeError('Faltan los paquetes de cada caja', '', 400)

    limpias = {}
    for p in paquetes:
        caja = asignaciones.get(p['clave'])
        try:
            caja = int(caja)
        except (TypeError, ValueError):
            caja = 0
        if not 1 <= caja <= num_cajas:
            caja = 0
        limpias[p['clave']] = caja
    sin_caja = [p['etiqueta'] for p in paquetes if not limpias[p['clave']]]
    if sin_caja:
        raise EmbalajeError(
            f'Quedan {len(sin_caja)} paquete{"s" if len(sin_caja) > 1 else ""} sin caja',
            'Asigna cada paquete a una caja antes de guardar', 400, sin_caja=sin_caja)
    vacias = sorted(set(range(1, num_cajas + 1)) - set(limpias.values()))
    if vacias:
        raise EmbalajeError(
            f'La caja {vacias[0]} se queda vacía' if len(vacias) == 1
            else f'Las cajas {", ".join(map(str, vacias))} se quedan vacías',
            'Pon algún paquete en cada caja, o elige menos cajas', 400)
    return num_cajas, limpias


def es_cambio(reparto, num_cajas, asignaciones):
    """True si guardar esto cambia algo ya decidido (pide supervisor).
    Añadir paquetes que el reparto no conocía no cuenta como cambio."""
    if not reparto:
        return False
    if int(reparto['num_cajas']) != int(num_cajas):
        return True
    return any(clave in asignaciones and int(asignaciones[clave]) != int(caja)
               for clave, caja in reparto['asignaciones'].items())


def guardar_reparto(conn, codigo_corte, paquetes, num_cajas, asignaciones, *,
                    cantidad, operario, orden_id, supervisor=None, supervisor_via=None):
    """Guarda el reparto del código de corte. Devuelve (reparto, era_cambio).

    Si cambia lo decidido, el anterior queda inactivo (no se borra: es la
    historia de cómo se embalaba) y se crea uno nuevo. Si solo añade
    paquetes nuevos, se completan en el mismo reparto.
    Lanza EmbalajeError('supervisor_requerido') si cambia y no hay supervisor.
    """
    num_cajas, limpias = _validar_asignaciones(paquetes, num_cajas, asignaciones)
    actual = reparto_activo(conn, codigo_corte)
    cambio = es_cambio(actual, num_cajas, limpias)
    if cambio and not supervisor:
        raise EmbalajeError('Cambiar un reparto guardado necesita un supervisor',
                            'Que un supervisor pase su tarjeta o ponga su clave', 403,
                            supervisor_requerido=True)

    if actual and not cambio:
        for clave, caja in limpias.items():
            if clave not in actual['asignaciones']:
                conn.execute(text(
                    "INSERT INTO embalaje_reparto_paquetes (reparto_id, clave, caja) "
                    "VALUES (:r, :c, :k)"), {'r': actual['id'], 'c': clave, 'k': caja})
        return reparto_activo(conn, codigo_corte), False

    if actual:
        conn.execute(text("UPDATE embalaje_repartos SET activo = 0 WHERE codigo_corte = :c"),
                     {'c': codigo_corte})
    reparto_id = uuid.uuid4().hex
    conn.execute(text("""
        INSERT INTO embalaje_repartos
            (id, codigo_corte, num_cajas, cantidad_ref, activo, creado_por, orden_id,
             supervisor, supervisor_via, created_at)
        VALUES (:id, :c, :n, :q, 1, :op, :o, :s, :sv, datetime('now', 'localtime'))
    """), {'id': reparto_id, 'c': codigo_corte, 'n': num_cajas, 'q': cantidad,
           'op': operario or None, 'o': orden_id, 's': supervisor, 'sv': supervisor_via})
    for clave, caja in limpias.items():
        conn.execute(text("INSERT INTO embalaje_reparto_paquetes (reparto_id, clave, caja) "
                          "VALUES (:r, :c, :k)"), {'r': reparto_id, 'c': clave, 'k': caja})
    return reparto_activo(conn, codigo_corte), cambio


def cajas_de(paquetes, reparto):
    """[[paquete, ...] por caja] según el reparto. Los paquetes que el reparto
    no conoce quedan fuera (los devuelve aparte la vista de la orden)."""
    cajas = [[] for _ in range(int(reparto['num_cajas']))]
    for p in paquetes:
        caja = reparto['asignaciones'].get(p['clave'])
        if caja and 1 <= int(caja) <= len(cajas):
            cajas[int(caja) - 1].append(p)
    return cajas


# ==================== registro ====================

def registrar_embalaje(conn, orden, bono, reparto, cajas_impresas, *, operario, operario_via,
                       supervisor=None, supervisor_via=None, con_pendientes=False):
    """Apunta quién embaló (o reimprimió) qué y cuándo. Datos copiados a
    propósito: el registro dice lo de aquel día aunque luego cambie la orden."""
    conn.execute(text("""
        INSERT INTO embalajes
            (id, orden_id, bono_id, bono_nombre, orden_numero, codigo_corte, descripcion,
             cantidad, num_cajas, cajas_impresas, reparto_id, operario, operario_via,
             supervisor, supervisor_via, con_pendientes, fecha)
        VALUES (:id, :o, :b, :bn, :num, :cc, :d, :q, :n, :ci, :r, :op, :opv, :s, :sv, :cp,
                datetime('now', 'localtime'))
    """), {'id': uuid.uuid4().hex, 'o': orden['id'], 'b': bono['id'], 'bn': bono['nombre'],
           'num': orden.get('numero'), 'cc': orden.get('codigo_corte'),
           'd': orden.get('descripcion'), 'q': orden.get('cantidad'),
           'n': reparto['num_cajas'], 'ci': ','.join(str(c) for c in cajas_impresas),
           'r': reparto['id'], 'op': operario, 'opv': operario_via,
           's': supervisor, 'sv': supervisor_via, 'cp': 1 if con_pendientes else 0})


# ==================== observaciones ====================
# Lo que hay que hacerle a un paquete antes de meterlo en la caja. Van por
# código de corte y paquete, como el reparto, pero aparte de él: rehacer el
# reparto no las borra. Ponerlas, cambiarlas o quitarlas lo autoriza un
# supervisor: son instrucciones para quien embala.

MAX_OBSERVACION = 200


def observaciones(conn, codigo_corte):
    """{clave: texto} del código de corte."""
    return {r[0]: r[1] for r in conn.execute(text(
        "SELECT clave, texto FROM embalaje_observaciones WHERE codigo_corte = :c"),
        {'c': codigo_corte})}


def guardar_observacion(conn, codigo_corte, clave, texto, autor, supervisor=None):
    """Pone, cambia o (con texto vacío) quita la observación de un paquete."""
    texto = ' '.join(str(texto or '').split())
    if len(texto) > MAX_OBSERVACION:
        raise EmbalajeError(f'La observación no puede pasar de {MAX_OBSERVACION} letras',
                            'Acórtala', 400)
    if not texto:
        conn.execute(text("DELETE FROM embalaje_observaciones WHERE codigo_corte = :c AND clave = :k"),
                     {'c': codigo_corte, 'k': clave})
        return ''
    conn.execute(text("""
        INSERT INTO embalaje_observaciones (codigo_corte, clave, texto, autor, supervisor, updated_at)
        VALUES (:c, :k, :t, :a, :s, datetime('now', 'localtime'))
        ON CONFLICT (codigo_corte, clave) DO UPDATE SET
            texto = excluded.texto, autor = excluded.autor, supervisor = excluded.supervisor,
            updated_at = excluded.updated_at
    """), {'c': codigo_corte, 'k': clave, 't': texto, 'a': autor or None, 's': supervisor})
    return texto


# ==================== nombres de las cajas ====================
# «CAJA 1 de 3» se queda siempre; el nombre es un añadido (p. ej. «Conectores»).
# Por código de corte y número de caja, aparte del reparto: rehacerlo no lo borra.
# Ponerlo o cambiarlo lo autoriza un supervisor, como las observaciones.

MAX_NOMBRE_CAJA = 40


def nombres_cajas(conn, codigo_corte):
    """{numero_caja: nombre} del código de corte."""
    return {int(r[0]): r[1] for r in conn.execute(text(
        "SELECT caja, nombre FROM embalaje_cajas_nombres WHERE codigo_corte = :c"),
        {'c': codigo_corte})}


def guardar_nombre_caja(conn, codigo_corte, caja, nombre, autor, supervisor=None):
    """Pone, cambia o (con nombre vacío) quita el nombre de una caja."""
    try:
        caja = int(caja)
    except (TypeError, ValueError):
        caja = 0
    if not 1 <= caja <= MAX_CAJAS:
        raise EmbalajeError('Esa caja no existe', 'Vuelve a abrir la orden', 400)
    nombre = ' '.join(str(nombre or '').split())
    if len(nombre) > MAX_NOMBRE_CAJA:
        raise EmbalajeError(f'El nombre de la caja no puede pasar de {MAX_NOMBRE_CAJA} letras',
                            'Pon un nombre más corto', 400)
    if not nombre:
        conn.execute(text("DELETE FROM embalaje_cajas_nombres WHERE codigo_corte = :c AND caja = :n"),
                     {'c': codigo_corte, 'n': caja})
        return ''
    conn.execute(text("""
        INSERT INTO embalaje_cajas_nombres (codigo_corte, caja, nombre, autor, supervisor, updated_at)
        VALUES (:c, :n, :t, :a, :s, datetime('now', 'localtime'))
        ON CONFLICT (codigo_corte, caja) DO UPDATE SET
            nombre = excluded.nombre, autor = excluded.autor, supervisor = excluded.supervisor,
            updated_at = excluded.updated_at
    """), {'c': codigo_corte, 'n': caja, 't': nombre, 'a': autor or None, 's': supervisor})
    return nombre


def ultimo_embalaje(conn, orden_id):
    fila = conn.execute(text("""
        SELECT fecha, operario, num_cajas, cajas_impresas FROM embalajes
        WHERE orden_id = :o ORDER BY fecha DESC, rowid DESC LIMIT 1
    """), {'o': orden_id}).mappings().first()
    return dict(fila) if fila else None


SQL_MIGRACION = """
    -- Reparto en cajas de cada código de corte (ver app/embalaje.py). Un
    -- reparto cambiado queda con activo = 0: no se borra.
    CREATE TABLE IF NOT EXISTS embalaje_repartos (
        id             TEXT PRIMARY KEY,
        codigo_corte   TEXT NOT NULL,
        num_cajas      INTEGER NOT NULL CHECK (num_cajas >= 1),
        cantidad_ref   INTEGER,
        activo         INTEGER NOT NULL DEFAULT 1,
        creado_por     TEXT,
        orden_id       TEXT,
        supervisor     TEXT,
        supervisor_via TEXT,
        created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_embalaje_repartos_corte ON embalaje_repartos(codigo_corte, activo);

    CREATE TABLE IF NOT EXISTS embalaje_reparto_paquetes (
        reparto_id TEXT NOT NULL,
        clave      TEXT NOT NULL,
        caja       INTEGER NOT NULL CHECK (caja >= 1),
        PRIMARY KEY (reparto_id, clave)
    );

    -- Operación que hay que hacer a un paquete antes de meterlo en la caja.
    CREATE TABLE IF NOT EXISTS embalaje_observaciones (
        codigo_corte TEXT NOT NULL,
        clave        TEXT NOT NULL,
        texto        TEXT NOT NULL,
        autor        TEXT,
        supervisor   TEXT,
        updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        PRIMARY KEY (codigo_corte, clave)
    );

    -- Nombre opcional de cada caja («CAJA 1 de 3 · Conectores»).
    CREATE TABLE IF NOT EXISTS embalaje_cajas_nombres (
        codigo_corte TEXT NOT NULL,
        caja         INTEGER NOT NULL CHECK (caja >= 1),
        nombre       TEXT NOT NULL,
        autor        TEXT,
        supervisor   TEXT,
        updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        PRIMARY KEY (codigo_corte, caja)
    );

    -- Cada vez que se imprimen los carteles de una orden.
    CREATE TABLE IF NOT EXISTS embalajes (
        id             TEXT PRIMARY KEY,
        orden_id       TEXT NOT NULL,
        bono_id        TEXT,
        bono_nombre    TEXT,
        orden_numero   TEXT,
        codigo_corte   TEXT,
        descripcion    TEXT,
        cantidad       INTEGER,
        num_cajas      INTEGER,
        cajas_impresas TEXT,
        reparto_id     TEXT,
        operario       TEXT,
        operario_via   TEXT,
        supervisor     TEXT,
        supervisor_via TEXT,
        con_pendientes INTEGER NOT NULL DEFAULT 0,
        fecha          TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_embalajes_orden ON embalajes(orden_id, fecha);
"""


def migrar_columnas(cur):
    """Columnas añadidas después de crear las tablas (sqlite3 en bruto)."""
    for tabla in ('embalaje_observaciones', 'embalaje_cajas_nombres'):
        cols = {r[1] for r in cur.execute(f"PRAGMA table_info({tabla})")}
        if 'supervisor' not in cols:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN supervisor TEXT")
