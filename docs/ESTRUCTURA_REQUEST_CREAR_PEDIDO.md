# Estructura de Request para Crear Pedido Manual (POST /api/pedidos)

## ⚠️ Problema Identificado

El frontend está enviando una estructura incorrecta al endpoint `POST /api/pedidos`. Este documento explica la estructura correcta esperada por el backend.

---

## ❌ Estructura Incorrecta (Frontend Actual)

```json
{
  "cabecera": {
    "numero_pedido": "P-12.56 - 12 - 2025",
    "fecha_pedido": "2025-12-25",
    "fecha_entrega": "INMEDIATO",
    "forma_pago": "120 DIAS",
    "proveedor_nombre": "TEXTILES EL RAYO S.A.",
    "comprador_nombre": "VACA ANDREA",
    "comprador_codigo": "801",
    "origen_traslado": "RL-CD",
    "serie": "10131"
  },
  "articulos": [
    {
      "codigo_producto": "R5000.911.AJCL",  // ❌ INCORRECTO
      "costo_unitario": 6.9,                // ❌ INCORRECTO
      "cantidad_total": 5,
      "comentario": "nuevo",
      "distribuciones": [
        {
          "tienda_codigo": "TOUT-COT",
          "cantidad": 5
        }
      ]
    }
  ]
}
```

**Errores:**
1. ❌ Campos de cabecera están dentro de objeto `cabecera` (deben estar en el body raíz)
2. ❌ `codigo_producto` debe ser `codigo_interno`
3. ❌ `costo_unitario` debe ser `costo_doc_sin_iva`

---

## ✅ Estructura Correcta Esperada por el Backend

```json
{
  "numero_pedido": "P-12.56 - 12 - 2025",
  "fecha_pedido": "2025-12-25",
  "fecha_entrega": "INMEDIATO",
  "forma_pago": "120 DIAS",
  "odc": null,
  "proveedor_nombre": "TEXTILES EL RAYO S.A.",
  "comprador_nombre": "VACA ANDREA",
  "comprador_codigo": "801",
  "origen_traslado": "RL-CD",
  "serie": "10131",
  "articulos": [
    {
      "codigo_interno": "R5000.911.AJCL",
      "descripcion_sap": "DESCRIPCION DEL PRODUCTO",
      "marca": "MARCA",
      "codigo_barras": null,
      "pack": null,
      "costo_doc_sin_iva": 6.9,
      "descuento_1": null,
      "pvp": null,
      "subtotal": null,
      "total": null,
      "distribuciones": [
        {
          "tienda_codigo": "TOUT-COT",
          "tienda_nombre": null,
          "cantidad": 5
        }
      ]
    }
  ],
  "validar_productos": true,
  "validar_tiendas": true
}
```

---

## 📋 Campos de Cabecera (Nivel Raíz del Body)

Los campos de cabecera **NO** van dentro de un objeto `cabecera`. Deben ir directamente en el body:

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `numero_pedido` | `string` | ✅ **SÍ** | Número único del pedido |
| `fecha_pedido` | `string` | No | Fecha del pedido (YYYY-MM-DD) |
| `fecha_entrega` | `string` | No | Fecha de entrega o "INMEDIATO" |
| `forma_pago` | `string` | No | Forma de pago |
| `odc` | `string` | No | Orden de compra interna |
| `proveedor_nombre` | `string` | No | Nombre del proveedor |
| `comprador_nombre` | `string` | No | Nombre del comprador |
| `comprador_codigo` | `string` | No | Código del comprador |
| `origen_traslado` | `string` | No | Origen de traslado (bodega) |
| `serie` | `string` | No | Serie del documento |

---

## 📦 Campos de Artículos (`articulos[]`)

Cada artículo debe tener la siguiente estructura:

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `codigo_interno` | `string` | ✅ **SÍ** | Código del producto (SKU) |
| `descripcion_sap` | `string` | No | Descripción del producto |
| `marca` | `string` | No | Marca del producto |
| `codigo_barras` | `string` | No | Código de barras |
| `pack` | `string` | No | Tipo de empaque/pack |
| `costo_doc_sin_iva` | `float` | No | Costo sin IVA (>= 0) |
| `descuento_1` | `float` | No | Descuento porcentual (0-100) |
| `pvp` | `float` | No | Precio de venta público (>= 0) |
| `subtotal` | `float` | No | Subtotal del artículo |
| `total` | `float` | No | Total del artículo |
| `distribuciones` | `array` | ✅ **SÍ** | Lista de distribuciones por tienda (min: 1) |

---

## 🏪 Campos de Distribución (`distribuciones[]`)

Cada distribución debe tener:

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `tienda_codigo` | `string` | ✅ **SÍ** | Código de la tienda (ej: "TOUT-COT", "TRL-QSN") |
| `tienda_nombre` | `string` | No | Nombre de la tienda (opcional) |
| `cantidad` | `integer` | ✅ **SÍ** | Cantidad a distribuir (>= 1) |

---

## 🔄 Campos de Validación (Opcionales)

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `validar_productos` | `boolean` | `true` | Validar que productos existan en catálogo |
| `validar_tiendas` | `boolean` | `true` | Validar que tiendas existan y estén activas |

---

## 🔍 Mapeo de Campos Frontend → Backend

