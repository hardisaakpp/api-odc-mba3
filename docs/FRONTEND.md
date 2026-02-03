# Documentación Frontend

Guías de implementación y requerimientos para el sistema frontend.

---

## 0. Auth y Capabilities (obligatorio para botones por permiso)

**Problema:** Si el botón "Cargar Plantilla Excel" (u otros gated por capabilities) no se muestra en pantallas como `/mba3-consultas/pedidos/{id}`, suele deberse a que **las capabilities no se cargan** o **los getters no las usan bien**, no a la configuración del backend. Si ya dependen solo de capabilities y siguen sin verse → **0.4.1 Diagnóstico**.

### 0.1 Fuente de verdad: `GET /api/auth/me` o `GET /api/Auth/me`

- El backend expone `GET /api/auth/me` y, como alias, `GET /api/Auth/me` (header `Authorization: Bearer {token}`).
- La respuesta **debe incluir siempre** `user`, `roles`, `permissions` y **`capabilities`**.
- El frontend debe usar **solo `capabilities`** para decidir qué botones/acciones mostrar (p. ej. `can_upload_templates`, `can_cargar_plantilla_excel`, `can_operate_pedidos`, `can_confirm_pedido`).

**Opción A (backend):** Si al llamar `/api/Auth/me` (o `/api/auth/me`) el frontend obtiene `data.capabilities === undefined`, el backend que sirve esa ruta **debe modificarse** para incluir el objeto `capabilities` en la respuesta. El backend de mba3-consultas ya lo hace: devuelve `user` (con `userName`, `fullName`, `permissions`, `roles`), `roles`, `permissions` y **`capabilities`**. Para que el frontend vea el botón "Gestión ODC SAP" y el resto por capability, la petición auth/me debe ir a un backend que implemente este contrato (p. ej. el de mba3-consultas) o el backend actual debe añadir el cálculo y envío de `capabilities`.

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

### 0.4.1 Diagnóstico: botones siguen sin mostrarse (ya solo dependen de capabilities)

Si eliminaste modo MABEL TRADING/EL RAYO y los botones dependen solo de capabilities pero **aún no se ven** (Cargar Plantilla Excel, Gestión ODC SAP, Descargar para MBA, etc.), revisar en este orden:

#### 1. ¿Se llama `/api/auth/me` y responde 200?

- Abrir DevTools → **Network**. Ir a `/mba3-consultas/pedidos/{id}` (o hacer **refresh** en esa ruta).
- Filtrar por `auth` o `me`. Debe existir `GET .../api/auth/me` con **200**.
- Si **no hay petición** o hay **401**: las capabilities nunca se cargan → todos los getters serán `false` → no se muestra nada.
- **Causas típicas:** no se llama auth/me al iniciar, al restaurar sesión o al entrar por URL directa; token ausente o inválido en el `Authorization` header.

#### 2. ¿La respuesta incluye las capabilities esperadas?

- En la petición `GET /api/auth/me` → **Response**.
- Debe existir `capabilities` con las claves en **snake_case** (el backend siempre usa snake_case):
  - `can_cargar_plantilla_excel`
  - `can_operate_pedidos`
  - `can_view_odc_sap`
  - `can_manage_order`
  - `can_view_order_list`
  - `mabel_view`
  - `can_confirm_pedido`
- Los valores dependen de los permisos del usuario. **`can_view_odc_sap`** es `true` **solo** si tiene `odc.view` (0.5.7.1). **`can_manage_order`** y **`can_view_order_list`** son `true` **solo** si tiene `odcsap.view` (0.5.7.2). **`mabel_view`** es `true` **solo** si tiene `mabel.view` (0.5.7.3).
- Si las claves vienen en otro formato (ej. camelCase) o no existen, el backend no las envía así; habría que revisar si hay una capa intermedia que transforma la respuesta.

#### 3. ¿Los getters leen **solo** de `capabilities`?

- Los nombres usados en el template (ej. `canOperatePedidos`, `canCargarPlantillaExcel`) suelen venir de **getters** o **computed**.
- Cada uno debe mapear **directamente** desde `capabilities`:
  - `canOperatePedidos` → `state.auth.capabilities?.can_operate_pedidos === true`
  - `canCargarPlantillaExcel` → `state.auth.capabilities?.can_cargar_plantilla_excel === true`
  - `canViewOdcSap` → `state.auth.capabilities?.can_view_odc_sap === true`
  - `canManageOrder` → `state.auth.capabilities?.can_manage_order === true`
  - `canViewOrderList` → `state.auth.capabilities?.can_view_order_list === true`
  - `canViewMabel` → `state.auth.capabilities?.mabel_view === true`
  - `canConfirmPedido` → `state.auth.capabilities?.can_confirm_pedido === true`
- **Evitar:** que los getters usen `modo`, `esModoMabelTrading`, `esModoElRayo`, `empresa`, etc. para derivar estos valores. Cualquier condición extra puede hacer que sigan en `false` aunque el backend envíe `true`.

#### 4. ¿El store se actualiza con la respuesta de `/api/auth/me`?

- Tras `GET /api/auth/me` exitoso, debe guardarse `response.capabilities` en el store (ej. `state.auth.capabilities = data.capabilities`).
- Comprobar en DevTools (Vue Devtools / Redux DevTools, etc.) que, tras cargar la app o hacer login, `state.auth.capabilities` contiene las claves anteriores con los valores esperados.

#### 5. Acceso directo por URL o refresh en `/mba3-consultas/pedidos/{id}`

- Si el usuario entra **directo** por enlace o **refresh** en esa ruta, la app puede renderizar la vista **antes** de que se llame `/api/auth/me`.
- En ese caso, `capabilities` sigue vacío o sin cargar → getters en `false` → botones no se muestran.
- **Solución:** Asegurar que en rutas que usan capabilities (p. ej. detalle de pedido) se espere a que auth/me haya terminado antes de renderizar, o que se dispare auth/me al entrar a la ruta si aún no se ha hecho.

#### 6. Vue: `v-if` y reactiveidad

- Si usas `v-if="canOperatePedidos"` (u otros), asegurarse de que `canOperatePedidos` sea **reactivo** (computed o getter del store). Si se toma una copia “en frío” al montar y el store se actualiza después, el `v-if` no se re-evalúa.
- Los getters del store (Pinia/Vuex) son reactivos; usarlos directamente en el template o en un computed que los use evita este problema.

#### Checklist rápido

