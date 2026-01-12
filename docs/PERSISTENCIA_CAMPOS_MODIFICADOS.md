# Implementación: Persistencia de Campos Modificados Manualmente

## 📋 Resumen

Este documento describe la implementación backend para persistir información sobre qué campos del `pedido_detalle` fueron modificados manualmente por el usuario, permitiendo que el frontend pueda resaltar estas celdas al cargar el pedido.

## 🎯 Objetivo

Permitir que el frontend sepa qué campos (`costo_doc_sin_iva`, `total`, `comentario`) fueron modificados manualmente, para poder resaltarlos visualmente, **persistiendo esta información en la base de datos** en lugar de solo usar `localStorage`.

## ✅ Ventajas de la solución Backend

- ✅ **Persiste entre navegadores/dispositivos**: Funciona en cualquier lugar donde el usuario inicie sesión
- ✅ **Auditoría completa**: Se puede rastrear qué campos fueron modificados y cuándo
- ✅ **Compartible entre usuarios**: Si se requiere, diferentes usuarios pueden ver qué campos fueron modificados
- ✅ **Más robusto**: No se pierde al limpiar caché del navegador

## 🗄️ Diseño de Base de Datos

### Opción 1: Campos Booleanos Individuales (Recomendada)

Agregar tres campos booleanos en `pedido_detalle`:

```sql
ALTER TABLE pedido_detalle
ADD costo_modificado_manual BIT DEFAULT 0,
    total_modificado_manual BIT DEFAULT 0,
    comentario_modificado_manual BIT DEFAULT 0;
```

**Ventajas:**
- ✅ Simple y directo
- ✅ Fácil de consultar con índices
- ✅ Tipo de dato nativo (BIT)
- ✅ Cada campo es independiente

**Desventajas:**
- ⚠️ Requiere agregar un campo por cada columna modificable (pero solo son 3)

### Opción 2: Campo JSON (Alternativa)

```sql
ALTER TABLE pedido_detalle
ADD campos_modificados_manual NVARCHAR(MAX) NULL; -- JSON: ["costo_doc_sin_iva", "total", "comentario"]
```

**Ventajas:**
- ✅ Flexible: fácil agregar nuevos campos sin migración
- ✅ Compacto: un solo campo

**Desventajas:**
- ⚠️ Más complejo de consultar
- ⚠️ No se puede indexar eficientemente
- ⚠️ Requiere parseo JSON

### ✅ Decisión: Opción 1 (Campos Booleanos)

Se implementará la **Opción 1** por simplicidad y rendimiento.

## 📝 Cambios Requeridos

### 1. Script SQL de Migración

**Archivo:** `scripts/add_campos_modificados_manual.sql`

Agrega los campos booleanos para marcar qué columnas fueron modificadas manualmente.

### 2. Actualizar Repositorio

**Archivo:** `src/database/repositories/pedido_repository.py`

Actualizar los métodos:
- `update_costo_detalle()`: Marcar `costo_modificado_manual = 1`
- `update_total_detalle()`: Marcar `total_modificado_manual = 1`
- `update_comentario_detalle()`: Marcar `comentario_modificado_manual = 1`
- `get_pedido_completo()`: Incluir estos campos en la respuesta

### 3. Actualizar Modelos Pydantic

**Archivo:** `src/models.py`

Agregar campos opcionales en la estructura de `PedidoDetalle` (implícito en el dict retornado por `get_pedido_completo`).

### 4. Actualizar Endpoints

**Archivo:** `src/endpoints/plantillas.py`

Los endpoints PATCH ya están correctamente implementados, pero ahora devolverán información adicional sobre qué campos fueron marcados como modificados.

## 🔄 Flujo de Funcionamiento

### Al Modificar un Campo (Frontend → Backend)

1. Usuario modifica `costo_doc_sin_iva` en el frontend
2. Frontend llama a `PATCH /api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/costo`
3. Backend actualiza:
   - `costo_doc_sin_iva` con el nuevo valor
   - `updated_at` con la fecha actual
   - `modificado_por` con el usuario
   - **`costo_modificado_manual = 1`** (nuevo)
4. Backend responde con éxito
5. Frontend puede actualizar `localStorage` inmediatamente (para cambio instantáneo) o esperar a recargar desde el backend

### Al Cargar un Pedido (Backend → Frontend)

1. Frontend llama a `GET /api/plantillas/{identificador}`
2. Backend ejecuta `get_pedido_completo()`
3. Backend incluye en cada `detalle`:
   ```json
   {
     "pedido_detalle_id": "...",
     "costo_doc_sin_iva": 25.50,
     "total": 510.00,
     "comentario": "Producto con descuento",
     "costo_modificado_manual": true,    // ⭐ NUEVO
     "total_modificado_manual": true,     // ⭐ NUEVO
     "comentario_modificado_manual": false // ⭐ NUEVO
   }
   ```
4. Frontend recibe los datos y aplica el resaltado según estos flags
5. Frontend puede sincronizar `localStorage` con los datos del backend

## 📊 Estructura de Respuesta Actualizada

### GET /api/plantillas/{identificador}

```json
{
  "cabecera": {...},
  "detalles": [
    {
      "pedido_detalle_id": "uuid-123",
      "codigo_interno": "R225.1012.BCO",
      "costo_doc_sin_iva": 25.50,
      "total": 510.00,
      "comentario": "Modificado manualmente",
      "costo_modificado_manual": true,    // ⭐ NUEVO
      "total_modificado_manual": true,     // ⭐ NUEVO
      "comentario_modificado_manual": true, // ⭐ NUEVO
      "tiendas": [...]
    }
  ]
}
```

