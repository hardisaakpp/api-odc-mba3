# Resumen: Base de Datos con Formato Real del Excel

## 📊 Formato Real del Excel

**Template_Pedido_Inicial_v1.0.xlsx**

- **Hoja 1: CABECERA_PEDIDO** (formato clave-valor)
- **Hoja 2: DETALLE_ARTICULO** (formato tabular)

---

## 🗄️ Estructura de Base de Datos

### Tablas Existentes (Sin Cambios Estructurales)

La estructura actual **ya soporta** el nuevo formato. Solo se requiere agregar el campo `fila_origen`:

```
┌─────────────────────────────────────────┐
│ tienda                                  │
├─────────────────────────────────────────┤
│ tienda_id (PK)                          │
│ codigo (UNIQUE) ← IdTienda del Excel   │
│ nombre                                  │
│ activa                                  │
└─────────────────────────────────────────┘
              ↑
              │ FK
┌─────────────────────────────────────────┐
│ pedido_detalle_tienda                  │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ pedido_detalle_id (FK)                  │
│ tienda_id (FK)                          │
│ cantidad ← Cantidad del Excel          │
│ fila_origen (NUEVO) ← Fila del Excel   │
└─────────────────────────────────────────┘
              ↑
              │ FK
┌─────────────────────────────────────────┐
│ pedido_detalle                         │
├─────────────────────────────────────────┤
│ pedido_detalle_id (PK)                 │
│ pedido_id (FK)                         │
│ codigo_interno ← CodigoProducto Excel  │
│ descripcion_sap                        │
│ marca                                  │
│ codigo_barras                          │
│ pack                                   │
│ ...                                    │
└─────────────────────────────────────────┘
              ↑
              │ FK
┌─────────────────────────────────────────┐
│ pedido                                 │
├─────────────────────────────────────────┤
│ pedido_id (PK)                         │
│ numero_pedido (UNIQUE)                 │
│ fecha_pedido                            │
│ fecha_entrega                           │
│ forma_pago                              │
│ proveedor_nombre                        │
│ comprador_nombre                        │
│ ... (campos de CABECERA_PEDIDO)        │
│ archivo_nombre                          │
│ creado_por                              │
└─────────────────────────────────────────┘
```

---

## 🔄 Flujo Completo: Excel → Base de Datos

### Paso 1: Parsing (Fase 1 - Tarea 2)

**Endpoint:** `POST /pedidos/importar-excel`

**Input:**
- Excel con 2 hojas: `CABECERA_PEDIDO` y `DETALLE_ARTICULO`

**Proceso:**
1. Lee `CABECERA_PEDIDO` → diccionario clave-valor
2. Lee `DETALLE_ARTICULO` → tabla con headers
3. Valida estructura técnica
4. Detecta duplicados (CodigoProducto + IdTienda)
5. Normaliza datos (trim, espacios dobles, tipos)

**Output:**
```json
{
  "cabecera": {
    "Número de pedido": "P-12.48",
    "Fecha de pedido": "21/01/2025",
    ...
  },
  "resumen": {...},
  "errores": [...],
  "data": [
    {
      "codigoProducto": "R225.1012.BCO",
      "idTienda": "T001",
      "cantidad": 10,
      "filaOrigen": 2
    }
  ]
}
```

**⚠️ NO se guarda en BD** - Solo parsing técnico.

---

### Paso 2: Validación y Guardado (Fase 1 - Tarea 3)

**Endpoint:** `POST /api/plantillas/upload`

**Proceso:**
1. Usa resultado del parsing (o parsea internamente)
2. Valida datos pre-negocio (catálogo, tiendas, unidades, fechas)
3. Si pasa validación → Guarda en BD:

**Mapeo a BD:**

**CABECERA_PEDIDO → `pedido`**
```sql
INSERT INTO pedido (
    numero_pedido,      -- De "Número de pedido"
    fecha_pedido,       -- De "Fecha de pedido" (convertido a DATE)
    fecha_entrega,      -- De "Fecha de entrega"
    forma_pago,         -- De "Forma de pago"
    proveedor_nombre,   -- De "Nombre de proveedor"
    comprador_nombre,   -- De "Nombre de comprador"
    ...
    archivo_nombre,     -- Nombre del Excel subido
    creado_por          -- User ID del JWT
)
```

**DETALLE_ARTICULO → `pedido_detalle` + `pedido_detalle_tienda`**

