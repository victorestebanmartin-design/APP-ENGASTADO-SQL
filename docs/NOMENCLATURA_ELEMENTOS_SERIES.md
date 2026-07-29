# Nomenclatura de Elementos — Columnas De Elemento / De Terminal / De Manguito

> **Fichero vivo:** actualizar aquí cuando se añadan nuevos códigos o se cambien reglas.  
> Última revisión: 2026-07-29

---

## Columna `De Elemento Etiquetas` (o `De Elemento`)

### 1. Elemento individual — formato normal

```
TB1
XPM-05
Q16.2
```

Un nombre de elemento sin ningún sufijo especial. Se genera una etiqueta individual y aparece como paquete propio en la pantalla del operario.

---

### 2. Elemento perteneciente a una serie — dos formas

#### Forma A — sufijo en `De Elemento Etiquetas`: `(SXXX)`

```
TB1(S216)
TB1(S216) 1-3
XPM-05(S203) ef17
```

El código de serie se pone **al final** del nombre entre paréntesis: `NOMBRE(SXXX)`.

> **Regla obligatoria:** el código dentro del paréntesis **debe empezar por `S`**.  
> Si no empieza por `S`, la app NO lo trata como serie — el elemento se procesa como individual normal.

---

#### Forma B — código en columna `Observaciones`: `(S_XXXX)`

```
(S_RELES)
(S_BORNES_24V)
```

Si la celda de `Observaciones` contiene un código entre paréntesis con el prefijo `S_`, todos los elementos del Excel que tengan **ese mismo código en sus observaciones** se agrupan como serie.

> El código debe empezar **exactamente por `S_`** (S mayúscula + guion bajo).  
> Puede aparecer en cualquier posición dentro de la celda de observaciones.

---

**Ambas formas producen el mismo resultado:** un paquete grupo padre con el totales, y los sub-elementos listados debajo. Se pueden usar indistintamente según lo que sea más cómodo poner en el Excel.

- Todos los elementos que comparten el mismo código se **agrupan automáticamente** en un paquete virtual de serie.
- En pantalla se muestra primero el **grupo padre** (resumen total) y debajo cada sub-elemento.

**Ejemplo con tres miembros del mismo grupo:**

| De Elemento Etiquetas | Resultado |
|---|---|
| `TB1(S216) 1-3` | sub-elemento 1 del grupo S216 |
| `TB1(S216) 1-6` | sub-elemento 2 del grupo S216 |
| `TB1(S216) 1-7` | sub-elemento 3 del grupo S216 |

→ La app crea un **paquete grupo S216** con el total de cables y terminales, y dentro lista los tres sub-elementos.

---

### 3. Terminal no se engasta — sufijo `*`

```
TB1*
XPM-05*
```

Cuando el nombre del elemento **termina en `*`**, ese terminal **no se engasta** en ese lado.

- El cable sigue apareciendo en el Excel y cuenta para manguitos, pero **no genera crimp** en la pantalla del operario.
- Puede afectar solo al lado De o solo al lado Para (según en qué columna esté el `*`).
- Compatible con series: `TB1(S216)*` también es válido.

---

## Columna `De Terminal` / `Para Terminal`

### 4. Sin terminal — valor `S/T`

```
S/T
```

Indica que ese lado de la fila **no tiene terminal** (cable sin engastar en ese extremo). La app lo ignora al contar crimps y al buscar terminales.

---

## Columna `De Manguito`

### 5. Sin manguito — valor `S/M`

```
S/M
```

Indica que esa fila **no lleva manguito**. La app la omite completamente al cargar la lista de manguitos.

---

## Columna `Observaciones` — código especial para manguitos

### 6. Activo del manguito — `(N)` cuando Longitud = 0

```
(2)
(3)
```

Cuando una fila tiene **Longitud = 0** y en Observaciones aparece un número entre paréntesis, ese número indica a **qué activo de la manguera** se conecta el manguito.

- Solo se usa en manguitos con longitud cero (punto de conexión intermedio sobre la manguera).
- El número hace referencia al activo de la manguera según su posición.

---

## Resumen rápido

| Notación | Columna | Significado |
|---|---|---|
| `ELEMENTO` | De Elemento | Paquete individual normal |
| `ELEMENTO(SXXX)` | De Elemento | Pertenece al grupo de serie SXXX (sufijo al final) |
| `(S_XXXX)` | Observaciones | Pertenece al grupo de serie S_XXXX (código en obs.) |
| `ELEMENTO*` | De Elemento | Terminal en ese lado no se engasta |
| `S/T` | De/Para Terminal | Sin terminal en ese extremo |
| `S/M` | De Manguito | Sin manguito en esa fila |
| `(N)` en obs. | Observaciones | Activo de manguera (solo si Longitud=0) |

---

## Reglas clave

1. **El `(SXXX)` debe ir al final** del nombre de elemento y **empezar por `S`** — `TB1(S216)` sí; `TB1(ABC)` o `TB1(123)` NO son serie, se tratan como elemento individual.
2. **El `(S_XXX)` en observaciones debe empezar por `S_`** — `(S_RELES)` sí; `(RELES)` o `(A_RELES)` NO se reconocen como serie.
2. **El `*` también debe ir al final** — `TB1*` sí; `*TB1` no funciona.
3. **`S/T` y `S/M` son insensibles a mayúsculas** — `s/t` también se reconoce.
4. **Un elemento puede combinar serie y asterisco:** `TB1(S216)*` agrupa y a la vez marca como no-engastar.
5. **Los grupos de serie se fusionan por código**, no por nombre base: `TB1(S216)` y `TB2(S216)` van al mismo grupo S216 aunque el nombre base sea distinto.
