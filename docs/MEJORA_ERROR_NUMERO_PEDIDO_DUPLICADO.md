# Mejora: Mensaje de Error para Número de Pedido Duplicado

## Problema Identificado

Cuando un usuario intenta subir una plantilla con un número de pedido que ya existe en el sistema, especialmente después de haber corregido errores de códigos de producto, el mensaje de error NO mostraba claramente el número de pedido duplicado.

### Escenario del Problema

1. Usuario sube plantilla con errores de código de producto
2. Sistema muestra modal con códigos de producto inválidos
3. Usuario corrige los códigos usando las sugerencias SAP
4. Usuario vuelve a subir la MISMA plantilla (con correcciones)
5. **Problema**: El sistema guarda exitosamente el pedido en el primer intento
6. En el segundo intento, el número de pedido ya existe (duplicado)
7. **Resultado**: El modal solo mostraba error genérico, sin indicar claramente que el problema era el número de pedido duplicado

## Solución Implementada

### Cambios Realizados

Se modificó el manejo del error de número de pedido duplicado para que siga el mismo patrón estructurado que los errores de validación SAP:

#### 1. `pedido_service.py` - Método `_persistir_pedido` (línea ~1470)

**Antes:**
```python
except ValueError as e:
    error_msg = str(e)
    if "número de pedido" in error_msg.lower() and "ya existe" in error_msg.lower():
        logger.warning(f"⚠️ Intento de crear pedido con número duplicado: {error_msg}")
        resultado["status"] = "error"
        resultado["errores"].append(error_msg)
        resultado["error_tipo"] = "numero_pedido_duplicado"
        return
```

**Después:**
```python
except ValueError as e:
    error_msg = str(e)
    if "número de pedido" in error_msg.lower() and "ya existe" in error_msg.lower():
        numero_pedido = cabecera.get("numero_pedido")
        logger.warning(f"⚠️ Intento de crear pedido con número duplicado: {numero_pedido}")
        
        # ✅ Lanzar BusinessException con datos estructurados
        raise BusinessException(
            message=f"El número de pedido '{numero_pedido}' ya existe en el sistema",
            error_code="NUMERO_PEDIDO_DUPLICADO",
            data={
                "numero_pedido": numero_pedido,
                "validacion": {
                    "numero_pedido": {
                        "duplicado": True,
                        "mensaje": f"El número de pedido '{numero_pedido}' ya fue utilizado anteriormente"
                    }
                }
            }
        )
```

#### 2. `pedido_service.py` - Método `crear_pedido_manual` (línea ~1424)

Se agregó información estructurada al resultado:

```python
resultado["validacion_numero_pedido"] = {
    "numero_pedido": numero_pedido,
    "duplicado": True,
    "mensaje": f"El número de pedido '{numero_pedido}' ya fue utilizado anteriormente"
}
```

### Estructura de la Respuesta de Error

Cuando se detecta un número de pedido duplicado, el backend ahora devuelve:

```json
{
  "type": "business_exception",
  "error_code": "NUMERO_PEDIDO_DUPLICADO",
  "message": "El número de pedido 'P-12.48' ya existe en el sistema",
  "status_code": 400,
  "numero_pedido": "P-12.48",
  "validacion": {
    "numero_pedido": {
      "duplicado": true,
      "mensaje": "El número de pedido 'P-12.48' ya fue utilizado anteriormente"
    }
  }
}
```

## Beneficios

1. **Consistencia**: Sigue el mismo patrón que los errores de validación SAP (productos, tiendas, bodegas)
2. **Claridad**: El número de pedido duplicado se muestra explícitamente en el mensaje y en los datos estructurados
3. **Frontend-Friendly**: El frontend puede extraer fácilmente el número de pedido de `data.numero_pedido` para mostrarlo en el modal
4. **Mejor UX**: El usuario sabe exactamente cuál es el problema y qué número de pedido debe cambiar

## Implementación en Frontend

El frontend puede manejar este error así:

```javascript
// Detectar error de número de pedido duplicado
if (response.error_code === 'NUMERO_PEDIDO_DUPLICADO') {
  const numeroPedido = response.numero_pedido;
  const mensaje = response.validacion?.numero_pedido?.mensaje || response.message;
  
  // Mostrar en modal con formato especial
  modalContent.innerHTML = `
    <div class="error-duplicado-pedido">
      <h3>Número de Pedido Duplicado</h3>
      <p>${mensaje}</p>
      <p><strong>Número de pedido:</strong> ${numeroPedido}</p>
      <p>Por favor, modifica el número de pedido en el archivo Excel e intenta nuevamente.</p>
    </div>
  `;
}
```

