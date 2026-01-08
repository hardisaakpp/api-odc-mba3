# 📋 VALIDACIÓN SINCRONIZACIÓN: ID TIENDA ↔ NOMBRE TIENDA

**Fecha:** 07 de Enero de 2026  
**Estado:** ✅ IMPLEMENTADO Y PROBADO

---

## 📌 REQUISITO

En la hoja **"Tiendas"** debe validarse que:

- Si hay información en la columna **ID TIENDA**, debe haber información en **NOMBRE TIENDA** y viceversa
- Si no hay información en una de las 2 columnas (cuando la otra sí tiene), **interrumpir la subida del Excel al sistema**

---

## ✅ IMPLEMENTACIÓN

### 1️⃣ Archivo Modificado

**[`src/database/services/pedido_parser.py`](src/database/services/pedido_parser.py)**

#### Método: `leer_hoja_tiendas()`

**Cambios principales:**

```python
# VALIDACIÓN ESTRICTA: ID TIENDA y NOMBRE TIENDA deben estar SINCRONIZADOS
# Si hay información en una columna, DEBE haber información en la otra
has_codigo = bool(codigo_bruto is not None and str(codigo_bruto).strip())
has_nombre = bool(nombre_bruto is not None and str(nombre_bruto).strip())

fila_tiene_datos = has_codigo or has_nombre or has_activa

if fila_tiene_datos:
    # Validar sincronización entre ID TIENDA y NOMBRE TIENDA
    # REGLA: Si una está llena, la otra DEBE estar llena
    sincronizacion_correcta = (has_codigo and has_nombre) or (not has_codigo and not has_nombre)

    if not sincronizacion_correcta:
        # ❌ Falta sincronización
        misaligned_rows_tiendas.append(fila_idx)
        # Lanzar ValueError con detalles
```

**Mensaje de error generado:**

```
❌ Validación fallida en hoja 'Tiendas': falta sincronización entre columnas
ID TIENDA y NOMBRE TIENDA. Filas problemáticas: 2, 4.
REGLA: Si hay información en la columna ID TIENDA, DEBE haber información en
NOMBRE TIENDA y viceversa. Las filas completamente vacías se ignoran automáticamente.
```

---

## 🧪 TESTS IMPLEMENTADOS

**Archivo:** [`tests/test_validacion_tiendas_sincronizacion.py`](tests/test_validacion_tiendas_sincronizacion.py)

### Resultados: ✅ 10/10 PASSED

| #   | Test                                                          | Resultado |
| --- | ------------------------------------------------------------- | --------- |
| 1   | `test_tiendas_validas_sincronizadas`                          | ✅ PASSED |
| 2   | `test_tienda_con_id_sin_nombre`                               | ✅ PASSED |
| 3   | `test_tienda_sin_id_con_nombre`                               | ✅ PASSED |
| 4   | `test_tienda_sin_id_sin_nombre`                               | ✅ PASSED |
| 5   | `test_tiendas_completamente_vacias`                           | ✅ PASSED |
| 6   | `test_espacios_en_blanco_son_considerados_vacios`             | ✅ PASSED |
| 7   | `test_id_vacio_nombre_con_espacios`                           | ✅ PASSED |
| 8   | `test_multiples_filas_problematicas`                          | ✅ PASSED |
| 9   | `test_tiendas_con_activo_vacio_pero_id_nombre_completo`       | ✅ PASSED |
| 10  | `test_caso_real_con_multiples_tiendas_validas_y_una_invalida` | ✅ PASSED |

---

## 📊 EJEMPLOS DE VALIDACIÓN

### ❌ CASO 1: ID TIENDA sin NOMBRE TIENDA

```excel
| ID TIENDA  | NOMBRE TIENDA | ACTIVO |
|------------|---------------|--------|
| TRL-QSN    | ROLAND QUI... | SI     |
| TRL-CCR    |               | SI     |  ❌ FALLA AQUÍ
```

