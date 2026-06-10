import sqlite3, os

db = os.path.join(os.path.dirname(__file__), '..', 'data', 'engastado.db')
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("""
    SELECT DISTINCT cod_cable
    FROM etiquetas_elementos
    WHERE cod_cable IS NOT NULL AND cod_cable != '' AND LOWER(cod_cable) != 'nan'
    ORDER BY cod_cable
""")
cods = [r[0] for r in cur.fetchall()]
con.close()

PALETA = [
    ('#d97706', 'Ambar'),
    ('#2563eb', 'Azul'),
    ('#059669', 'Verde esmeralda'),
    ('#7c3aed', 'Violeta'),
    ('#dc2626', 'Rojo'),
    ('#0891b2', 'Cyan'),
    ('#db2777', 'Rosa'),
    ('#65a30d', 'Lima'),
    ('#0d9488', 'Teal'),
    ('#ea580c', 'Naranja'),
    ('#4f46e5', 'Indigo'),
    ('#be185d', 'Fucsia'),
]

def get_color(cod):
    s = str(cod).strip().upper()
    h = 0
    for c in s:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    idx = h % len(PALETA)
    return PALETA[idx]

print(f'Total cod_cable distintos: {len(cods)}\n')
for cod in cods:
    hex_col, name = get_color(cod)
    print(f'{cod:<22} -> {name:<20} {hex_col}')