## Archivos Modificados

- `src/database/services/pedido_service.py`
  - Método `_persistir_pedido`: Convertido a BusinessException con datos estructurados
  - Método `crear_pedido_manual`: Agregados datos estructurados al resultado

## Compatibilidad

- ✅ Compatible con código existente (el exception handler ya maneja BusinessException)
- ✅ El frontend puede seguir usando el mensaje de error genérico si no implementa el manejo específico
- ✅ Mejora progresiva: el frontend puede aprovechar los datos estructurados cuando esté listo

## Testing

Para probar este cambio:

1. Subir una plantilla Excel válida con número de pedido "P-TEST-001"
2. Esperar a que se guarde exitosamente
3. Intentar subir nuevamente la misma plantilla (o una diferente con el mismo número de pedido)
4. Verificar que el error muestre claramente:
   - `error_code: "NUMERO_PEDIDO_DUPLICADO"`
   - `numero_pedido: "P-TEST-001"`
   - Mensaje descriptivo en `message` y `validacion.numero_pedido.mensaje`

## ✅ Implementación de Validación Temprana (COMPLETADA)

La validación de número de pedido duplicado ahora se ejecuta **INMEDIATAMENTE después del parsing**, antes de cualquier validación SAP costosa.

### Orden de Validación Actualizado (Implementado)

1. Validaciones de archivo (tipo, tamaño)
2. Parsing de cabecera
3. **⭐ VALIDACIÓN DE NUMERO PEDIDO DUPLICADO** ← ✅ IMPLEMENTADO (línea ~757)
4. Validación SAP - Productos
5. Validación SAP - Tiendas/Bodegas
6. Validaciones de reglas de negocio
7. Persistencia en BD

### Beneficios de la Validación Temprana

1. **Ahorro de tiempo**: Se detecta el duplicado ANTES de consultar SAP (ahorra 1-2 minutos)
2. **Ahorro de recursos**: Evita consultas costosas a SAP cuando el pedido no se puede guardar
3. **Mejor experiencia de usuario**: Error inmediato en lugar de esperar todo el proceso
4. **Consistencia**: Todos los caminos (Excel y manual) validan tempranamente

### Implementación Técnica

#### Nuevo Método en `PedidoRepository`

```python
def existe_numero_pedido(self, numero_pedido: str) -> bool:
    """
    Verifica si un número de pedido ya existe en el sistema.
    
    Returns:
        True si el número de pedido ya existe, False si no existe
    """
    cursor.execute("""
        SELECT COUNT(*) 
        FROM pedido 
        WHERE numero_pedido = ?
    """, (numero_pedido,))
    
    return cursor.fetchone()[0] > 0
```

#### Validación en `validar_y_procesar_archivo_excel` (línea ~757)

```python
# Después de normalizar cabecera
cabecera = self._normalizar_cabecera_para_bd(...)

# ✅ VALIDACIÓN TEMPRANA
numero_pedido = cabecera.get("numero_pedido")
if numero_pedido:
    with get_db_connection_context() as conn_check:
        repo_check = PedidoRepository(conn_check)
        
        if repo_check.existe_numero_pedido(numero_pedido):
            # Lanzar BusinessException INMEDIATAMENTE
            raise BusinessException(
                message=f"El número de pedido '{numero_pedido}' ya existe",
                error_code="NUMERO_PEDIDO_DUPLICADO",
                data={...}
            )
```

#### Validación en `crear_pedido_manual` (línea ~1210)

Similar a la validación en Excel, pero retorna el resultado en lugar de lanzar excepción (para compatibilidad con el flujo de creación manual).

### Logs de la Validación Temprana

Cuando se detecta un duplicado tempranamente, los logs mostrarán:

```
INFO - ✓ Campo mapeado: 'CODIGO PEDIDO' → 'numero_pedido' = 'P-12.03 - 12 - 2025'
INFO - ✅ Cabecera parseada: 18 campos encontrados
WARNING - ⚠️ [VALIDACIÓN TEMPRANA] Número de pedido duplicado detectado: 'P-12.03 - 12 - 2025'
```

**Nota**: Ya NO se verán los logs de validación SAP porque el proceso se interrumpe antes.