| Paso | Comprobar |
|------|-----------|
| 1 | Hay `GET /api/auth/me` con 200 al abrir o refrescar la pantalla de detalle |
| 2 | La respuesta tiene `capabilities` con las claves esperadas y valores según permisos del usuario |
| 3 | El store guarda `capabilities` y los getters leen solo de ahí (sin modo/empresa) |
| 4 | En la vista de detalle, auth/me ya se ejecutó antes de renderizar |
| 5 | Los `v-if` usan getters/computed reactivos que mapean esas capabilities |

Si todo lo anterior es correcto y los botones siguen sin mostrarse, revisar si algún **componente padre** o **ruta** oculta por completo la sección donde están los botones (p. ej. otro `v-if` con modo o permisos).

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

#### 0.5.7.1 Botón sidebar "Gestión ODC SAP" — permiso `odc.view`

El botón **"Gestión ODC SAP"** en el sidebar depende **únicamente** del permiso `odc.view`.

**Reglas exactas:**

- La capability `can_view_odc_sap` es `true` **solo** si el usuario tiene el permiso `odc.view` (sin admin override).
- El botón **solo debe mostrarse** si `capabilities.can_view_odc_sap === true`.
- El permiso `odc.view` **no** condiciona ningún otro botón ni funcionalidad del dashboard.
- El frontend **no** debe chequear permisos directamente; solo la capability.

**Implementación en frontend:**

```tsx
{capabilities.can_view_odc_sap && <SidebarODCButton />}
```

Nada más. No usar `permissions.includes('odc.view')` ni lógica distinta a la capability.

**Comportamiento esperado:**

- Usuario sin `odc.view` → no ve el botón.
- Usuario con `odc.view` → ve el botón y puede entrar.

#### 0.5.7.2 Botones "Gestionar Pedido" y "Listado de Pedidos" — permiso `odcsap.view`

Los botones **"Gestionar Pedido"** y **"Listado de Pedidos"** dependen **únicamente** del permiso `odcsap.view`.

**Reglas exactas:**

- El permiso `odcsap.view` habilita **exclusivamente** estos dos botones:
  - "Gestionar Pedido" → capability `can_manage_order`
  - "Listado de Pedidos" → capability `can_view_order_list`
- Cada capability es `true` **solo** si el usuario tiene el permiso `odcsap.view`.
- Usuarios **sin** `odcsap.view` **no** ven ninguno de los dos botones.
- El permiso `odcsap.view` **no** afecta al botón "Gestión ODC SAP" del sidebar ni a ningún otro botón del dashboard.
- El frontend **solo** debe usar capabilities para mostrar u ocultar estos botones; nunca permisos directos.

**Mapeo:**

| Permiso       | Capability            | Botón              |
|---------------|-----------------------|--------------------|
| `odcsap.view` | `can_manage_order`    | Gestionar Pedido   |
| `odcsap.view` | `can_view_order_list` | Listado de Pedidos |

**Implementación en frontend:**

```tsx
{capabilities.can_manage_order && <Button to="/mba3-consultas/gestionar-pedido">Gestionar Pedido</Button>}
{capabilities.can_view_order_list && <Link to="/mba3-consultas/listado-pedidos">Listado de Pedidos</Link>}
```

No usar `permissions.includes('odcsap.view')` ni lógica distinta a las capabilities.

**Comportamiento esperado:**

- Usuario con `odcsap.view` → ve "Gestionar Pedido" y "Listado de Pedidos".
- Usuario sin `odcsap.view` → no ve ninguno de los dos.
- El sidebar **no cambia** por este permiso.

#### 0.5.7.3 Botones del módulo MABEL — permiso `mabel.view`

Los botones del **módulo MABEL** dependen **únicamente** del permiso `mabel.view`.

**Reglas exactas:**

- La capability `mabel_view` es `true` **solo** si el usuario tiene el permiso `mabel.view` (sin admin override).
- Cuando `capabilities.mabel_view === true`, el usuario **puede visualizar únicamente** los siguientes botones:
  - **Cargar Plantilla**
  - **Redistribución**
  - **Procesamiento SAP**
  - **Procesos**
  - **Homologaciones**
- Cuando `capabilities.mabel_view !== true`, **ninguno** de esos botones debe mostrarse.
- El frontend **no** debe deducir permisos; el backend es la única autoridad sobre capabilities.

**Implementación en frontend:**

```tsx
{capabilities.mabel_view && <Button to="...">Cargar Plantilla</Button>}
{capabilities.mabel_view && <Button to="...">Redistribución</Button>}
{capabilities.mabel_view && <Button to="...">Procesamiento SAP</Button>}
{capabilities.mabel_view && <Button to="...">Procesos</Button>}
{capabilities.mabel_view && <Button to="...">Homologaciones</Button>}
```

O mediante getter: `canViewMabel` → `state.auth.capabilities?.mabel_view === true`.

No usar `permissions.includes('mabel.view')` ni lógica distinta a la capability.

**Comportamiento esperado:**

- Usuario con `mabel.view` → ve Cargar Plantilla, Redistribución, Procesamiento SAP, Procesos y Homologaciones.
- Usuario sin `mabel.view` → no ve ninguno de esos botones.

**Regla de oro:** Frontend NO deduce permisos. Backend es la única autoridad sobre capabilities.

### 0.5.8 Pantalla "Detalle del Pedido - EL RAYO" (`/mba3-consultas/pedidos/{id}`)

**Ruta:** `http://localhost:3000/mba3-consultas/pedidos/{numero_pedido}` (ej. `P-12.21 - 12 - 2025`).

- **MOSTRAR** "Cargar Plantilla Excel" si `capabilities.can_cargar_plantilla_excel`.
- **MOSTRAR** Redistribuir, Exportar, Descargar para MBA si `capabilities.can_operate_pedidos`.
- **MOSTRAR** el botón "Confirmar" solo si `capabilities.can_confirm_pedido === true`.

### 0.5.8.1 Gestión del botón "Confirmar" en detalle del pedido

En la pantalla `/mba3-consultas/pedidos/{numero_pedido}` (ej. `P-12.23 - 12 - 2025`), cuando el usuario hace clic en **"Confirmar"** se debe:

1. **Llamar al backend** para guardar y registrar la confirmación.
2. **Persistir el estado** del pedido en el backend (el backend lo hace; el frontend solo debe llamar al endpoint).
3. **Deshabilitar el botón "Confirmar"** una vez que el pedido está confirmado o ya tiene respuesta cargada, para evitar confirmaciones duplicadas.

**Endpoint a usar:** `POST /api/pedidos/{pedido_id}/crear-respuesta-desde-pedido`

