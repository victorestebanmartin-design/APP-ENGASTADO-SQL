# 🔍 Diagnóstico SQL Server - 16 Feb 2026

## ✅ Lo que SÍ tienes instalado

### 1. Drivers ODBC de SQL Server
```
✅ SQL Server (32-bit)
✅ SQL Server (64-bit)
```

**Esto significa:**
- Puedes conectarte a servidores SQL Server **remotos**
- Windows incluye estos drivers básicos por defecto
- **NO son suficientes para tener tu propia base de datos local**

---

## ❌ Lo que NO tienes instalado

### 1. SQL Server Motor de Base de Datos
- ❌ SQL Server Express
- ❌ SQL Server Developer
- ❌ SQL Server LocalDB
- ❌ Ninguna instancia local

### 2. Herramientas de SQL Server
- ❌ sqlcmd (línea de comandos)
- ❌ SQL Server Management Studio (SSMS)
- ❌ SQL Server Configuration Manager

### 3. Librerías Python
- ❌ pyodbc (no está en tu entorno actual)

---

## 🎯 ¿Qué necesitas instalar?

### OPCIÓN 1: SQL Server Express (Recomendado - GRATIS)

**Qué es:**
- Motor completo de base de datos
- Gratis para producción
- Ideal para tu caso (4-10 usuarios)

**Instalar:**
1. **SQL Server 2022 Express:**
   - Descargar: https://go.microsoft.com/fwlink/p/?linkid=2216019
   - Ejecutar instalador
   - Elegir "Basic" installation
   - Anotar el nombre de instancia (ej: `.\SQLEXPRESS`)
   - Tiempo: ~10-15 minutos

2. **SQL Server Management Studio (SSMS):**
   - Descargar: https://aka.ms/ssmsfullsetup
   - Ejecutar instalador
   - Tiempo: ~5-10 minutos

3. **ODBC Driver 17 o 18 (opcional, para mejor performance):**
   - Ya tienes driver básico "SQL Server" ✅
   - Para más moderno: https://go.microsoft.com/fwlink/?linkid=2249004
   - NO es obligatorio, el que tienes funciona

**Total tiempo:** 20-30 minutos

---

### OPCIÓN 2: SQL Server LocalDB (Más ligero - GRATIS)

**Qué es:**
- Versión "lite" de SQL Server
- No corre como servicio (se inicia on-demand)
- Ideal para desarrollo, **NO recomendado para 10 usuarios**

**Instalar:**
- Viene incluido en SQL Server Express
- O descargar standalone

❌ **NO recomendado para tu caso** (necesitas multiusuario real)

---

### OPCIÓN 3: SQL Server Developer (Completo - GRATIS)

**Qué es:**
- Versión Enterprise completa
- Gratis solo para desarrollo/testing
- **NO legal para producción** (pero técnicamente igual que Express para tu caso)

**Instalar:**
- Similar a Express pero más grande

---

## 🚀 Plan de instalación HOY

### Paso 1: Instalar SQL Server Express (15 min)

```powershell
# Descargar instalador Express
# https://go.microsoft.com/fwlink/p/?linkid=2216019

# Ejecutar instalador:
# 1. Elegir "Basic"
# 2. Aceptar licencia
# 3. Dejar ubicación por defecto
# 4. Esperar instalación
# 5. ¡ANOTAR EL NOMBRE DE SERVIDOR QUE APARECE AL FINAL!
#    Ejemplo: .\SQLEXPRESS o DESKTOP-ABC\SQLEXPRESS
```

### Paso 2: Instalar SSMS (10 min)

```powershell
# Descargar SSMS
# https://aka.ms/ssmsfullsetup

# Ejecutar instalador
# Siguiente, Siguiente, Install
```

### Paso 3: Verificar instalación (2 min)

```powershell
# Verificar servicio corriendo
Get-Service | Where-Object {$_.Name -like "MSSQL*"}

# Debe aparecer:
# Name: MSSQL$SQLEXPRESS
# Status: Running ✅
```

### Paso 4: Conectar con SSMS (2 min)

```
1. Abrir SQL Server Management Studio
2. Conectar a: .\SQLEXPRESS 
   (o el nombre que anotaste)
3. Autenticación: Windows Authentication
4. Conectar
```

### Paso 5: Ejecutar schema.sql (2 min)

```
1. En SSMS: File > Open > File
2. Seleccionar: C:\Users\estebanv\APP-ENGASTADO-SQL\schema.sql
3. Presionar F5 (Execute)
4. Verificar mensaje: "Schema creado exitosamente"
```

### Paso 6: Instalar pyodbc en nueva app (3 min)

```powershell
cd C:\Users\estebanv\APP-ENGASTADO-SQL
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Paso 7: Probar conexión (2 min)

```powershell
# Editar config.py (línea 28):
# DB_SERVER = r'.\SQLEXPRESS'  # O el nombre que anotaste

python run_sql.py

# Abrir navegador:
# http://localhost:5001/health

# Debe mostrar:
# {"status": "ok", "database": "connected"}
```

---

## 📋 Resumen

| Componente | Estado | Acción |
|------------|--------|--------|
| Drivers ODBC básicos | ✅ Instalado | Ninguna (ya tienes) |
| SQL Server Express | ❌ NO instalado | **INSTALAR** (15 min) |
| SSMS | ❌ NO instalado | **INSTALAR** (10 min) |
| pyodbc | ❌ NO instalado | pip install (en paso 6) |
| Schema EngastadoDB | ❌ NO creado | Ejecutar en SSMS (paso 5) |

---

## ⏱️ Tiempo total estimado

- **Descarga:** 5-10 min (depende de internet)
- **Instalación SQL Server:** 10-15 min
- **Instalación SSMS:** 5-10 min
- **Setup Python + schema:** 5-7 min
- **TOTAL:** ~35-45 minutos

---

## 🎯 Siguiente paso INMEDIATO

**Descargar SQL Server Express 2022:**
👉 https://go.microsoft.com/fwlink/p/?linkid=2216019

Ejecuta el instalador y sigue el asistente "Basic".

**Mientras descarga, puedes:**
- Leer el README.md completo
- Revisar el schema.sql para entender las tablas
- Preparar un café ☕

---

## ❓ FAQ

**P: ¿El driver "SQL Server" que ya tengo no sirve?**
R: Sirve para CONECTAR a un servidor, pero necesitas el servidor instalado primero.

**P: ¿Por qué recomiendas Express y no LocalDB?**
R: LocalDB es para 1 usuario. Express soporta múltiples conexiones simultáneas (tu caso: 4-10 usuarios).

**P: ¿Necesito pagar licencia?**
R: NO. SQL Server Express es 100% gratis, incluso para producción.

**P: ¿Cuánto espacio ocupa?**
R: ~1.5 GB SQL Server + ~600 MB SSMS = ~2.1 GB total

**P: ¿Puedo usar MySQL o PostgreSQL en vez de SQL Server?**
R: Técnicamente sí, pero tendrías que adaptar el schema.sql (sintaxis distinta). SQL Server es nativo en Windows y más simple para este caso.

---

**Próximo archivo a abrir después de instalar:**
📄 [README.md](README.md) - Paso 2: "Crear base de datos"
