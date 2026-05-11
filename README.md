# 🚀 SISTEMA DE ENGASTADO AUTOMÁTICO - SQLite

> **⚠️ NOTA IMPORTANTE:** Este README describe la instalación con SQL Server, pero **estamos usando SQLite** porque no tenemos permisos de administrador.
>
> 👉 **Para arrancar AHORA (5 min):** Lee [INICIO.md](INICIO.md) o [GUIA_RAPIDA_SQLITE.md](GUIA_RAPIDA_SQLITE.md)

---

**Versión 2.0 - SQLite (sin permisos admin)**  
Fecha: Febrero 2026

---

## 📋 Descripción

Nueva versión del sistema de gestión de engastado automático con persistencia en **SQLite** para soportar:
- ✅ Concurrencia controlada (4-10 usuarios con WAL mode)
- ✅ Transacciones ACID
- ✅ Integridad referencial
- ✅ **Sin permisos de administrador necesarios**
- ✅ Portabilidad (archivo único)

Esta aplicación corre **en paralelo** al sistema JSON existente hasta validar su funcionamiento completo.

---

_El resto de este documento describe SQL Server. Para SQLite, lee las guías mencionadas arriba._

---

**Versión 2.0 - Migración a SQL Server** (ANTICUADO - ver guías SQLite)
Fecha: Febrero 2026

---

## 📋 Descripción

Nueva versión del sistema de gestión de engastado automático con persistencia en **SQL Server** para soportar:
- ✅ Concurrencia real (4-10 usuarios simultáneos)
- ✅ Transacciones ACID
- ✅ Auditoría automática de cambios
- ✅ Integridad referencial
- ✅ Backup y recuperación robustos

Esta aplicación corre **en paralelo** al sistema JSON existente hasta validar su funcionamiento completo.

---

## 🗂️ Estructura del Proyecto

```
APP-ENGASTADO-SQL/
├── schema.sql              # Schema de base de datos
├── requirements.txt        # Dependencias Python
├── config.py              # Configuración (SQL Server, Flask, etc.)
├── run_sql.py             # Script de arranque
├── migrate_json_to_sql.py # Migrador de datos JSON → SQL
├── app/                   # Lógica de negocio
│   ├── __init__.py
│   ├── routes.py
│   ├── excel_manager.py
│   ├── printer_manager.py
│   └── zpl_templates.py
├── repositories/          # Capa de acceso a datos SQL
│   ├── __init__.py
│   ├── proyecto_repository.py
│   ├── orden_repository.py
│   ├── bono_repository.py
│   └── ...
├── templates/             # HTML (Flask)
├── static/               # CSS, JS, imágenes
├── migrations/           # Scripts de migración SQL
├── docs/                 # Documentación
└── logs/                 # Logs de aplicación
```

---

## ⚙️ Requisitos Previos

### 1. SQL Server instalado

**Opción A: SQL Server Express (gratuito)**
- Descargar: https://www.microsoft.com/es-es/sql-server/sql-server-downloads
- Instalar SQL Server Express con herramientas (SSMS recomendado)

**Opción B: SQL Server Developer (gratuito para dev)**
- Más completo, incluye todas las características enterprise

### 2. ODBC Driver para SQL Server

Descargar e instalar:
- **ODBC Driver 17**: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
- O **ODBC Driver 18** (más reciente)

Verificar instalación en PowerShell:
```powershell
Get-OdbcDriver | Where-Object {$_.Name -like "*SQL Server*"}
```

### 3. Python 3.9+

Verificar versión:
```bash
python --version
```

---

## 🚀 Instalación

### Paso 1: Crear base de datos

Abrir **SQL Server Management Studio (SSMS)** o ejecutar desde PowerShell:

```powershell
sqlcmd -S localhost\SQLEXPRESS -i schema.sql
```

O manualmente:
1. Conectar a SQL Server con SSMS
2. Abrir `schema.sql`
3. Ejecutar script completo (F5)

Verificar que se creó la base `EngastadoDB` con todas las tablas.

### Paso 2: Configurar conexión

Editar `config.py` según tu instalación:

**Para SQL Server Express con Windows Authentication:**
```python
DB_SERVER = r'.\SQLEXPRESS'  # O 'localhost\SQLEXPRESS'
DB_NAME = 'EngastadoDB'
DB_USER = ''  # Vacío para Windows Auth
DB_PASSWORD = ''
```

**Para SQL Server con autenticación SQL:**
```python
DB_SERVER = 'localhost'
DB_NAME = 'EngastadoDB'
DB_USER = 'app_engastado'
DB_PASSWORD = 'TuPasswordSeguro123!'
```

### Paso 3: Crear entorno virtual e instalar dependencias