- **Método:** POST  
- **URL:** `/api/pedidos/{pedido_id}/crear-respuesta-desde-pedido`  
- **Nota:** La ruta de la app usa `numero_pedido` (ej. `P-12.23 - 12 - 2025`), pero el API recibe **`pedido_id`** (UUID). Usar siempre el **`cabecera.pedido_id`** del pedido cargado en esa pantalla.  
- **Body:** no se envía body (o vacío).  
- **Autenticación:** JWT en header `Authorization: Bearer {token}`.  
- **Permiso:** `mba3-consultas.proceso.execute`.

**Qué hace el backend:**

- Toma los datos actuales del pedido (totales, costos, etc.), genera la respuesta del proveedor y la guarda.
- Actualiza el estado del pedido a **`RESPUESTA_PROVEEDOR_CARGADA`**.
- Registra la confirmación en el historial (tabla de confirmaciones EL RAYO).
- Responde con `status: "success"`, `confirmacion_registrada: true/false`, `estado_guardado`, etc.

**Comportamiento en el frontend:**

| Acción | Comportamiento |
|--------|----------------|
| **Al hacer clic en "Confirmar"** | Enviar `POST /api/pedidos/{cabecera.pedido_id}/crear-respuesta-desde-pedido`. Mostrar indicador de carga (p. ej. botón deshabilitado + “Guardando…” o spinner). |
| **Si la petición es exitosa** | Actualizar el estado local del pedido con el nuevo `estado` (p. ej. `RESPUESTA_PROVEEDOR_CARGADA`) o recargar el pedido desde el backend. Deshabilitar el botón "Confirmar". Opcionalmente, según diseño: redirigir a la pantalla de redistribución del mismo pedido (como en el flujo anterior). |
| **Si la petición falla** | Mostrar mensaje de error, dejar el botón habilitado para reintentar. |

**Cuándo deshabilitar el botón "Confirmar":**

Deshabilitar (y no permitir nueva confirmación) cuando el estado del pedido ya indica que la respuesta está cargada o confirmada. Usar el campo **`cabecera.estado`** del pedido cargado:

- `RESPUESTA_PROVEEDOR_CARGADA` → respuesta ya guardada; deshabilitar.
- `CONFIRMADO_PROVEEDOR` → confirmación ya procesada; deshabilitar.
- `CONFIRMADO REDISTRIBUCION` (o `PEDIDO_CONFIRMADO` por compatibilidad) → redistribución ya confirmada; deshabilitar.
- Cualquier otro estado posterior (p. ej. `PROCESADO_SAP`, `CONFIRMADO_ENVIADO`, etc.) → deshabilitar.

**Resumen:**

- **Mostrar** el botón solo si `capabilities.can_confirm_pedido` (ya definido en 0.5.8).
- **Deshabilitar** el botón si `cabecera.estado` está en uno de los estados anteriores (ya confirmado / respuesta cargada).
- **Al hacer clic:** `POST /api/pedidos/{cabecera.pedido_id}/crear-respuesta-desde-pedido` → tras éxito, actualizar estado (o recargar pedido) y deshabilitar el botón.

### 0.5.10 Cambio de Ruta: Cargar Plantillas → Gestionar Pedido

**⚠️ CAMBIO DE RUTA IMPLEMENTADO**

La ruta para cargar plantillas Excel ha sido renombrada:

- **❌ Ruta antigua:** `/mba3-consultas/cargar-plantillas`
- **✅ Ruta nueva:** `/mba3-consultas/gestionar-pedido`

### 0.5.11 Visibilidad del Botón "Gestionar Pedido"

**Requerimiento:** El botón "Gestionar Pedido" debe aparecer solo cuando existan pedidos guardados en la base de datos.

**Endpoint:** `GET /api/pedidos/existe`

**Autenticación:** JWT token requerido  
**Permiso:** `mba3-consultas.facturas.view`

**Respuesta:**
```json
{
  "status": "success",
  "tiene_pedidos": true,
  "message": "Existen pedidos en el sistema"
}
```

**Implementación en el Frontend:**

```tsx
// React/TypeScript
import { useState, useEffect } from 'react';

const Sidebar = () => {
  const [tienePedidos, setTienePedidos] = useState<boolean>(false);
  const [cargando, setCargando] = useState<boolean>(true);

  useEffect(() => {
    const verificarPedidos = async () => {
      try {
        const response = await fetch('/api/pedidos/existe', {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        
        const data = await response.json();
        setTienePedidos(data.tiene_pedidos);
      } catch (error) {
        console.error('Error al verificar pedidos:', error);
        setTienePedidos(false);
      } finally {
        setCargando(false);
      }
    };

    verificarPedidos();
  }, []);

  return (
    <nav>
      {/* Otros elementos del sidebar */}
      
      {/* Mostrar botón solo si hay pedidos */}
      {!cargando && tienePedidos && (
        <Link to="/mba3-consultas/gestionar-pedido">
          Gestionar Pedido
        </Link>
      )}
    </nav>
  );
};
```

```vue
<!-- Vue.js -->
<template>
  <nav>
    <!-- Otros elementos del sidebar -->
    
    <!-- Mostrar botón solo si hay pedidos -->
    <router-link 
      v-if="!cargando && tienePedidos"
      to="/mba3-consultas/gestionar-pedido"
    >
      Gestionar Pedido
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';

const tienePedidos = ref<boolean>(false);
const cargando = ref<boolean>(true);

const verificarPedidos = async () => {
  try {
    const response = await fetch('/api/pedidos/existe', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    
    const data = await response.json();
    tienePedidos.value = data.tiene_pedidos;
  } catch (error) {
    console.error('Error al verificar pedidos:', error);
    tienePedidos.value = false;
  } finally {
    cargando.value = false;
  }
};

onMounted(() => {
  verificarPedidos();
});
</script>
```

**Cuándo verificar:**

1. **Al cargar la aplicación:** Verificar al montar el componente del sidebar o menú principal
2. **Después de crear un pedido:** Si el usuario crea un pedido (manual o desde Excel), actualizar el estado para mostrar el botón
3. **Después de eliminar el último pedido:** Si se elimina el último pedido, ocultar el botón

**Optimización (opcional):**

Para evitar múltiples llamadas, puedes cachear el resultado en el store de estado global:

```tsx
// Store (Zustand/Pinia/Redux)
const usePedidosStore = create((set) => ({
  tienePedidos: false,
  verificarPedidos: async () => {
    const response = await fetch('/api/pedidos/existe', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    set({ tienePedidos: data.tiene_pedidos });
  }
}));
```

