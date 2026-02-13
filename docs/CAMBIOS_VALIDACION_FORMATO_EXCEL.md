# Mejora de Mensajes de Validación de Formato Excel

## Problema Resuelto

Anteriormente, cuando un usuario intentaba subir un archivo Excel con formato incorrecto (por ejemplo, sin las hojas `'cabecera'` y `'detalle'`), el sistema lanzaba un `ValueError` que se capturaba genéricamente y el mensaje completo (incluyendo texto como "Se esperaba: hoja 'cabecera' y hoja 'detalle'") era malinterpretado por el frontend como si fuera un error de validación de productos SAP.

### Ejemplo del error anterior:
```
Descripción del problema: Existen 1 código(s) no válidos en SAP.
❌ Códigos de PRODUCTO no encontrados (1):
• hoja 'cabecera' y hoja 'detalle'"]
```

Esto confundía al usuario porque no era un código de producto, sino un error de formato de archivo.

## Solución Implementada

Se reemplazaron **4 casos de `ValueError`** por **`BusinessException`** con códigos de error estructurados para permitir que el frontend maneje estos errores de forma específica y muestre mensajes coherentes.

### Cambios realizados en `pedido_service.py`

#### 1. Error de formato inválido (hojas incorrectas)

**Antes:**
```python
raise ValueError(error_msg)
```

**Después:**
```python
raise BusinessException(
    message="El archivo Excel no tiene el formato correcto",
    error_code="FORMATO_EXCEL_INVALIDO",
    data={
        "hojas_encontradas": ["Sheet1", "Hoja2"],  # Ejemplo
        "hojas_esperadas": ["cabecera", "detalle"],
        "mensaje_detallado": "...",
        "validacion": {
            "formato_archivo": {
                "valido": False,
                "mensaje": "El archivo debe contener dos hojas llamadas 'cabecera' y 'detalle' (en minúsculas)"
            }
        }
    }
)
```

#### 2. Error de archivo vacío (sin datos)

**Antes:**
```python
raise ValueError("No se encontraron datos válidos en el archivo")
```

**Después:**
```python
raise BusinessException(
    message="El archivo Excel está vacío o no contiene datos válidos",
    error_code="ARCHIVO_SIN_DATOS",
    data={
        "mensaje_detallado": "No se encontraron productos con distribuciones válidas en el archivo",
        "validacion": {
            "datos_archivo": {
                "valido": False,
                "mensaje": "El archivo debe contener al menos un producto con cantidades para tiendas o bodegas"
            }
        }
    }
)
```

### Cambios realizados en `pedido_proveedor_service.py`

#### 3. Error de formato de respuesta del proveedor (hoja faltante)

**Antes:**
```python
raise ValueError("Hoja requerida no encontrada: RESUMEN")
```

**Después:**
```python
raise BusinessException(
    message="El archivo de respuesta del proveedor no tiene el formato correcto",
    error_code="FORMATO_RESPUESTA_PROVEEDOR_INVALIDO",
    data={
        "hojas_encontradas": ["Sheet1", "Datos"],  # Ejemplo
        "hojas_esperadas": ["RESUMEN"],
        "mensaje_detallado": "El archivo debe contener una hoja llamada 'RESUMEN' (en mayúsculas)...",
        "validacion": {
            "formato_archivo": {
                "valido": False,
                "mensaje": "El archivo de respuesta del proveedor debe contener una hoja llamada 'RESUMEN'"
            }
        }
    }
)
```

## Códigos de Error Disponibles

El frontend ahora puede detectar y manejar específicamente estos códigos de error:

| Código de Error | Descripción | Uso |
|----------------|-------------|-----|
| `FORMATO_EXCEL_INVALIDO` | El archivo no tiene las hojas correctas (cabecera/detalle) | Mostrar mensaje específico sobre hojas requeridas |
| `ARCHIVO_SIN_DATOS` | El archivo está vacío o sin datos válidos | Mostrar mensaje sobre datos requeridos |
| `FORMATO_RESPUESTA_PROVEEDOR_INVALIDO` | Archivo de respuesta sin hoja RESUMEN | Mostrar mensaje sobre formato de respuesta del proveedor |
| `PRODUCTOS_NO_VALIDOS_SAP` | Productos no encontrados en SAP | Ya existente - no se modifica |
| `NUMERO_PEDIDO_DUPLICADO` | Número de pedido ya existe | Ya existente - no se modifica |

## Estructura de Respuesta del Backend

Cuando ocurre un error de validación, el backend devuelve:

```json
{
  "type": "business_exception",
  "error_code": "FORMATO_EXCEL_INVALIDO",
  "message": "El archivo Excel no tiene el formato correcto",
  "status_code": 400,
  "hojas_encontradas": ["Sheet1", "Datos"],
  "hojas_esperadas": ["cabecera", "detalle"],
  "mensaje_detallado": "El sistema solo soporta el formato v1.0 con hojas 'cabecera' y 'detalle'...",
  "validacion": {
    "formato_archivo": {
      "valido": false,
      "mensaje": "El archivo debe contener dos hojas llamadas 'cabecera' y 'detalle' (en minúsculas)"
    }
  }
}
```

