# 📋 Guía de Implementación Frontend - Requerimientos Implementados

**Fecha:** 29 de Enero de 2026  
**Versión:** 1.0  
**Estado:** ✅ Backend Implementado - Listo para Frontend

---

## 🎯 Resumen de Funcionalidades Implementadas

Se han implementado **2 funcionalidades de alta prioridad** según el documento de requerimientos:

1. ✅ **Solicitudes de Transferencia (HU-04)** - Generación automática de Solicitudes de Traslado en SAP
2. ✅ **Listado de Pedidos con Filtros (HU-02, HU-07)** - Pantalla de visualización y seguimiento

---

## 1. 📦 Solicitudes de Transferencia (HU-04)

### Descripción
Cuando se genera una Orden de Compra en SAP, el sistema ahora **automáticamente crea Solicitudes de Transferencia** para cada tienda que tiene productos asignados en la distribución confirmada.

### Cambios en el Endpoint Existente

**Endpoint:** `POST /integrar-sap`

**Comportamiento Nuevo:**
- Después de crear la OC exitosamente en SAP, el sistema automáticamente:
  1. Obtiene la distribución confirmada del pedido (por tienda)
  2. Crea un Inventory Transfer Request por cada tienda en SAP (POST /InventoryTransferRequests)
  3. Retorna información detallada de cada transferencia creada

**Respuesta Actualizada:**
```json
{
  "status": "success",
  "oc_id": "uuid-de-oc",
  "success": true,
  "doc_entry": 123,
  "doc_num": 456,
  "message": "Orden creada exitosamente. DocNum: 456",
  "solicitudes_transferencia": {
    "success": true,
    "pedido_id": "uuid-del-pedido",
    "total_tiendas": 3,
    "transferencias_creadas": 3,
    "transferencias_errores": 0,
    "resultados": [
      {
        "tienda_id": "uuid-tienda-1",
        "tienda_codigo": "TRL-QSN",
        "success": true,
        "doc_entry": 789,
        "doc_num": 101112,
        "error": null
      },
      {
        "tienda_id": "uuid-tienda-2",
        "tienda_codigo": "TRL-SMA",
        "success": true,
        "doc_entry": 790,
        "doc_num": 101113,
        "error": null
      },
      {
        "tienda_id": "uuid-tienda-3",
        "tienda_codigo": "TOUT-BOMB",
        "success": false,
        "doc_entry": null,
        "doc_num": null,
        "error": "Error al crear transferencia: [mensaje de error]"
      }
    ]
  }
}
```

### Qué Mostrar en el Frontend

**En la pantalla de integración SAP o después de generar OC:**

1. **Mostrar resumen de Solicitudes de Transferencia:**
   ```
   ✅ Solicitudes de Transferencia creadas: 3/3
   
   📦 TRL-QSN - DocNum: 101112 ✅
   📦 TRL-SMA - DocNum: 101113 ✅
   📦 TOUT-BOMB - Error: [mensaje] ❌
   ```

2. **Tabla detallada (opcional):**
   | Tienda | Código | Estado | DocNum | Error |
   |--------|--------|--------|--------|-------|
   | Tienda 1 | TRL-QSN | ✅ Creada | 101112 | - |
   | Tienda 2 | TRL-SMA | ✅ Creada | 101113 | - |
   | Tienda 3 | TOUT-BOMB | ❌ Error | - | Error al crear... |

3. **Si hay errores:**
   - Mostrar alerta de advertencia indicando cuántas transferencias fallaron
   - Permitir reintentar las transferencias fallidas (si se implementa endpoint de reintento)

### Nota Importante
Las Solicitudes de Transferencia se crean **automáticamente** después de una OC exitosa. No se requiere acción adicional del usuario.

---

## 2. 📋 Listado de Pedidos con Filtros (HU-02, HU-07)

### Descripción
Nuevo endpoint para listar pedidos con múltiples filtros y paginación. Permite a usuarios de **Mabel Trading** y **El Rayo** visualizar y dar seguimiento a los pedidos según sus necesidades.

### Nuevo Endpoint

**URL:** `GET /api/pedidos`

**Autenticación:** Requerida (JWT Token)  
**Permisos:** `mba3-consultas.facturas.view`

### Query Parameters

| Parámetro | Tipo | Requerido | Descripción | Ejemplo |
|-----------|------|-----------|-------------|---------|
| `estado` | string | No | Filtrar por estado del pedido | `PENDIENTE_CONFIRMACION_PROVEEDOR` |
| `fecha_desde` | string | No | Fecha desde (YYYY-MM-DD) | `2025-01-01` |
| `fecha_hasta` | string | No | Fecha hasta (YYYY-MM-DD) | `2025-01-31` |
| `proveedor_nombre` | string | No | Búsqueda parcial por nombre | `RAYO` |
| `numero_pedido` | string | No | Búsqueda parcial por número | `P-12.48` |
| `creado_por` | string | No | Filtrar por usuario creador | `user@example.com` |
| `limit` | integer | No | Registros por página (default: 50) | `20` |
| `offset` | integer | No | Offset para paginación (default: 0) | `0` |

