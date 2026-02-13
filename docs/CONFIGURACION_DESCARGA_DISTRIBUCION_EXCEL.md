# Configuración del Botón "Descargar Distribución Excel"

## Resumen

Se ha implementado un nuevo endpoint para descargar la distribución confirmada del pedido en formato Excel (.xlsx). Este botón se encuentra en la pantalla de redistribución y permite descargar toda la información de cómo se distribuyeron los productos entre las tiendas.

## Endpoint

### `/api/pedidos/{pedido_id}/distribucion/descargar-excel`

- **Método:** GET
- **Formato:** Excel (.xlsx)
- **Estado requerido:** Debe existir una distribución confirmada
- **Autenticación:** JWT Token requerido
- **Permisos:** `odcsap.view` o `mabel.view`

## Query Parameters

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `version` | int | No | Versión específica de la redistribución. Si no se especifica, descarga la última versión. |

## Estructura del Archivo Excel

El archivo Excel generado contiene **3 hojas**:

### Hoja 1: "Información del Pedido"

Información de cabecera del pedido y la redistribución:

| Campo | Descripción | Origen |
|-------|-------------|--------|
| Número de Pedido | Número del pedido | `pedido.numero_pedido` |
| Pedido ID | UUID del pedido | `pedido.pedido_id` |
| Versión Redistribución | Versión de la redistribución | `distribucion_confirmada.version` |
| Estado | Estado actual del pedido | `pedido.estado_nombre` |
| Fecha Pedido | Fecha de creación del pedido | `pedido.fecha_pedido` |
| Fecha Entrega | Fecha de entrega estimada | `pedido.fecha_entrega` |
| Proveedor | Nombre del proveedor | `pedido.proveedor_nombre` |
| Comprador | Nombre del comprador | `pedido.comprador_nombre` |
| Forma de Pago | Forma de pago acordada | `pedido.forma_pago` |
| ODC | Orden de compra | `pedido.odc` |
| Creado Por | Usuario que creó el pedido | `pedido.creado_por` |
| Descargado por | Usuario que descargó el Excel | `user.username` |
| Fecha de descarga | Fecha y hora de descarga | `datetime.now()` |

### Hoja 2: "Resumen de Productos"

Tabla resumen con las cantidades por producto:

| Columna | Descripción | Cálculo |
|---------|-------------|---------|
| Código Interno | Código interno del artículo | `pedido_detalle.codigo_interno` |
| Descripción | Descripción del artículo | `pedido_detalle.descripcion_sap` |
| Cantidad Solicitada | Cantidad originalmente solicitada | `SUM(cantidad_solicitada_total)` |
| Cantidad Confirmada | Cantidad confirmada por el proveedor | `SUM(cantidad_confirmada_total)` |
| Cantidad Asignada | Cantidad redistribuida a tiendas | `SUM(distribucion_confirmada.cantidad_asignada)` |
| Diferencia | Diferencia entre confirmado y asignado | `Confirmada - Asignada` |

**Incluye fila de TOTALES** con la suma de todas las cantidades.

#### Interpretación de la Diferencia:
- **Diferencia = 0**: Toda la cantidad confirmada fue distribuida ✅
- **Diferencia > 0**: Hay cantidad confirmada sin asignar (sobra) ⚠️
- **Diferencia < 0**: Se asignó más de lo confirmado (error) ❌

### Hoja 3: "Distribución por Tienda"

Tabla detallada con la distribución de cada producto por tienda:

| Columna | Descripción |
|---------|-------------|
| Código Interno | Código interno del artículo |
| Descripción | Descripción del artículo |
| Código Tienda | Código de la tienda |
| Nombre Tienda | Nombre completo de la tienda |
| Cantidad Asignada | Cantidad asignada a esa tienda |
| Costo Unitario | Costo unitario ajustado |
| Observaciones | Observaciones específicas de la distribución |

**Nota:** Los costos están formateados con separador de miles y 2 decimales.

## Origen de Datos

Los datos se obtienen de las siguientes fuentes:

