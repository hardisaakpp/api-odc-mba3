# Validación de Tiendas contra SAP en Carga de Excel

## Descripción General
Se implementó validación de códigos de tienda (ID TIENDA) contra SAP directamente en el momento de la carga del archivo Excel. Esto asegura que **cualquier código de tienda utilizado en la plantilla debe existir en SAP OWHS**, rechazando la subida si hay tiendas no válidas.

## Cambios Realizados

### 1. Nuevo Método en PedidoValidator
**Archivo:** `src/database/services/pedido_validator.py`

Se agregó el método `validar_tiendas_existen_en_sap()`:

```python
def validar_tiendas_existen_en_sap(
    self,
    codigos_tiendas: List[str],
    sap_obligatorio: bool = True
) -> Dict[str, Any]:
    """
    Valida que los códigos de tienda existan directamente en SAP OWHS.
    
    Args:
        codigos_tiendas: Lista de códigos de tiendas a validar (ej: ["ROL01", "ROL02"])
        sap_obligatorio: Si True, errores de SAP bloquean
        
    Returns:
        {
            "validas": List[str],
            "no_encontradas": List[str],
            "errores": List[str],
            "warnings": List[str],
            "todas_validas": bool,
            "detalle": Dict[str, Dict[str, Any]]
        }
    """
```

**Características:**
- Obtiene el catálogo completo de tiendas desde SAP OWHS (tabla `OWHS`)
- Valida cada código contra el catálogo SAP
- Normaliza códigos a mayúsculas para comparación confiable
- Retorna información detallada por tienda (código, nombre, ubicación)
- Maneja excepciones de SAP gracefully

### 2. Integración en Formato v1.0 (4 hojas)
**Archivo:** `src/database/services/pedido_service.py`

Se agregó validación de tiendas después del procesamiento de la hoja "Movimiento":

**Ubicación:** En método `_procesar_formato_v1_0()` después de línea 1345

**Flujo:**
1. Extrae códigos únicos de tiendas de la hoja "Movimiento"
2. Valida cada código contra SAP OWHS
3. Si `sap_obligatorio=True` y hay tiendas no encontradas:
   - Rechaza la subida con error `TIENDAS_NO_VALIDAS_SAP`
   - Incluye lista detallada de tiendas no encontradas
   - Lanza `BusinessException` con información estructurada

**Respuesta de Error:**
```json
{
    "status": "validation_error",
    "message": "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP...",
    "errores": ["Tiendas no encontradas en SAP OWHS: ROL99, ROL98"],
    "validacion_tiendas_sap": {
        "total_codigos": 5,
        "validas": 3,
        "no_encontradas": 2,
        "errores": 0,
        "todas_validas": false
    }
}
```

### 3. Integración en Formato DOS HOJAS (Cabecera + Detalle)
**Archivo:** `src/database/services/pedido_service.py`

Se agregó la misma validación para compatibilidad con el formato antiguo (CABECERA_PEDIDO + DETALLE_ARTICULO).

**Ubicación:** Después de línea 672 (antes de validación general)

**Flujo idéntico al formato v1.0**, extrayendo tiendas de los detalles con tiendas consolidados.

### 4. Integración en Formato SIMPLE
La validación se aplica automáticamente a cualquier formato que contenga distribuciones por tienda, incluyendo el formato simple (CodigoProducto, IdTienda, Cantidad).

## Parámetro de Control

La validación se controla con el parámetro de query existente:

```python
sap_obligatorio: bool = True  # En todos los endpoints de upload
```

**Comportamiento:**
- `sap_obligatorio=True` (default): Las tiendas no válidas en SAP BLOQUEAN la carga
- `sap_obligatorio=False`: Las tiendas no válidas generan WARNING pero no bloquean

## Integración con Flujo Existente