**Error:** Validación fallida: falta sincronización entre ID TIENDA y NOMBRE TIENDA. Fila 3.

---

### ❌ CASO 2: NOMBRE TIENDA sin ID TIENDA

```excel
| ID TIENDA  | NOMBRE TIENDA | ACTIVO |
|------------|---------------|--------|
| TRL-QSN    | ROLAND QUI... | SI     |
|            | ROLAND CENTRO | SI     |  ❌ FALLA AQUÍ
```

**Error:** Validación fallida: falta sincronización entre ID TIENDA y NOMBRE TIENDA. Fila 3.

---

### ✅ CASO 3: Ambos campos completos (VÁLIDO)

```excel
| ID TIENDA  | NOMBRE TIENDA | ACTIVO |
|------------|---------------|--------|
| TRL-QSN    | ROLAND QUI... | SI     | ✅
| TRL-CCR    | ROLAND CENTRO | SI     | ✅
```

**Resultado:** Carga exitosa. Catálogo de 2 tiendas.

---

### ✅ CASO 4: Fila completamente vacía (SE IGNORA)

```excel
| ID TIENDA  | NOMBRE TIENDA | ACTIVO |
|------------|---------------|--------|
| TRL-QSN    | ROLAND QUI... | SI     | ✅
|            |               |        | ⏭️ Se ignora
| TRL-AQZ    | ROLAND ANT... | NO     | ✅
```

**Resultado:** Carga exitosa. Catálogo de 2 tiendas (la fila vacía se ignora automáticamente).

---

## 🔄 FLUJO DE VALIDACIÓN

```
┌─────────────────────────────────────┐
│   Lee hoja "Tiendas" del Excel      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Para cada fila (desde fila 2)      │
└──────────────┬──────────────────────┘
               │
               ▼
        ┌──────────────────┐
        │ ¿Fila vacía?     │
        │ (ID y NOMBRE)    │
        └─┬──────────────┬─┘
          │ SÍ (Vacía)   │ NO
          │              │
          ▼              ▼
      IGNORAR      ┌─────────────────────┐
                   │ ¿ID TIENDA tiene    │
                   │ valor?              │
                   └─┬──────────────────┬┘
                     │ SÍ    │ NO
                     ▼       │
                  ┌─────┐    │
                  │¿NOMBRE  │
                  │tiene?   │
                  └─┬───┬──┘
                    │   │
              SÍ ────   NO ─── ERROR ❌
              │        SÍ       │
              ▼                 ▼
            ✅ OK          ┌──────────────┐
                           │ ¿NOMBRE SIN  │
                           │ ID TIENDA?   │
                           └─┬──────────┬─┘
                             │ SÍ  │ NO
                             ▼     ▼
                           ERROR  ✅ OK
                            ❌
```

---

## 📝 CASOS DE USO IMPLEMENTADOS

### Caso A: Validación Estricta ✅

- Ambas columnas (ID TIENDA y NOMBRE TIENDA) tienen valor
- **Resultado:** ✅ Tienda válida, se carga

### Caso B: ID sin NOMBRE ❌

- ID TIENDA tiene valor, NOMBRE TIENDA está vacío
- **Resultado:** ❌ Validación fallida, se interrumpe la carga

### Caso C: NOMBRE sin ID ❌

- NOMBRE TIENDA tiene valor, ID TIENDA está vacío
- **Resultado:** ❌ Validación fallida, se interrumpe la carga

### Caso D: Fila Completamente Vacía ⏭️

- Tanto ID TIENDA como NOMBRE TIENDA están vacíos
- **Resultado:** ⏭️ Fila ignorada automáticamente (no es error)

### Caso E: Múltiples Filas Problemáticas ❌

- Varias filas tienen falta de sincronización
- **Resultado:** ❌ Error detallado listando las filas problemáticas

### Caso F: ACTIVO vacío (pero ID y NOMBRE completos) ✅

- ID TIENDA y NOMBRE TIENDA tienen valor, ACTIVO está vacío
- **Resultado:** ✅ Tienda válida (ACTIVO por defecto = True)