### 1. Información del Pedido
```sql
SELECT 
    pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
    forma_pago, proveedor_nombre, comprador_nombre, estado_nombre,
    odc, creado_por
FROM pedido
WHERE pedido_id = ?
```

### 2. Distribución Confirmada
```sql
SELECT 
    dc.pedido_detalle_id,
    dc.tienda_id,
    t.codigo AS tienda_codigo,
    t.nombre AS tienda_nombre,
    dc.cantidad_asignada,
    dc.costo_unitario_ajustado,
    dc.subtotal_ajustado,
    dc.cantidad_solicitada,
    dc.cantidad_confirmada,
    dc.version
FROM distribucion_confirmada dc
INNER JOIN tienda t ON dc.tienda_id = t.tienda_id
WHERE dc.pedido_id = ? AND dc.version = ?
ORDER BY dc.pedido_detalle_id, t.codigo
```

### 3. Detalles del Producto
```sql
SELECT 
    pedido_detalle_id,
    codigo_interno,
    descripcion_sap
FROM pedido_detalle
WHERE pedido_id = ?
```

## Formato y Estilos

El archivo Excel incluye:
- **Títulos**: Fondo azul claro, texto en negrita, tamaño 14
- **Encabezados de tablas**: Fondo azul, texto blanco en negrita, tamaño 12
- **Formato numérico**: Números con separador de miles y 2 decimales (`#,##0.00`)
- **Anchos de columna**: Ajustados automáticamente para mejor legibilidad
- **Bordes**: Aplicados a las celdas de encabezado
- **Celdas combinadas**: En los títulos de cada hoja

## Validaciones

### 1. Existencia del Pedido
El pedido debe existir en la base de datos.

**Respuesta si el pedido no existe:**
```json
{
  "error": "not_found",
  "message": "Pedido no encontrado"
}
```

### 2. Existencia de Distribución Confirmada
El pedido debe tener al menos una versión de distribución confirmada.

**Respuesta si no hay distribución:**
```json
{
  "error": "not_found",
  "message": "No se encontró distribución confirmada para este pedido"
}
```

## Nombre del Archivo

Formato: `distribucion_{numero_pedido}_v{version}_{fecha_hora}.xlsx`

Ejemplos:
- `distribucion_P-12_06_-_12_-_2025_v1_20250205_153045.xlsx`
- `distribucion_P-12_48_-_12_-_2025_v2_20250205_160122.xlsx`

Donde:
- `{numero_pedido}`: Número del pedido sanitizado (caracteres especiales reemplazados por `_`)
- `{version}`: Versión de la redistribución (v1, v2, v3, etc.)
- `{fecha_hora}`: Fecha y hora de descarga en formato `YYYYMMDD_HHMMSS`

## Flujo de Usuario

1. Usuario accede a la pantalla de redistribución:
   ```
   /pedidos/{numero_pedido}/redistribucion?soloLectura=1
   ```

2. Usuario hace clic en **"Descargar Distribución Excel"**

3. El sistema:
   - Verifica que exista distribución confirmada
   - Obtiene la última versión (o la especificada)
   - Genera el archivo Excel con 3 hojas
   - Descarga el archivo

4. Usuario abre el Excel y puede ver:
   - ✅ Información completa del pedido
   - ✅ Resumen de cantidades por producto
   - ✅ Distribución detallada por tienda con costos

## Permisos Requeridos

El usuario debe tener uno de los siguientes permisos:
- `odcsap.view` (Usuario EL RAYO)
- `mabel.view` (Usuario MABEL TRADING)

## Ejemplo de Uso desde Frontend

```javascript
// Descargar Excel de distribución
async function descargarDistribucionExcel(pedidoId, version = null) {
  const url = version 
    ? `/api/pedidos/${pedidoId}/distribucion/descargar-excel?version=${version}`
    : `/api/pedidos/${pedidoId}/distribucion/descargar-excel`;
  
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  if (response.ok) {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `distribucion_${pedidoId}.xlsx`;
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

### Ejemplo con React/TypeScript

```typescript
import { useState } from 'react';

interface DescargarDistribucionProps {
  pedidoId: string;
  version?: number;
}

