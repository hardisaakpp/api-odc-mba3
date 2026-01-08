# Formato Excel de Pedidos - Template_Pedido_Inicial_v1.0.xlsx

## 📋 Estructura del Archivo

El archivo Excel contiene **dos hojas independientes**:

1. **CABECERA_PEDIDO** - Información general del pedido
2. **DETALLE_ARTICULO** - Líneas de artículos del pedido

---

## 🧾 Hoja 1: CABECERA_PEDIDO

### Formato

**Tipo:** Clave-Valor (diccionario)

**Estructura:**
| Campo | Valor | Ejemplo |
|-------|-------|---------|
| Número de pedido | P-12.48 | P-12.48 |
| Fecha de pedido | 21/01/2025 | 21/01/2025 |
| Fecha de entrega | INMEDIATO | INMEDIATO |
| ... | ... | ... |

### Campos Típicos

- Número de pedido
- Fecha de pedido
- Fecha de entrega
- Forma de pago
- Código de proveedor
- Nombre de proveedor
- Código de comprador
- Nombre de comprador
- Origen de traslado
- Serie del documento
- Comentarios generales
- Estado del pedido

### Parsing

- Se procesa como un **diccionario** (`Campo → Valor`)
- No existen filas repetibles
- Los valores se guardan como texto (transformación a fechas, etc. se hace después)
- El backend valida campos obligatorios antes de procesar el detalle

---

## 📦 Hoja 2: DETALLE_ARTICULO

### Formato

**Tipo:** Tabular (tabla con headers)

**Estructura:**
| Identificador | Código/SKU | Marca | ... | Cantidad | IdTienda | ... |
|---------------|------------|-------|-----|----------|----------|-----|
| 1 | R225.1012.BCO | ... | ... | 10 | T001 | ... |
| 2 | R225.1012.BCO | ... | ... | 5 | T002 | ... |
| 3 | A889.3321.NEG | ... | ... | 2 | T001 | ... |

### Campos Típicos

- Identificador de línea
- **Código / SKU del producto** (obligatorio)
- Marca
- Código de barras
- Descripción del producto (SAP)
- Tipo de empaque / pack
- Costos y precios
- **Cantidad solicitada** (obligatorio)
- **Identificador de tienda** (obligatorio)
- Fecha asociada a la línea
- Comentarios por artículo
- Campo de error de validación (informativo, no se persiste)

### Parsing

- Primera fila = headers
- Cada fila siguiente = un artículo
- Campos numéricos se validan (cantidad, costos, precios)
- El campo de error **no se persiste**, solo sirve para feedback
- Si algún dato viene vacío, puede heredarse desde la cabecera (según reglas)

---

## 🔄 Flujo de Procesamiento

```
1. Cargar archivo Excel
   ↓
2. Validar que existan ambas hojas
   ↓
3. Leer CABECERA_PEDIDO (formato clave-valor)
   ↓
4. Validar campos obligatorios de cabecera
   ↓
5. Leer DETALLE_ARTICULO (formato tabular)
   ↓
6. Validar columnas obligatorias (CodigoProducto, IdTienda, Cantidad)
   ↓
7. Procesar cada fila del detalle:
   - Normalizar datos (trim, espacios dobles)
   - Validar tipos (cantidad = entero)
   - Detectar duplicados (CodigoProducto + IdTienda)
   ↓
8. Retornar resultado:
   {
     "cabecera": {...},
     "resumen": {...},
     "errores": [...],
     "data": [...]
   }
```

---

## 📊 Mapeo a Base de Datos

### Mapeo de CABECERA_PEDIDO → `pedido`

Según el encabezado real de la hoja `CABECERA_PEDIDO`, los campos se mapean así:

