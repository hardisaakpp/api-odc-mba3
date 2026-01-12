# Guía Frontend: Interfaz "Productos Procesados"

## 📋 Resumen

Este documento describe cómo configurar la interfaz "Productos Procesados" en el frontend para mostrar correctamente el campo `descripcion_producto` que ahora está disponible en la respuesta del API.

## 🔌 Endpoint

**GET** `/api/pedidos/{pedido_id}/procesamiento-sap`

- **Parámetro:** `pedido_id` puede ser un UUID o un `numero_pedido` (ej: "P-12.55 - 12 - 2025")
- **Autenticación:** Requiere JWT token
- **Permiso:** `mba3-consultas.facturas.view`

## 📦 Estructura de Respuesta

El endpoint devuelve un objeto `ProcesamientoSAPResponse` con la siguiente estructura:

```typescript
interface ProcesamientoSAPResponse {
  status: string;
  pedido_id: string;
  numero_pedido: string | null;
  productos: ProductoSAPProcesamientoItem[];
  estadisticas: EstadisticasProcesamientoSAP;
  fecha_procesamiento: string | null;
}
```

### ProductoSAPProcesamientoItem

Cada producto en el array `productos` tiene la siguiente estructura:

```typescript
interface ProductoSAPProcesamientoItem {
  procesamiento_detalle_id: string;
  pedido_detalle_id: string;
  codigo_interno: string;
  descripcion_producto: string | null;  // ⭐ NUEVO CAMPO
  item_code_sap: string | null;
  pack_sap: string | null;
  unidad_conversion: number | null;
  unidad_sap: string | null;
  cantidad_original: number | null;
  cantidad_sap: number | null;
  precio_unitario_original: number | null;
  precio_unitario_sap: number | null;
  total_linea_original: number | null;
  total_linea_sap: number | null;
  producto_homologado: boolean;
  tipo_problema: string | null;
  item_code_sap_encontrado: string | null;
  mensaje_error: string | null;
  fecha_procesamiento: string | null;
  procesado_por: string | null;
}
```

## ✅ Cambios Requeridos en el Frontend

### 1. Actualizar la Interfaz TypeScript/Interface

Si estás usando TypeScript, actualiza la interfaz del modelo:

```typescript
// Antes
interface ProductoSAPProcesamientoItem {
  codigo_interno: string;
  // ... otros campos
}

// Después
interface ProductoSAPProcesamientoItem {
  codigo_interno: string;
  descripcion_producto: string | null;  // ⭐ AGREGAR ESTE CAMPO
  // ... otros campos
}
```

### 2. Agregar Columna en la Tabla

En el componente de la tabla "Productos Procesados", agrega una nueva columna para mostrar la descripción:

#### Ejemplo con Vue.js (Vuetify)

```vue
<template>
  <v-data-table
    :headers="headers"
    :items="productos"
    :loading="loading"
  >
    <!-- Columnas existentes -->
    <template v-slot:item.descripcion_producto="{ item }">
      <span>{{ item.descripcion_producto || 'N/A' }}</span>
    </template>
  </v-data-table>
</template>

<script setup lang="ts">
const headers = [
  { text: 'Código Interno', value: 'codigo_interno' },
  { text: 'Producto', value: 'descripcion_producto' },  // ⭐ NUEVA COLUMNA
  { text: 'Item Code SAP', value: 'item_code_sap' },
  { text: 'Pack SAP', value: 'pack_sap' },
  { text: 'Cantidad Original', value: 'cantidad_original' },
  { text: 'Cantidad SAP', value: 'cantidad_sap' },
  { text: 'Precio Unit. Original', value: 'precio_unitario_original' },  // ⭐ IMPORTANTE
  { text: 'Precio Unit. SAP', value: 'precio_unitario_sap' },
  { text: 'Total Original', value: 'total_linea_original' },
  { text: 'Total SAP', value: 'total_linea_sap' },
  { text: 'Homologado', value: 'producto_homologado' },
  // ... otras columnas
];
</script>
```

#### Ejemplo con React (Material-UI)