**Nota:** El endpoint es ligero y eficiente, pero si prefieres evitar una llamada adicional, también puedes usar `GET /api/pedidos?limit=1` y verificar si `metadata.total > 0`. Sin embargo, el endpoint `/api/pedidos/existe` es más semántico y eficiente para este propósito.

#### Cambios Requeridos en el Frontend

**1. Actualizar el Router:**

```tsx
// React Router
// ❌ ANTES
<Route path="/mba3-consultas/cargar-plantillas" component={CargarPlantillas} />

// ✅ DESPUÉS
<Route path="/mba3-consultas/gestionar-pedido" component={CargarPlantillas} />
```

```ts
// Vue Router
// ❌ ANTES
{ path: '/mba3-consultas/cargar-plantillas', component: CargarPlantillas }

// ✅ DESPUÉS
{ path: '/mba3-consultas/gestionar-pedido', component: CargarPlantillas }
```

**2. Actualizar Enlaces y Navegación:**

```tsx
// ❌ ANTES
<Link to="/mba3-consultas/cargar-plantillas">Cargar Plantillas</Link>
<router-link to="/mba3-consultas/cargar-plantillas">Cargar Plantillas</router-link>

// ✅ DESPUÉS
<Link to="/mba3-consultas/gestionar-pedido">Gestionar Pedido</Link>
<router-link to="/mba3-consultas/gestionar-pedido">Gestionar Pedido</router-link>
```

**3. Actualizar Redirecciones:**

```tsx
// ❌ ANTES
navigate('/mba3-consultas/cargar-plantillas');
router.push('/mba3-consultas/cargar-plantillas');

// ✅ DESPUÉS
navigate('/mba3-consultas/gestionar-pedido');
router.push('/mba3-consultas/gestionar-pedido');
```

**4. (Opcional) Mantener Compatibilidad con Redirect:**

Para que la ruta antigua redirija automáticamente a la nueva:

```tsx
// React Router
<Route 
  path="/mba3-consultas/cargar-plantillas" 
  element={<Navigate to="/mba3-consultas/gestionar-pedido" replace />} 
/>

// Vue Router
{
  path: '/mba3-consultas/cargar-plantillas',
  redirect: '/mba3-consultas/gestionar-pedido'
}
```

**5. Checklist de Cambios:**

- [ ] Actualizar ruta en el router principal
- [ ] Buscar y actualizar todos los `<Link>` o `<router-link>`
- [ ] Buscar y actualizar todos los `navigate()` o `router.push()`
- [ ] Actualizar referencias en sidebar/menú de navegación
- [ ] Actualizar breadcrumbs si existen
- [ ] Actualizar títulos de página si mencionan "Cargar Plantillas"
- [ ] (Opcional) Agregar redirect de ruta antigua a nueva
- [ ] Actualizar documentación interna del frontend

**Nota:** El backend no requiere cambios. Los endpoints API (ej. `POST /api/plantillas/upload`) siguen funcionando igual. Solo cambia la ruta del frontend.

### 0.5.12 Comportamiento de Redirección Después de Cargar Plantilla Excel

**⚠️ IMPORTANTE: Comportamiento Correcto de Navegación**

Cuando se termina de cargar la información de la plantilla Excel exitosamente:

- **❌ INCORRECTO:** Redirigir a `/mba3-consultas/pedidos/{numero_pedido}`
- **✅ CORRECTO:** Permanecer en `/mba3-consultas/cargar-plantilla/{numero_pedido}`

**Razón:** La interfaz de "Cargar Plantilla" es diferente a la interfaz de "Detalle de Pedido". Después de cargar, el usuario debe permanecer en la misma interfaz para poder:
- Ver el resultado de la carga
- Cargar otra plantilla si es necesario
- Revisar errores o advertencias de validación

**Implementación Correcta:**

```tsx
// React/TypeScript
const handleUpload = async () => {
  if (!file) return;

  try {
    setUploading(true, 'Cargando plantilla Excel...');

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/api/plantillas/upload', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Error al cargar plantilla');
    }

    // ✅ CORRECTO: Actualizar URL sin cambiar de ruta base
    const numeroPedido = data.numero_pedido;
    if (numeroPedido) {
      // Actualizar la URL para incluir el número de pedido, pero mantener la ruta base
      navigate(`/mba3-consultas/cargar-plantilla/${encodeURIComponent(numeroPedido)}`, { replace: true });
    }

    setUploading(false);
    showSuccessNotification('Plantilla cargada exitosamente');
    
    // Opcional: Recargar los datos del pedido en la misma interfaz
    if (numeroPedido) {
      await cargarDatosPedido(numeroPedido);
    }

  } catch (error) {
    setUploading(false);
    showErrorNotification(error.message || 'Error al procesar plantilla');
  }
};
```

```vue
<!-- Vue.js -->
<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const file = ref<File | null>(null);
const isUploading = ref(false);

const handleUpload = async () => {
  if (!file.value) return;

  try {
    isUploading.value = true;

    const formData = new FormData();
    formData.append('file', file.value);

    const response = await fetch('/api/plantillas/upload', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Error al cargar plantilla');
    }

    // ✅ CORRECTO: Actualizar URL sin cambiar de ruta base
    const numeroPedido = data.numero_pedido;
    if (numeroPedido) {
      // Actualizar la URL para incluir el número de pedido, pero mantener la ruta base
      router.push({
        path: `/mba3-consultas/cargar-plantilla/${encodeURIComponent(numeroPedido)}`,
        replace: true
      });
    }

    isUploading.value = false;
    // Mostrar notificación de éxito
    
    // Opcional: Recargar los datos del pedido en la misma interfaz
    if (numeroPedido) {
      await cargarDatosPedido(numeroPedido);
    }

  } catch (error) {
    isUploading.value = false;
    // Mostrar notificación de error
  }
};
</script>
```

**Estructura de Respuesta del Backend:**

El endpoint `POST /api/plantillas/upload` devuelve:

```json
{
  "status": "success",
  "message": "Plantilla procesada y guardada exitosamente",
  "pedido_id": "uuid-del-pedido",
  "numero_pedido": "P-12.21 - 12 - 2025",
  "formato_detectado": "v1.0",
  "articulos_cargados": 150,
  "distribuciones_cargadas": 450,
  "validation": { ... },
  "file_info": {
    "filename": "pedido.xlsx",
    "size_mb": 2.5
  },
  "metadata": {
    "uploaded_by": "usuario@example.com",
    "uploaded_at": "2025-01-26T10:30:00"
  }
}
```

**Checklist de Implementación:**