| Campo Excel | Campo BD | Tipo | Notas |
|-------------|----------|------|-------|
| **CODIGO PEDIDO** | `numero_pedido` | NVARCHAR(50) | UNIQUE, obligatorio |
| **FECHA PEDIDO** | `fecha_pedido` | DATE | Convertido de string (DD/MM/YYYY) |
| **FECHA ENTREGA** | `fecha_entrega` | NVARCHAR(50) | Puede ser "INMEDIATO" o fecha |
| **FORMA PAGO** | `forma_pago` | NVARCHAR(50) | |
| **ODC** | `odc` | NVARCHAR(50) | |
| **NOMBRE PROVEEDOR** | `proveedor_nombre` | NVARCHAR(150) | |
| **COMPRADOR NOMBRE** | `comprador_nombre` | NVARCHAR(150) | |
| **COD COMPRADOR** | `comprador_codigo` | NVARCHAR(50) | |
| **ORIGEN TRASLADO** | `origen_traslado` | NVARCHAR(50) | |
| **SERIE** | `serie` | NVARCHAR(50) | |
| (generado) | `archivo_nombre` | NVARCHAR(255) | Nombre del Excel subido |
| (generado) | `creado_por` | NVARCHAR(450) | User ID del JWT |
| (generado) | `creado_en` | DATETIME | Timestamp automático |

**Ejemplo de mapeo:**
```python
mapeo_campos_cabecera = {
    "CODIGO PEDIDO": "numero_pedido",
    "FECHA PEDIDO": "fecha_pedido",
    "FECHA ENTREGA": "fecha_entrega",
    "FORMA PAGO": "forma_pago",
    "ODC": "odc",
    "NOMBRE PROVEEDOR": "proveedor_nombre",
    "COMPRADOR NOMBRE": "comprador_nombre",
    "COD COMPRADOR": "comprador_codigo",
    "ORIGEN TRASLADO": "origen_traslado",
    "SERIE": "serie"
}
```

**Conversión de tipos:**
- **Fechas**: Se convierten de string (DD/MM/YYYY) a `date`
- **Strings**: Se mantienen como están (con trim)
- **NULLs**: Se preservan si el campo está vacío en el Excel

### Mapeo de DETALLE_ARTICULO → `pedido_detalle` + `pedido_detalle_tienda`

| Campo Excel | Campo BD | Tabla | Notas |
|-------------|----------|-------|-------|
| **Código/SKU** | `codigo_interno` | `pedido_detalle` | Obligatorio |
| **Marca** | `marca` | `pedido_detalle` | |
| **Código de barras** | `codigo_barras` | `pedido_detalle` | |
| **Descripción SAP** | `descripcion_sap` | `pedido_detalle` | |
| **Pack** | `pack` | `pedido_detalle` | |
| **Cantidad** | `cantidad` | `pedido_detalle_tienda` | Obligatorio, entero > 0 |
| **IdTienda** | `tienda_id` | `pedido_detalle_tienda` | Obligatorio (vía tabla `tienda`) |
| (generado) | `fila_origen` | `pedido_detalle_tienda` | Fila del Excel (auditoría) |

---

## ✅ Validaciones Técnicas (Fase 1 - Tarea 2)

### Archivo
- ✅ Extensión: `.xlsx`
- ✅ Tamaño máximo: 10 MB
- ✅ Hojas obligatorias: `CABECERA_PEDIDO` y `DETALLE_ARTICULO`

### Cabecera
- ✅ Debe existir la hoja `CABECERA_PEDIDO`
- ✅ Formato clave-valor válido
- ⚠️ Campos obligatorios se validan en fase siguiente (pre-negocio)

### Detalle
- ✅ Debe existir la hoja `DETALLE_ARTICULO`
- ✅ Deben existir columnas: `CodigoProducto`, `IdTienda`, `Cantidad`
- ✅ Case-insensitive para nombres de columnas
- ✅ Trim automático de valores
- ✅ Cantidad debe ser entero válido (> 0)
- ✅ Duplicados (CodigoProducto + IdTienda) = ERROR

---

## 🔍 Ejemplo de Respuesta del Parsing

```json
{
  "cabecera": {
    "Número de pedido": "P-12.48",
    "Fecha de pedido": "21/01/2025",
    "Fecha de entrega": "INMEDIATO",
    "Forma de pago": "Contado",
    "Código de proveedor": "PROV001",
    "Nombre de proveedor": "Proveedor XYZ"
  },
  "resumen": {
    "filasLeidas": 3,
    "filasValidas": 3,
    "filasInvalidas": 0
  },
  "errores": [],
  "data": [
    {
      "codigoProducto": "R225.1012.BCO",
      "idTienda": "T001",
      "cantidad": 10,
      "filaOrigen": 2
    },
    {
      "codigoProducto": "R225.1012.BCO",
      "idTienda": "T002",
      "cantidad": 5,
      "filaOrigen": 3
    },
    {
      "codigoProducto": "A889.3321.NEG",
      "idTienda": "T001",
      "cantidad": 2,
      "filaOrigen": 4
    }
  ]
}
```

