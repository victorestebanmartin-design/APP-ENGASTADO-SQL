"""Diagnóstico del bono 18022026_3 para el dashboard ponderado"""
import sqlite3
import json
import os

BONO = "18022026_3"
DB = "data/engastado.db"
DATA_DIR = "data"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=" * 60)
print(f"DIAGNÓSTICO BONO: {BONO}")
print("=" * 60)

# 1) Bono
c.execute("SELECT * FROM bonos WHERE nombre=?", (BONO,))
bono = c.fetchone()
if not bono:
    print("❌ BONO NO ENCONTRADO en la BD")
    conn.close()
    exit()

bono_id = bono["id"]
print(f"✅ Bono encontrado: id={bono_id}, estado={bono['estado']}")

# 2) Órdenes
c.execute("""SELECT id, numero, codigo_corte, archivo_excel, carro_numero
             FROM ordenes_produccion WHERE bono_id=?""", (bono_id,))
ordenes = c.fetchall()
print(f"\nÓRDENES ({len(ordenes)}):")
for o in ordenes:
    d = dict(o)
    print(f"  carro={d['carro_numero']} | archivo={d['archivo_excel']} | cod_corte={d['codigo_corte']}")

# 3) Etiquetas_elementos por archivo
print("\nETIQUETAS_ELEMENTOS por archivo:")
archivos_bono = [o["archivo_excel"] for o in ordenes if o["archivo_excel"]]
total_global = 0
for arch in archivos_bono:
    c.execute("SELECT COUNT(*), SUM(num_terminales) FROM etiquetas_elementos WHERE archivo_excel=?", (arch,))
    row = c.fetchone()
    cnt = row[0] or 0
    total_terminales = row[1] or 0
    print(f"  [{arch}]: {cnt} grupos, {total_terminales} num_terminales total")
    total_global += total_terminales

    if cnt > 0:
        c.execute("SELECT DISTINCT de_terminal FROM etiquetas_elementos WHERE archivo_excel=? AND de_terminal IS NOT NULL LIMIT 10", (arch,))
        term_rows = c.fetchall()
        terminales_unicos = [r[0] for r in term_rows if r[0] and str(r[0]).upper() not in ("", "NAN", "S/T")]
        print(f"    Terminales únicos (sample): {terminales_unicos[:8]}")
    else:
        print(f"    ⚠️  Sin datos en etiquetas_elementos para este archivo")
        # Ver si existe el archivo físicamente
        candidatos = [
            os.path.join("data", "cortes", arch),
            os.path.join("uploads", arch),
        ]
        for ruta in candidatos:
            if os.path.exists(ruta):
                print(f"    ✅ Archivo físico encontrado en: {ruta}")
                break
        else:
            print(f"    ❌ Archivo físico NO encontrado en data/cortes/ ni uploads/")

print(f"\nTotal num_terminales ponderados en etiquetas_elementos: {total_global}")

# 4) Archivo de progreso
prog_path = os.path.join(DATA_DIR, f"progreso_bono_{BONO}.json")
if os.path.exists(prog_path):
    with open(prog_path, "r", encoding="utf-8") as f:
        progreso = json.load(f)
    print(f"\nPROGRESO guardado ({len(progreso)} terminales):")
    for terminal, data in list(progreso.items())[:10]:
        cc = data.get("carros_completados", [])
        pend = data.get("carros_con_pendientes", {})
        print(f"  {terminal}: completados={cc}, pendientes_carros={list(pend.keys())}")
else:
    print(f"\n❌ NO existe archivo de progreso: {prog_path}")

# 5) Si etiquetas vacías, mostrar cómo sería el endpoint ponderado sin ellas
if total_global == 0 and len(ordenes) > 0:
    print("\n" + "=" * 60)
    print("DIAGNÓSTICO: etiquetas_elementos VACÍO para este bono.")
    print("El endpoint progreso-ponderado devuelve 0 porque no encuentra")
    print("num_terminales por terminal. Soluciones posibles:")
    print("  A) Los archivos Excel necesitan cargarse en etiquetas_elementos")
    print("     (llamando a /api/etiquetas/cargar_grupos con cada archivo)")
    print("  B) Calcular pesos directamente del Excel en el endpoint")
    print("     (no depender de etiquetas_elementos pre-cargadas)")

conn.close()
print("\n✅ Diagnóstico completado")