- [ ] NO redirigir a `/mba3-consultas/pedidos/{numero_pedido}` después de cargar
- [ ] Permanecer en `/mba3-consultas/cargar-plantilla/{numero_pedido}` (o actualizar URL si no tiene el número de pedido)
- [ ] Usar `replace: true` al actualizar la URL para no crear una nueva entrada en el historial
- [ ] Mostrar notificación de éxito/error
- [ ] Opcional: Recargar datos del pedido en la misma interfaz si es necesario

**Nota:** Si el usuario quiere ver el detalle completo del pedido, puede hacer clic en un botón/link que lo lleve a `/mba3-consultas/pedidos/{numero_pedido}`, pero esto debe ser una acción explícita del usuario, no una redirección automática.

### 0.5.13 Título de la Pantalla Proceso (`/mba3-consultas/proceso`)

**Ruta:** `http://localhost:3000/mba3-consultas/proceso`

**Título obligatorio:** **Procesar ODC - MABEL TRADING**

El título de la página (etiqueta `<title>` del documento y/o encabezado visible de la vista) debe ser exactamente:

```
Procesar ODC - MABEL TRADING
```

**Implementación sugerida:**

- **React:** En el componente de la ruta `/mba3-consultas/proceso`, usar `document.title = "Procesar ODC - MABEL TRADING"` en `useEffect` o definir el título en el meta/helmet según la convención del proyecto.
- **Vue:** En el componente de la ruta `/mba3-consultas/proceso`, usar `document.title = "Procesar ODC - MABEL TRADING"` en `onMounted` o el mecanismo de title del router (ej. `meta.title`).

---

## 0.6 Bloqueo de Interfaz Durante Carga de Plantilla Excel

**Requerimiento:** Mientras se carga y procesa una plantilla Excel, se debe bloquear toda la interfaz con un modal de carga que impida cualquier interacción del usuario.

### 0.6.1 Comportamiento Requerido

Cuando el usuario hace clic en "Cargar Plantilla Excel" y selecciona un archivo:

1. **Inmediatamente** mostrar un modal/overlay que bloquee toda la interfaz
2. **Deshabilitar** todos los botones y acciones de la página
3. **Mostrar** un indicador de carga con mensaje descriptivo
4. **Mantener** el bloqueo durante todo el proceso (upload + validación + procesamiento)
5. **Ocultar** el modal solo cuando la respuesta del backend llegue (éxito o error)

### 0.6.2 Implementación Recomendada

#### Opción A: Modal de Carga Global (Recomendado)

```tsx
// Componente: LoadingOverlay.tsx
import React from 'react';
import './LoadingOverlay.css';

interface LoadingOverlayProps {
  isVisible: boolean;
  message?: string;
}

export const LoadingOverlay: React.FC<LoadingOverlayProps> = ({ 
  isVisible, 
  message = "Procesando plantilla Excel..." 
}) => {
  if (!isVisible) return null;

  return (
    <div className="loading-overlay">
      <div className="loading-modal">
        <div className="loading-spinner"></div>
        <p className="loading-message">{message}</p>
        <p className="loading-subtitle">Por favor, no cierre esta ventana</p>
      </div>
    </div>
  );
};
```

```css
/* LoadingOverlay.css */
.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999; /* Máxima prioridad */
  backdrop-filter: blur(4px);
}

.loading-modal {
  background: white;
  border-radius: 12px;
  padding: 2rem;
  min-width: 300px;
  text-align: center;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-message {
  font-size: 1.1rem;
  font-weight: 600;
  color: #333;
  margin: 0.5rem 0;
}

.loading-subtitle {
  font-size: 0.9rem;
  color: #666;
  margin: 0.5rem 0 0;
}
```

#### Opción B: Usando un Store/Context Global

```tsx
// Store: useLoadingStore.ts (Pinia/Zustand/Context)
import { create } from 'zustand';

interface LoadingState {
  isUploading: boolean;
  uploadMessage: string;
  setUploading: (isUploading: boolean, message?: string) => void;
}

export const useLoadingStore = create<LoadingState>((set) => ({
  isUploading: false,
  uploadMessage: '',
  setUploading: (isUploading, message = '') => 
    set({ isUploading, uploadMessage: message }),
}));
```

#### Uso en el Componente de Carga

```tsx
// Componente: PedidoHeaderActions.vue o equivalente
import { useState } from 'react';
import { LoadingOverlay } from '@/components/LoadingOverlay';
import { useLoadingStore } from '@/stores/useLoadingStore';

export const PedidoHeaderActions = () => {
  const [file, setFile] = useState<File | null>(null);
  const { isUploading, setUploading } = useLoadingStore();

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    try {
      // 1. ACTIVAR BLOQUEO INMEDIATAMENTE
      setUploading(true, 'Cargando plantilla Excel...');

      const formData = new FormData();
      formData.append('file', file);

      // 2. Realizar petición
      const response = await fetch('/api/plantillas/upload', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Error al cargar plantilla');
      }

      // 3. ÉXITO: Ocultar modal y mostrar mensaje
      setUploading(false);
      // Mostrar notificación de éxito
      showSuccessNotification('Plantilla cargada exitosamente');

    } catch (error) {
      // 4. ERROR: Ocultar modal y mostrar error
      setUploading(false);
      showErrorNotification(error.message || 'Error al procesar plantilla');
    }
  };

  return (
    <>
      {/* Modal de carga - se muestra sobre TODO */}
      <LoadingOverlay 
        isVisible={isUploading} 
        message="Procesando plantilla Excel..."
      />

      {/* Resto de la interfaz */}
      <div className="pedido-header-actions">
        <input
          type="file"
          accept=".xlsx,.xls"
          onChange={handleFileChange}
          disabled={isUploading} // Deshabilitar input durante carga
        />
        <button 
          onClick={handleUpload}
          disabled={!file || isUploading} // Deshabilitar botón durante carga
        >
          Cargar Plantilla Excel
        </button>
        
        {/* Otros botones también deshabilitados */}
        <button disabled={isUploading}>Redistribuir</button>
        <button disabled={isUploading}>Exportar</button>
        <button disabled={isUploading}>Confirmar</button>
      </div>
    </>
  );
};
```

### 0.6.3 Mensajes de Carga por Etapa (Opcional)

Si quieres mostrar diferentes mensajes según la etapa del proceso:

```tsx
const handleUpload = async () => {
  setUploading(true, 'Subiendo archivo...');
  
  // Simular diferentes etapas
  await new Promise(resolve => setTimeout(resolve, 500));
  setUploading(true, 'Validando estructura...');
  
  await new Promise(resolve => setTimeout(resolve, 500));
  setUploading(true, 'Procesando datos...');
  
  // Petición real
  const response = await fetch('/api/plantillas/upload', { ... });
  
  setUploading(false);
};
```