| Frontend (Actual) | Backend (Esperado) | Notas |
|-------------------|-------------------|-------|
| `cabecera.numero_pedido` | `numero_pedido` | Mover a nivel raíz |
| `cabecera.fecha_pedido` | `fecha_pedido` | Mover a nivel raíz |
| `cabecera.fecha_entrega` | `fecha_entrega` | Mover a nivel raíz |
| `cabecera.forma_pago` | `forma_pago` | Mover a nivel raíz |
| `cabecera.proveedor_nombre` | `proveedor_nombre` | Mover a nivel raíz |
| `cabecera.comprador_nombre` | `comprador_nombre` | Mover a nivel raíz |
| `cabecera.comprador_codigo` | `comprador_codigo` | Mover a nivel raíz |
| `cabecera.origen_traslado` | `origen_traslado` | Mover a nivel raíz |
| `cabecera.serie` | `serie` | Mover a nivel raíz |
| `articulos[].codigo_producto` | `articulos[].codigo_interno` | Cambiar nombre |
| `articulos[].costo_unitario` | `articulos[].costo_doc_sin_iva` | Cambiar nombre |
| `articulos[].cantidad_total` | ❌ Eliminar | No se usa en el backend |
| `articulos[].comentario` | ❌ Eliminar | No se usa en el backend |
| `articulos[].distribuciones[].tienda_codigo` | `articulos[].distribuciones[].tienda_codigo` | ✅ Correcto |
| `articulos[].distribuciones[].cantidad` | `articulos[].distribuciones[].cantidad` | ✅ Correcto |

---

## 📝 Ejemplo Completo de Request Correcto

```json
{
  "numero_pedido": "P-12.56 - 12 - 2025",
  "fecha_pedido": "2025-12-25",
  "fecha_entrega": "INMEDIATO",
  "forma_pago": "120 DIAS",
  "proveedor_nombre": "TEXTILES EL RAYO S.A.",
  "comprador_nombre": "VACA ANDREA",
  "comprador_codigo": "801",
  "origen_traslado": "RL-CD",
  "serie": "10131",
  "articulos": [
    {
      "codigo_interno": "R5000.911.AJCL",
      "costo_doc_sin_iva": 6.9,
      "distribuciones": [
        {
          "tienda_codigo": "TOUT-COT",
          "cantidad": 5
        }
      ]
    }
  ],
  "validar_productos": true,
  "validar_tiendas": true
}
```

---

## 🔧 Corrección Necesaria en el Frontend

### JavaScript/TypeScript

```typescript
// ❌ INCORRECTO (Estructura actual)
const requestBody = {
  cabecera: {
    numero_pedido: formData.numero_pedido,
    fecha_pedido: formData.fecha_pedido,
    // ...
  },
  articulos: articulos.map(art => ({
    codigo_producto: art.codigo_producto,
    costo_unitario: art.costo_unitario,
    // ...
  }))
};

// ✅ CORRECTO (Estructura esperada)
const requestBody = {
  // Campos de cabecera directamente en el body (NO dentro de "cabecera")
  numero_pedido: formData.numero_pedido,
  fecha_pedido: formData.fecha_pedido,
  fecha_entrega: formData.fecha_entrega,
  forma_pago: formData.forma_pago,
  proveedor_nombre: formData.proveedor_nombre,
  comprador_nombre: formData.comprador_nombre,
  comprador_codigo: formData.comprador_codigo,
  origen_traslado: formData.origen_traslado,
  serie: formData.serie,
  
  // Artículos con nombres de campo correctos
  articulos: articulos.map(art => ({
    codigo_interno: art.codigo_producto,        // Cambiar nombre
    costo_doc_sin_iva: art.costo_unitario,      // Cambiar nombre
    descripcion_sap: art.descripcion_sap,
    marca: art.marca,
    distribuciones: art.distribuciones.map(dist => ({
      tienda_codigo: dist.tienda_codigo,
      cantidad: dist.cantidad
    }))
  })),
  
  // Opciones de validación
  validar_productos: true,
  validar_tiendas: true
};
```

---

## ✅ Validación del Modelo Backend

El modelo `CrearPedidoRequest` en `src/models.py` (líneas 1251-1298) define:

```python
class CrearPedidoRequest(BaseModel):
    # Campos de cabecera (directamente en el modelo, NO anidados)
    numero_pedido: str = Field(..., description="Número único del pedido")
    fecha_pedido: Optional[str] = Field(None, ...)
    fecha_entrega: Optional[str] = Field(None, ...)
    forma_pago: Optional[str] = Field(None, ...)
    # ...
    
    # Artículos
    articulos: List[ArticuloRequest] = Field(..., min_length=1)
    
class ArticuloRequest(BaseModel):
    codigo_interno: str = Field(..., description="Código del producto (SKU)")
    costo_doc_sin_iva: Optional[float] = Field(None, ge=0, ...)
    distribuciones: List[DistribucionTiendaRequest] = Field(..., min_length=1)
```

**Nota importante:** FastAPI valida automáticamente que los campos requeridos (`numero_pedido`, `codigo_interno`, etc.) estén presentes y en la estructura correcta.

---

## 🎯 Resumen de Cambios Necesarios

1. ✅ **Mover campos de cabecera al nivel raíz** (eliminar objeto `cabecera`)
2. ✅ **Cambiar `codigo_producto` → `codigo_interno`** en artículos
3. ✅ **Cambiar `costo_unitario` → `costo_doc_sin_iva`** en artículos
4. ✅ **Eliminar campos no usados:** `cantidad_total`, `comentario` (si no son necesarios)
5. ✅ **Mantener estructura de `distribuciones`** (ya está correcta)

---

## 📚 Referencias

- **Modelo Backend:** `src/models.py` - `CrearPedidoRequest` (líneas 1251-1298)
- **Endpoint:** `src/endpoints/plantillas.py` - `POST /api/pedidos` (líneas 1026-1157)
- **Documentación:** Ver documentación de FastAPI en `/docs` cuando el servidor esté corriendo

---

**Última actualización:** 25 de Diciembre de 2025
