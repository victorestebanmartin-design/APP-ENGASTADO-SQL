# Sistema de Engastado Automático — Descripción Completa

**Versión:** 2.0 SQLite  
**Stack:** Python · Flask · SQLite · HTML/CSS/JS vanilla  
**Acceso:** Aplicación web local, puerto 5001 (`http://localhost:5001`)

---

## ¿Qué hace esta aplicación?

Es un sistema de gestión integral para el proceso de engastado de cables en producción. Controla todo el ciclo: desde la carga del listado de cables (Excel) hasta el engastado físico en máquina, pasando por la creación de bonos de trabajo, asignación a carros, etiquetado, y preparación de consumibles (manguitos y mangueras).

---

## Módulos principales

### 1. Engastado V3 — Módulo de operación (`/v3`)

Es el módulo principal que usan los operarios en la máquina de engastado.

**Flujo de trabajo:**
1. El operario escanea su código de barras (identificación de sesión)
2. El sistema muestra los terminales pendientes del bono activo asignado a su carro
3. Los terminales se agrupan inteligentemente por máquina (terminal aplicadora)
4. El operario va confirmando cada engastado; el sistema actualiza el progreso en tiempo real
5. Cuando se completan todos los terminales de un paquete, se libera automáticamente

**Características:**
- Lector de códigos de barras integrado
- Agrupado por máquina para minimizar cambios de herramienta
- Sesiones de trabajo con bloqueo (evita que dos operarios trabajen el mismo paquete)
- Progreso en tiempo real sincronizado entre pestañas

---

### 2. Administración (`/admin`)

Panel de configuración del sistema. Acceso solo para supervisores.

**Lo que permite:**
- **Subir archivos Excel** con los listados de cables de corte
- **Ver y eliminar archivos** cargados en el sistema
- **Gestionar terminales:** activar/desactivar terminales, asignar terminales a máquinas
- **Gestionar máquinas y puestos:** configurar qué máquinas hay en cada puesto
- **Colores de cable:** asignar color visual a cada código de cable
- **Actualizaciones del sistema:** comprobar y aplicar actualizaciones desde el repositorio
- **Impresora de etiquetas:** configuración de la impresora ZPL

---

### 3. Gestión de Bonos (`/proyectos`)

Un **bono** es la unidad de trabajo diaria: agrupa órdenes de producción que se van a fabricar juntas.

**Flujo:**
1. Se crean órdenes de producción (por código de corte y cantidad)
2. Se genera un bono agrupando varias órdenes
3. El bono se asigna a uno o varios **carros** (1 a 6 disponibles)
4. Cada carro lleva físicamente las piezas a la máquina
5. Se hace seguimiento del progreso del bono

**Entidades:**
- **Proyectos:** archivos Excel cargados, representan un corte/proyecto
- **Bonos:** agrupación de órdenes con fecha, estado y progreso
- **Carros:** 6 carros físicos (1-6), cada uno puede llevar un bono activo

---

### 4. Visualización (`/visualizacion`)

Dashboard de monitoreo en tiempo real, pensado para pantallas externas (TV, pantalla de planta).

**Muestra:**
- Estado de cada bono activo
- Progreso por carro (barra de porcentaje)
- Órdenes completadas vs. pendientes
- Se actualiza automáticamente sin recargar página

---

### 5. Órdenes de Producción (`/registro-ordenes`)

Registro y control de las órdenes de fabricación.

**Permite:**
- Crear órdenes manualmente (código de corte, cantidad, prioridad, fecha de entrega)
- Ver el listado de órdenes con su estado (`pendiente` / `en_bono` / `en_proceso` / `completado`)
- Editar y eliminar órdenes
- Planificar qué órdenes entran en el próximo bono

**Estados de una orden:**
```
pendiente → en_bono → en_proceso → completado
                                  cancelado
```

---

### 6. Etiquetas (`/etiquetas`)

Genera e imprime etiquetas identificativas para los elementos de cable de un corte.

**Características:**
- Lee un Excel de corte y agrupa cables por `Cod. cable` + `De Elemento`
- Asigna número de etiqueta a cada grupo (individual o en serie)
- Genera el HTML de impresión: formato A4 con 65 etiquetas troqueladas (5×13 mm)
- Guarda los números de etiqueta en BD (`etiquetas_elementos`) para que otros módulos (manguitos, mangueras) puedan ordenar por número de etiqueta
- Soporta sub-grupos con notación `X.YY` (ej: `5.01`, `5.02`)

