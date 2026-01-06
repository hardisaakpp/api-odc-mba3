# Estructura de Respuestas de Error - Backend

## 🎯 Objetivo

Proporcionar respuestas de error estructuradas que el frontend pueda procesar fácilmente sin necesidad de hacer regex sobre mensajes de texto.

---

## 📋 Estructura General de Error BusinessException

### ✅ Nueva Estructura (Mejorada)

```json
{
  "type": "business_exception",
  "error_code": "PRODUCTOS_NO_VALIDOS_SAP",
  "message": "No se puede persistir el pedido: existen productos no válidos en SAP. Productos no encontrados en SAP: MTF123.9899",
  "status_code": 400,
  "validacion": {
    "productos": {
      "no_encontrados": ["MTF123.9899", "ABC456.7890"],
      "errores": ["DEF789.1234"],
      "total_validos": 24,
      "total_invalidos": 3
    }
  },
  "validacion_sap": {
    "validos": 24,
    "no_encontrados": 2,
    "errores": 1,
    "warnings": 0,
    "total_codigos": 27,
    "todos_validos": false
  }
}
```

### ❌ Estructura Antigua (Deprecada)

```json
{
  "type": "business_exception",
  "error": "No se puede persistir el pedido: existen productos no válidos en SAP. Productos no encontrados en SAP: MTF123.9899",
  "status_code": 400
}
```

---

## 🔧 Cambios Implementados

### 1️⃣ Clase `BusinessException` (`src/exceptions.py`)

**Antes:**
```python
class BusinessException(Exception):
    pass
```

**Ahora:**
```python
class BusinessException(Exception):
    def __init__(self, message: str, error_code: str = None, data: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "BUSINESS_ERROR"
        self.data = data or {}
```

**Uso:**
```python
raise BusinessException(
    message="No se puede persistir el pedido: existen productos no válidos en SAP",
    error_code="PRODUCTOS_NO_VALIDOS_SAP",
    data={
        "validacion": {
            "productos": {
                "no_encontrados": ["MTF123.9899"],
                "total_validos": 24,
                "total_invalidos": 1
            }
        }
    }
)
```

---

### 2️⃣ Exception Handler (`src/middleware/exception_handlers.py`)

**Antes:**
```python
@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    return JSONResponse(
        status_code=400,
        content={
            "error": str(exc),
            "type": "business_exception"
        }
    )
```

**Ahora:**
```python
@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    response_content = {
        "type": "business_exception",
        "error_code": exc.error_code,
        "message": exc.message,
        "status_code": 400
    }
    
    # Agregar datos estructurados
    if exc.data:
        response_content.update(exc.data)
    
    # Mantener compatibilidad
    if "error" not in response_content:
        response_content["error"] = exc.message
    
    return JSONResponse(status_code=400, content=response_content)
```

---

### 3️⃣ Validación SAP (`src/database/services/pedido_service.py`)

**Antes:**
```python
if sap_obligatorio and not validacion_sap.get("todos_validos", False):
    mensaje_error = "No se puede persistir el pedido: ..."
    raise BusinessException(mensaje_error)
```

**Ahora:**
```python
if sap_obligatorio and not validacion_sap.get("todos_validos", False):
    no_encontrados = validacion_sap.get("no_encontrados", [])
    errores = validacion_sap.get("errores", [])
    validos = validacion_sap.get("validos", [])
    
    # Mensaje legible para logs
    mensaje_error = "No se puede persistir el pedido: ..."
    
    # Datos estructurados para el frontend
    datos_estructurados = {
        "validacion": {
            "productos": {
                "no_encontrados": no_encontrados,
                "errores": errores,
                "total_validos": len(validos),
                "total_invalidos": len(no_encontrados) + len(errores)
            }
        },
        "validacion_sap": {
            "validos": len(validos),
            "no_encontrados": len(no_encontrados),
            "errores": len(errores),
            "warnings": validacion_sap.get("warnings", 0),
            "total_codigos": len(codigos_productos),
            "todos_validos": False
        }
    }
    
    raise BusinessException(
        message=mensaje_error,
        error_code="PRODUCTOS_NO_VALIDOS_SAP",
        data=datos_estructurados
    )
```

---

## 📊 Beneficios

### Para el Frontend

✅ **No más regex**: El frontend puede acceder directamente a `errorData.validacion.productos.no_encontrados`

✅ **Tipado fuerte**: Estructura predecible y documentada

✅ **Mejor UX**: Puede mostrar listas completas de productos con errores

✅ **Internacionalización**: Los mensajes se pueden cambiar sin tocar el backend

### Para el Backend

✅ **Más información**: Puede enviar detalles adicionales fácilmente

✅ **Compatibilidad**: Mantiene el campo `error` para código legacy

✅ **Extensible**: Fácil agregar nuevos campos sin romper código existente

---

## 🧪 Ejemplo de Uso en Frontend

```typescript
try {
  const response = await uploadFile(file);
  // ...
} catch (error: any) {
  const errorData = error.response?.data;
  
  // Acceso directo a datos estructurados (sin regex)
  if (errorData?.validacion?.productos?.no_encontrados) {
    const productosNoEncontrados = errorData.validacion.productos.no_encontrados;
    console.log('Productos no encontrados:', productosNoEncontrados);
    
    // Mostrar lista en modal
    modal.show({
      title: 'Productos no válidos en SAP',
      productos: productosNoEncontrados,
      totalValidos: errorData.validacion.productos.total_validos,
      totalInvalidos: errorData.validacion.productos.total_invalidos
    });
  }
  
  // Fallback a mensaje de texto (compatibilidad)
  else {
    alert(errorData?.message || errorData?.error || 'Error desconocido');
  }
}
```

---

## 🔄 Códigos de Error Disponibles

| Código | Descripción | Datos Adicionales |
|--------|-------------|-------------------|
| `PRODUCTOS_NO_VALIDOS_SAP` | Productos no encontrados o con errores en SAP | `validacion.productos`, `validacion_sap` |
| `BUSINESS_ERROR` | Error genérico de negocio | Variable |

---

## 📝 Notas

- **Compatibilidad**: El campo `error` se mantiene para código legacy que espera solo un string
- **Extensible**: Nuevos campos se pueden agregar sin romper código existente
- **HTTP Status**: Siempre 400 (Bad Request) para errores de negocio
- **Type**: Siempre `"business_exception"` para identificación rápida