## 🧪 Casos de Uso

### Caso 1: Modificar Costo
- Usuario cambia `costo_doc_sin_iva` de 20.00 a 25.50
- Backend marca `costo_modificado_manual = 1`
- Al recargar el pedido, el frontend resalta la celda de costo

### Caso 2: Modificar Total
- Usuario cambia `total` de 500.00 a 510.00
- Backend marca `total_modificado_manual = 1`
- Al recargar el pedido, el frontend resalta la celda de total

### Caso 3: Modificar Comentario
- Usuario agrega un comentario
- Backend marca `comentario_modificado_manual = 1`
- Al recargar el pedido, el frontend resalta la celda de comentario

### Caso 4: Cargar Pedido Existente
- Pedido tiene `costo_modificado_manual = 1`, `total_modificado_manual = 0`, `comentario_modificado_manual = 1`
- Frontend resalta solo las celdas de costo y comentario

## 🔄 Migración de Datos Existentes

Para pedidos existentes, todos los campos `*_modificado_manual` se inicializan en `0` (false), ya que no tenemos historial de qué campos fueron modificados antes de esta implementación.

Si se requiere marcar campos existentes como modificados (por ejemplo, si ya tienen `updated_at` o `modificado_por`), se puede crear un script de migración adicional:

```sql
-- Opcional: Marcar como modificados manualmente si ya tienen updated_at/modificado_por
UPDATE pedido_detalle
SET costo_modificado_manual = CASE 
    WHEN modificado_por IS NOT NULL AND updated_at IS NOT NULL THEN 1 
    ELSE 0 
END,
total_modificado_manual = costo_modificado_manual, -- Asumir que si tiene updated_at, total también fue modificado
comentario_modificado_manual = CASE 
    WHEN comentario IS NOT NULL AND modificado_por IS NOT NULL THEN 1 
    ELSE 0 
END;
```

**Nota:** Este script es opcional y solo debería ejecutarse si hay un requisito de negocio para marcar campos históricos como modificados.

## ⚠️ Consideraciones

### Resetear Flags de Modificación

Si se requiere permitir "desmarcar" un campo como modificado (por ejemplo, si el usuario restaura el valor original), se puede agregar lógica adicional:

- Opción A: Resetear flag cuando el valor vuelve al original (requiere guardar valor original)
- Opción B: Endpoint específico para resetear flags (más simple)
- Opción C: Solo marcar como modificado cuando se cambia (flag permanece aunque se restaure)

**Recomendación:** Opción C - Una vez marcado como modificado, permanece marcado. Es más simple y refleja el historial real.

### Sincronización Frontend-Backend

El frontend puede:
1. **Cambio inmediato en `localStorage`** (para UX instantánea)
2. **Actualizar desde backend** al cargar el pedido (para sincronización)
3. **Priorizar datos del backend** cuando estén disponibles

Esto permite:
- ✅ Experiencia instantánea (localStorage)
- ✅ Persistencia robusta (backend)
- ✅ Funciona entre dispositivos (backend)

## 📋 Checklist de Implementación

- [ ] Crear script SQL `add_campos_modificados_manual.sql`
- [ ] Actualizar `PedidoRepository.update_costo_detalle()` para marcar flag
- [ ] Actualizar `PedidoRepository.update_total_detalle()` para marcar flag
- [ ] Actualizar `PedidoRepository.update_comentario_detalle()` para marcar flag
- [ ] Actualizar `PedidoRepository.get_pedido_completo()` para incluir flags en respuesta
- [ ] Verificar que los endpoints PATCH devuelven información de flags (opcional, ya viene en get_pedido_completo)
- [ ] Probar flujo completo: modificar campo → cargar pedido → verificar resaltado
- [ ] Documentar cambios para el equipo de frontend

## 🔗 Integración con Frontend

El frontend debe actualizar su código para:

1. **Al recibir datos del backend:**
   ```typescript
   const columnasModificadas = useColumnasModificadas();
   
   pedido.detalles.forEach(detalle => {
     if (detalle.costo_modificado_manual) {
       columnasModificadas.marcarComoModificado(detalle.pedido_detalle_id, 'costo_doc_sin_iva');
     }
     if (detalle.total_modificado_manual) {
       columnasModificadas.marcarComoModificado(detalle.pedido_detalle_id, 'total');
     }
     if (detalle.comentario_modificado_manual) {
       columnasModificadas.marcarComoModificado(detalle.pedido_detalle_id, 'comentario');
     }
   });
   ```

2. **Al modificar un campo:**
   - Actualizar `localStorage` inmediatamente (para UX)
   - Llamar al endpoint PATCH correspondiente (backend actualiza el flag automáticamente)
   - Opcionalmente recargar desde backend para sincronizar

3. **Prioridad de datos:**
   - Si el backend devuelve flags → usar esos (más confiable)
   - Si no hay flags del backend → usar `localStorage` (fallback)

## 📚 Referencias

- Script SQL de auditoría existente: `scripts/add_audit_fields_pedido_detalle.sql`
- Endpoints de edición: `src/endpoints/plantillas.py` (líneas 1326-1608)
- Repositorio de pedidos: `src/database/repositories/pedido_repository.py`
