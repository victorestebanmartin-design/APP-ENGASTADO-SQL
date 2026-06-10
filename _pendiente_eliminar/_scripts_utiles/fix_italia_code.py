import sqlite3

conn = sqlite3.connect('data/engastado.db')
cursor = conn.cursor()

# Agregar código ITALIA
cursor.execute("""
    INSERT OR REPLACE INTO codigos_cortes (codigo, archivo_excel, proyecto_nombre, activo)
    VALUES ('ITALIA', 'LISTADO_CABLEADO_CORADIA_ITALIA_APANTALLADOS_MOD.xlsx', 'CORADIA ITALIA', 1)
""")

# Actualizar la orden ITALIA con el archivo correcto
cursor.execute("""
    UPDATE ordenes_produccion 
    SET archivo_excel = 'LISTADO_CABLEADO_CORADIA_ITALIA_APANTALLADOS_MOD.xlsx'
    WHERE codigo_corte = 'ITALIA'
""")

conn.commit()
print('✅ Código ITALIA agregado y orden actualizada')
conn.close()