### Ejemplos de Uso

```javascript
// Obtener pedidos pendientes de confirmación del proveedor
GET /api/pedidos?estado=PENDIENTE_CONFIRMACION_PROVEEDOR&limit=20&offset=0

// Buscar pedidos de El Rayo en enero 2025
GET /api/pedidos?fecha_desde=2025-01-01&fecha_hasta=2025-01-31&proveedor_nombre=RAYO

// Buscar pedido específico
GET /api/pedidos?numero_pedido=P-12.48

// Segunda página de resultados
GET /api/pedidos?limit=20&offset=20
```

### Respuesta

```json
{
  "status": "success",
  "data": [
    {
      "pedido_id": "AEDEC52D-D007-416F-8A09-9F0D31282EEE",
      "numero_pedido": "P-12.48 - 12 - 2025",
      "fecha_pedido": "2025-01-21",
      "fecha_entrega": "INMEDIATO",
      "forma_pago": "120 DIAS",
      "odc": null,
      "proveedor_nombre": "TEXTILES EL RAYO S.A.",
      "comprador_nombre": "VACA ANDREA",
      "comprador_codigo": "801",
      "origen_traslado": "RL-CD",
      "serie": null,
      "archivo_nombre": "Template_Pedido_Inicial_v1.0.xlsx",
      "creado_por": "user@example.com",
      "estado": "PENDIENTE_CONFIRMACION_PROVEEDOR",
      "creado_en": "2025-01-21T10:30:00"
    },
    {
      // ... más pedidos
    }
  ],
  "metadata": {
    "total": 150,
    "limit": 50,
    "offset": 0,
    "has_more": true
  }
}
```

### Estados de Pedido Disponibles

Los siguientes estados pueden usarse en el filtro `estado`:

- `PENDIENTE_CONFIRMACION_PROVEEDOR` - Esperando confirmación de El Rayo
- `RESPUESTA_PROVEEDOR_CARGADA` - Respuesta del proveedor cargada
- `CONFIRMADO_PROVEEDOR` - Confirmado por el proveedor
- `ORDEN_COMPRA_CREADA` - OC creada en el sistema
- `ENVIADA_SAP` - OC enviada a SAP
- `CONFIRMADO_ENVIADO` - Pedido completo y cerrado
- `CERRADO` - Cerrado
- `CANCELADO` - Cancelado

### Implementación en Frontend

#### Pantalla Principal (HU-02, HU-07)

**Para usuarios de Mabel Trading y El Rayo:**

1. **Barra de Filtros:**
   - Selector de Estado (dropdown con estados disponibles)
   - Rango de Fechas (date picker desde/hasta)
   - Campo de búsqueda de Proveedor (texto libre)
   - Campo de búsqueda de Número de Pedido (texto libre)
   - Botón "Buscar" / "Limpiar Filtros"

2. **Tabla de Pedidos:**
   - Columnas sugeridas:
     - Número de Pedido
     - Fecha de Pedido
     - Proveedor
     - Estado (con badge de color)
     - Comprador
     - Fecha de Creación
     - Acciones (Ver Detalle, etc.)
   - Paginación en la parte inferior
   - Ordenamiento (opcional, por fecha de creación DESC por defecto)

3. **Indicadores:**
   - Total de registros encontrados
   - Mostrando X - Y de Z resultados
   - Botones: Anterior / Siguiente

#### Ejemplo de Componente Vue/React

