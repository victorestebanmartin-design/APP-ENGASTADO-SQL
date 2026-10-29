# qr_mini.py -- generador de codigos QR minimo para MicroPython.
#
# Solo lo que necesita el carro: texto en modo byte, correccion de errores L
# y versiones 1 a 5 (hasta 100 bytes, de sobra para el codigo de un bono).
# Se calcula entero en la placa: no hace falta red para dibujar el QR.
#
#   m = qr_mini.crear("0000002_2026")   # lista de filas, True = modulo oscuro
#   None si el texto no cabe (mas de 100 bytes).
#
# Todas las versiones 1-5 con nivel L llevan un unico bloque de datos, que es
# lo que simplifica el reparto de bytes. Tope de 100 bytes: con 106 (el maximo
# teorico de la v5) el QR no se decodifica.

# version -> (bytes de datos, bytes de correccion, posiciones de alineacion)
_VER = {
    1: (19, 7, ()),
    2: (34, 10, (6, 18)),
    3: (55, 15, (6, 22)),
    4: (80, 20, (6, 26)),
    5: (108, 26, (6, 30)),
}

_EXP = [0] * 512
_LOG = [0] * 256


def _tablas():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_tablas()


def _mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _generador(n):
    g = [1]
    for i in range(n):
        sig = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            sig[j] ^= c
            sig[j + 1] ^= _mul(c, _EXP[i])
        g = sig
    return g


def _correccion(datos, n):
    g = _generador(n)
    resto = list(datos) + [0] * n
    for i in range(len(datos)):
        c = resto[i]
        if c:
            for j in range(1, len(g)):
                resto[i + j] ^= _mul(g[j], c)
    return resto[len(datos):]


def _codewords(texto_bytes, version):
    n_datos, n_ec, _ = _VER[version]
    bits = []

    def poner(valor, n):
        for i in range(n - 1, -1, -1):
            bits.append((valor >> i) & 1)

    poner(0b0100, 4)                 # modo byte
    poner(len(texto_bytes), 8)       # longitud (versiones 1-9)
    for b in texto_bytes:
        poner(b, 8)
    tope = n_datos * 8
    for _ in range(min(4, tope - len(bits))):
        bits.append(0)               # terminador
    while len(bits) % 8:
        bits.append(0)
    datos = []
    for i in range(0, len(bits), 8):
        v = 0
        for k in range(8):
            v = (v << 1) | bits[i + k]
        datos.append(v)
    pad = 0xEC
    while len(datos) < n_datos:
        datos.append(pad)
        pad = 0x11 if pad == 0xEC else 0xEC
    return datos + _correccion(datos, n_ec)


def _bits_formato(mascara):
    # nivel L = 01; BCH(15,5) con 0x537 y mascara XOR 0x5412
    d = (0b01 << 3) | mascara
    r = d << 10
    for i in range(14, 9, -1):
        if (r >> i) & 1:
            r ^= 0x537 << (i - 10)
    return ((d << 10) | r) ^ 0x5412