### Orden de Validaciones
1. **Validación de archivo:** Formato Excel, tamaño, etc.
2. **Parsing:** Lectura de hojas
3. **Validación SAP de Productos** (Detalle Articulos): Productos contra SAP
4. **Validación SAP de Tiendas** ← **NUEVA** (Movimiento/Distribuciones)
5. **Validación de Coherencia:** Artículos en Movimiento vs Detalle
6. **Validación General:** Cabecera, fechas, cantidades, etc.
7. **Persistencia:** Si todas las validaciones pasan

### Error Handling
Si la validación falla:
- La excepción `BusinessException` es capturada por el middleware global
- Se retorna respuesta HTTP 400 con detalles de validación
- El pedido NO se guarda en BD

## Casos de Uso

### Caso 1: Excel con Tiendas Válidas
```
Resultado: ✅ Aceptado
- Todas las tiendas en Movimiento existen en SAP
- Pedido se procesa y guarda normalmente
```

### Caso 2: Excel con Tiendas No Válidas
```
Resultado: ❌ Rechazado
- Se detecta tienda "ROL99" que no existe en SAP OWHS
- Respuesta incluye lista de tiendas no válidas
- Usuario debe corregir el Excel y reintentar
```

### Caso 3: Sin validación obligatoria (`sap_obligatorio=False`)
```
Resultado: ⚠️ Aceptado con advertencia
- Las tiendas inválidas generan WARNING
- El pedido se procesa igualmente
- El usuario ve el warning en la validación
```

## Testing

Para probar la implementación:

```bash
# 1. Crear Excel de prueba con tienda válida (ej: ROL01)
# 2. Subir: ?validar=true&sap_obligatorio=true
# Resultado: ✅ Aceptado

# 3. Crear Excel con tienda inválida (ej: ROL99)
# 4. Subir: ?validar=true&sap_obligatorio=true
# Resultado: ❌ Rechazado con error de tienda

# 5. Subir mismo Excel: ?validar=true&sap_obligatorio=false
# Resultado: ⚠️ Aceptado con warnings
```

## Notas Técnicas

1. **Catálogo SAP:** Se obtiene en tiempo de validación (no cacheado en esta validación específica)
2. **Normalización:** Los códigos se normalizan a mayúsculas para comparación confiable
3. **Mensajes:** Los errores incluyen listas de tiendas problemáticas (máximo 5 en el mensaje, resto resumido)
4. **Información detallada:** El campo `validacion_tiendas_sap` en la respuesta incluye:
   - Total de códigos validados
   - Cantidad de válidas, no encontradas, errores, warnings
   - Bandera `todas_validas` para client-side

## Compatibilidad

- ✅ Formato v1.0 (4 hojas): Cabecera Pedido, Detalle Articulos, Movimiento, Tiendas
- ✅ Formato DOS HOJAS: Cabecera Pedido, Detalle Articulos
- ✅ Formato SIMPLE: CodigoProducto, IdTienda, Cantidad
- ✅ Formato COMPLEJO (legacy): Estructura con cabecera y columnas de tiendas

## Diferencias con Validación Anterior

**Antes:** 
- Tiendas se validaban solo contra la hoja "Tiendas" del Excel
- Dependía de que el usuario mantuviera catálogo actualizado
- No validaba contra SAP en tiempo real

**Ahora:**
- Tiendas se validan directamente contra SAP OWHS
- Garantiza que solo tiendas válidas en SAP puedan usarse
- Validación es independiente del catálogo Excel (aunque sigue siendo útil)
- Mayor seguridad en la integridad de datos

## Beneficios

1. **Prevención de errores:** Los códigos de tienda deben existir en SAP antes de procesarlos
2. **Consistencia:** Garantiza que el sistema y SAP están sincronizados en tiendas
3. **Mensajes claros:** Indica exactamente qué tiendas son inválidas
4. **Flexible:** Puede ser deshabilitado si es necesario (`sap_obligatorio=false`)
5. **Trazable:** Información detallada en respuesta para debugging