### 0.6.4 Prevención de Navegación (Opcional)

Para evitar que el usuario navegue o cierre la página durante la carga:

```tsx
import { useEffect } from 'react';

useEffect(() => {
  if (isUploading) {
    // Prevenir cierre de página
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = 'Hay una carga en progreso. ¿Estás seguro de que quieres salir?';
      return e.returnValue;
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }
}, [isUploading]);
```

### 0.6.5 Checklist de Implementación

- [ ] Modal/overlay que cubre toda la pantalla (z-index alto)
- [ ] Spinner o indicador de carga visible
- [ ] Mensaje descriptivo ("Procesando plantilla Excel...")
- [ ] Todos los botones deshabilitados durante la carga
- [ ] Input de archivo deshabilitado durante la carga
- [ ] Modal se oculta al recibir respuesta (éxito o error)
- [ ] Manejo de errores: ocultar modal y mostrar mensaje de error
- [ ] (Opcional) Prevenir navegación durante carga

### 0.6.6 Ejemplo Vue.js (si usas Vue)

```vue
<template>
  <div>
    <!-- Modal de carga -->
    <div v-if="isUploading" class="loading-overlay">
      <div class="loading-modal">
        <div class="loading-spinner"></div>
        <p class="loading-message">{{ uploadMessage }}</p>
        <p class="loading-subtitle">Por favor, no cierre esta ventana</p>
      </div>
    </div>

    <!-- Interfaz principal -->
    <div class="pedido-header-actions">
      <input
        type="file"
        accept=".xlsx,.xls"
        @change="handleFileChange"
        :disabled="isUploading"
      />
      <button 
        @click="handleUpload"
        :disabled="!file || isUploading"
      >
        Cargar Plantilla Excel
      </button>
      
      <button :disabled="isUploading">Redistribuir</button>
      <button :disabled="isUploading">Exportar</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

const file = ref<File | null>(null);
const isUploading = ref(false);
const uploadMessage = ref('Procesando plantilla Excel...');

const handleFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  file.value = target.files?.[0] || null;
};

const handleUpload = async () => {
  if (!file.value) return;

  try {
    isUploading.value = true;
    uploadMessage.value = 'Cargando plantilla Excel...';

    const formData = new FormData();
    formData.append('file', file.value);

    const response = await fetch('/api/plantillas/upload', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Error al cargar plantilla');
    }

    // Éxito
    isUploading.value = false;
    // Mostrar notificación de éxito

  } catch (error) {
    // Error
    isUploading.value = false;
    // Mostrar notificación de error
  }
};
</script>
```

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

**Autenticación:** JWT token requerido  
**Permiso:** `mba3-consultas.proceso.execute`

**Query Parameters:**
- `oc_id` (opcional, múltiple): UUID de la orden de compra. Puede especificarse múltiples veces.
- `referencia_despacho` (opcional, múltiple): Número de factura/despacho. Puede especificarse múltiples veces.
- Si no se proporciona ningún parámetro, procesa la primera OC pendiente.

**Comportamiento:**
1. Obtiene distribución confirmada del pedido (por tienda)
2. Crea Inventory Transfer Request por cada tienda en SAP
3. Retorna información detallada de cada transferencia

**Estructura de Respuesta:**
```json
{
  "status": "success" | "partial" | "error",
  "message": "ODC enviada exitosamente a SAP (DocNum: 17098)",
  "metadata": {
    "enviadas": 1,
    "errores": 0,
    "total_procesadas": 1,
    "detalles": [
      {
        "oc_id": "uuid-de-oc",
        "proveedor": "P1790389219001",
        "success": true,
        "doc_entry": 123,
        "doc_num": 17098,
        "referencia_despacho": "900125353",
        "error": null,
        "error_message": null,
        "error_code": null,
        "error_source": null,
        "sap_response": { /* respuesta completa de SAP */ },
        "solicitudes_transferencia": {
          "success": true,
          "total_tiendas": 3,
          "transferencias_creadas": 3,
          "transferencias_errores": 0,
          "resultados": [
            {
              "tienda_id": "uuid-tienda",
              "tienda_codigo": "TOUT-CEN",
              "tienda_nombre": "TRANSITORIA DESCUENTON CENTRO HISTORICO",
              "success": true,
              "doc_entry": 456,
              "doc_num": 17100,
              "error": null
            }
          ]
        }
      }
    ]
  }
}
```

**Notas importantes:**
- El campo `solicitudes_transferencia` está dentro de cada elemento del array `metadata.detalles[]`
- Si se procesan múltiples OCs, `detalles` tendrá un elemento por cada OC
- El campo `tienda_nombre` puede ser `null` si no se pudo obtener de SAP

### 1.2 Listado de Pedidos con Filtros (HU-02, HU-07)

**Descripción:** Pantalla de visualización y seguimiento de pedidos con múltiples filtros y paginación.

**Endpoint:** `GET /api/pedidos`

**Autenticación:** JWT token requerido  
**Permiso:** `mba3-consultas.facturas.view`

**Query Parameters:**
- `estado` (string, opcional) - Filtrar por estado (ej: "PENDIENTE_CONFIRMACION_PROVEEDOR", "CONFIRMADO_PROVEEDOR")
- `fecha_desde` (string, opcional) - Filtrar desde fecha (YYYY-MM-DD)
- `fecha_hasta` (string, opcional) - Filtrar hasta fecha (YYYY-MM-DD)
- `proveedor_nombre` (string, opcional) - Búsqueda parcial por nombre de proveedor
- `numero_pedido` (string, opcional) - Búsqueda parcial por número de pedido
- `creado_por` (string, opcional) - Filtrar por usuario que creó el pedido
- `limit` (int, default: 50) - Límite de registros por página
- `offset` (int, default: 0) - Offset para paginación

**Ejemplos:**
```
GET /api/pedidos?estado=PENDIENTE_CONFIRMACION_PROVEEDOR&limit=20&offset=0
GET /api/pedidos?fecha_desde=2025-01-01&fecha_hasta=2025-01-31&proveedor_nombre=RAYO
```

