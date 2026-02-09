# Configuración del Botón "Descargar Excel"

## Resumen de Cambios

Se ha actualizado el endpoint de descarga para generar archivos Excel (.xlsx) en lugar de CSV, incluyendo toda la información del pedido en estado "Confirmado" (ESTADO_REDISTRIBUCION = 4).

## Endpoints Disponibles

### 1. `/api/pedidos/{pedido_id}/descargar-excel` (Nuevo)
- **Método:** GET
- **Formato:** Excel (.xlsx)
- **Estado requerido:** CONFIRMADO (estado_id = 4)

### 2. `/api/pedidos/{pedido_id}/descargar-csv` (Compatibilidad)
- **Método:** GET
- **Formato:** Excel (.xlsx) - ahora genera el mismo archivo que el endpoint anterior
- **Estado requerido:** CONFIRMADO (estado_id = 4)

> **Nota:** Ambos endpoints generan ahora archivos Excel. El endpoint `/descargar-csv` se mantiene por compatibilidad con el frontend existente.

## Estructura del Archivo Excel

El archivo Excel generado contiene **3 hojas**:

### Hoja 1: "Información del Pedido"
Información de cabecera del pedido:
- Número de Pedido
- Pedido ID
- Estado
- Fecha Pedido
- Fecha Entrega
- Proveedor
- Comprador
- Código Comprador
- ODC
- Forma de Pago
- Origen Traslado
- Serie
- Archivo
- Creado Por
- Fecha de Creación
- Descargado por
- Fecha de descarga

### Hoja 2: "Detalles de Artículos"
Tabla con los detalles de todos los artículos del pedido:

| Columna | Descripción | Origen |
|---------|-------------|--------|
| Código Interno | Código interno del artículo | `pedido_detalle.codigo_interno` |
| SKU SAP | SKU en SAP (si existe) | `pedido_sap_procesamiento_detalle.item_code_sap` |
| Descripción | Descripción del artículo | `pedido_detalle.descripcion_sap` |
| Cantidad Total | Cantidad total del artículo | `SUM(distribucion_confirmada.cantidad_asignada)` |
| Costo Unitario | Costo unitario sin IVA | `distribucion_confirmada.costo_unitario_ajustado` |
| Total | Subtotal (cantidad × costo) | `distribucion_confirmada.subtotal_ajustado` |
| Unidad | Unidad de medida SAP | `pedido_sap_procesamiento_detalle.unidad_sap` |
| Código de Barras | Código de barras | `pedido_detalle.codigo_barras` |
| Comentario | Comentario del artículo | `pedido_detalle.comentario` |

**Nota:** Incluye fila de TOTALES al final con suma de cantidades y valores.

### Hoja 3: "Distribución por Tiendas"
Tabla con la distribución de artículos por tienda:

| Columna | Descripción |
|---------|-------------|
| Código Interno | Código interno del artículo |
| Descripción | Descripción del artículo |
| Código Tienda | Código de la tienda |
| Nombre Tienda | Nombre de la tienda |
| Cantidad Asignada | Cantidad asignada a la tienda |
| Costo Unitario | Costo unitario ajustado |
| Subtotal | Subtotal para esa tienda |

## Origen de Datos

### Estado CONFIRMADO (estado_id = 4)

El sistema intenta obtener los datos en el siguiente orden:

#### 1. Intento Primario: `distribucion_confirmada`
Si existe una redistribución confirmada, se obtienen los datos de:

```sql
SELECT 
    dc.pedido_detalle_id,
    pd.codigo_interno,
    pd.descripcion_sap,
    pd.codigo_barras,
    pd.pack,
    SUM(dc.cantidad_asignada) AS total_asignada,
    MAX(dc.costo_unitario_ajustado) AS costo_unitario_ajustado,
    SUM(dc.subtotal_ajustado) AS subtotal_ajustado,
    ps.item_code_sap,
    ps.unidad_sap,
    pd.comentario
FROM distribucion_confirmada dc
INNER JOIN pedido_detalle pd ON dc.pedido_detalle_id = pd.pedido_detalle_id
LEFT JOIN pedido_sap_procesamiento_detalle ps ON pd.pedido_detalle_id = ps.pedido_detalle_id
WHERE dc.pedido_id = ? AND dc.version = ?
GROUP BY dc.pedido_detalle_id, pd.codigo_interno, pd.descripcion_sap, 
         pd.codigo_barras, pd.pack, ps.item_code_sap, ps.unidad_sap, pd.comentario
ORDER BY pd.codigo_interno
```