Para cada fila válida del detalle:

```sql
-- 1. Crear/obtener producto (si no existe ya para este pedido)
INSERT INTO pedido_detalle (
    pedido_id,
    codigo_interno,     -- De "Código/SKU"
    descripcion_sap,    -- De "Descripción SAP"
    marca,              -- De "Marca"
    codigo_barras,      -- De "Código de barras"
    pack,               -- De "Pack"
    ...
)

-- 2. Crear/obtener tienda (si no existe)
INSERT INTO tienda (codigo, nombre)  -- codigo = IdTienda del Excel
ON CONFLICT DO NOTHING;

-- 3. Crear distribución
INSERT INTO pedido_detalle_tienda (
    pedido_detalle_id,
    tienda_id,
    cantidad,           -- De "Cantidad"
    fila_origen         -- De filaOrigen del parsing
)
```

---

## 📝 Ejemplo Completo

### Excel Input

**CABECERA_PEDIDO:**
| Campo | Valor |
|-------|-------|
| Número de pedido | P-12.48 |
| Fecha de pedido | 21/01/2025 |
| Proveedor | Proveedor XYZ |

**DETALLE_ARTICULO:**
| Código/SKU | IdTienda | Cantidad |
|------------|----------|----------|
| R225.1012.BCO | T001 | 10 |
| R225.1012.BCO | T002 | 5 |
| A889.3321.NEG | T001 | 2 |

### Base de Datos Resultante

**pedido:**
```sql
pedido_id: 'abc-123...'
numero_pedido: 'P-12.48'
fecha_pedido: '2025-01-21'
proveedor_nombre: 'Proveedor XYZ'
archivo_nombre: 'Template_Pedido_Inicial_v1.0.xlsx'
```

**pedido_detalle:**
```sql
-- Producto 1
pedido_detalle_id: 'def-456...'
pedido_id: 'abc-123...'
codigo_interno: 'R225.1012.BCO'

-- Producto 2
pedido_detalle_id: 'ghi-789...'
pedido_id: 'abc-123...'
codigo_interno: 'A889.3321.NEG'
```

**pedido_detalle_tienda:**
```sql
-- Distribución 1
id: 'jkl-012...'
pedido_detalle_id: 'def-456...'
tienda_id: (UUID de T001)
cantidad: 10
fila_origen: 2

-- Distribución 2
id: 'mno-345...'
pedido_detalle_id: 'def-456...'
tienda_id: (UUID de T002)
cantidad: 5
fila_origen: 3

-- Distribución 3
id: 'pqr-678...'
pedido_detalle_id: 'ghi-789...'
tienda_id: (UUID de T001)
cantidad: 2
fila_origen: 4
```

---

## ✅ Cambios Necesarios en BD

### 1. Ejecutar Script de Migración

```sql
-- scripts/add_fila_origen_pedido.sql
ALTER TABLE pedido_detalle_tienda
ADD fila_origen INT NULL;

CREATE INDEX idx_pedido_detalle_tienda_fila_origen 
ON pedido_detalle_tienda(fila_origen);
```

### 2. Código Actualizado

✅ **Repositorio** - Acepta `fila_origen` opcional
✅ **Servicio** - Pasa `fila_origen` al guardar
✅ **Parsing** - Retorna `filaOrigen` para cada registro

---

## 🎯 Resumen Final

### Estructura de BD
- ✅ **Sin cambios estructurales** - Solo campo opcional `fila_origen`
- ✅ **Retrocompatible** - Funciona sin el campo nuevo
- ✅ **Soporta formato real** - Dos hojas (cabecera + detalle)

### Flujo Implementado
- ✅ **Parsing técnico** - Lee ambas hojas correctamente
- ✅ **Validación estructura** - Valida hojas y columnas
- ✅ **Detección duplicados** - Marca como ERROR (no consolida)
- ✅ **Guardado completo** - Mapea cabecera y detalle a BD

### Próximos Pasos
1. Ejecutar script de migración (`add_fila_origen_pedido.sql`)
2. Probar con archivo Excel real
3. Verificar que `fila_origen` se guarde correctamente

---

## 📚 Documentación Relacionada

- `docs/FORMATO_EXCEL_PEDIDOS.md` - Descripción completa del formato Excel
- `docs/ESTRUCTURA_BD_PEDIDOS.md` - Estructura detallada de BD
- `scripts/add_fila_origen_pedido.sql` - Script de migración