def _matriz_base(version):
    n = 17 + 4 * version
    m = [[False] * n for _ in range(n)]
    f = [[False] * n for _ in range(n)]      # True = modulo de funcion (no es dato)

    def poner(x, y, v):
        if 0 <= x < n and 0 <= y < n:
            m[y][x] = v
            f[y][x] = True

    def buscador(cx, cy):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                d = max(abs(dx), abs(dy))
                poner(cx + dx, cy + dy, d not in (2, 4))

    buscador(3, 3)
    buscador(n - 4, 3)
    buscador(3, n - 4)
    for i in range(8, n - 8):                # lineas de sincronismo
        poner(i, 6, i % 2 == 0)
        poner(6, i, i % 2 == 0)
    pos = _VER[version][2]
    for cy in pos:
        for cx in pos:
            if (cx == 6 and cy == 6) or (cx == 6 and cy == n - 7) or (cx == n - 7 and cy == 6):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    poner(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
    poner(8, n - 8, True)                    # modulo oscuro fijo
    # Zona de formato (se rellena luego). El sincronismo de (8,6) y (6,8) manda
    # sobre ella: se reserva sin tocar el valor.
    for i in range(9):
        if not f[i][8]:
            poner(8, i, False)
        if not f[8][i]:
            poner(i, 8, False)
    for i in range(8):
        poner(n - 1 - i, 8, False)
        poner(8, n - 1 - i, False)
    poner(8, n - 8, True)
    return m, f


def _poner_formato(m, mascara):
    n = len(m)
    b = _bits_formato(mascara)

    def bit(i):
        return bool((b >> i) & 1)

    for i in range(6):
        m[i][8] = bit(i)
    m[7][8] = bit(6)
    m[8][8] = bit(7)
    m[8][7] = bit(8)
    for i in range(9, 15):
        m[8][14 - i] = bit(i)
    for i in range(8):
        m[8][n - 1 - i] = bit(i)
    for i in range(8, 15):
        m[n - 15 + i][8] = bit(i)
    m[n - 8][8] = True


def _colocar_datos(m, f, cw):
    n = len(m)
    bits = []
    for c in cw:
        for i in range(7, -1, -1):
            bits.append((c >> i) & 1)
    i = 0
    x = n - 1
    arriba = True
    while x > 0:
        if x == 6:
            x -= 1
        rango = range(n - 1, -1, -1) if arriba else range(n)
        for y in rango:
            for dx in (0, 1):
                xx = x - dx
                if not f[y][xx]:
                    m[y][xx] = bool(bits[i]) if i < len(bits) else False
                    i += 1
        arriba = not arriba
        x -= 2


def _mascara(k, x, y):
    if k == 0: return (x + y) % 2 == 0
    if k == 1: return y % 2 == 0
    if k == 2: return x % 3 == 0
    if k == 3: return (x + y) % 3 == 0
    if k == 4: return (x // 3 + y // 2) % 2 == 0
    if k == 5: return (x * y) % 2 + (x * y) % 3 == 0
    if k == 6: return ((x * y) % 2 + (x * y) % 3) % 2 == 0
    return ((x + y) % 2 + (x * y) % 3) % 2 == 0


def _penalizacion(m):
    n = len(m)
    p = 0
    for filas in (m, [list(c) for c in zip(*m)]):
        for fila in filas:
            racha = 1
            for i in range(1, n):
                if fila[i] == fila[i - 1]:
                    racha += 1
                else:
                    if racha >= 5:
                        p += racha - 2
                    racha = 1
            if racha >= 5:
                p += racha - 2
            # patron 1:1:3:1:1 con 4 claros a un lado
            s = ''.join('1' if v else '0' for v in fila)
            p += 40 * (s.count('10111010000') + s.count('00001011101'))
    for y in range(n - 1):
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                p += 3
    oscuros = sum(1 for fila in m for v in fila if v)
    p += (abs(oscuros * 100 // (n * n) - 50) // 5) * 10
    return p


def crear(texto):
    """Matriz QR (lista de filas de bool) o None si pasa de 100 bytes."""
    datos = texto.encode('utf-8') if isinstance(texto, str) else bytes(texto)
    version = None
    if len(datos) > 100:
        return None
    for v in (1, 2, 3, 4, 5):
        # 4 bits de modo + 8 de longitud = 12 bits = 1,5 bytes de cabecera
        if len(datos) + 2 <= _VER[v][0]:
            version = v
            break
    if version is None:
        return None
    cw = _codewords(datos, version)
    base, funcion = _matriz_base(version)
    n = len(base)
    _colocar_datos(base, funcion, cw)
    mejor = None
    mejor_p = None
    for k in range(8):
        m = [fila[:] for fila in base]
        for y in range(n):
            for x in range(n):
                if not funcion[y][x] and _mascara(k, x, y):
                    m[y][x] = not m[y][x]
        _poner_formato(m, k)
        p = _penalizacion(m)
        if mejor is None or p < mejor_p:
            mejor, mejor_p = m, p
    return mejor
