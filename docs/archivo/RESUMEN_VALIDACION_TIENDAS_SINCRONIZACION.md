## 📋 RESUMEN: Validación Sincronización ID TIENDA ↔ NOMBRE TIENDA

### ✅ Implementación Completada

Se ha implementado validación estricta en la hoja **"Tiendas"** para asegurar sincronización entre las columnas **ID TIENDA** y **NOMBRE TIENDA**.

---

### 🎯 Regla de Validación

```
SI hay información en ID TIENDA → DEBE haber información en NOMBRE TIENDA
SI hay información en NOMBRE TIENDA → DEBE haber información en ID TIENDA
SI una está vacía → la otra TAMBIÉN debe estar vacía
```

---

### ⚙️ Cambios Realizados

**Archivo: `src/database/services/pedido_parser.py`**

Método: `leer_hoja_tiendas()` (líneas ~1520-1650)

**Lógica implementada:**

```python
# Para cada fila de datos:
has_codigo = bool(codigo_bruto is not None and str(codigo_bruto).strip())
has_nombre = bool(nombre_bruto is not None and str(nombre_bruto).strip())

# Validar sincronización
sincronizacion_correcta = (has_codigo and has_nombre) or (not has_codigo and not has_nombre)

if fila_tiene_datos and not sincronizacion_correcta:
    # ❌ ERROR: Falta sincronización
    misaligned_rows_tiendas.append(fila_idx)
    raise ValueError("Falta sincronización entre ID TIENDA y NOMBRE TIENDA")
```

---

### 🧪 Tests Implementados

**Archivo: `tests/test_validacion_tiendas_sincronizacion.py`**

✅ **10/10 Tests Pasados:**

1. ✅ Tiendas válidas sincronizadas
2. ✅ Tienda con ID sin NOMBRE → Rechazada
3. ✅ Tienda con NOMBRE sin ID → Rechazada
4. ✅ Tienda sin ID sin NOMBRE → Ignorada (no error)
5. ✅ Tiendas completamente vacías → Ignoradas
6. ✅ Espacios en blanco = vacío → Rechazada
7. ✅ ID vacío + NOMBRE con espacios → Rechazada
8. ✅ Múltiples filas problemáticas → Detectadas todas
9. ✅ ACTIVO vacío pero ID+NOMBRE completo → Aceptado
10. ✅ Caso real con múltiples tiendas → Validación correcta

---

### 📊 Ejemplos de Comportamiento

#### ❌ FALLA: ID sin NOMBRE

```
Fila 3: ID TIENDA="TRL-CCR", NOMBRE TIENDA=[VACÍO]
Error: Falta sincronización. ID TIENDA tiene valor pero NOMBRE TIENDA está vacío
```

#### ❌ FALLA: NOMBRE sin ID

```
Fila 4: ID TIENDA=[VACÍO], NOMBRE TIENDA="ROLAND CENTRO"
Error: Falta sincronización. NOMBRE TIENDA tiene valor pero ID TIENDA está vacío
```

#### ✅ ÉXITO: Ambos presentes

```
Fila 2: ID TIENDA="TRL-QSN", NOMBRE TIENDA="ROLAND QUICENTRO NORTE"
Resultado: Tienda cargada exitosamente
```

#### ⏭️ IGNORADO: Ambos vacíos

```
Fila 5: ID TIENDA=[VACÍO], NOMBRE TIENDA=[VACÍO]
Resultado: Fila ignorada (sin error)
```

---

### 🚀 Flujo de Validación

```
Excel cargado
    │
    ▼
Lee hoja "Tiendas"
    │
    ├─ Para cada fila:
    │  │
    │  ├─ ¿Fila completamente vacía?
    │  │  └─ SÍ: Ignorar → Siguiente fila
    │  │
    │  ├─ ¿ID TIENDA tiene valor Y NOMBRE TIENDA tiene valor?
    │  │  └─ SÍ: ✅ Válida → Cargar tienda
    │  │
    │  ├─ ¿Ambos están vacíos?
    │  │  └─ SÍ: Ignorar → Siguiente fila
    │  │
    │  └─ SINO: ❌ Falta sincronización → Error
    │
    ▼
¿Hay errores de sincronización?
    │
    ├─ SÍ: ❌ Interrumpir carga (validation_error)
    │       Mostrar filas problemáticas
    │
    └─ NO: ✅ Continuar con SAP validation
```

---

### 📦 Integración Automática

La validación se aplica automáticamente cuando:

1. Usuario sube un Excel con hoja "Tiendas"
2. Sistema llama a `leer_hoja_tiendas()`
3. Validador revisa sincronización ID TIENDA ↔ NOMBRE TIENDA
4. Si hay error → Bloquea la carga con mensaje claro
5. Si OK → Continúa con validación SAP

---

### 📋 Mensajes de Error

**Cuando hay problemas de sincronización:**

```
❌ Validación fallida en hoja 'Tiendas': falta sincronización
entre columnas ID TIENDA y NOMBRE TIENDA.

Filas problemáticas: 3, 5, 8

REGLA: Si hay información en la columna ID TIENDA, DEBE haber
información en NOMBRE TIENDA y viceversa. Las filas completamente
vacías se ignoran automáticamente.

Detalles:
- Fila 3: ID TIENDA="TRL-CCR" | NOMBRE TIENDA=[VACÍO]
- Fila 5: ID TIENDA=[VACÍO] | NOMBRE TIENDA="ROLAND CENTRO"
- Fila 8: ID TIENDA="TRL-AQZ" | NOMBRE TIENDA=[VACÍO]
```

---

### ✨ Características de la Implementación

- ✅ Sincronización obligatoria entre ID y NOMBRE
- ✅ Detección inteligente de filas vacías vs incompletas
- ✅ Espacios en blanco = considerados como vacío
- ✅ Mensajes de error específicos por fila
- ✅ Logs detallados para diagnóstico
- ✅ No requiere cambios en la API ni endpoints
- ✅ Completamente probado (10/10 tests)
- ✅ Escalable para múltiples filas problemáticas

---

### 📁 Archivos Modificados

| Archivo                                           | Cambios                                     |
| ------------------------------------------------- | ------------------------------------------- |
| `src/database/services/pedido_parser.py`          | ✏️ Actualizado método `leer_hoja_tiendas()` |
| `tests/test_validacion_tiendas_sincronizacion.py` | ✅ Nuevo archivo - 10 tests                 |
| `docs/VALIDACION_SINCRONIZACION_TIENDAS.md`       | 📄 Documentación completa                   |

---

### 🔄 Flujo de Carga Actualizado

**ANTES:**

```
Excel → Leer Tiendas → Validar SAP → Cargar
```

**AHORA:**

```
Excel → Leer Tiendas → ✅ Validar Sincronización ID↔NOMBRE → Validar SAP → Cargar
                       ❌ Si hay error de sincronización → Interrumpir
```

---

**✅ Completado: 07 de Enero de 2026**
