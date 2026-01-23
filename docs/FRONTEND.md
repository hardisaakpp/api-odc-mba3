# Documentación Frontend

Guías de implementación y requerimientos para el sistema frontend.

---

## 1. Guía de Implementación - Requerimientos

**Fecha:** 29 de Enero de 2026  
**Versión:** 1.0  
**Estado:** ✅ Backend Implementado - Listo para Frontend

### 🎯 Resumen de Funcionalidades

Se han implementado **2 funcionalidades de alta prioridad**:

1. ✅ **Solicitudes de Transferencia (HU-04)** - Generación automática de Solicitudes de Traslado en SAP
2. ✅ **Listado de Pedidos con Filtros (HU-02, HU-07)** - Pantalla de visualización y seguimiento

### 1.1 Solicitudes de Transferencia (HU-04)

**Descripción:** Cuando se genera una Orden de Compra en SAP, el sistema automáticamente crea Solicitudes de Transferencia para cada tienda.

**Endpoint:** `POST /integrar-sap`

**Comportamiento:**
1. Obtiene distribución confirmada del pedido (por tienda)
2. Crea Inventory Transfer Request por cada tienda en SAP
3. Retorna información detallada de cada transferencia

**Respuesta:**
```json
{
  "status": "success",
  "oc_id": "uuid-de-oc",
  "doc_entry": 123,
  "solicitudes_transferencia": {
    "success": true,
    "total_tiendas": 3,
    "transferencias_creadas": 3,
    "resultados": [...]
  }
}
```

---

## 2. Interfaz "Productos Procesados"

### Endpoint

**GET** `/api/pedidos/{pedido_id}/procesamiento-sap`

- **Parámetro:** `pedido_id` puede ser UUID o `numero_pedido`
- **Autenticación:** JWT token requerido
- **Permiso:** `mba3-consultas.facturas.view`

### Estructura de Respuesta

```typescript
interface ProcesamientoSAPResponse {
  status: string;
  pedido_id: string;
  numero_pedido: string | null;
  productos: ProductoSAPProcesamientoItem[];
  estadisticas: EstadisticasProcesamientoSAP;
  fecha_procesamiento: string | null;
}

interface ProductoSAPProcesamientoItem {
  procesamiento_detalle_id: string;
  codigo_interno: string;
  descripcion_producto: string | null;  // ⭐ NUEVO CAMPO
  item_code_sap: string | null;
  pack_sap: string | null;
  unidad_conversion: number | null;
  cantidad_original: number | null;
  cantidad_sap: number | null;
  precio_unitario_original: number | null;
  precio_unitario_sap: number | null;
  total_linea_original: number | null;
  total_linea_sap: number | null;
  producto_homologado: boolean;
}
```

### Campo Nuevo: `descripcion_producto`

El campo `descripcion_producto` ahora está disponible en la respuesta y puede ser:
- ✅ `string` - Descripción del producto
- ❌ `null` - Si no se encontró en SAP

---

## ✅ Estado

Todas las funcionalidades están implementadas en backend y listas para integración con frontend.
