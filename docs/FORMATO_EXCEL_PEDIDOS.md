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

### Del Excel a las Tablas

**CABECERA_PEDIDO → `pedido`**
```
Número de pedido → numero_pedido
Fecha de pedido → fecha_pedido
Fecha de entrega → fecha_entrega
Forma de pago → forma_pago
Código de proveedor → proveedor_codigo (si existe)
Nombre de proveedor → proveedor_nombre
...
```

**DETALLE_ARTICULO → `pedido_detalle` + `pedido_detalle_tienda`**
```
Código/SKU → pedido_detalle.codigo_interno
Marca → pedido_detalle.marca
Código de barras → pedido_detalle.codigo_barras
Descripción SAP → pedido_detalle.descripcion_sap
Pack → pedido_detalle.pack
Cantidad → pedido_detalle_tienda.cantidad
IdTienda → pedido_detalle_tienda.tienda_id (vía tabla tienda)
Fila del Excel → pedido_detalle_tienda.fila_origen
```

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

## 📝 Notas Importantes

1. **No se consolidan duplicados**: Si hay duplicados (mismo CodigoProducto + IdTienda), se marcan como ERROR en el parsing.

2. **Cabecera se guarda completa**: Todos los campos de la cabecera se guardan en `pedido`, aunque algunos puedan ser NULL.

3. **Fila origen se preserva**: El campo `fila_origen` en `pedido_detalle_tienda` permite rastrear exactamente de qué fila del Excel vino cada registro.

4. **Tiendas se crean automáticamente**: Si una tienda no existe, se crea automáticamente al procesar el pedido.

5. **Relación implícita**: La relación entre cabecera y detalle se construye durante el parsing (no hay clave externa en el Excel).