#### 2. Fallback: `pedido_detalle` + `pedido_detalle_tienda` (Directamente)
Si **NO** hay datos en `distribucion_confirmada`, el sistema automáticamente usa los datos originales:

```sql
SELECT 
    pd.pedido_detalle_id,
    pd.codigo_interno,
    pd.descripcion_sap,
    pd.codigo_barras,
    pd.pack,
    ISNULL(SUM(pdt.cantidad), 0) AS total_cantidad,
    pd.costo_doc_sin_iva AS costo_unitario,
    pd.total AS total_linea,
    ps.item_code_sap,
    ps.unidad_sap,
    pd.comentario
FROM pedido_detalle pd
LEFT JOIN pedido_detalle_tienda pdt ON pd.pedido_detalle_id = pdt.pedido_detalle_id
LEFT JOIN pedido_sap_procesamiento_detalle ps ON pd.pedido_detalle_id = ps.pedido_detalle_id
WHERE pd.pedido_id = ?
GROUP BY pd.pedido_detalle_id, pd.codigo_interno, pd.descripcion_sap, 
         pd.codigo_barras, pd.pack, pd.costo_doc_sin_iva, pd.total,
         ps.item_code_sap, ps.unidad_sap, pd.comentario
ORDER BY pd.codigo_interno
```

**Para las distribuciones por tienda (Hoja 3) en el fallback:**

```sql
SELECT 
    t.codigo AS tienda_codigo,
    t.nombre AS tienda_nombre,
    pdt.cantidad,
    pd.costo_doc_sin_iva AS costo_unitario,
    (pdt.cantidad * pd.costo_doc_sin_iva) AS subtotal
FROM pedido_detalle_tienda pdt
INNER JOIN tienda t ON pdt.tienda_id = t.tienda_id
INNER JOIN pedido_detalle pd ON pdt.pedido_detalle_id = pd.pedido_detalle_id
WHERE pdt.pedido_detalle_id = ?
ORDER BY t.codigo
```

**⚠️ Nota Importante:** Este fallback garantiza que SIEMPRE se puedan descargar los detalles del pedido, incluso si no se ha realizado una redistribución. Las cantidades se suman desde `pedido_detalle_tienda`.

## Formato y Estilos

El archivo Excel incluye:
- **Títulos**: Fondo azul claro, texto en negrita
- **Encabezados de tablas**: Fondo azul, texto blanco en negrita
- **Formato numérico**: Números con separador de miles y 2 decimales
- **Anchos de columna**: Ajustados automáticamente para mejor legibilidad
- **Bordes**: Aplicados a las celdas de encabezado

## Validaciones

### 1. Estado del Pedido
El pedido debe estar en estado **CONFIRMADO (estado_id = 4)** para poder descargarse.

**Respuesta si el estado no es válido:**
```json
{
  "error": "estado_no_permitido",
  "message": "El pedido debe estar en estado CONFIRMADO para descargar. Estado actual: {estado_nombre}"
}
```

### 2. Existencia del Pedido
El pedido debe existir en la base de datos.

**Respuesta si el pedido no existe:**
```json
{
  "error": "not_found",
  "message": "Pedido no encontrado"
}
```

## Flujo de Usuario

1. Usuario crea o selecciona un pedido
2. Usuario hace clic en **"Gestionar Pedido"** (cambia a estado GESTIONAR_PEDIDO)
3. Usuario revisa los detalles y hace clic en **"Confirmar"** (cambia a estado CONFIRMADO)
4. Aparece el botón **"Descargar Excel"**
5. Usuario hace clic en **"Descargar Excel"**
6. Se descarga un archivo Excel con toda la información del pedido

## Nombre del Archivo

Formato: `pedido_{numero_pedido}_{fecha_hora}.xlsx`

Ejemplo: `pedido_P-12_06_-_12_-_2025_20250205_143022.xlsx`

