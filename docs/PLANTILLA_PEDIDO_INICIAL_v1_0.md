# Plantilla Pedido Inicial v1.0 - Documentación Completa

**Versión:** 1.0  
**Última Actualización:** 6 de Enero de 2026  
**Formato:** XLSX (Microsoft Excel)  
**Hojas:** 4 (Cabecera Pedido, Detalle Articulos, Movimiento, Tiendas)

---

## 📋 Descripción General

El archivo **Template_Pedido_Inicial_v1.0.xlsx** es una **plantilla de carga masiva de datos** diseñada para gestionar un pedido comercial completo, incluyendo:

1. **Metadatos del Pedido** - Quién compra, quién vende, fechas y términos
2. **Catálogo de Productos** - SKUs, costos, precios y descripciones
3. **Distribución a Tiendas** - Asignación de cantidades por punto de venta
4. **Maestro de Tiendas** - Catálogo de sucursales válidas

Este archivo se utiliza para importación masiva de órdenes de compra y distribuciones en un sistema ERP/Retail.

---

## 📊 Estructura de Hojas

### 1. Hoja: **Cabecera Pedido**

**Propósito:** Metadatos de alto nivel que definen la transacción comercial (la "carátula" de la orden).

**Formato:** Clave-Valor en formato vertical  
**Estructura:**

| Campo | Valor | Ejemplo |
|-------|-------|---------|
| CODIGO PEDIDO | P-12.48 - 12 - 2025 | Identificador único del pedido |
| FECHA DE PEDIDO | 2025-12-22 | Fecha de emisión (formato YYYY-MM-DD) |
| FECHA DE ENTREGA | INMEDIATO | Plazo de entrega o instrucción logística |
| FORMA DE PAGO | 120 DIAS | Condición de crédito con proveedor |
| ODC | (vacío) | Orden de Compra interna (opcional) |
| NOMBRE PROVEEDOR | TEXTILES EL RAYO S.A. | Entidad que suministra la mercancía |
| COMPRADOR NOMBRE | VACA ANDREA | Persona responsable de la gestión |
| COD COMPRADOR | 801 | ID interno del comprador |
| ORIGEN TRASLADO | RL-CD | Bodega/Centro de Distribución origen |
| SERIE | 10131 | Número de serie del documento |

**Notas:**
- Los campos pueden estar en **formato vertical** (Campo | Valor) o **horizontal** (campos en fila 1, valores en fila 2)
- El sistema detecta automáticamente el formato
- `CODIGO PEDIDO` es obligatorio
- Las fechas deben estar en formato YYYY-MM-DD

---

### 2. Hoja: **Detalle Articulos**

**Propósito:** Catálogo maestro de productos con costos y precios.

**Formato:** Tabular con encabezados en primera fila  
**Estructura:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| CODIGO PRODUCTO | Texto | SKU único (ej: `MTF123.9`, `R5000.1012-2`) |
| MARCA | Texto | Fabricante del producto (ej: `ROLAND`) |
| DESCRIPCION SAP | Texto | Nombre técnico en el ERP (ej: `VALETAS C. TALONERA LISA`) |
| CODIGO BARRAS | Texto | EAN/UPC para escaneo (ej: `7861224113401`) |
| PACK | Texto | Unidad de empaque (ej: `X1`, `X6`, `X12`) |
| COSTO SIN IVA | Decimal | Costo de adquisición por unidad (ej: `5.65`) |
| DESCUENTO | Decimal | Porcentaje de descuento (ej: `0.2` para 20%) |
| PVP | Decimal | Precio de Venta al Público (ej: `9.99`) |
| BODEGA | Entero | Cantidad disponible en bodega central |

**Ejemplo de Datos:**

```
CODIGO PRODUCTO | MARCA  | DESCRIPCION SAP              | CODIGO BARRAS | PACK | COSTO SIN IVA | DESCUENTO | PVP   | BODEGA
MTF123.9        | ROLAND | VALETAS C. TALONERA LISA     | 7861224113401 | X1   | 5.65          | 0.2       | 9.99  | 150
R5000.1012-2    | ROLAND | MEDIA TOBILLERA              | 7861224113402 | X1   | 6.75          | 0.2       | 10.99 | 200
```

