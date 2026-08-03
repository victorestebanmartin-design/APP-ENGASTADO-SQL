# Nomenclatura de Observaciones — Preparación de Mangueras

> **Fichero vivo:** actualizar aquí cuando se añadan nuevos tokens o se cambien reglas.  
> Última revisión: 2026-08-03

---

## Formato actual — columnas separadas por lado

Cada lado tiene su propia columna en el Excel. Los tokens se escriben directamente, sin `<-` ni `->`:

| Columna | Contiene | Ejemplo |
|---|---|---|
| `Instrucciones Mangueras DE` | tokens del lado De | `PM150/M70` |
| `Instrucciones Mangueras PARA` | tokens del lado Para | `PM200/MCORTAR` |

- Se pueden rellenar una sola o las dos columnas — si una está vacía, ese lado queda sin instrucciones.
- Los tokens dentro de cada columna se separan con `/`.

---

## Formato legacy — columna Observaciones (mantener hasta migrar todos los Excels)

> ⚠️ **A eliminar** una vez todos los ficheros usen las columnas nuevas.

```
[texto libre] <-[instrucciones lado DE] // [instrucciones lado PARA]->
```

- `<-` marca el **lado De** — las instrucciones van **después** de `<-`
- `->` marca el **lado Para** — las instrucciones van **antes** de `->`
- `//` ó `$` separa ambos lados
- El texto libre antes de `<-` se ignora

---

## Tokens disponibles (válidos en cada lado)

| Token | Qué hace | Ejemplo |
|---|---|---|
| `PM{n}` | Pelado de **manguera** en mm | `PM150` → pelar 150 mm |
| `M{n}` | Pelado de **malla** en mm (valor específico) | `M70` → pelar malla 70 mm |
| `MCORTAR` | **Cortar** la malla (no se pela, se corta) | `MCORTAR` |
| `MRS` | Malla **hacia atrás**, sin retráctil | `MRS` |
| `MRC` | Malla **hacia atrás**, con retráctil (sin medida) | `MRC` |
| `MRC{n}` | Malla hacia atrás con retráctil, medida en mm | `MRC30` → retráctil 30 mm |
| `A{n}` | Pelado de **todos los activos** en mm | `A150` → activos a 150 mm |
| `A{activo}_{n}` | Pelado de un **activo concreto** en mm | `A2_40` → activo 2 a 40 mm |

### Valores por defecto (cuando se omite un token)

| Campo | Si no se especifica… |
|---|---|
| Malla (`M`) | Queda igual que `PM` |
| Activos (`A`) | Quedan igual que `PM` |

---

## Ejemplos completos

### Ambos lados con malla específica
```
<-PM150/M70 // PM200/MCORTAR->
```
- **Lado De:** manguera 150 mm · malla 70 mm
- **Lado Para:** manguera 200 mm · **cortar malla**

---

### Activos y malla hacia atrás
```
<-PM120/M110/A150 // PM300/MRS->
```
- **Lado De:** manguera 120 mm · malla 110 mm · activos 150 mm
- **Lado Para:** manguera 300 mm · malla hacia atrás sin retráctil

---

### Retráctil con medida
```
<-PM80/MRC30 // PM200->
```
- **Lado De:** manguera 80 mm · malla hacia atrás con retráctil de 30 mm
- **Lado Para:** manguera 200 mm · malla = 200 mm (= PM) · activos = 200 mm

---

### Texto libre antes de las instrucciones (válido)
```
MANGUERA 1144 (Placa) <-PM150/M70 // PM200/MCORTAR->
```
- El texto `MANGUERA 1144 (Placa)` se ignora — solo se leen las instrucciones tras `<-`

---

### Solo un lado definido
```
<-PM50
```
- **Lado De:** manguera 50 mm · malla = 50 mm · activos = 50 mm
- **Lado Para:** sin instrucciones

---

### Solo lado Para
```
PM100/A2_40->
```
- **Lado Para:** manguera 100 mm · activo nº 2 a 40 mm · resto de activos = 100 mm

---

## Reglas y avisos

1. **`MCORTAR` y `M_CORTAR` son equivalentes** — ambas formas funcionan.
2. **Solo un token de malla por lado** — no mezclar `M{n}`, `MCORTAR`, `MRS`, `MRC`, `MRC{n}` en el mismo lado.
3. **`A{n}` y `A{activo}_{n}` no se mezclan en el mismo lado** — si usas `A150` se aplica a todos los activos; si usas `A2_40` solo afecta al activo 2 (el resto queda a PM).
4. **Mayúsculas/minúsculas indiferentes** — `pm150`, `MCORTAR`, `mrc30` son igualmente válidos.
5. **Separador de lados:** preferir `//`; el `$` también funciona pero es menos legible.