- `{numero_pedido}`: Número del pedido sanitizado (caracteres especiales reemplazados por `_`)
- `{fecha_hora}`: Fecha y hora de descarga en formato `YYYYMMDD_HHMMSS`

## Permisos Requeridos

El usuario debe tener uno de los siguientes permisos:
- `odcsap.view` (Usuario EL RAYO)
- `mabel.view` (Usuario MABEL TRADING)

## Tecnología Utilizada

- **Backend:** FastAPI (Python)
- **Librería Excel:** openpyxl
- **Base de datos:** SQL Server

## Ejemplo de Uso desde Frontend

```javascript
// Descargar Excel del pedido
async function descargarExcel(pedidoId) {
  const response = await fetch(
    `/api/pedidos/${pedidoId}/descargar-excel`,
    {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  if (response.ok) {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pedido_${pedidoId}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } else {
    const error = await response.json();
    console.error('Error al descargar:', error);
    alert(error.message);
  }
}
```

## Registro de Actividad

Cada descarga genera un log en el servidor:

```
✅ Excel generado para pedido {pedido_id} ({numero_pedido}) por usuario {username}
```

## Correspondencia con SQL Proporcionado

El archivo Excel incluye todos los campos solicitados en la consulta SQL:

### Cabecera (tabla `pedido`):
- ✅ `pedido_id`
- ✅ `numero_pedido`
- ✅ `fecha_pedido`
- ✅ `fecha_entrega`
- ✅ `forma_pago`
- ✅ `proveedor_nombre`
- ✅ `comprador_nombre`
- ✅ `estado` (como `estado_nombre`)

### Detalle (tabla `pedido_detalle`):
- ✅ `pedido_detalle_id` (usado internamente para las queries)
- ✅ `codigo_interno`
- ✅ `descripcion_sap`
- ✅ `costo_doc_sin_iva` (mostrado como `costo_unitario_ajustado`)
- ✅ `total` (mostrado como `subtotal_ajustado`)
- ✅ `comentario`

## Soporte y Mantenimiento

Para cualquier modificación o mejora:
1. Editar archivo: `src/endpoints/pedidos/pedidos_crud.py`
2. Función: `descargar_pedido_excel()`
3. Líneas aproximadas: 1343-1730

---

## Historial de Cambios

### v1.2 - 2025-02-05 (Corrección Crítica)
- 🔧 **CORREGIDO:** Error "Invalid column name 'cantidad'" en tabla `pedido_detalle`
- ✅ Suma de cantidades ahora obtiene datos desde `pedido_detalle_tienda` (tabla correcta)
- ✅ Agregado JOIN con `pedido_detalle_tienda` para obtener cantidades totales
- ✅ Distribuciones por tienda ahora funcionan correctamente en fallback
- ✅ Calcula subtotales correctamente: `cantidad * costo_doc_sin_iva`

### v1.1 - 2025-02-05 (Actualización)
- ✅ Agregado **fallback automático** a `pedido_detalle` cuando no hay datos en `distribucion_confirmada`
- ✅ Garantiza que siempre se descarguen los detalles del pedido en estado CONFIRMADO
- ✅ Agregado manejo de excepciones para distribuciones por tienda
- ✅ Mejoras en logging para diagnóstico

### v1.0 - 2025-02-05 (Inicial)
- ✅ Implementación inicial del endpoint de descarga Excel
- ✅ Generación de archivo Excel con 3 hojas
- ✅ Validación de estado CONFIRMADO

---

**Fecha de implementación:** 2025-02-05  
**Última actualización:** 2025-02-05 (v1.2)  
**Implementado por:** Cursor AI Assistant  
**Estado:** Completado y Funcionando ✅

## Notas Técnicas Importantes

### Estructura de Datos
- **`pedido_detalle`**: Contiene información del artículo (código, descripción, costos, total) pero **NO tiene columna `cantidad`**
- **`pedido_detalle_tienda`**: Contiene las cantidades distribuidas por tienda para cada artículo
- **`distribucion_confirmada`**: Contiene las redistribuciones confirmadas (si existen)

### Obtención de Cantidades
- La cantidad total de un artículo se obtiene sumando: `SUM(pedido_detalle_tienda.cantidad)`
- Si existe redistribución: `SUM(distribucion_confirmada.cantidad_asignada)`
