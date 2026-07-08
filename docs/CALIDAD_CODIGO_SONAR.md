# Guía de Calidad de Código — Hallazgos Recurrentes de Sonar

Documento generado a partir de la campaña de correcciones en la rama `ci/pipeline-azure`.
Cubre los patrones más repetidos para que no se vuelvan a introducir en desarrollos futuros.

---

## S3776 — Cognitive Complexity demasiado alta

**Regla:** ninguna función debe superar CC = 15.

### Cómo se acumula la complejidad

| Construcción | Costo |
|---|---|
| `if` / `for` / `while` al nivel 0 | +1 |
| Cada nivel de anidamiento adicional | +1 extra por nivel |
| `elif` / `except` | +1 (plano, sin bonus) |
| `else` | 0 |
| `try` | +1 (plano) |
| `and` / `or` en una secuencia nueva | +1 por secuencia |
| Expresión ternaria `a if cond else b` | +1 + bonus de anidamiento |
| Función anidada (`def` dentro de `def`) | suma toda su CC a la externa |

### Patrón de corrección: extracción a helpers privados

Cada helper extraído elimina *toda* su CC del padre. El punto de llamada no agrega nada.

```python
# MAL — CC acumulada en un solo lugar
def procesar(datos):
    for item in datos:                          # +1
        if item.tipo == "A":                    # +2
            for sub in item.subs:               # +3
                if sub.activo:                  # +4
                    resultado = sub.valor * 2
        elif item.tipo == "B":                  # +1
            ...

# BIEN — helpers privados, CC distribuida
def _procesar_tipo_a(item):
    for sub in item.subs:                       # +1
        if sub.activo:                          # +2
            resultado = sub.valor * 2

def procesar(datos):
    for item in datos:                          # +1
        if item.tipo == "A":                    # +2
            _procesar_tipo_a(item)
        elif item.tipo == "B":                  # +1
            ...
```

### Convenciones para helpers

- Prefijo `_` → privado al módulo o a la clase.
- Nombre que describe *qué hace*, no cómo lo hace.
- Máximo un nivel de anidamiento en el helper (si hay más, extraer otro nivel).
- Si el helper necesita retornar un "early exit" al padre, usar tupla `(resultado, early_response_or_None)`:

```python
def _resolver_ids(repo, id_param, source):
    if not id_param:
        return [], JSONResponse(status_code=404, ...)   # señal de salida temprana
    ids = repo.buscar(id_param)
    return ids, None                                     # flujo normal

# En el padre:
ids, early = _resolver_ids(repo, oc_id, source)
if early is not None:
    return early
```

### Señales de alerta al escribir código nuevo

- Más de 3 niveles de `if` anidados → extraer.
- Un `for` con `try/except` dentro + más lógica → extraer el cuerpo del `for`.
- Una función que supera las ~60 líneas → revisar CC antes de commitear.
- Ternarias anidadas (`a if x else (b if y else c)`) → extraer a función o variable temporal.

---

## S1481 — Variable o parámetro local no utilizado

**Regla:** no declarar variables ni parámetros que no se usen.

### Parámetro no usado en función

```python
# MAL
def _handle_exportar(request, user, pedido_id):
    # pedido_id nunca se referencia dentro
    datos = request.json()
    ...

# BIEN — eliminarlo si la firma no es un contrato externo
def _handle_exportar(request, user):
    datos = request.json()
    ...

# BIEN — si la firma es fija (callback, interfaz), usar _ para señalar intención
def _handle_exportar(request, user, _pedido_id):
    ...
```

### Variable local asignada pero nunca leída

```python
# MAL
resultado = calcular()
return {"ok": True}   # resultado nunca se usa

# BIEN — eliminar la asignación
calcular()
return {"ok": True}

# BIEN — si el valor se necesitará, documentar por qué se calcula ahora
```

### Cuándo NO eliminar

- El parámetro forma parte de una firma de callback que un framework invoca (FastAPI, Celery).  
  En ese caso cambiar a `_nombre` para indicar que es intencional.
- La variable se usa como efecto secundario (ej. context manager sin `as`).

---