```powershell
# Crear entorno virtual
python -m venv venv

# Activar
.\venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

**Verificar instalación de pyodbc:**
```python
python -c "import pyodbc; print('Drivers:', pyodbc.drivers())"
```

Deberías ver `ODBC Driver 17 for SQL Server` o similar.

### Paso 4: Migrar datos desde JSON

```powershell
python migrate_json_to_sql.py
```

Este script:
1. Lee todos los archivos JSON del proyecto viejo
2. Valida integridad
3. Inserta en SQL Server con transacciones
4. Genera reporte de registros migrados

**IMPORTANTE:** Hacer backup de la carpeta `data/` antes de migrar.

### Paso 5: Arrancar aplicación

```powershell
python run_sql.py
```

La aplicación arrancará en:
- Local: http://localhost:5001
- Red: http://TU_IP:5001

**Nota:** Se usa puerto **5001** para no conflictuar con la app JSON existente (puerto 5000).

---

## 🧪 Testing Piloto

### Plan de validación paralela

1. **Fase 1 (1-2 días):** Solo desarrollador
   - Probar todas las funcionalidades críticas
   - Validar integridad de datos migrados
   - Verificar logs de SQL

2. **Fase 2 (1 semana):** 2-3 usuarios piloto
   - Apuntar sus PCs a `http://IP:5001`
   - Otros usuarios siguen en sistema viejo `:5000`
   - Comparar resultados entre sistemas

3. **Fase 3 (2-3 días):** Todos los usuarios
   - Deprecar sistema JSON
   - Cambiar puerto a 5000
   - Mantener JSON como backup read-only

### Checklist funcional

- [ ] Carga de archivos Excel
- [ ] Escaneo de órdenes de producción
- [ ] Creación de bonos
- [ ] Asignación de carros
- [ ] Actualización de estados
- [ ] Generación de etiquetas ZPL
- [ ] Gestión de puestos/máquinas/terminales
- [ ] Consulta de progreso
- [ ] Concurrencia: 5+ usuarios simultáneos escribiendo

---

## 🗄️ Backup y Recuperación

### Backup manual (script incluido en `migrations/backup.sql`)

```sql
BACKUP DATABASE EngastadoDB 
TO DISK = 'C:\Backups\EngastadoDB_20260216.bak'
WITH FORMAT, COMPRESSION;
```

### Restore desde backup

```sql
USE master;
GO
RESTORE DATABASE EngastadoDB
FROM DISK = 'C:\Backups\EngastadoDB_20260216.bak'
WITH REPLACE;
```

### Backup automático diario

Configurar tarea programada Windows:
```powershell
# Ver migrations/schedule_backup.ps1
```

---

## 🔧 Troubleshooting

### Error: "No se puede conectar a SQL Server"

**Verificar:**
1. SQL Server está corriendo:
   ```powershell
   Get-Service | Where-Object {$_.Name -like "*SQL*"}
   ```
2. Nombre del servidor correcto en `config.py`
3. Firewall permite conexión al puerto 1433

### Error: "Driver not found"

**Solución:**
1. Verificar drivers instalados:
   ```python
   import pyodbc; print(pyodbc.drivers())
   ```
2. Actualizar `DB_DRIVER` en `config.py` según el driver disponible

### Error: "Login failed"

**Si usas SQL Auth:**
1. Verificar que el usuario existe en SQL Server
2. Comprobar que tiene permisos en EngastadoDB
3. Revisar usuario/contraseña en `config.py`

**Si usas Windows Auth:**
- Asegurarte que `DB_USER` y `DB_PASSWORD` están vacíos
- `Trusted_Connection=yes` está en connection string

### Performance lenta

**Solución:**
1. Verificar índices creados:
   ```sql
   SELECT * FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.ordenes_produccion');
   ```
2. Actualizar estadísticas:
   ```sql
   UPDATE STATISTICS dbo.ordenes_produccion WITH FULLSCAN;
   ```

---

## 🔄 Rollback (volver a JSON)

Si surge algún problema crítico:

1. Detener app SQL:
   ```powershell
   # Ctrl+C en terminal de run_sql.py
   ```

2. Arrancar sistema viejo:
   ```powershell
   cd C:\Users\estebanv\PROYECTO-ENGASTADO1git
   python run.py
   ```

3. Apuntar PCs de vuelta a puerto 5000

---

## 📊 Monitoreo

Ver consultas activas:
```sql
SELECT 
    session_id, 
    start_time, 
    status, 
    command, 
    DB_NAME(database_id) AS database_name,
    wait_type,
    wait_time
FROM sys.dm_exec_requests
WHERE database_id = DB_ID('EngastadoDB');
```

Ver locks:
```sql
SELECT * FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID('EngastadoDB');
```

---

## 📞 Contacto

Para dudas técnicas sobre la migración:
- Revisar logs en `logs/app.log`
- Consultar documentación SQL Server
- Verificar proyecto original en paralelo

---

## 📝 TODO

- [ ] Implementar capa repositories/
- [ ] Adaptar app/routes.py a SQL
- [ ] Copiar templates/ y static/
- [ ] Testing de carga concurrente
- [ ] Documentar diferencias vs versión JSON
- [ ] Script de backup automático
- [ ] Monitoring y alertas

---

**Última actualización:** 16 de febrero de 2026
