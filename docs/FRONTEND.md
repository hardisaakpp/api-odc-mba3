# Documentación Frontend

Guías de implementación y requerimientos para el sistema frontend.

---

## 0. Auth y Capabilities (obligatorio para botones por permiso)

**Problema:** Si el botón "Cargar Plantilla Excel" (u otros gated por capabilities) no se muestra en pantallas como `/mba3-consultas/pedidos/{id}`, suele deberse a que **las capabilities no se cargan**, no a la configuración del backend.

### 0.1 Fuente de verdad: `GET /api/auth/me`

- El backend expone `GET /api/auth/me` (header `Authorization: Bearer {token}`).
- La respuesta incluye `user`, `roles`, `permissions` y **`capabilities`**.
- El frontend debe usar **solo `capabilities`** para decidir qué botones/acciones mostrar (p. ej. `can_upload_templates`, `can_cargar_plantilla_excel`, `can_operate_pedidos`, `can_confirm_pedido`).

### 0.2 Cuándo llamar a `/api/auth/me`

| Momento | Acción |
|--------|--------|
| **Inicio de app** | Llamar `GET /api/auth/me` y guardar `capabilities` en el store de auth (p. ej. en `initializeAuth` o equivalente). |
| **Tras login** | Tras obtener el token, llamar `/api/auth/me` y actualizar el store. |
| **Restaurar sesión** | Si hay token en `localStorage` al cargar la app, llamar `/api/auth/me` para restaurar user y capabilities. |
| **Acceso directo por URL** | Si el usuario entra directo a `/mba3-consultas/pedidos/...` (refresh o enlace), el router debe asegurar que se haya llamado `/api/auth/me` antes de renderizar vistas que usan capabilities. |

Si **nunca** se llama `/api/auth/me` (o falla con 401), `capabilities` queda `null` → getters como `canUploadTemplates` devuelven `false` → botones como "Cargar Plantilla Excel" **no se muestran**.

### 0.3 Implementación recomendada

- **`initializeAuth`** (o similar): al arrancar la app, si hay token, llamar `GET /api/auth/me`, guardar `user` y `capabilities` en el store, y aplicar el token al cliente HTTP para el resto de peticiones.
- Invocar esta inicialización en `main.ts` (o punto de entrada) al cargar la app, y también cuando el router detecte rutas protegidas y aún no se hayan cargado capabilities.

### 0.4 Comprobación rápida

1. **Network:** Al abrir `/mba3-consultas/pedidos/{id}`, ¿existe una petición `GET .../api/auth/me` con 200?
2. **Respuesta:** ¿Incluye `capabilities.can_upload_templates` o `capabilities.can_cargar_plantilla_excel` en `true`?
3. **Store:** En el store de auth, ¿`state.capabilities` tiene esos campos en `true`?

Si falla alguno de estos puntos, corregir el flujo de auth (cuándo y cómo se llama `/api/auth/me`) antes de ajustar lógica de UI.

### 0.5 Migración desde Configuraciones Antiguas

**⚠️ IMPORTANTE:** Antes de implementar capabilities, el sistema usaba otras formas de controlar la visibilidad de botones. Si este código legacy aún existe en el frontend, **debe eliminarse** porque está interfiriendo con las capabilities.

#### 0.5.1 Lógica basada en "modo" o "tipo de usuario"

**Código legacy que DEBE eliminarse:**

```tsx
// ❌ CÓDIGO ANTIGUO (DEBE ELIMINARSE)
{modo === 'el-rayo' && <Button disabled={true}>...</Button>}
{modo === 'mabel-trading' && <Button>...</Button>}
{usuario.tipo === 'EL_RAYO' && <Button>...</Button>}
{empresa === 'MABEL_TRADING' && <Button>...</Button>}
{user.mode === 'el-rayo' && <Button>...</Button>}
```

**Solución:** Eliminar estas condiciones y usar capabilities:

```tsx
// ✅ CÓDIGO CORRECTO
{capabilities?.can_cargar_plantilla_excel && (
  <Button onClick={handleUploadExcel}>
    Cargar Plantilla Excel
  </Button>
)}

{capabilities?.can_confirm_pedido && (
  <Button onClick={handleConfirm}>
    Confirmar
  </Button>
)}
```

#### 0.5.2 Validación por nombre de usuario o empresa

**Código legacy que DEBE eliminarse:**