**Notas:**
- Cada fila representa un SKU único
- Los costos y precios deben ser decimales (usar `.` como separador)
- La columna `BODEGA` es informativa (no se utiliza en distribución)
- El sistema valida que `CODIGO PRODUCTO` no esté vacío

---

### 3. Hoja: **Movimiento**

**Propósito:** Distribución de cantidades por tienda (la más importante para operaciones).

**Formato:** Tabular con encabezados en primera fila  
**Estructura:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| CODIGO PRODUCTO | Texto | SKU a distribuir (debe existir en Detalle Articulos) |
| TIENDAS | Texto | Código o nombre de la tienda (debe existir en hoja Tiendas) |
| CANTIDAD | Entero | Número de unidades a enviar (> 0) |

**Ejemplo de Datos:**

```
CODIGO PRODUCTO | TIENDAS                      | CANTIDAD
MTF123.9        | TRL-QSN                      | 10
MTF123.9        | TRL-SMA                      | 5
MTF123.9        | ROLAND MALL DEL SOL          | 8
R5000.1012-2    | TRL-REGIONAL-QUITO           | 3
R5000.1012-2    | TOUT-BOMB                    | 2
```

**Características:**

- **Múltiples Filas por Producto:** Un producto puede distribuirse a varias tiendas
- **Flexibilidad en Códigos:** Soporta códigos cortos (`TRL-QSN`) o nombres completos (`ROLAND MALL DEL SOL`)
- **Validación Automática:**
  - CODIGO PRODUCTO debe existir en Detalle Articulos
  - TIENDAS debe existir en hoja Tiendas y estar ACTIVA
  - CANTIDAD debe ser entero positivo
- **Fila Origen:** El sistema registra la fila exacta para auditoría y debugging

**Orden de Procesamiento:**
1. El sistema lee todas las distribuciones
2. Las consolida por producto
3. Valida cada tienda contra el catálogo
4. Genera un aviso si hay tiendas inactivas (si está configurado)

---

### 4. Hoja: **Tiendas**

**Propósito:** Maestro de datos de ubicaciones (validación y referencia).

**Formato:** Tabular con encabezados en primera fila  
**Estructura:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| ID TIENDA | Texto | Código único corto (ej: `TRL-QSN`, `TOUT-BOMB`, `RG-INT`) |
| NOMBRE_TIENDA | Texto | Descripción completa (ej: `ROLAND QUICENTRO NORTE`) |
| ACTIVO | Texto | Estado (`SI` o `NO`) |
| ID_TIENDA_ACTIVA | Texto | Validación/confirmación (puede repetir ID) |

**Ejemplo de Datos:**

```
ID TIENDA       | NOMBRE_TIENDA                    | ACTIVO | ID_TIENDA_ACTIVA
TRL-QSN         | ROLAND QUICENTRO NORTE           | SI     | TRL-QSN
TRL-SMA         | ROLAND SAN MARINO                | SI     | TRL-SMA
TOUT-BOMB       | DESCUENTON BOMBOLÍ               | SI     | TOUT-BOMB
RG-INT          | ROLAND REGIONS QUITO (INT)       | SI     | RG-INT
RL-CD           | BODEGA ROLAND CD                 | SI     | RL-CD
OUT-CD          | BODEGA OUTLET                    | SI     | OUT-CD
```

**Segmentación Observada:**

1. **Tiendas ROLAND (TRL-):**
   - Tiendas principales de la marca
   - Ubicaciones premium (Malls, centros comerciales)
   - Ejemplos: Quicentro, San Marino, CC El Bosque

2. **Tiendas DESCUENTON (TOUT-):**
   - Outlets o tiendas de descuento
   - Ejemplos: Bombolí, Mapasingue

3. **Tiendas REGIONS (RG-):**
   - Puntos de venta en aeropuertos
   - Ejemplos: Regional Quito (INT y NAC), Regional Guayaquil

4. **Bodegas (.*-CD):**
   - Centros de distribución
   - Ejemplos: RL-CD (ROLAND CD), OUT-CD, RG-CD

**Notas:**
- El sistema valida que tiendas referenciadas en Movimiento existan aquí
- Solo tiendas con `ACTIVO = SI` son aceptadas (con warnings para inactivas)
- El código en `ID TIENDA` debe ser único
- El nombre en `NOMBRE_TIENDA` facilita identificación pero el código es lo importante

