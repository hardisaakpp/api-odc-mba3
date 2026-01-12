# Resumen de Implementación: Persistencia de Campos Modificados Manualmente

## 📋 Cambios Realizados

### 1. Script SQL de Migración ✅

**Archivo:** `scripts/add_campos_modificados_manual.sql`

Se creó un script SQL que agrega tres campos booleanos a la tabla `pedido_detalle`:
- `costo_modificado_manual` (BIT, DEFAULT 0)
- `total_modificado_manual` (BIT, DEFAULT 0)
- `comentario_modificado_manual` (BIT, DEFAULT 0)

**Características:**
- ✅ Script idempotente (se puede ejecutar múltiples veces sin errores)
- ✅ Incluye índices filtrados para mejorar rendimiento
- ✅ Verificación de existencia de columnas antes de crear

### 2. Actualización del Repositorio ✅

**Archivo:** `src/database/repositories/pedido_repository.py`

#### Métodos Actualizados:

**a) `update_costo_detalle()`** (línea ~850)
- Ahora marca `costo_modificado_manual = 1` al actualizar el costo
- Actualiza también `updated_at` y `modificado_por`

**b) `update_total_detalle()`** (línea ~920)
- Ahora marca `total_modificado_manual = 1` al actualizar el total
- Actualiza también `updated_at` y `modificado_por`

**c) `update_comentario_detalle()`** (línea ~1050)
- Ahora marca `comentario_modificado_manual = 1` al agregar/modificar un comentario
- Solo marca como modificado si el comentario no es None o vacío
- Si se limpia el comentario, mantiene el flag (para preservar historial)

**d) `get_pedido_completo()`** (línea ~480)
- Incluye los campos `*_modificado_manual` en la consulta SQL
- Usa `ISNULL()` para manejar bases de datos antiguas donde estos campos no existen
- Devuelve `False` por defecto si los campos no existen

**e) `get_pedido_completo_por_numero()`** (línea ~680)
- Misma lógica que `get_pedido_completo()` pero busca por número de pedido
- Incluye los campos `*_modificado_manual` en la respuesta

### 3. Documentación ✅

**Archivo:** `docs/PERSISTENCIA_CAMPOS_MODIFICADOS.md`

Se creó documentación completa que incluye:
- Objetivo y ventajas de la solución backend
- Diseño de base de datos (comparación de opciones)
- Flujo de funcionamiento
- Casos de uso
- Consideraciones y mejores prácticas
- Checklist de implementación
- Guía de integración con frontend

## 🔄 Flujo de Funcionamiento

### Al Modificar un Campo (Frontend → Backend)

1. Usuario modifica `costo_doc_sin_iva` en el frontend
2. Frontend llama a `PATCH /api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/costo`
3. Backend ejecuta `PedidoRepository.update_costo_detalle()`
4. Backend actualiza:
   - `costo_doc_sin_iva` con el nuevo valor
   - `updated_at` con la fecha actual
   - `modificado_por` con el usuario
   - **`costo_modificado_manual = 1`** ⭐ NUEVO
5. Backend responde con éxito
6. Frontend puede actualizar `localStorage` inmediatamente (para UX) o esperar a recargar desde el backend

### Al Cargar un Pedido (Backend → Frontend)

1. Frontend llama a `GET /api/plantillas/{identificador}`
2. Backend ejecuta `PedidoRepository.get_pedido_completo()` o `get_pedido_completo_por_numero()`
3. Backend incluye en cada `detalle`:
   ```json
   {
     "pedido_detalle_id": "...",
     "costo_doc_sin_iva": 25.50,
     "total": 510.00,
     "comentario": "Producto con descuento",
     "costo_modificado_manual": true,      // ⭐ NUEVO
     "total_modificado_manual": true,      // ⭐ NUEVO
     "comentario_modificado_manual": false // ⭐ NUEVO
   }
   ```
4. Frontend recibe los datos y aplica el resaltado según estos flags
5. Frontend puede sincronizar `localStorage` con los datos del backend

## 📊 Estructura de Respuesta Actualizada

### GET /api/plantillas/{identificador}

```json
{
  "cabecera": {
    "pedido_id": "uuid-123",
    "numero_pedido": "P-12.48 - 12 - 2025",
    ...
  },
  "detalles": [
    {
      "pedido_detalle_id": "uuid-456",
      "codigo_interno": "R225.1012.BCO",
      "costo_doc_sin_iva": 25.50,
      "total": 510.00,
      "comentario": "Modificado manualmente",
      "costo_modificado_manual": true,      // ⭐ NUEVO
      "total_modificado_manual": true,      // ⭐ NUEVO
      "comentario_modificado_manual": true, // ⭐ NUEVO
      "tiendas": [...]
    }
  ]
}
```

## ✅ Compatibilidad con Bases de Datos Antiguas

El código maneja automáticamente bases de datos donde estos campos no existen:

1. **En las consultas (`get_pedido_completo`)**: Usa `ISNULL()` para devolver `0` (false) si el campo no existe
2. **En las actualizaciones**: Si los campos no existen, la actualización fallará con un error claro, indicando que se debe ejecutar el script SQL

**Recomendación:** Ejecutar el script SQL `add_campos_modificados_manual.sql` antes de desplegar estos cambios.

## 🔄 Migración de Datos Existentes

Para pedidos existentes:
- Todos los campos `*_modificado_manual` se inicializan en `0` (false) por defecto
- No se intenta inferir qué campos fueron modificados antes de esta implementación
- Si se requiere marcar campos históricos como modificados, se puede crear un script de migración adicional