```tsx
// ❌ CÓDIGO ANTIGUO (DEBE ELIMINARSE)
{user.username.includes('mabel') && <Button>...</Button>}
{user.company === 'MABEL_TRADING' && <Button>...</Button>}
{user.empresa === 'EL_RAYO' && <Button>...</Button>}
```

**Solución:** Usar capabilities en lugar de validar identidad:

```tsx
// ✅ CÓDIGO CORRECTO
{capabilities?.can_upload_templates && <Button>Subir Excel</Button>}
{capabilities?.can_operate_pedidos && <Button>Operar Pedidos</Button>}
```

#### 0.5.3 Uso de permisos directamente (en lugar de capabilities)

**Código legacy que DEBE eliminarse:**

```tsx
// ❌ CÓDIGO ANTIGUO (DEBE ELIMINARSE)
{permissions.includes('mba3-consultas.proceso.execute') && <Button>...</Button>}
{hasPermission('mba3-consultas.facturas.view') && <Button>...</Button>}
{user.permissions?.includes('mba3-consultas.plantillas.upload') && <Button>...</Button>}
```

**Solución:** Usar capabilities, no permissions:

```tsx
// ✅ CÓDIGO CORRECTO
{capabilities?.can_upload_templates && <Button>Subir Excel</Button>}
{capabilities?.can_view_templates && <Button>Ver Plantillas</Button>}
```

#### 0.5.4 Endpoint de simulación (ya eliminado del backend)

**⚠️ El endpoint `/api/auth/dev/simulate` ya no existe en el backend.**

Si el frontend todavía intenta usar este endpoint, debe eliminarse y usar solo `/api/auth/me`.

**Código legacy que DEBE eliminarse:**

```tsx
// ❌ CÓDIGO ANTIGUO (DEBE ELIMINARSE)
const response = await fetch('/api/auth/dev/simulate?profile=mabel-trading');
```

**Solución:** Usar solo `/api/auth/me`:

```tsx
// ✅ CÓDIGO CORRECTO
const response = await fetch('/api/auth/me', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
const data = await response.json();
// Usar data.capabilities
```

#### 0.5.5 Configuraciones de entorno o feature flags

Si hay variables de entorno o flags que controlan la visibilidad de botones, deben eliminarse:

```tsx
// ❌ CÓDIGO ANTIGUO (DEBE ELIMINARSE)
{process.env.ENABLE_UPLOAD_BUTTON && <Button>...</Button>}
{config.showUploadButton && <Button>...</Button>}
{featureFlags.uploadEnabled && <Button>...</Button>}
```

**Solución:** Usar capabilities:

```tsx
// ✅ CÓDIGO CORRECTO
{capabilities?.can_upload_templates && <Button>Subir Excel</Button>}
```

#### 0.5.6 Checklist de Migración

Para identificar y eliminar código legacy en el frontend, buscar:

- [ ] `modo ===` o `mode ===`
- [ ] `usuario.tipo ===` o `user.type ===`
- [ ] `empresa ===` o `company ===`
- [ ] `permissions.includes(`
- [ ] `hasPermission(`
- [ ] Referencias a `/api/auth/dev/simulate`
- [ ] Feature flags o variables de entorno que controlen botones
- [ ] Validaciones por nombre de usuario o empresa

**Reemplazar TODO con capabilities:**

```tsx
// ✅ ÚNICA FORMA CORRECTA
{capabilities?.can_cargar_plantilla_excel && <Button>Cargar Plantilla Excel</Button>}
{capabilities?.can_confirm_pedido && <Button>Confirmar</Button>}
{capabilities?.can_operate_pedidos && <Button>Redistribuir</Button>}
```

#### 0.5.7 Mapeo de Configuraciones Antiguas a Capabilities

| Configuración Antigua | Capability Correcta |
|----------------------|---------------------|
| `modo === 'mabel-trading'` → mostrar botón "Cargar Plantilla Excel" | `capabilities.can_cargar_plantilla_excel` |
| `modo === 'el-rayo'` → mostrar botón "Confirmar" | `capabilities.can_confirm_pedido` |
| `permissions.includes('mba3-consultas.proceso.execute')` | `capabilities.can_upload_templates` o `capabilities.can_operate_pedidos` |
| `permissions.includes('mba3-consultas.facturas.view')` | `capabilities.can_view_templates` |
| `usuario.tipo === 'EL_RAYO'` → operar pedidos | `capabilities.can_operate_pedidos` |

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