**Estructura de Respuesta:**
```json
{
  "status": "success",
  "data": [
    {
      "pedido_id": "uuid-del-pedido",
      "numero_pedido": "P-12.48 - 12 - 2025",
      "fecha_pedido": "2025-01-21",
      "proveedor_nombre": "TEXTILES EL RAYO S.A.",
      "estado": "PENDIENTE_CONFIRMACION_PROVEEDOR",
      "creado_por": "usuario@example.com",
      "fecha_creacion": "2025-01-21T10:30:00",
      /* ... otros campos del pedido ... */
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

### 1.3 Pedidos para Redistribución y “último pedido” (misma lógica que cargar-plantilla)

**Rutas de la interfaz Redistribución:**

- **Entrada (sin pedido):** `http://localhost:3000/mba3-consultas/redistribucion`  
  Aquí se muestra el **input de búsqueda** donde el usuario puede ingresar el número del pedido. Si no se hace nada más, el usuario tiene que buscar manualmente.
- **Vista de un pedido:** `http://localhost:3000/mba3-consultas/pedidos/{numero_pedido}/redistribucion`  
  Ejemplo: `http://localhost:3000/mba3-consultas/pedidos/P-12.24%20-%2012%20-%202025/redistribucion`. En esta URL se visualiza la información de redistribución de ese pedido.

**Requerimiento:** Cuando el usuario haga clic en **“Redistribución”**, entra en `http://localhost:3000/mba3-consultas/redistribucion`. Se debe usar **la misma lógica que en cargar-plantilla** (`/mba3-consultas/cargar-plantilla/{numero_pedido}`): al entrar sin número de pedido, **cargar el último pedido que corresponda** y, si existe, **redirigir de inmediato** a `http://localhost:3000/mba3-consultas/pedidos/{numero_pedido}/redistribucion`. Para Redistribución, ese “último” debe ser solo pedidos con estado **`RESPUESTA_PROVEEDOR_CARGADA`** (listos para redistribuir).

**Comportamiento esperado:**

- En `http://localhost:3000/mba3-consultas/redistribucion` (sin `{numero_pedido}`), al montar la vista se debe llamar a **`GET /api/pedidos/ultimo-redistribucion`** (misma idea que `GET /api/plantillas/ultimo` en cargar-plantilla). Si la respuesta trae un pedido, tomar su `numero_pedido` y hacer `router.replace('/mba3-consultas/pedidos/' + encodeURIComponent(numero_pedido) + '/redistribucion')`. Así el usuario ve de inmediato el último pedido con estado `RESPUESTA_PROVEEDOR_CARGADA` sin buscarlo.
- Sigue siendo válido **búsqueda por número de pedido** (input): el usuario escribe el número, se busca y se redirige a `/pedidos/{numero_pedido}/redistribucion`.
- Opcional: para mostrar una **lista** de pedidos en esa pantalla se puede usar `GET /api/pedidos/confirmados` (véase más abajo). La redirección automática al “último” se hace con `GET /api/pedidos/ultimo-redistribucion`.

**Endpoint “último pedido para redistribución” (recomendado al entrar en `/redistribucion`):** `GET /api/pedidos/ultimo-redistribucion`

Misma lógica que `GET /api/plantillas/ultimo` en cargar-plantilla, pero devuelve solo el último pedido con estado **`RESPUESTA_PROVEEDOR_CARGADA`**.

**Autenticación:** JWT token requerido  
**Permiso:** `mba3-consultas.facturas.view`

**Query Parameters:**
- `solo_usuario` (bool, default: `true`) - Si `true`, último pedido RESPUESTA_PROVEEDOR_CARGADA del usuario autenticado; si `false`, último en todo el sistema.

**Respuesta:** Objeto con cabecera básica (`pedido_id`, `numero_pedido`, `estado`, `fecha_pedido`, etc.) o **`null`** si no hay ninguno en ese estado.

**Ejemplo de uso en el front (al montar `/redistribucion` sin `{numero_pedido}`):**
```text
GET /api/pedidos/ultimo-redistribucion
```
Si la respuesta es un objeto con `numero_pedido`, hacer  
`router.replace('/mba3-consultas/pedidos/' + encodeURIComponent(numero_pedido) + '/redistribucion')`.

---

**Endpoint para listar pedidos confirmados (lista opcional en Redistribución):** `GET /api/pedidos/confirmados`

**Autenticación:** JWT token requerido  
**Permiso:** `mba3-consultas.facturas.view`

**Query Parameters (contrato backend/frontend):**
- `page` (int, default: 1) - Número de página.
- `pageSize` o `page_size` (int, default: 50, max: 100) - Tamaño de página. El front suele enviar `pageSize`.
- `redistribucion_confirmada` (opcional) - Si vale `"true"`, el backend devuelve solo pedidos con **redistribución ya confirmada** (estado `CONFIRMADO REDISTRIBUCION`). Si no se envía o es `"false"`, devuelve pedidos en `CONFIRMADO_PROVEEDOR` o `CONFIRMADO REDISTRIBUCION`.

**Ejemplos de URL:**
- Lista para pantalla Redistribución (opcional):  
  `GET /api/pedidos/confirmados?page=1&pageSize=20&redistribucion_confirmada=true`
- Solo el último confirmado (alternativa si no se usa `ultimo-redistribucion`):  
  `GET /api/pedidos/confirmados?page=1&pageSize=1`

**Formato de respuesta (lo que devuelve el backend y debe consumir el front):**
```json
{
  "status": "success",
  "data": [
    {
      "cabecera": {
        "pedido_id": "uuid",
        "numero_pedido": "P-12.24 - 12 - 2025",
        "fecha_pedido": "2025-01-24",
        "estado": "CONFIRMADO REDISTRIBUCION",
        "proveedor_nombre": "...",
        "creado_por": "...",
        "creado_en": "..."
      },
      "pedido_id": "uuid",
      "numero_pedido": "P-12.24 - 12 - 2025",
      "fecha_pedido": "2025-01-24",
      "estado": "CONFIRMADO REDISTRIBUCION"
    }
  ],
  "total": 5,
  "page": 1,
  "pageSize": 20,
  "totalPages": 1
}
```
Cada elemento de `data` incluye `cabecera` (con `numero_pedido`, `fecha_pedido`, `estado`, etc.) para que el front pueda usar `cabecera.numero_pedido` y armar la lista o el detalle en `/mba3-consultas/redistribucion`.

**Pasos concretos:**