---

## 🔄 Flujo de Procesamiento

```
Excel Input (4 hojas)
    ↓
┌─────────────────────────────────────────┐
│ 1. LEER HOJA TIENDAS                   │
│    • Cargar maestro de tiendas         │
│    • Validar estado (ACTIVO/INACTIVO)  │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 2. LEER HOJA CABECERA PEDIDO           │
│    • Extraer metadatos                 │
│    • Normalizar campos                 │
│    • Generar Pedido ID                 │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 3. LEER HOJA DETALLE ARTICULOS         │
│    • Cargar catálogo de SKUs           │
│    • Obtener costos y precios          │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 4. LEER HOJA MOVIMIENTO                │
│    • Procesar distribuciones           │
│    • Validar productos (vs Detalle)    │
│    • Validar tiendas (vs Tiendas)      │
│    • Validar cantidades                │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 5. CONSOLIDAR POR PRODUCTO             │
│    • Agrupar distribuciones            │
│    • Consolidar cantidades por tienda  │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 6. VALIDACIÓN PRE-NEGOCIO              │
│    • Validar integridad de datos       │
│    • Validar reglas de negocio         │
│    • Generar reportes de errores       │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 7. PERSISTENCIA EN BD                  │
│    • Crear cabecera pedido             │
│    • Crear detalles (artículos)        │
│    • Crear distribuciones por tienda   │
│    • Registrar trazabilidad            │
└─────────────────────────────────────────┘
    ↓
Output: Pedido cargado exitosamente
        • Pedido ID generado
        • Artículos cargados: N
        • Distribuciones cargadas: M
        • Warnings/Errores (si aplica)
```

---

## 🔧 Detección Automática de Formato

El sistema detecta automáticamente si el Excel es formato **v1.0** (4 hojas) o **anterior** (2 hojas):

### Formato v1.0 (4 hojas):
```
✅ Cabecera Pedido    (obligatoria)
✅ Detalle Articulos  (obligatoria)
✅ Movimiento         (obligatoria)
✅ Tiendas            (obligatoria)
```

**Acción:** Usa el nuevo flujo `_procesar_formato_v1_0()`

### Formato Anterior (2 hojas):
```
✅ CABECERA_PEDIDO     (obligatoria)
✅ DETALLE_ARTICULO    (obligatoria)
❌ Movimiento          (no existe)
❌ Tiendas             (no existe)
```

**Acción:** Usa el flujo antiguo `validar_y_procesar_archivo_excel()`

---

## ✅ Validaciones Implementadas

### Validaciones de Estructura:

| Validación | Nivel | Descripción |
|-----------|-------|-------------|
| Hojas obligatorias | ERROR | Todas las 4 hojas deben existir |
| CODIGO PEDIDO obligatorio | ERROR | Cabecera debe tener número de pedido |
| CODIGO PRODUCTO no vacío | ERROR | Cada fila de Movimiento debe tener SKU |
| TIENDA no vacía | ERROR | Cada fila de Movimiento debe tener tienda |
| CANTIDAD válida | ERROR | Debe ser entero > 0 |

### Validaciones de Referencia:

| Validación | Nivel | Descripción |
|-----------|-------|-------------|
| Producto existe | ERROR | CODIGO PRODUCTO debe estar en Detalle Articulos |
| Tienda existe | ERROR | TIENDA debe estar en hoja Tiendas |
| Tienda activa | WARNING | Si tienda está INACTIVO |

### Validaciones de Negocio:

| Validación | Nivel | Descripción |
|-----------|-------|-------------|
| Cantidad > 0 | ERROR | No se permite cantidad 0 o negativa |
| Duplicados por tienda | ERROR | Un producto no puede distribuirse 2x a misma tienda |

---

## 📤 Ejemplo de Respuesta del Sistema

### Caso: Éxito Completo

```json
{
  "status": "success",
  "formato_detectado": "cuatro_hojas_v1_0",
  "pedido_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "articulos_cargados": 3,
  "distribuciones_cargadas": 12,
  "validation": {
    "valid": true,
    "errors": [],
    "warnings": []
  },
  "resumen": {
    "hojas_procesadas": ["Tiendas", "Cabecera Pedido", "Detalle Articulos", "Movimiento"],
    "tiendas_validadas": 15,
    "productos_cargados": 3,
    "distribuciones_totales": 12
  },
  "errores": [],
  "warnings": []
}
```