```tsx
import { DataGrid, GridColDef } from '@mui/x-data-grid';

const columns: GridColDef[] = [
  { field: 'codigo_interno', headerName: 'Código Interno', width: 150 },
  { field: 'descripcion_producto', headerName: 'Producto', width: 300 },  // ⭐ NUEVA COLUMNA
  { field: 'item_code_sap', headerName: 'Item Code SAP', width: 150 },
  { field: 'pack_sap', headerName: 'Pack SAP', width: 100 },
  { field: 'cantidad_original', headerName: 'Cantidad Original', width: 150 },
  { field: 'cantidad_sap', headerName: 'Cantidad SAP', width: 150 },
  { field: 'precio_unitario_original', headerName: 'Precio Unit. Original', width: 150, type: 'number' },  // ⭐ IMPORTANTE
  { field: 'precio_unitario_sap', headerName: 'Precio Unit. SAP', width: 150, type: 'number' },
  { field: 'total_linea_original', headerName: 'Total Original', width: 130, type: 'number' },
  { field: 'total_linea_sap', headerName: 'Total SAP', width: 130, type: 'number' },
  { field: 'producto_homologado', headerName: 'Homologado', width: 120 },
  // ... otras columnas
];

function ProductosProcesadosTable({ productos }: { productos: ProductoSAPProcesamientoItem[] }) {
  return (
    <DataGrid
      rows={productos}
      columns={columns}
      getRowId={(row) => row.procesamiento_detalle_id}
    />
  );
}
```

### 3. Orden de Columnas Recomendado

Se recomienda mostrar las columnas en el siguiente orden para mejor UX:

1. **Código Interno** (`codigo_interno`) - Identificador principal
2. **Producto** (`descripcion_producto`) - ⭐ **NUEVA COLUMNA** - Descripción legible
3. **Item Code SAP** (`item_code_sap`)
4. **Pack SAP** (`pack_sap`)
5. **Cantidad Original** (`cantidad_original`)
6. **Cantidad SAP** (`cantidad_sap`)
7. **Precio Unitario Original** (`precio_unitario_original`) - ⭐ **IMPORTANTE** - Precio por unidad en unidades originales
8. **Precio Unitario SAP** (`precio_unitario_sap`) - Precio por unidad en unidades SAP
9. **Total Línea Original** (`total_linea_original`)
10. **Total Línea SAP** (`total_linea_sap`)
11. **Homologado** (`producto_homologado`) - Con indicador visual (✓/✗)
12. **Tipo Problema** (`tipo_problema`) - Solo si `producto_homologado === false`
13. **Mensaje Error** (`mensaje_error`) - Solo si existe

**Nota:** El campo `precio_unitario_original` es importante para mostrar el precio por unidad antes de la conversión SAP. Debe estar visible en la tabla principal.

### 4. Manejo de Valores Nulos

El campo `descripcion_producto` puede ser `null` en algunos casos (productos procesados antes de agregar este campo). Maneja esto apropiadamente:

```typescript
// Opción 1: Mostrar texto por defecto
const descripcion = producto.descripcion_producto || 'Sin descripción';

// Opción 2: Mostrar código interno como fallback
const descripcion = producto.descripcion_producto || producto.codigo_interno;

// Opción 3: Mostrar "N/A" o placeholder
const descripcion = producto.descripcion_producto || 'N/A';
```

### 5. Ejemplo Completo de Componente Vue

