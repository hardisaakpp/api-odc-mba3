# Query para Obtener Cantidades Confirmadas del Proveedor

Este documento describe el query SQL para obtener las cantidades confirmadas del proveedor que deben usarse al crear órdenes de compra para SAP.

## 📋 Propósito

Obtener productos con `cantidad_confirmada_total > 0` desde `pedido_respuesta_proveedor` para crear la orden de compra en SAP. Este es el flujo correcto según el negocio:

```
Pedido → Respuesta Proveedor (cantidades confirmadas) → Orden de Compra → SAP
```

## 🔍 Query SQL Base

```sql
-- ============================================================================
-- Query: Obtener cantidades confirmadas del proveedor para crear OC
-- ============================================================================
-- Devuelve productos con cantidad_confirmada_total > 0
-- Solo incluye respuestas en estado CONFIRMADO
-- ============================================================================

DECLARE @pedido_id UNIQUEIDENTIFIER = 'TU-PEDIDO-ID-AQUI'; -- Reemplazar

SELECT 
    -- Información de la respuesta
    r.respuesta_id,
    r.version,
    r.estado AS estado_respuesta,
    r.fecha_aprobacion,
    
    -- Información del pedido (cabecera)
    p.pedido_id,
    p.numero_pedido,
    p.proveedor_nombre,
    p.fecha_pedido,
    
    -- Información del producto (detalle)
    pd.pedido_detalle_id,
    pd.codigo_interno,  -- SKU MBA3
    pd.descripcion_sap,
    pd.pack AS pack_sap,  -- X1, X2, X3, etc.
    
    -- Cantidades
    rd.cantidad_solicitada_total,
    rd.cantidad_confirmada_total,  -- ⭐ ESTA ES LA QUE USAS
    
    -- Precios (usar ajustado si existe, sino original)
    COALESCE(rd.costo_doc_sin_iva_ajustado, rd.costo_doc_sin_iva_original) AS costo_unitario,
    COALESCE(rd.descuento_1_ajustado, rd.descuento_1_original) AS descuento,
    
    -- Metadatos
    rd.observaciones
    
FROM pedido_respuesta_proveedor r
INNER JOIN pedido p ON r.pedido_id = p.pedido_id
INNER JOIN pedido_respuesta_proveedor_detalle rd ON r.respuesta_id = rd.respuesta_id
INNER JOIN pedido_detalle pd ON rd.pedido_detalle_id = pd.pedido_detalle_id

WHERE 
    r.pedido_id = @pedido_id
    AND r.estado = 'CONFIRMADO'  -- ⚠️ IMPORTANTE: Verificar el estado correcto
    AND rd.cantidad_confirmada_total > 0  -- ⭐ Excluir productos con 0
    
ORDER BY pd.codigo_interno;
```

## ⚠️ Notas Importantes

### Estado de la Respuesta

El query filtra por `r.estado = 'CONFIRMADO'`. **Verifica** que este sea el estado final correcto en tu sistema. Podría ser:
- `'CONFIRMADO'`
- `'APROBADO'`
- `'PROCESADO'`
- Otro estado específico de tu flujo

**Ajusta el WHERE según tu caso.**

### Conversión de Unidades

El query retorna `cantidad_confirmada_total` en unidades MBA3 (docenas). 

**Para SAP necesitas convertir a packs:**

```python
cantidad_sap_packs = cantidad_confirmada_total * unidad_conversion
```

Donde `unidad_conversión` viene de:
- Tabla `pack_conversion` (por `pack_sap`)
- O tabla `producto_sap_cache`
- O tabla `sku_homologacion`

### Precios

El query usa `COALESCE` para preferir precios ajustados si existen:
- `costo_doc_sin_iva_ajustado` → si existe
- `costo_doc_sin_iva_original` → fallback

## 📝 Uso en Python

```python
def obtener_cantidades_confirmadas(
    conn,
    pedido_id: str
) -> List[Dict[str, Any]]:
    """
    Obtiene cantidades confirmadas del proveedor para un pedido.
    
    Args:
        conn: Conexión a BD
        pedido_id: UUID del pedido
        
    Returns:
        Lista de productos con cantidades confirmadas
    """
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                r.respuesta_id,
                pd.pedido_detalle_id,
                pd.codigo_interno,
                pd.descripcion_sap,
                pd.pack AS pack_sap,
                rd.cantidad_confirmada_total,
                COALESCE(rd.costo_doc_sin_iva_ajustado, rd.costo_doc_sin_iva_original) AS costo_unitario,
                COALESCE(rd.descuento_1_ajustado, rd.descuento_1_original) AS descuento
            FROM pedido_respuesta_proveedor r
            INNER JOIN pedido_respuesta_proveedor_detalle rd ON r.respuesta_id = rd.respuesta_id
            INNER JOIN pedido_detalle pd ON rd.pedido_detalle_id = pd.pedido_detalle_id
            WHERE 
                r.pedido_id = ?
                AND r.estado = 'CONFIRMADO'
                AND rd.cantidad_confirmada_total > 0
            ORDER BY pd.codigo_interno
        """, (pedido_id,))
        
        resultados = []
        for row in cursor.fetchall():
            resultados.append({
                "respuesta_id": str(row[0]),
                "pedido_detalle_id": str(row[1]),
                "codigo_interno": row[2],
                "descripcion_sap": row[3],
                "pack_sap": row[4],
                "cantidad_confirmada_total": int(row[5]),
                "costo_unitario": float(row[6]) if row[6] else None,
                "descuento": float(row[7]) if row[7] else None,
            })
        
        return resultados
    finally:
        cursor.close()
```

## 🔄 Integración con Flujo de OC

Este query debe usarse cuando se crea la OC desde un pedido confirmado. 

**Flujo recomendado:**
1. Validar que existe respuesta confirmada para el pedido
2. Ejecutar este query
3. Para cada producto:
   - Convertir `cantidad_confirmada_total` a packs SAP
   - Obtener `sku_sap` desde homologación
   - Crear línea en `orden_compra_detalle`
4. Crear cabecera en `orden_compra_cabecera` con `pedido_id`
5. Enviar a SAP

## ✅ Validaciones

Antes de usar los resultados:
- ✅ Verificar que `cantidad_confirmada_total > 0`
- ✅ Verificar que existe `sku_sap` homologado
- ✅ Verificar que existe conversión de unidades (pack_sap → unidad_conversion)
- ✅ Excluir productos sin precio unitario válido