---

## 🗄️ Estructura de Base de Datos Resultante

Después del parsing y guardado, la BD queda así:

### `pedido` (1 registro)
```
pedido_id: abc-123...
numero_pedido: P-12.48
fecha_pedido: 2025-01-21
fecha_entrega: INMEDIATO
proveedor_nombre: Proveedor XYZ
archivo_nombre: Template_Pedido_Inicial_v1.0.xlsx
```

### `pedido_detalle` (2 registros - productos únicos)
```
pedido_detalle_id: def-456...
pedido_id: abc-123...
codigo_interno: R225.1012.BCO
marca: ...
```

```
pedido_detalle_id: ghi-789...
pedido_id: abc-123...
codigo_interno: A889.3321.NEG
marca: ...
```

### `pedido_detalle_tienda` (3 registros - distribuciones)
```
id: jkl-012...
pedido_detalle_id: def-456...
tienda_id: (T001)
cantidad: 10
fila_origen: 2
```

```
id: mno-345...
pedido_detalle_id: def-456...
tienda_id: (T002)
cantidad: 5
fila_origen: 3
```

```
id: pqr-678...
pedido_detalle_id: ghi-789...
tienda_id: (T001)
cantidad: 2
fila_origen: 4
```

---

## 📝 Ejemplo Completo de Mapeo

### Excel Input (CABECERA_PEDIDO)

| Campo | Valor |
|-------|-------|
| CODIGO PEDIDO | P-12.48 |
| FECHA PEDIDO | 21/01/2025 |
| FECHA ENTREGA | INMEDIATO |
| FORMA PAGO | Contado |
| ODC | ODC-001 |
| NOMBRE PROVEEDOR | Proveedor XYZ |
| COMPRADOR NOMBRE | Juan Pérez |
| COD COMPRADOR | COMP001 |
| ORIGEN TRASLADO | Almacén Central |
| SERIE | A |

### Resultado en Base de Datos

**Registro en `pedido`:**
```sql
pedido_id: 'abc-123-def-456...'
numero_pedido: 'P-12.48'
fecha_pedido: '2025-01-21'  -- Convertido a DATE
fecha_entrega: 'INMEDIATO'
forma_pago: 'Contado'
odc: 'ODC-001'
proveedor_nombre: 'Proveedor XYZ'
comprador_nombre: 'Juan Pérez'
comprador_codigo: 'COMP001'
origen_traslado: 'Almacén Central'
serie: 'A'
archivo_nombre: 'Template_Pedido_Inicial_v1.0.xlsx'
creado_por: 'user123'
creado_en: '2025-01-21 12:00:00'
```

## ✅ Validaciones del Mapeo

### Campos Obligatorios
- `numero_pedido` (CODIGO PEDIDO) - **Obligatorio**
- Otros campos son opcionales según reglas de negocio

### Conversión de Fechas
- Formato aceptado: `DD/MM/YYYY` o `YYYY-MM-DD`
- Si falla la conversión, se guarda como NULL y se registra warning

### Case-Insensitive
- El mapeo funciona con variaciones de mayúsculas/minúsculas
- Se mantienen nombres originales además de normalizados para retrocompatibilidad

## 📝 Notas Importantes

1. **No se consolidan duplicados**: Si hay duplicados (mismo CodigoProducto + IdTienda), se marcan como ERROR en el parsing.

2. **Cabecera se guarda completa**: Todos los campos de la cabecera se guardan en `pedido`, aunque algunos puedan ser NULL.

3. **Fila origen se preserva**: El campo `fila_origen` en `pedido_detalle_tienda` permite rastrear exactamente de qué fila del Excel vino cada registro.

4. **Tiendas se crean automáticamente**: Si una tienda no existe, se crea automáticamente al procesar el pedido.

5. **Relación implícita**: La relación entre cabecera y detalle se construye durante el parsing (no hay clave externa en el Excel).

6. **Mapeo implementado**: Todos los campos de la cabecera se mapean correctamente con conversión automática de tipos.