---

### 7. Manguitos (`/manguitos`)

Gestión de los manguitos (ferrules/terminales de protección) que se colocan en los extremos de los cables.

El módulo tiene **tres pestañas:**

#### Guiado de colocación
- Carga un Excel de corte y muestra los manguitos agrupados por elemento
- Navega elemento a elemento con ← → o Enter/Espacio
- Muestra visualmente cada manguito con su color, marca y conexiones (De Elemento/Punto → Para Elemento/Punto)
- Filtra por tipo de manguito (ristra) usando los botones de colores
- **Orden:** por número de etiqueta (si hay etiquetas cargadas en BD), garantizando el mismo orden que el operario tiene en el carro

#### Generar TXT de pedido
- A partir de un Excel ya subido al sistema, genera un fichero `.txt` por código de manguito
- El TXT tiene el formato requerido por el proveedor para hacer el pedido
- Los manguitos se ordenan por número de etiqueta
- Si hay más de un código, se descarga un `.zip` con todos los TXT

#### TXT desde Excel propio
- Igual que el anterior pero el usuario sube un Excel en el momento (sin que esté en el sistema)
- El orden preserva el del Excel (no reordena por etiqueta)

**Formato de línea del TXT:**
```
De_Marca, De_Elemento De_Pto_Conexion,, Para_Elemento Para_Pto_Conexion, De_Elemento De_Pto_Conexion, De_Marca, Para_Elemento Para_Pto_Conexion,,
```

---

### 8. Preparación de Mangueras (`/mangueras`)

Módulo de apoyo para la preparación de mangueras antes de la fase de engastado.

- Lee las filas del Excel donde la columna `Observaciones` contiene instrucciones de pelado (`<-` o `->`)
- Muestra cada instrucción de forma guiada al operario
- Indica qué extremo pelar, cuánto, y el tipo de preparación

---

## Base de datos (SQLite)

Fichero: `data/engastado.db`

| Tabla | Descripción |
|---|---|
| `proyectos` | Archivos Excel cargados |
| `bonos` | Bonos de producción |
| `carros` | 6 carros físicos (1-6) |
| `ordenes_produccion` | Órdenes con estado y asignación |
| `codigos_cortes` | Códigos de corte registrados |
| `puestos` | Puestos de trabajo en planta |
| `maquinas` | Máquinas de engastado por puesto |
| `maquinas_terminales` | Terminales que puede hacer cada máquina |
| `terminales_desactivados` | Terminales excluidos del proceso |
| `etiquetas_elementos` | Grupos de etiqueta por cable+elemento |
| `grupos_etiquetas` | Historial de impresiones ZPL |
| `etiquetas_pendientes` | Cola de etiquetas a reimprimir |
| `app_state` | Estado global de la app (clave-valor) |

---

## Flujo de trabajo típico

```
1. ADMIN sube Excel de corte
        ↓
2. ETIQUETAS genera y numera grupos → BD etiquetas_elementos
        ↓
3. ÓRDENES crea órdenes por código de corte
        ↓
4. BONOS agrupa órdenes → asigna a carro
        ↓
5. MANGUITOS prepara pedido de ferrules (TXT proveedor)
   MANGUERAS prepara pelados previos
        ↓
6. ENGASTADO V3 — operario escanea y confirma terminal a terminal
        ↓
7. VISUALIZACIÓN monitorea progreso en tiempo real
```

---

## Estructura de ficheros clave

```
app/
  routes.py          — Toda la lógica de rutas y API (~4000 líneas)
  excel_manager.py   — Lectura y parseo de Excels de corte
  __init__.py        — Inicialización Flask + SQLAlchemy

repositories/        — Acceso a BD por entidad
  bono_repository.py
  orden_repository.py
  maquina_repository.py
  puesto_repository.py
  ...

templates/           — HTML (Jinja2)
static/
  js/                — Lógica frontend por módulo
  css/               — Estilos
  img/

data/
  engastado.db       — Base de datos SQLite
  cortes/            — Excels de corte subidos
  manguitos/         — TXTs generados
```

---

## Arranque rápido

```bash
# Activar entorno virtual
.\venv\Scripts\Activate.ps1

# Arrancar servidor (puerto 5001)
python run_sql.py
```

Acceder a `http://localhost:5001`
