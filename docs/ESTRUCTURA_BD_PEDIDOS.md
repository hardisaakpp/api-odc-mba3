# Estructura de Base de Datos - Pedidos

> **Alcance:** este documento explica con ejemplos el modelo de las tablas de pedidos y el mapeo desde el Excel; fue escrito en febrero de 2026 y describe sobre todo las 4 tablas originales. Para el **esquema completo y exacto** (las 43 tablas con columnas, tipos, claves primarias y foráneas, leído de la base real) ver [ESQUEMA_BD.md](ESQUEMA_BD.md). Para qué hace cada migración y en qué orden se aplican ver [CATALOGO_MIGRACIONES.md](CATALOGO_MIGRACIONES.md). Los campos agregados después de este documento están resumidos en [«Campos agregados posteriormente»](#campos-agregados-posteriormente).

## 📊 Modelo de Datos

El sistema de pedidos utiliza un modelo jerárquico de 3 niveles:

```
pedido (cabecera)
  └── pedido_detalle (productos)
       └── pedido_detalle_tienda (distribución por tienda)
```

---

## 🗂️ Tablas

### 1. `tienda` (Maestro de Tiendas)

Almacena el catálogo de tiendas/sucursales.

```sql
CREATE TABLE tienda (
    tienda_id UNIQUEIDENTIFIER PRIMARY KEY,
    codigo NVARCHAR(100) NOT NULL UNIQUE,  -- Ej: "T001", "RECREO"
    nombre NVARCHAR(150) NULL,              -- Nombre descriptivo
    activa BIT DEFAULT 1,
    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME DEFAULT GETDATE()
);
```

**Características:**
- Se crea automáticamente si no existe cuando se procesa un pedido
- `codigo` es único y se usa como identificador principal
- `activa` permite deshabilitar tiendas sin eliminarlas

---

### 2. `pedido` (Cabecera del Pedido)

Almacena la información general del pedido.

```sql
CREATE TABLE pedido (
    pedido_id UNIQUEIDENTIFIER PRIMARY KEY,
    numero_pedido NVARCHAR(50) NOT NULL UNIQUE,  -- Business key
    fecha_pedido DATE NULL,
    fecha_entrega NVARCHAR(50) NULL,            -- "INMEDIATO" o fecha
    forma_pago NVARCHAR(50) NULL,
    odc NVARCHAR(50) NULL,
    proveedor_nombre NVARCHAR(150) NULL,
    comprador_nombre NVARCHAR(150) NULL,
    comprador_codigo NVARCHAR(50) NULL,
    origen_traslado NVARCHAR(50) NULL,
    serie NVARCHAR(50) NULL,
    archivo_nombre NVARCHAR(255) NOT NULL,      -- Nombre del Excel original
    creado_por NVARCHAR(450) NULL,              -- User ID del JWT
    creado_en DATETIME DEFAULT GETDATE()
);
```

**Características:**
- `numero_pedido` es único (business key)
- `archivo_nombre` permite rastrear el origen del pedido
- `creado_por` almacena el usuario que subió el archivo
- **Estados:** el pedido tiene `estado` (legacy string) y/o `estado_id` (FK a `pedido_estado`). Ver [ESTADOS_PEDIDO.md](ESTADOS_PEDIDO.md) para la tabla maestra y migración.

---

### 3. `pedido_detalle` (Productos del Pedido)

Almacena cada producto/artículo del pedido.

```sql
CREATE TABLE pedido_detalle (
    pedido_detalle_id UNIQUEIDENTIFIER PRIMARY KEY,
    pedido_id UNIQUEIDENTIFIER NOT NULL,
    
    -- Información del producto
    codigo_interno NVARCHAR(50) NULL,           -- CodigoProducto del Excel
    descripcion_sap NVARCHAR(255) NULL,
    marca NVARCHAR(50) NULL,
    codigo_barras NVARCHAR(50) NULL,
    
    -- Datos SAP
    pack NVARCHAR(50) NULL,
    
    -- Precios (NO cantidad aquí, va en pedido_detalle_tienda)
    costo_doc_sin_iva DECIMAL(18, 4) NULL,
    descuento_1 DECIMAL(5, 2) NULL,
    pvp DECIMAL(18, 4) NULL,
    
    -- Totales (se guardan tal cual vienen del Excel, NO se recalculan)
    subtotal DECIMAL(18, 2) NULL,
    total DECIMAL(18, 2) NULL,
    
    created_at DATETIME DEFAULT GETDATE(),
    
    FOREIGN KEY (pedido_id) REFERENCES pedido(pedido_id) ON DELETE CASCADE
);
```

**Características:**
- Un producto puede tener múltiples distribuciones por tienda
- `codigo_interno` corresponde al `CodigoProducto` del Excel
- Los totales se guardan tal cual vienen del Excel (no se recalculan)

---

### 4. `pedido_detalle_tienda` (Distribución por Tienda)

Almacena la cantidad de cada producto por tienda.

```sql
CREATE TABLE pedido_detalle_tienda (
    id UNIQUEIDENTIFIER PRIMARY KEY,
    pedido_detalle_id UNIQUEIDENTIFIER NOT NULL,
    tienda_id UNIQUEIDENTIFIER NOT NULL,
    cantidad INT NOT NULL CHECK (cantidad > 0),
    fila_origen INT NULL,                        -- Fila del Excel (nuevo campo)
    created_at DATETIME DEFAULT GETDATE(),
    
    FOREIGN KEY (pedido_detalle_id) REFERENCES pedido_detalle(pedido_detalle_id) ON DELETE CASCADE,
    FOREIGN KEY (tienda_id) REFERENCES tienda(tienda_id) ON DELETE CASCADE,
    UNIQUE (pedido_detalle_id, tienda_id)       -- Un producto no puede tener dos distribuciones para la misma tienda
);
```

**Características:**
- `cantidad` es el único campo que varía por tienda
- `fila_origen` permite rastrear de qué fila del Excel vino el registro (auditoría)
- Constraint UNIQUE evita duplicados producto+tienda en el mismo detalle

---

## 🔄 Flujo de Datos

### Fase 1 - Tarea 2: Parsing Técnico

```
Excel → parsear_excel_pedido() → {
    resumen: { filasLeidas, filasValidas, filasInvalidas },
    errores: [...],
    data: [
        { codigoProducto, idTienda, cantidad, filaOrigen }
    ]
}
```

**NO se guarda en BD en esta fase** - Solo parsing y validación técnica.

---

### Fase 1 - Tarea 3: Validaciones Pre-Negocio

```
Resultado del parsing → validar_y_procesar_archivo_excel() → {
    validation: { valid, errors, warnings, issues_by_row },
    pedido_id: "...",
    articulos_cargados: N,
    distribuciones_cargadas: M
}
```

**SÍ se guarda en BD** si pasa las validaciones:

1. **Crear cabecera** en `pedido`
   - `numero_pedido`: Auto-generado o del Excel
   - `archivo_nombre`: Nombre del archivo subido
   - `creado_por`: User ID del JWT

2. **Para cada producto válido** en `data`:
   - **Crear detalle** en `pedido_detalle`
     - `codigo_interno`: Del campo `codigoProducto`
     - Otros campos: NULL (formato simple) o del Excel (formato complejo)
   
   - **Para cada distribución** (producto + tienda):
     - **Crear/obtener tienda** en `tienda` (si no existe)
     - **Crear distribución** en `pedido_detalle_tienda`
       - `cantidad`: Del campo `cantidad`
       - `fila_origen`: Del campo `filaOrigen` (si está disponible)

---

## 📝 Mapeo Excel → BD

### Formato Simple (CodigoProducto, IdTienda, Cantidad)

**Excel:**
```
Fila 2: R225.1012.BCO | T001 | 10
Fila 3: R225.1012.BCO | T002 | 5
Fila 4: A889.3321.NEG | T001 | 2
```

**BD Resultante:**

**pedido:**
```
pedido_id: abc-123...
numero_pedido: AUTO-20250121-120000
archivo_nombre: pedido.xlsx
```

**pedido_detalle:**
```
pedido_detalle_id: def-456...
pedido_id: abc-123...
codigo_interno: R225.1012.BCO
```

**pedido_detalle_tienda:**
```
id: ghi-789...
pedido_detalle_id: def-456...
tienda_id: (T001)
cantidad: 10
fila_origen: 2
```

```
id: jkl-012...
pedido_detalle_id: def-456...
tienda_id: (T002)
cantidad: 5
fila_origen: 3
```

**pedido_detalle:**
```
pedido_detalle_id: mno-345...
pedido_id: abc-123...
codigo_interno: A889.3321.NEG
```

**pedido_detalle_tienda:**
```
id: pqr-678...
pedido_detalle_id: mno-345...
tienda_id: (T001)
cantidad: 2
fila_origen: 4
```

---

## 🔍 Consultas Útiles

### Obtener pedido completo con distribuciones

```sql
SELECT 
    p.numero_pedido,
    p.archivo_nombre,
    pd.codigo_interno,
    t.codigo AS tienda_codigo,
    t.nombre AS tienda_nombre,
    pdt.cantidad,
    pdt.fila_origen
FROM pedido p
INNER JOIN pedido_detalle pd ON p.pedido_id = pd.pedido_id
INNER JOIN pedido_detalle_tienda pdt ON pd.pedido_detalle_id = pdt.pedido_detalle_id
INNER JOIN tienda t ON pdt.tienda_id = t.tienda_id
WHERE p.pedido_id = @pedido_id
ORDER BY pd.codigo_interno, t.codigo;
```

### Buscar por fila origen (debugging)

```sql
SELECT 
    p.numero_pedido,
    pd.codigo_interno,
    t.codigo AS tienda_codigo,
    pdt.cantidad,
    pdt.fila_origen
FROM pedido_detalle_tienda pdt
INNER JOIN pedido_detalle pd ON pdt.pedido_detalle_id = pd.pedido_detalle_id
INNER JOIN pedido p ON pd.pedido_id = p.pedido_id
INNER JOIN tienda t ON pdt.tienda_id = t.tienda_id
WHERE pdt.fila_origen = 18;
```

---

## 📋 Formato Excel

El sistema soporta el formato `Template_Pedido_Inicial_v1.0.xlsx` con dos hojas:

1. **CABECERA_PEDIDO** (formato clave-valor) → Mapea a tabla `pedido`
2. **DETALLE_ARTICULO** (formato tabular) → Mapea a `pedido_detalle` + `pedido_detalle_tienda`

Ver [FORMATO_EXCEL_PEDIDOS.md](FORMATO_EXCEL_PEDIDOS.md) y [MAPEO_CABECERA_PEDIDO.md](MAPEO_CABECERA_PEDIDO.md) para detalles completos.

## 🆕 Cambios Recientes

### Campo `fila_origen` (Nuevo)

**Script:** `scripts/add_fila_origen_pedido.sql`

Permite rastrear de qué fila del Excel vino cada registro, útil para:
- Auditoría
- Debugging
- Reportes de trazabilidad

**Nota:** El campo es opcional (NULL) para mantener compatibilidad con datos existentes.

---

### Campos agregados posteriormente

Resumen de columnas que este documento no describe, con la migración que las creó y el tipo actual en la base (verificado el 01/10/2026 contra `ESQUEMA_BD.md`). Descripción tomada del manifest de migraciones.

| Tabla | Campo | Tipo en BD | Qué es | Migración |
|---|---|---|---|---|
| `pedido` | `pedido_padre_id` | uniqueidentifier, null (FK a `pedido.pedido_id`) | Enlaza el pedido **hijo** de una Producción Pospuesta (`numero_pedido = '<original>.NN'`) con su pedido original. Un pedido es parcial si `pedido_padre_id IS NOT NULL`; no hay columna booleana aparte. | 643 |
| `pedido` | `fecha_facturacion` | date, null | Fecha de facturación; en blanco por defecto. Exclusiva de `odcsap.view` (EL RAYO) y editable solo con el pedido en Confirmado y Enviado; habilita "Despachar y Facturar". | 627 |
| `pedido` | `numero_pedido` | nvarchar(100), not null | Ampliado de 50 a 100 caracteres (solo amplía, nunca reduce). | 665 |
| `pedido` | `mensaje` | nvarchar(500), null | Ampliado a 500 caracteres (también en `pedido_original`). | 668 |
| `pedido_detalle` | `cantidad_solicitada_original` | decimal(18,4), null | Cantidad pedida originalmente. Se escribe **una sola vez** al cargar el Excel y no la tocan las ediciones de "Total", para poder calcular la diferencia con el total vigente. Filas anteriores a la migración quedan en NULL. | 641 |
| `pedido_detalle_tienda` | `cantidad_solicitada_original` | decimal(18,4), null | Lo mismo, a nivel de tienda. | 642 |
| `pedido_detalle_tienda` | `cantidad` | decimal(18,4), not null | Ahora admite decimales (0.5, 1.5, 2.25); antes era entera y se truncaba. | 666 |
| `pedido_detalle` | `costo_margen` | decimal(18,4), null | Columna "Costo" de la plantilla Excel; solo informativa. Distinta de `costo_doc_sin_iva`. | 618 |
| `pedido_detalle` | `costo_unitario` | decimal(18,4), null | `costo_doc_sin_iva / unidad_conversion` (por el pack ya resuelto entre SAP y Excel). Es el insumo del **Margen de Rentabilidad** y reemplaza a `costo_margen` para ese cálculo. | 619 |
| `pedido_detalle` | `orden_linea` | int, not null | Conserva el orden de las filas de la plantilla en las pantallas y en los Excel (también en `pedido_detalle_original`). | 607, 609 |
| `tienda` | `marca` | nvarchar(20), null | ROLAND, REGIONS o DESCUENTON, sincronizada desde `sc_maestros.dbo.almacenes_local`. Permite saber a qué bodega (RL-CD, RG-CD, OUT-CD) pertenece cada tienda; base de las **dos ODC** para pedidos que mezclan marcas. | 648 |
| `distribucion_confirmada` | `agregada_manualmente` | bit, not null (0) | Marca las tiendas agregadas a mano en la Vista Excel de Redistribución (pedidos hijo, fuera del Excel original), para que el resaltado se conserve al recargar o confirmar. | 658 |
| varias | `creado_por`, `modificado_por`, `modificado_fecha`, `origen`, `ip_origen` | — | Campos de auditoría en pedidos, despachos y órdenes de compra. | 661, 662 |

Tablas nuevas relacionadas con pedidos: `pedido_estado_historial` (bitácora de transiciones de estado, migración 664), `archivo_plantilla` (archivos Excel originales, 659) y `pedido_detalle_modificacion_columna` (qué celdas se editaron y por qué rol, 639). Detalle de columnas en [ESQUEMA_BD.md](ESQUEMA_BD.md).

---

## 📊 Índices

```sql
-- Búsqueda rápida por número de pedido
CREATE INDEX idx_pedido_numero_pedido ON pedido(numero_pedido);

-- Búsqueda por código de producto
CREATE INDEX idx_pedido_detalle_codigo_interno ON pedido_detalle(codigo_interno);

-- Búsqueda por tienda
CREATE INDEX idx_pedido_detalle_tienda_tienda_id ON pedido_detalle_tienda(tienda_id);

-- Búsqueda por fila origen (debugging)
CREATE INDEX idx_pedido_detalle_tienda_fila_origen ON pedido_detalle_tienda(fila_origen);
```

---

## ⚠️ Consideraciones

1. **No se consolidan duplicados**: Si el Excel tiene duplicados (mismo producto+tienda), se marcan como ERROR en el parsing, no se guardan.

2. **Totales no se recalculan**: Los campos `subtotal` y `total` se guardan tal cual vienen del Excel.

3. **Tiendas se crean automáticamente**: Si una tienda no existe, se crea automáticamente al procesar el pedido.

4. **Cascada de eliminación**: Si se elimina un `pedido`, se eliminan automáticamente sus detalles y distribuciones.