### Caso: Error en Validación

```json
{
  "status": "validation_error",
  "formato_detectado": "cuatro_hojas_v1_0",
  "pedido_id": null,
  "validation": {
    "valid": false,
    "errors": [
      "Fila 5: Tienda 'TRL-XYZ' no existe en catálogo",
      "Fila 8: CODIGO PRODUCTO 'SKU999' no encontrado en Detalle Articulos"
    ],
    "warnings": [
      "Fila 12: Tienda 'TOUT-INACTIVA' está INACTIVA"
    ]
  },
  "errores": [],
  "warnings": []
}
```

---

## 🎯 Casos de Uso

### Caso 1: Importación Inicial Completa

```
1. Crear Excel con 4 hojas
2. Llenar todos los metadatos en Cabecera Pedido
3. Listar todos los SKUs en Detalle Articulos
4. Definir distribución por tienda en Movimiento
5. Validar lista de tiendas en Tiendas
6. Subir archivo
7. Sistema genera pedido con todas las distribuciones
```

**Resultado:** Un pedido completo con distribución a múltiples tiendas.

### Caso 2: Actualización de Distribución Existente

```
1. Tomar Excel anterior
2. Modificar cantidades en hoja Movimiento
3. Agregar nuevas tiendas si es necesario en Tiendas
4. Subir archivo como nuevo pedido
```

**Resultado:** Nuevo pedido con distribución diferente.

### Caso 3: Reabastecimiento a Tienda Específica

```
1. Crear Excel con Cabecera Pedido única
2. Incluir 5 SKUs en Detalle Articulos
3. En Movimiento: solo las 5 SKUs para 1 tienda específica
4. Copiar catálogo de tiendas de plantilla anterior
5. Subir archivo
```

**Resultado:** Pedido pequeño (reabastecimiento) hacia una tienda.

---

## 📝 Notas Importantes

### Sobre Formato de Fechas:
- Usar formato YYYY-MM-DD (ej: `2025-12-22`)
- El sistema intenta detectar otros formatos pero YYYY-MM-DD es preferido

### Sobre Números Decimales:
- Usar `.` (punto) como separador decimal, NO `,` (coma)
- Para cantidades: solo enteros (sin decimales)

### Sobre Códigos:
- Los códigos de tienda pueden tener guiones (`TRL-QSN`) - se mantienen
- Los códigos de producto pueden tener puntos (`MTF123.9`) - se mantienen
- Todos se normalizan a MAYÚSCULAS para comparación

### Sobre Errores:
- El sistema detiene el procesamiento en errores CRÍTICOS
- Los WARNINGS se registran pero el pedido se procesa de todas formas
- Revisar sección "Validaciones" para entender qué es error vs warning

---

## 🔍 Debugging y Troubleshooting

### Problema: "Tienda no encontrada"

**Causa:** La tienda en Movimiento no existe en hoja Tiendas o está inactiva.

**Solución:**
1. Verificar el código exacto en Movimiento
2. Verificar que esté en hoja Tiendas
3. Verificar que ACTIVO = SI en hoja Tiendas

### Problema: "Producto no encontrado"

**Causa:** CODIGO PRODUCTO en Movimiento no existe en Detalle Articulos.

**Solución:**
1. Verificar el SKU exacto en Movimiento
2. Verificar que esté en Detalle Articulos
3. Verificar espacios en blanco (trim)

### Problema: "Hoja no encontrada"

**Causa:** El Excel no tiene las 4 hojas requeridas.

**Solución:**
1. Verificar que existan exactamente estas hojas:
   - `Cabecera Pedido` (o similar)
   - `Detalle Articulos` (o similar)
   - `Movimiento`
   - `Tiendas`
2. Verificar que los nombres sean exactos

---

## 📞 Contacto y Soporte

Para preguntas sobre el formato o problemas de procesamiento:

1. Revisar logs del sistema
2. Verificar que el Excel cumpla con estructura
3. Contactar al equipo de desarrollo con:
   - Archivo Excel problemático
   - Logs de error
   - Descripción del problema

---

**Documento generado automáticamente**  
**Última revisión:** 6 de Enero de 2026
