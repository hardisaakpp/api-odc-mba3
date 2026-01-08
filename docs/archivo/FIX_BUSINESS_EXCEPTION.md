# 🔧 Fix: BusinessException no llegaba al Exception Handler

## 🐛 Problema Identificado

La `BusinessException` con datos estructurados que lanzábamos en `pedido_service.py` **no llegaba al exception handler global**. En su lugar, era capturada por un `except Exception` genérico y convertida en un resultado con `status = "error"`.

### Síntomas

El frontend recibía:
```json
{
  "error": "Error al procesar plantilla: ['No se puede persistir...']",
  "type": "http_exception",  // ← Debería ser "business_exception"
  "status_code": 400
}
```

En lugar de:
```json
{
  "type": "business_exception",
  "error_code": "PRODUCTOS_NO_VALIDOS_SAP",
  "message": "No se puede persistir el pedido...",
  "validacion": {
    "productos": {
      "no_encontrados": ["MTF123.9899"],
      // ...
    }
  }
}
```

---

## 🔍 Causa Raíz

En `src/database/services/pedido_service.py`, el método `validar_y_procesar_archivo_excel` tenía:

```python
def validar_y_procesar_archivo_excel(...):
    resultado = {...}
    
    try:
        # ... procesamiento ...
        
        # Aquí se lanza BusinessException
        raise BusinessException(
            message="...",
            error_code="PRODUCTOS_NO_VALIDOS_SAP",
            data={...}
        )
        
    except Exception as e:  # ← ❌ PROBLEMA: Captura TODAS las excepciones
        logger.error(f"❌ Error al procesar plantilla Excel: {e}")
        resultado["status"] = "error"
        resultado["errores"].append(str(e))  # ← Convierte a string
        return resultado  # ← Retorna dict en lugar de lanzar excepción
```

### Flujo del Error

1. Se lanza `BusinessException` con datos estructurados
2. El `except Exception` la captura (porque `BusinessException` hereda de `Exception`)
3. Convierte el mensaje a string: `str(BusinessException(...))`
4. Lo agrega a `resultado["errores"]` (lista)
5. Retorna con `status = "error"`
6. El endpoint ve `status == "error"` y lanza `HTTPException` genérico con `detail=resultado.get('errores')`
7. El HTTPException convierte la lista a string: `f"Error al procesar plantilla: {['mensaje']}"`
8. El exception handler de `HTTPException` devuelve `type = "http_exception"`

---

## ✅ Solución Aplicada

### 1️⃣ Agregar import a nivel módulo

**Archivo**: `src/database/services/pedido_service.py`

```python
# Al inicio del archivo (línea 19)
from src.exceptions import BusinessException
```

### 2️⃣ Capturar BusinessException ANTES del except genérico

**Archivo**: `src/database/services/pedido_service.py` (línea 874)

```python
def validar_y_procesar_archivo_excel(...):
    resultado = {...}
    
    try:
        # ... procesamiento ...
        
        raise BusinessException(
            message="...",
            error_code="PRODUCTOS_NO_VALIDOS_SAP",
            data={...}
        )
        
    except BusinessException:  # ← ✅ NUEVO: Captura específica
        # Re-lanzar para que el exception handler global la maneje
        # NO capturar aquí, debe llegar al handler con sus datos estructurados
        raise
    except Exception as e:
        # Solo captura otras excepciones
        logger.error(f"❌ Error al procesar plantilla Excel: {e}")
        resultado["status"] = "error"
        resultado["errores"].append(str(e))
        return resultado
```

### 3️⃣ Eliminar import local redundante

```python
# ANTES (línea 725):
if sap_obligatorio and not validacion_sap.get("todos_validos", False):
    from src.exceptions import BusinessException  # ← Redundante
    no_encontrados = ...

# DESPUÉS:
if sap_obligatorio and not validacion_sap.get("todos_validos", False):
    no_encontrados = ...  # ← Import ya está a nivel módulo
```

---

## 🎯 Resultado

### Flujo Correcto Ahora

1. Se lanza `BusinessException` con datos estructurados
2. El `except BusinessException` la captura
3. **La re-lanza inmediatamente** con `raise`
4. Llega al exception handler global de `src/middleware/exception_handlers.py`
5. El handler devuelve la respuesta estructurada completa:

```json
{
  "type": "business_exception",
  "error_code": "PRODUCTOS_NO_VALIDOS_SAP",
  "message": "No se puede persistir el pedido: existen productos no válidos en SAP",
  "error": "No se puede persistir el pedido...",  // Compatibilidad
  "validacion": {
    "productos": {
      "no_encontrados": ["MTF123.9899"],
      "errores": [],
      "total_validos": 24,
      "total_invalidos": 1
    }
  },
  "validacion_sap": {
    "validos": 24,
    "no_encontrados": 1,
    "errores": 0,
    "warnings": 0,
    "total_codigos": 25,
    "todos_validos": false
  },
  "status_code": 400
}
```

---

## 📋 Archivos Modificados

1. ✅ `src/database/services/pedido_service.py`
   - Agregado import de `BusinessException` a nivel módulo
   - Agregado `except BusinessException` que re-lanza la excepción
   - Eliminado import local redundante

---

## ✅ Verificación

- ✅ Sin errores de sintaxis: `py_compile` exitoso
- ✅ Servidor recargado automáticamente: 3 reloads detectados
- ✅ Frontend recibirá la estructura completa de datos

---

## 🧪 Cómo Probar

1. Subir un archivo Excel con productos que no existen en SAP
2. Verificar que el error tenga:
   - `type: "business_exception"`
   - `error_code: "PRODUCTOS_NO_VALIDOS_SAP"`
   - `validacion.productos.no_encontrados` con la lista completa
3. El frontend puede acceder directamente a `errorData.validacion.productos.no_encontrados`

---

## 📚 Lecciones Aprendidas

1. **Orden de los except importa**: Los `except` más específicos deben ir ANTES de los genéricos
2. **Re-lanzar excepciones**: Usar `raise` sin argumentos re-lanza la excepción actual preservando su tipo y datos
3. **Exception hierarchy**: `except Exception` captura todas las excepciones custom a menos que las captures antes
4. **Debugging**: Los logs del servidor muestran claramente si una excepción fue capturada o no

---

## 🔗 Ver También

- `docs/ESTRUCTURA_RESPUESTA_ERRORES.md` - Estructura completa de respuestas de error
- `src/exceptions.py` - Definición de BusinessException
- `src/middleware/exception_handlers.py` - Exception handlers globales