## Recomendaciones para el Frontend

### 1. Detectar el código de error

```typescript
// En el manejador de errores del upload
if (error.response?.data?.error_code === "FORMATO_EXCEL_INVALIDO") {
  // Mostrar modal específico para formato inválido
  showFormatoInvalidoModal(error.response.data);
} else if (error.response?.data?.error_code === "ARCHIVO_SIN_DATOS") {
  // Mostrar modal específico para archivo vacío
  showArchivoVacioModal(error.response.data);
} else if (error.response?.data?.error_code === "PRODUCTOS_NO_VALIDOS_SAP") {
  // Mostrar modal de productos SAP (ya existente)
  showProductosSAPModal(error.response.data);
}
```

### 2. Ejemplo de modal para FORMATO_EXCEL_INVALIDO

```tsx
function FormatoInvalidoModal({ data }: { data: ErrorResponse }) {
  return (
    <Modal>
      <Title>❌ Formato de archivo incorrecto</Title>
      
      <Description>
        El archivo Excel debe contener dos hojas llamadas:
        <ul>
          <li><strong>'cabecera'</strong> (en minúscula)</li>
          <li><strong>'detalle'</strong> (en minúscula)</li>
        </ul>
      </Description>
      
      <Alert type="info">
        <strong>Hojas encontradas en tu archivo:</strong>
        <ul>
          {data.hojas_encontradas.map(hoja => (
            <li key={hoja}>{hoja}</li>
          ))}
        </ul>
      </Alert>
      
      <Actions>
        <Button variant="primary" onClick={onClose}>
          Entendido
        </Button>
        <Button variant="secondary" onClick={downloadTemplate}>
          Descargar plantilla correcta
        </Button>
      </Actions>
    </Modal>
  );
}
```

### 3. Ejemplo de modal para ARCHIVO_SIN_DATOS

```tsx
function ArchivoVacioModal({ data }: { data: ErrorResponse }) {
  return (
    <Modal>
      <Title>⚠️ Archivo sin datos válidos</Title>
      
      <Description>
        El archivo Excel no contiene productos con distribuciones válidas.
      </Description>
      
      <Alert type="warning">
        <strong>Verifica que:</strong>
        <ul>
          <li>La hoja 'cabecera' contenga información del pedido</li>
          <li>La hoja 'detalle' contenga al menos un producto</li>
          <li>Los productos tengan cantidades asignadas a tiendas o bodegas</li>
        </ul>
      </Alert>
      
      <Actions>
        <Button variant="primary" onClick={onClose}>
          Revisar archivo
        </Button>
      </Actions>
    </Modal>
  );
}
```

## Beneficios de la Solución

✅ **Claridad**: Los mensajes de error son específicos y claros para el usuario
✅ **No interferencia**: No afecta las validaciones SAP existentes que ya funcionan correctamente
✅ **Consistencia**: Usa la misma estructura (`BusinessException`) que otros errores de validación
✅ **Mantenibilidad**: El frontend puede manejar cada tipo de error de forma independiente
✅ **Extensibilidad**: Fácil agregar nuevos códigos de error en el futuro

## Validaciones que NO se modificaron

Las siguientes validaciones **siguen funcionando exactamente igual** (no se tocaron):

- ✅ Validación de productos contra SAP
- ✅ Validación de tiendas/bodegas contra SAP
- ✅ Validación de número de pedido duplicado
- ✅ Todas las demás validaciones de negocio

## Testing Recomendado

### Backend
1. Subir Excel sin hojas 'cabecera' y 'detalle' → Debe retornar `FORMATO_EXCEL_INVALIDO`
2. Subir Excel con hojas correctas pero vacías → Debe retornar `ARCHIVO_SIN_DATOS`
3. Subir Excel con productos inválidos → Debe retornar `PRODUCTOS_NO_VALIDOS_SAP` (sin cambios)

### Frontend
1. Verificar que cada `error_code` muestre el modal correcto
2. Verificar que los mensajes sean claros y específicos
3. Verificar que las validaciones SAP sigan mostrando el modal anterior (sin cambios)

## Archivos Modificados

- `src/database/services/pedido_service.py` (líneas 850-910 aprox.)
  - 3 casos de `ValueError` → `BusinessException` 
- `src/database/services/pedido_proveedor_service.py` (línea 315 aprox.)
  - 1 caso de `ValueError` → `BusinessException`
- Exception handler existente en `src/middleware/exception_handlers.py` (sin cambios, ya soporta BusinessException)

## Fecha de Implementación

- Backend: 2026-02-13
- Frontend: Pendiente
**Última revisión:** 2026-02-13 (frontend sigue pendiente)