## S1192 — Literal de cadena duplicado (≥ 3 ocurrencias)

**Regla:** si un string literal aparece 3 o más veces en el mismo archivo, extraerlo a una constante.

```python
# MAL — "application/json" aparece 4 veces
headers = {"Content-Type": "application/json"}
...
if response.headers.get("Content-Type") == "application/json":
...

# BIEN
_CONTENT_TYPE_JSON = "application/json"

headers = {"Content-Type": _CONTENT_TYPE_JSON}
...
if response.headers.get("Content-Type") == _CONTENT_TYPE_JSON:
```

### Convenciones de nomenclatura

| Alcance | Estilo | Ejemplo |
|---|---|---|
| Módulo (privado) | `_MAYUSCULAS` | `_LABEL_NUMERO_PEDIDO` |
| Clase | `_MAYUSCULAS` dentro de la clase | `_SECCION_INFO` |
| Módulo (público / exportado) | `MAYUSCULAS` | `DEFAULT_TIMEOUT` |

### Casos frecuentes en este proyecto

- Literales HTML/CSS repetidos en plantillas de correo.
- Claves de diccionario que se referencian en múltiples métodos de la misma clase.
- Nombres de campos SAP o de base de datos usados en validaciones y en queries.

---

## F401 — Import no utilizado

**Regla:** no importar módulos o símbolos que no se usen en el archivo.

```python
# MAL
import datetime          # si solo se usa ahora_naive() de timezone
from typing import List  # si Python 3.9+ y se usa list[] nativo

# BIEN — eliminar el import
```

**Excepción:** imports necesarios como efecto secundario (registro de handlers, plugins).  
En ese caso añadir `# noqa: F401` al final de la línea para silenciar el warning con intención explícita.

---

## F541 — f-string sin interpolación

**Regla:** no usar `f"..."` si la cadena no contiene `{variable}`.

```python
# MAL
mensaje = f"Error al procesar el pedido"

# BIEN
mensaje = "Error al procesar el pedido"
```

---

## S5659 — Verificación de JWT sin validar la firma

**Regla:** nunca llamar a `jwt.decode()` con `algorithms=None` o sin especificar el algoritmo esperado.

```python
# MAL — acepta cualquier algoritmo, incluyendo "none"
payload = jwt.decode(token, SECRET, algorithms=None)

# BIEN
payload = jwt.decode(token, SECRET, algorithms=["HS256"])
```

---

## S1166 — Bloque except que no usa la excepción capturada

**Regla:** si capturas una excepción con `except X as e`, usa `e` (en un log, re-raise, o mensaje).  
Si no la necesitas, captura sin `as`.

```python
# MAL
except Exception as e:
    pass                    # e declarada pero nunca usada

# BIEN — si no necesitas la excepción
except Exception:
    pass

# BIEN — si quieres loguear
except Exception as e:
    logger.warning(f"Error ignorado: {e}")
```

---

## S112 — Bloque except vacío (bare except)

**Regla:** nunca usar `except:` sin especificar el tipo.  
Captura incluso `SystemExit`, `KeyboardInterrupt` y `GeneratorExit`.

```python
# MAL
try:
    conectar()
except:
    pass

# BIEN
try:
    conectar()
except Exception:
    pass
```

---

## Checklist antes de hacer commit

1. **CC nueva función > 15?** → extraer helpers antes de commitear.
2. **Parámetros en la firma que no aparecen en el cuerpo?** → eliminar o prefijo `_`.
3. **Variables asignadas pero no leídas?** → eliminar.
4. **Mismo string literal ≥ 3 veces en el archivo?** → constante.
5. **`f"..."` sin `{}`?** → quitar la `f`.
6. **`import X` sin usar X?** → quitar el import.
7. **`except X as e:` sin usar `e`?** → quitar el `as e`.
8. **`except:`?** → especificar `except Exception:`.

---

## Referencias

- [SonarSource — Python rules](https://rules.sonarsource.com/python/)
- `pyproject.toml` de este proyecto — configuración de Ruff (linter local complementario)
- `.pre-commit-config.yaml` — hooks que se ejecutan en cada commit