## ⚠️ Consideraciones Importantes

### Resetear Flags de Modificación

**Decisión implementada:** Una vez marcado como modificado, el flag permanece marcado incluso si se restaura el valor original.

**Razón:** Esto refleja el historial real de modificaciones y es más simple de implementar.

**Alternativa futura:** Si se requiere, se puede agregar lógica para resetear flags cuando el valor vuelve al original (requiere guardar valor original).

### Sincronización Frontend-Backend

El frontend debe:
1. **Priorizar datos del backend** cuando estén disponibles (más confiable)
2. **Usar `localStorage` como fallback** si el backend no devuelve flags (bases de datos antiguas)
3. **Actualizar `localStorage` inmediatamente** para UX instantánea
4. **Sincronizar con backend** al cargar el pedido

## 📋 Checklist de Implementación

- [x] Crear script SQL `add_campos_modificados_manual.sql`
- [x] Actualizar `PedidoRepository.update_costo_detalle()` para marcar flag
- [x] Actualizar `PedidoRepository.update_total_detalle()` para marcar flag
- [x] Actualizar `PedidoRepository.update_comentario_detalle()` para marcar flag
- [x] Actualizar `PedidoRepository.get_pedido_completo()` para incluir flags
- [x] Actualizar `PedidoRepository.get_pedido_completo_por_numero()` para incluir flags
- [x] Verificar manejo de bases de datos antiguas (usando ISNULL)
- [x] Crear documentación completa
- [ ] **PENDIENTE:** Ejecutar script SQL en base de datos de desarrollo
- [ ] **PENDIENTE:** Probar flujo completo: modificar campo → cargar pedido → verificar resaltado
- [ ] **PENDIENTE:** Actualizar código frontend para usar flags del backend
- [ ] **PENDIENTE:** Documentar cambios para el equipo de frontend

## 🔗 Próximos Pasos

### Para el Backend:
1. Ejecutar el script SQL `add_campos_modificados_manual.sql` en la base de datos
2. Probar los endpoints PATCH para verificar que marcan los flags correctamente
3. Probar el endpoint GET para verificar que devuelve los flags

### Para el Frontend:
1. Actualizar tipos TypeScript para incluir los nuevos campos:
   ```typescript
   interface PedidoDetalle {
     // ... campos existentes ...
     costo_modificado_manual?: boolean
     total_modificado_manual?: boolean
     comentario_modificado_manual?: boolean
   }
   ```

2. Actualizar el composable `useColumnasModificadas` para:
   - Cargar flags desde el backend al cargar el pedido
   - Priorizar datos del backend sobre `localStorage`
   - Sincronizar `localStorage` con los datos del backend

3. Probar el flujo completo:
   - Modificar un campo → verificar resaltado inmediato
   - Recargar página → verificar que el resaltado persiste
   - Cambiar de navegador/dispositivo → verificar que el resaltado persiste

## 📚 Archivos Modificados

1. ✅ `scripts/add_campos_modificados_manual.sql` (nuevo)
2. ✅ `src/database/repositories/pedido_repository.py` (modificado)
3. ✅ `docs/PERSISTENCIA_CAMPOS_MODIFICADOS.md` (nuevo)
4. ✅ `docs/RESUMEN_IMPLEMENTACION_CAMPOS_MODIFICADOS.md` (este archivo, nuevo)

## 🧪 Pruebas Recomendadas

### Test 1: Modificar Costo
```bash
PATCH /api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/costo
{
  "costo_doc_sin_iva": 25.50
}
```
**Verificar:**
- ✅ Campo `costo_doc_sin_iva` se actualiza
- ✅ Campo `costo_modificado_manual` se marca como `1` (true)
- ✅ Campo `updated_at` se actualiza
- ✅ Campo `modificado_por` se actualiza

### Test 2: Modificar Total
```bash
PATCH /api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/total
{
  "total": 510.00
}
```
**Verificar:**
- ✅ Campo `total` se actualiza
- ✅ Campo `total_modificado_manual` se marca como `1` (true)

### Test 3: Modificar Comentario
```bash
PATCH /api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/comentario
{
  "comentario": "Producto con descuento especial"
}
```
**Verificar:**
- ✅ Campo `comentario` se actualiza
- ✅ Campo `comentario_modificado_manual` se marca como `1` (true)

### Test 4: Cargar Pedido con Campos Modificados
```bash
GET /api/plantillas/{identificador}
```
**Verificar:**
- ✅ Los detalles incluyen los campos `*_modificado_manual`
- ✅ Los valores son `true` o `false` (boolean)
- ✅ Si la BD es antigua, los campos devuelven `false` por defecto

## ✅ Estado de Implementación

**Backend:** ✅ Completo
- Script SQL creado
- Repositorio actualizado
- Manejo de BD antiguas implementado
- Documentación completa

**Frontend:** ⏳ Pendiente
- Actualizar tipos TypeScript
- Actualizar composable para usar flags del backend
- Priorizar datos del backend sobre localStorage
- Probar flujo completo

## 📝 Notas Adicionales

- Los campos `*_modificado_manual` son independientes entre sí
- Un campo puede estar marcado como modificado sin afectar a los otros
- Si se limpia un comentario, el flag `comentario_modificado_manual` se mantiene (preserva historial)
- Los índices filtrados solo incluyen registros donde el flag es `1` (true), optimizando búsquedas
