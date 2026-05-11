# Guía de Formato Excel para el Sistema de Engastado

## Hoja requerida

El archivo debe contener una hoja llamada exactamente **`Format`** (con F mayúscula).

---

## Columnas obligatorias

Estas columnas deben existir con este nombre exacto o el archivo no cargará:

| Columna | Descripción |
|---|---|
| `Cod. cable` | Código identificador del cable (ej. `640C10024A`) |
| `Cable / Marca` | Referencia o nombre del cable que ve el operario (ej. `H0420724`) |
| `De Terminal` | Terminal de origen donde va el extremo del cable |
| `Para Terminal` | Terminal de destino donde va el otro extremo |

---

## Columnas opcionales pero recomendadas

Se usan para mostrar información en pantalla y en las etiquetas imprimibles:

| Columna | Descripción |
|---|---|
| `De Elemento` | Nombre del elemento/componente (ej. `K18`, `Q1(S216)`) |
| `Descripción Cable` | Descripción del tipo de cable |
| `Sección` | Sección del cable (ej. `3X0,5+P`, `6X1,5`) |
| `Longitud` | Longitud en metros (número decimal) |
| `Para Elemento` | Elemento de destino (informativo) |
| `Para Pto.Conexión` | Punto de conexión de destino (informativo) |

---

## Reglas de contenido

### Terminales manuales (excluidos del engastado)
- Si un terminal **no se procesa** en la máquina (se hace a mano), añade `*` al final:  
  `640204*`, `641H056*`
- El sistema ignora los cables donde **ambos lados** llevan `*`.
- Si solo un lado lleva `*`, el cable sí aparece pero con 1 solo terminal.

### Series de elementos — patrón `NOMBRE(SXXX)`
- Si varios elementos forman una **serie** que se engasta junta, añade el código de serie entre paréntesis al final del nombre en `De Elemento`:  
  `K18(S216)`, `Q1(S216)`, `Q1(S206)`
- Todos los elementos con el mismo código de serie `(SXXX)` se agrupan en **un único paquete** con etiqueta padre + hijos numerados (`1`, `1.01`, `1.02`...).
- El código de serie puede ser cualquier texto alfanumérico: `S216`, `S206`, `GRP1`, etc.
- **No incluyas** la versión sin sufijo del mismo elemento en el mismo cable  
  (si tienes `K18(S216)` en cable `640C10024A`, no pongas también `K18` en ese mismo cable — se considera duplicado y el sistema lo elimina automáticamente).

---

## Resumen de lo mínimo para que funcione

```
Hoja "Format" con columnas:
  Cod. cable | Cable / Marca | De Terminal | Para Terminal
```

Con solo esas 4 columnas el sistema puede:
- Buscar terminales
- Agrupar cables por terminal
- Construir paquetes de trabajo

Añadiendo `De Elemento`, `Descripción Cable` y `Sección` se obtienen las etiquetas completas para impresión.