```vue
<template>
  <div class="productos-procesados">
    <v-card>
      <v-card-title>
        Productos Procesados - {{ numeroPedido }}
      </v-card-title>
      
      <v-card-text>
        <v-data-table
          :headers="headers"
          :items="productos"
          :loading="loading"
          :items-per-page="25"
          class="elevation-1"
        >
          <!-- Columna de descripción del producto -->
          <template v-slot:item.descripcion_producto="{ item }">
            <span class="text-body-2">
              {{ item.descripcion_producto || item.codigo_interno }}
            </span>
          </template>
          
          <!-- Columna de precio unitario original (formateado) -->
          <template v-slot:item.precio_unitario_original="{ item }">
            <span class="text-body-2">
              {{ item.precio_unitario_original ? formatCurrency(item.precio_unitario_original) : '-' }}
            </span>
          </template>
          
          <!-- Columna de precio unitario SAP (formateado) -->
          <template v-slot:item.precio_unitario_sap="{ item }">
            <span class="text-body-2">
              {{ item.precio_unitario_sap ? formatCurrency(item.precio_unitario_sap) : '-' }}
            </span>
          </template>
          
          <!-- Columna de homologado con badge -->
          <template v-slot:item.producto_homologado="{ item }">
            <v-chip
              :color="item.producto_homologado ? 'success' : 'error'"
              small
            >
              {{ item.producto_homologado ? 'Sí' : 'No' }}
            </v-chip>
          </template>
          
          <!-- Columna de mensaje de error (solo si existe) -->
          <template v-slot:item.mensaje_error="{ item }">
            <v-tooltip v-if="item.mensaje_error" bottom>
              <template v-slot:activator="{ on }">
                <v-icon color="error" small v-on="on">mdi-alert</v-icon>
              </template>
              <span>{{ item.mensaje_error }}</span>
            </v-tooltip>
            <span v-else>-</span>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { ProductoSAPProcesamientoItem } from '@/types/api';

const props = defineProps<{
  pedidoId: string;
}>();

const productos = ref<ProductoSAPProcesamientoItem[]>([]);
const numeroPedido = ref<string>('');
const loading = ref(false);

const headers = [
  { text: 'Código Interno', value: 'codigo_interno', width: 150 },
  { text: 'Producto', value: 'descripcion_producto', width: 300 },  // ⭐ NUEVA COLUMNA
  { text: 'Item Code SAP', value: 'item_code_sap', width: 150 },
  { text: 'Pack SAP', value: 'pack_sap', width: 100 },
  { text: 'Cantidad Original', value: 'cantidad_original', width: 130 },
  { text: 'Cantidad SAP', value: 'cantidad_sap', width: 130 },
  { text: 'Precio Unit. Original', value: 'precio_unitario_original', width: 150 },  // ⭐ IMPORTANTE
  { text: 'Precio Unit. SAP', value: 'precio_unitario_sap', width: 150 },
  { text: 'Total Original', value: 'total_linea_original', width: 130 },
  { text: 'Total SAP', value: 'total_linea_sap', width: 130 },
  { text: 'Homologado', value: 'producto_homologado', width: 120 },
  { text: 'Error', value: 'mensaje_error', width: 100 },
];

async function cargarProductos() {
  loading.value = true;
  try {
    const response = await fetch(`/api/pedidos/${props.pedidoId}/procesamiento-sap`, {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
      },
    });
    
    const data = await response.json();
    productos.value = data.productos;
    numeroPedido.value = data.numero_pedido || props.pedidoId;
  } catch (error) {
    console.error('Error al cargar productos:', error);
  } finally {
    loading.value = false;
  }
}

// Función helper para formatear moneda
function formatCurrency(value: number): string {
  return new Intl.NumberFormat('es-CL', {
    style: 'currency',
    currency: 'CLP',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

onMounted(() => {
  cargarProductos();
});
</script>
```

## 🧪 Pruebas

Para verificar que el campo se está mostrando correctamente:

1. **Verificar respuesta del API:**
   ```bash
   curl -X GET "http://localhost:8000/api/pedidos/{pedido_id}/procesamiento-sap" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

2. **Verificar en el navegador:**
   - Abre las herramientas de desarrollador (F12)
   - Ve a la pestaña "Network"
   - Busca la llamada al endpoint `/api/pedidos/.../procesamiento-sap`
   - Verifica que el campo `descripcion_producto` esté presente en cada producto

3. **Verificar en la interfaz:**
   - La columna "Producto" debe aparecer después de "Código Interno"
   - Debe mostrar la descripción del producto o el código interno como fallback
   - La columna "Precio Unit. Original" debe estar visible y mostrar valores formateados
   - Los precios deben mostrarse con formato de moneda (ej: $25.50)
   - No debe mostrar errores en la consola

## 📝 Notas Importantes

- El campo `descripcion_producto` puede ser `null` para productos procesados antes de implementar este campo
- Se recomienda mostrar el `codigo_interno` como fallback cuando `descripcion_producto` sea `null`
- El campo tiene un máximo de 255 caracteres según la base de datos
- La descripción proviene del campo `descripcion_sap` de la tabla `pedido_detalle`
- **Precio Unitario Original**: ⭐ **IMPORTANTE** - Este campo muestra el precio por unidad antes de la conversión SAP. Debe estar visible en la tabla principal y formateado como moneda
- Los campos de precio (`precio_unitario_original`, `precio_unitario_sap`, `total_linea_original`, `total_linea_sap`) deben formatearse como moneda para mejor legibilidad

## 🔗 Referencias

- Endpoint: `GET /api/pedidos/{pedido_id}/procesamiento-sap`
- Modelo: `ProductoSAPProcesamientoItem` en `src/models.py`
- Repositorio: `PedidoSAPProcesamientoRepository` en `src/database/repositories/pedido_sap_procesamiento_repository.py`