1. **Usuario hace clic en “Redistribución”** → la app navega a `http://localhost:3000/mba3-consultas/redistribucion` (ruta sin id).
2. **En esa ruta (p. ej. en `onMounted`):**  
   - Mostrar “Buscando último pedido…” (o similar) mientras se consulta.  
   - Llamar a **`GET /api/pedidos/ultimo-redistribucion`** (misma lógica que `GET /api/plantillas/ultimo` en cargar-plantilla; aquí solo pedidos con estado `RESPUESTA_PROVEEDOR_CARGADA`).  
   - Si la respuesta es un objeto con `numero_pedido`, hacer  
     `router.replace('/mba3-consultas/pedidos/' + encodeURIComponent(numero_pedido) + '/redistribucion')`.  
     Usar `encodeURIComponent(numero_pedido)` para que espacios y guiones se codifiquen bien en la URL (p. ej. `P-12.24 - 12 - 2025` → `P-12.24%20-%2012%20-%202025`).  
   - Tras el `replace`, la URL pasa a ser `http://localhost:3000/mba3-consultas/pedidos/P-12.24%20-%2012%20-%202025/redistribucion` y la vista carga ese pedido (p. ej. con `loadPedido()` o un `watch` de `route.params.id`), mostrando la información del último pedido con `RESPUESTA_PROVEEDOR_CARGADA`.
3. **Si la respuesta es `null` o falla la llamada:** permanecer en `/mba3-consultas/redistribucion` con el input de búsqueda; el usuario puede buscar por número de pedido y, al enviar la búsqueda, la app redirige a `/mba3-consultas/pedidos/{numero_pedido}/redistribucion` para visualizarlo.
4. **Si el usuario ya está en** `http://localhost:3000/mba3-consultas/pedidos/{numero_pedido}/redistribucion` (p. ej. por enlace o tras la redirección): cargar ese pedido como siempre; no volver a llamar al endpoint de último pedido.

**Resumen:** Clic en “Redistribución” → entra en `/mba3-consultas/redistribucion` → se llama a **`GET /api/pedidos/ultimo-redistribucion`** → si hay último pedido con `RESPUESTA_PROVEEDOR_CARGADA`, `router.replace` a `/mba3-consultas/pedidos/{numero_pedido}/redistribucion` (con `encodeURIComponent`) → el usuario ve de inmediato ese pedido en esa URL.

### 1.3.1 Gestión del botón "Confirmar Redistribución"

En la pantalla de redistribución (`/mba3-consultas/pedidos/{numero_pedido}/redistribucion`), el botón **"Confirmar Redistribución"** debe deshabilitarse en dos casos:

1. **Mientras se procesa el clic** — para evitar doble envío y dar feedback.
2. **Cuando la redistribución ya está confirmada** — según el estado del pedido (`cabecera.estado`).

**Endpoint a usar:** `POST /api/pedidos/{numero_pedido}/redistribucion/confirmar`

- **Método:** POST  
- **Body:** `RedistribucionConfirmarRequest` (p. ej. `{ "ajustes_detalle": [ ... ] }`).  
- **Respuesta exitosa:** incluye `status: "success"`, `numero_pedido`, `message`, etc. El backend actualiza el estado del pedido a **`CONFIRMADO REDISTRIBUCION`**.

**Comportamiento en el frontend:**

| Acción | Comportamiento |
|--------|----------------|
| **Al hacer clic en "Confirmar Redistribución"** | Enviar `POST /api/pedidos/{numero_pedido}/redistribucion/confirmar` con el body correspondiente. **Deshabilitar el botón de inmediato** y mostrar indicador de carga (p. ej. texto "Confirmando…" o spinner). |
| **Si la petición es exitosa** | Actualizar el estado local del pedido con el nuevo `estado` (p. ej. `CONFIRMADO REDISTRIBUCION`) o recargar el pedido desde el backend. **Mantener el botón deshabilitado** (la redistribución ya está confirmada). |
| **Si la petición falla** | Mostrar mensaje de error y **volver a habilitar el botón** para que el usuario pueda reintentar. |

**Cuándo deshabilitar el botón "Confirmar Redistribución" (al cargar la vista o tras recargar):**

Deshabilitar cuando el estado del pedido indica que la redistribución ya está confirmada. Usar el campo **`cabecera.estado`** del pedido cargado en esa pantalla:

- `CONFIRMADO REDISTRIBUCION` (o `PEDIDO_CONFIRMADO` por compatibilidad) → redistribución ya confirmada; deshabilitar.
- Cualquier estado posterior (p. ej. `PROCESADO_SAP`, `CONFIRMADO_ENVIADO`, etc.) → deshabilitar.

**Resumen de implementación:**

- **Al cargar la vista:** Deshabilitar el botón si `cabecera.estado === 'CONFIRMADO REDISTRIBUCION'` o `cabecera.estado === 'PEDIDO_CONFIRMADO'` (o estado posterior).
- **Al hacer clic:** Deshabilitar de inmediato y mostrar "Confirmando…" (o spinner); llamar a `POST /api/pedidos/{numero_pedido}/redistribucion/confirmar`.
- **Si la petición tiene éxito:** Actualizar estado (o recargar pedido) y dejar el botón deshabilitado.
- **Si la petición falla:** Rehabilitar el botón y mostrar el error.

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
  pedido_detalle_id: string;
  codigo_interno: string;
  descripcion_producto: string | null;  // ⭐ Descripción del producto desde SAP
  item_code_sap: string | null;
  pack_sap: string | null;
  unidad_conversion: number | null;
  unidad_sap: string | null;  // ⭐ Unidad SAP (ej: "PACK", "UN")
  cantidad_original: number | null;
  cantidad_sap: number | null;
  precio_unitario_original: number | null;
  precio_unitario_sap: number | null;
  total_linea_original: number | null;
  total_linea_sap: number | null;
  producto_homologado: boolean;
  tipo_problema: string | null;  // ⭐ "no_existe", "mismatch", "error", o null
  item_code_sap_encontrado: string | null;  // ⭐ ItemCode encontrado en SAP (para mismatch)
  mensaje_error: string | null;  // ⭐ Mensaje de error si hubo problema
  fecha_procesamiento: string | null;  // ⭐ Fecha de procesamiento (ISO 8601)
  procesado_por: string | null;  // ⭐ Usuario que procesó
}

interface EstadisticasProcesamientoSAP {
  total_productos: number;
  productos_homologados: number;
  productos_no_homologados: number;
  productos_con_error: number;
  total_cantidad_original: number | null;
  total_cantidad_sap: number | null;
  total_precio_original: number | null;
  total_precio_sap: number | null;
}
```

### Campo Nuevo: `descripcion_producto`

El campo `descripcion_producto` ahora está disponible en la respuesta y puede ser:
- ✅ `string` - Descripción del producto
- ❌ `null` - Si no se encontró en SAP

---

## ✅ Estado

Todas las funcionalidades están implementadas en backend y listas para integración con frontend.