const DescargarDistribucionButton: React.FC<DescargarDistribucionProps> = ({ 
  pedidoId, 
  version 
}) => {
  const [loading, setLoading] = useState(false);

  const handleDescargar = async () => {
    setLoading(true);
    try {
      const url = version
        ? `/api/pedidos/${pedidoId}/distribucion/descargar-excel?version=${version}`
        : `/api/pedidos/${pedidoId}/distribucion/descargar-excel`;

      const token = localStorage.getItem('token');
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Error al descargar');
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `distribucion_${pedidoId}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      console.error('Error al descargar:', error);
      alert('No se pudo descargar el archivo');
    } finally {
      setLoading(false);
    }
  };

  return (
    <button 
      onClick={handleDescargar} 
      disabled={loading}
      className="btn btn-primary"
    >
      {loading ? 'Descargando...' : 'Descargar Distribución Excel'}
    </button>
  );
};

export default DescargarDistribucionButton;
```

## Registro de Actividad

Cada descarga genera un log en el servidor:

```
✅ Excel de distribución generado para pedido {pedido_id} ({numero_pedido}) por usuario {username}
```

## Casos de Uso

### Caso 1: Descargar última versión
```http
GET /api/pedidos/B98C0193-4A40-47DD-8ADE-ECAA2270966F/distribucion/descargar-excel
Authorization: Bearer {token}
```

### Caso 2: Descargar versión específica
```http
GET /api/pedidos/B98C0193-4A40-47DD-8ADE-ECAA2270966F/distribucion/descargar-excel?version=2
Authorization: Bearer {token}
```

## Diferencias con "Descargar Excel" del Pedido

| Característica | Descargar Excel (Pedido) | Descargar Distribución Excel |
|----------------|--------------------------|------------------------------|
| Endpoint | `/api/pedidos/{id}/descargar-csv` | `/api/pedidos/{id}/distribucion/descargar-excel` |
| Estado requerido | CONFIRMADO (4) | Distribución confirmada existente |
| Hoja 1 | Información del Pedido | Información del Pedido + Versión |
| Hoja 2 | Detalles de Artículos | **Resumen de Productos** (cantidades comparativas) |
| Hoja 3 | Distribución por Tiendas | **Distribución Detallada** (con costos ajustados) |
| Información adicional | Totales generales | Diferencias entre confirmado y asignado |
| Uso | Ver detalles del pedido original | Ver redistribución confirmada |

## Soporte y Mantenimiento

Para cualquier modificación o mejora:
1. Editar archivo: `src/endpoints/pedidos/pedidos_redistribucion.py`
2. Función: `descargar_distribucion_excel()`
3. Líneas aproximadas: 1697-2024

## Troubleshooting

### Problema: "No se encontró distribución confirmada"
**Causa:** El pedido no tiene ninguna redistribución confirmada.

**Solución:** 
1. Verificar que el pedido esté en estado correcto
2. Confirmar que se haya completado la redistribución
3. Revisar logs del servidor para errores de guardado

### Problema: "Error al generar Excel"
**Causa:** Datos corruptos o faltantes en la base de datos.

**Solución:**
1. Revisar logs del servidor: `❌ Error al generar Excel de distribución`
2. Verificar integridad de datos en `distribucion_confirmada`
3. Verificar que todas las tiendas referenciadas existan

---

## Historial de Cambios

### v1.1 - 2025-02-05
- 🔧 **Removida columna "Subtotal"** de la hoja "Distribución por Tienda"
- ✅ Ahora la hoja tiene 7 columnas en lugar de 8
- ✅ Simplificación de la información mostrada

### v1.0 - 2025-02-05
- ✅ Implementación inicial del endpoint
- ✅ Generación de archivo Excel con 3 hojas
- ✅ Información completa de distribución confirmada

---

**Fecha de implementación:** 2025-02-05  
**Última actualización:** 2025-02-05 (v1.1)  
**Implementado por:** Cursor AI Assistant  
**Ubicación:** `/api/pedidos/{pedido_id}/distribucion/descargar-excel`  
**Estado:** Completado y Actualizado ✅
**Última revisión:** 2026-02-13 (sin cambios funcionales)