---

## 🚀 COMPORTAMIENTO DEL SISTEMA

### Cuando hay error de sincronización:

1. **Se detiene la lectura** de la hoja "Tiendas"
2. **Se retorna error** con tipo `validation_error`
3. **Se lista** las filas problemáticas (máximo 10)
4. **Se interrumpe** la carga del archivo al sistema
5. **El usuario recibe** un mensaje claro indicando qué filas tienen problemas

### Logs de diagnóstico:

```
❌ FILA 3 (Excel): INCOMPLETA - FALTA SINCRONIZACIÓN ENTRE ID TIENDA Y NOMBRE TIENDA
   ID TIENDA      = 'TRL-CCR'                     →
   NOMBRE TIENDA  = None                          → ❌ VACÍO
   ACTIVO         = 'SI'

   ❌ PROBLEMA: ID TIENDA tiene valor pero NOMBRE TIENDA está vacío
```

---

## 📦 INTEGRACIÓN

### Punto de entrada en la API:

**Archivo:** `src/endpoints/plantillas.py` (endpoint `/subir-excel`)

Los cambios en `pedido_parser.py` se aplican automáticamente cuando:

1. Se carga un archivo Excel con hoja "Tiendas"
2. Se llama a `procesar_tiendas_y_validar_sap_v1_0()`
3. Se ejecuta `service.parser.leer_hoja_tiendas(file_content)`

---

## ✨ CARACTERÍSTICAS

- ✅ **Validación exacta:** Sincronización entre ID TIENDA y NOMBRE TIENDA
- ✅ **Detección inteligente:** Detecta filas vacías vs incompletas
- ✅ **Mensajes claros:** Indica exactamente qué columnas faltan
- ✅ **Logs detallados:** Diagnóstico por fila para facilitar correcciones
- ✅ **Ignorancia de filas vacías:** No trata como error las filas completamente vacías
- ✅ **Normalizacion:** Espacios en blanco = vacío
- ✅ **Escalable:** Maneja múltiples filas problemáticas

---

## 🔍 VALIDACIÓN REALIZADA

```bash
$ pytest tests/test_validacion_tiendas_sincronizacion.py -v

================================ test session starts ==================================
collected 10 items

test_tiendas_validas_sincronizadas PASSED                                    [ 10%]
test_tienda_con_id_sin_nombre PASSED                                         [ 20%]
test_tienda_sin_id_con_nombre PASSED                                         [ 30%]
test_tienda_sin_id_sin_nombre PASSED                                         [ 40%]
test_tiendas_completamente_vacias PASSED                                     [ 50%]
test_espacios_en_blanco_son_considerados_vacios PASSED                       [ 60%]
test_id_vacio_nombre_con_espacios PASSED                                     [ 70%]
test_multiples_filas_problematicas PASSED                                    [ 80%]
test_tiendas_con_activo_vacio_pero_id_nombre_completo PASSED                [ 90%]
test_caso_real_con_multiples_tiendas_validas_y_una_invalida PASSED          [100%]

========================== 10 passed in 2.30s ===========================
```

---

## 📋 RESUMEN

| Aspecto                | Descripción                                                        |
| ---------------------- | ------------------------------------------------------------------ |
| **Regla Principal**    | Si hay info en ID TIENDA → DEBE haber en NOMBRE TIENDA y viceversa |
| **Condición de Falla** | Sincronización incorrecta entre las dos columnas                   |
| **Condición de Éxito** | Ambas columnas tienen valor o ambas están vacías                   |
| **Filas Vacías**       | Se ignoran automáticamente (no son error)                          |
| **Espacios en Blanco** | Se consideran como vacío                                           |
| **Mensajes de Error**  | Claros y con número de fila exacto                                 |
| **Logs**               | Detallados para diagnóstico rápido                                 |
| **Tests**              | 10/10 ✅ Todos pasando                                             |

---

**✅ Implementación completada y validada el 07/01/2026**
