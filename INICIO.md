# ⚡ EMPEZAR AHORA - 5 MINUTOS

Sin permisos de admin → **Usamos SQLite** (incluido en Python)

---

## 3 comandos para arrancar:

```powershell
# 1. Crear entorno
cd C:\Users\estebanv\APP-ENGASTADO-SQL
python -m venv venv
.\venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Arrancar
python run_sql.py
```

---

## Verificar:

Abre navegador → **http://localhost:5001/health**

Si ves `"status": "ok"` → ✅ **LISTO**

---

## ¿Qué tienes ahora?

- ✅ Base de datos SQLite transaccional
- ✅ Soporte para 4-10 usuarios concurrentes
- ✅ MEJOR que JSON (no más condiciones de carrera)
- ✅ Sin permisos admin necesarios
- ✅ Proyecto viejo intacto

---

## Más info:

- **Guía completa:** [GUIA_RAPIDA_SQLITE.md](GUIA_RAPIDA_SQLITE.md)
- **Resumen ejecutivo:** [LEEME_PRIMERO.md](LEEME_PRIMERO.md)

---

**¿Funciona?** → Siguiente paso: Implementar repositories y migrar datos JSON