```vue
<template>
  <div class="pedidos-listado">
    <!-- Filtros -->
    <div class="filters">
      <select v-model="filtros.estado">
        <option value="">Todos los estados</option>
        <option value="PENDIENTE_CONFIRMACION_PROVEEDOR">Pendiente Confirmación</option>
        <option value="CONFIRMADO_PROVEEDOR">Confirmado</option>
        <!-- ... más opciones -->
      </select>
      
      <input type="date" v-model="filtros.fecha_desde" />
      <input type="date" v-model="filtros.fecha_hasta" />
      
      <input 
        type="text" 
        v-model="filtros.proveedor_nombre" 
        placeholder="Buscar proveedor..." 
      />
      
      <input 
        type="text" 
        v-model="filtros.numero_pedido" 
        placeholder="Buscar número de pedido..." 
      />
      
      <button @click="buscar">Buscar</button>
      <button @click="limpiarFiltros">Limpiar</button>
    </div>
    
    <!-- Tabla -->
    <table>
      <thead>
        <tr>
          <th>Número</th>
          <th>Fecha</th>
          <th>Proveedor</th>
          <th>Estado</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="pedido in pedidos" :key="pedido.pedido_id">
          <td>{{ pedido.numero_pedido }}</td>
          <td>{{ pedido.fecha_pedido }}</td>
          <td>{{ pedido.proveedor_nombre }}</td>
          <td>
            <span :class="'badge-' + pedido.estado">
              {{ pedido.estado }}
            </span>
          </td>
          <td>
            <button @click="verDetalle(pedido.pedido_id)">
              Ver Detalle
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    
    <!-- Paginación -->
    <div class="pagination">
      <button 
        @click="cambiarPagina(offset - limit)" 
        :disabled="offset === 0"
      >
        Anterior
      </button>
      <span>
        Mostrando {{ offset + 1 }} - {{ Math.min(offset + limit, total) }} 
        de {{ total }} resultados
      </span>
      <button 
        @click="cambiarPagina(offset + limit)" 
        :disabled="!hasMore"
      >
        Siguiente
      </button>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      pedidos: [],
      filtros: {
        estado: '',
        fecha_desde: '',
        fecha_hasta: '',
        proveedor_nombre: '',
        numero_pedido: ''
      },
      metadata: {
        total: 0,
        limit: 50,
        offset: 0,
        has_more: false
      }
    }
  },
  methods: {
    async buscar() {
      const params = new URLSearchParams({
        limit: this.metadata.limit,
        offset: this.metadata.offset,
        ...Object.fromEntries(
          Object.entries(this.filtros).filter(([_, v]) => v)
        )
      })
      
      const response = await fetch(`/api/pedidos?${params}`, {
        headers: {
          'Authorization': `Bearer ${this.token}`
        }
      })
      
      const data = await response.json()
      this.pedidos = data.data
      this.metadata = data.metadata
    },
    cambiarPagina(nuevoOffset) {
      this.metadata.offset = nuevoOffset
      this.buscar()
    },
    limpiarFiltros() {
      this.filtros = {
        estado: '',
        fecha_desde: '',
        fecha_hasta: '',
        proveedor_nombre: '',
        numero_pedido: ''
      }
      this.metadata.offset = 0
      this.buscar()
    }
  },
  mounted() {
    this.buscar()
  }
}
</script>
```

---

## 🔄 Flujo Completo Actualizado

### Antes (sin Solicitudes de Transferencia):
1. Crear pedido ✅
2. El Rayo confirma ✅
3. Mabel Trading redistribuye ✅
4. Generar OC → Solo OC en SAP ❌

### Ahora (con Solicitudes de Transferencia):
1. Crear pedido ✅
2. El Rayo confirma ✅
3. Mabel Trading redistribuye ✅
4. Generar OC → **OC + Solicitudes de Transferencia automáticamente** ✅

---

## ✅ Checklist para Frontend

### Pantalla de Integración SAP
- [ ] Mostrar información de Solicitudes de Transferencia creadas
- [ ] Mostrar tabla/lista de transferencias por tienda
- [ ] Mostrar DocNum de cada transferencia exitosa
- [ ] Mostrar errores si alguna transferencia falló
- [ ] Indicador visual de éxito/error por transferencia

### Pantalla de Listado de Pedidos (NUEVA)
- [ ] Crear componente/ruta nueva para listado
- [ ] Implementar filtros (estado, fechas, proveedor, número)
- [ ] Tabla con columnas relevantes
- [ ] Paginación funcional
- [ ] Badges de color por estado
- [ ] Botón "Ver Detalle" que navega al detalle del pedido
- [ ] Manejo de estados vacíos (sin resultados)

### Estados y Badges Sugeridos
```css
/* Sugerencias de colores para badges de estado */
.badge-PENDIENTE_CONFIRMACION_PROVEEDOR { background: #ffc107; }
.badge-CONFIRMADO_PROVEEDOR { background: #17a2b8; }
.badge-ORDEN_COMPRA_CREADA { background: #007bff; }
.badge-ENVIADA_SAP { background: #28a745; }
.badge-CONFIRMADO_ENVIADO { background: #6c757d; }
.badge-CANCELADO { background: #dc3545; }
```

---

## 📝 Notas Adicionales

1. **Las Solicitudes de Transferencia son automáticas**: No requieren acción del usuario, solo mostrar la información.

2. **El listado de pedidos es opcional**: Puede implementarse como una nueva vista o integrarse en una vista existente.

3. **Paginación del lado del servidor**: El backend ya implementa paginación eficiente, no es necesario cargar todos los pedidos.

4. **Filtros combinables**: Todos los filtros pueden usarse simultáneamente.

5. **Búsquedas parciales**: `proveedor_nombre` y `numero_pedido` hacen búsqueda parcial (LIKE), no exacta.

---

## 🔗 Endpoints Relacionados (Ya Existentes)

- `GET /api/plantillas/{identificador}` - Ver detalle de un pedido específico
- `POST /integrar-sap` - Generar OC (ahora incluye Solicitudes de Transferencia)

---

## 📞 Soporte

Si necesitas información adicional o aclaraciones sobre estos endpoints, consulta:
- Documentación de endpoints: `docs/ENDPOINTS.md`
- Estructura de base de datos: `docs/ESTRUCTURA_BD_PEDIDOS.md`
