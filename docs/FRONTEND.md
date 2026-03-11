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

#### 0.5.7.4 Botón "Listado Pedidos Originales" — permiso `mabel.view`

El botón **"Listado Pedidos Originales"** en la sección **"Información ODC"** permite a los usuarios ver, descargar y eliminar los archivos Excel originales que han subido al sistema.

**Reglas exactas:**

- La capability `can_view_plantillas_originales` es `true` si el usuario tiene el permiso `mabel.view` o es admin.
- El botón **solo debe mostrarse** si `capabilities.can_view_plantillas_originales === true`.
- Al hacer clic, debe abrir un modal/vista con el listado de archivos Excel originales del usuario.

**Mapeo:**

| Permiso       | Capability                      | Botón                        |
|---------------|---------------------------------|------------------------------|
| `mabel.view`  | `can_view_plantillas_originales`| Listado Pedidos Originales   |

**Implementación en frontend:**

```tsx
{capabilities.can_view_plantillas_originales && (
  <Button onClick={handleOpenListadoOriginales}>
    Listado Pedidos Originales
  </Button>
)}
```

**Endpoints disponibles:**

1. **`GET /api/plantillas/archivos`** - Lista archivos Excel originales del usuario
   
   **Query Parameters:**
   - `limit` (int, default: 50) - Cantidad máxima de archivos
   - `solo_activos` (bool, default: true) - Solo mostrar archivos activos

   **Respuesta:**
   ```json
   {
     "status": "success",
     "data": [
       {
         "archivo_id": 1,
         "pedido_id": "uuid-del-pedido",
         "numero_pedido": "P-12.08 - 12 - 2025",
         "nombre_original": "plantilla_enero.xlsx",
         "tamaño_bytes": 45678,
         "tamaño_mb": 0.04,
         "subido_por": "usuario@empresa.com",
         "fecha_subida": "2025-01-21T10:30:00",
         "activo": true,
         "descargas": 3,
         "ultima_descarga": "2025-01-22T15:00:00",
         "url_descarga": "/api/plantillas/{pedido_id}/descargar-original"
       }
     ],
     "metadata": {
       "total": 15,
       "limit": 50,
       "storage_habilitado": true
     }
   }
   ```

2. **`GET /api/plantillas/{pedido_id}/descargar-original`** - Descarga el archivo Excel
   - Retorna el archivo como `StreamingResponse` con headers de descarga

3. **`DELETE /api/plantillas/archivos/{archivo_id}`** - Elimina un archivo
   
   **Query Parameters:**
   - `eliminar_fisicamente` (bool, default: false) - Si es true, elimina también del storage MinIO

   **Respuesta:**
   ```json
   {
     "status": "success",
     "message": "Archivo eliminado correctamente",
     "archivo_id": 123,
     "nombre_archivo": "plantilla.xlsx",
     "eliminacion_fisica": false
   }
   ```

**Interfaz del modal/vista sugerida:**

```tsx
// Componente ListadoPedidosOriginales
function ListadoPedidosOriginales({ isOpen, onClose }) {
  const [archivos, setArchivos] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    if (isOpen) {
      fetchArchivos();
    }
  }, [isOpen]);
  
  const fetchArchivos = async () => {
    setLoading(true);
    const response = await fetch('/api/plantillas/archivos');
    const data = await response.json();
    setArchivos(data.data);
    setLoading(false);
  };
  
  const handleDescargar = (pedidoId) => {
    window.open(`/api/plantillas/${pedidoId}/descargar-original`, '_blank');
  };
  
  const handleEliminar = async (archivoId) => {
    if (confirm('¿Estás seguro de eliminar este archivo?')) {
      await fetch(`/api/plantillas/archivos/${archivoId}`, { method: 'DELETE' });
      fetchArchivos(); // Recargar lista
    }
  };
  
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Listado Pedidos Originales">
      {loading ? (
        <Spinner />
      ) : archivos.length === 0 ? (
        <p>No hay archivos Excel originales disponibles.</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <th>Pedido</th>
              <th>Archivo</th>
              <th>Tamaño</th>
              <th>Fecha</th>
              <th>Descargas</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {archivos.map(archivo => (
              <tr key={archivo.archivo_id}>
                <td>{archivo.numero_pedido}</td>
                <td>{archivo.nombre_original}</td>
                <td>{archivo.tamaño_mb} MB</td>
                <td>{formatDate(archivo.fecha_subida)}</td>
                <td>{archivo.descargas}</td>
                <td>
                  <Button onClick={() => handleDescargar(archivo.pedido_id)}>
                    📥 Descargar
                  </Button>
                  <Button onClick={() => handleEliminar(archivo.archivo_id)} variant="danger">
                    🗑️ Eliminar
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Modal>
  );
}
```

**Comportamiento esperado:**

- Usuario con `mabel.view` → ve el botón "Listado Pedidos Originales" en la sección Información ODC.
- Usuario sin `mabel.view` → no ve el botón.
- Solo se muestran los archivos subidos por el usuario autenticado.
- El usuario puede descargar cualquier archivo de su lista.
- El usuario puede eliminar cualquier archivo de su lista (soft delete por defecto).

#### 0.5.7.5 Botón "Descargar Pedido Original" — datos originales sin ediciones

El botón **"Descargar Pedido Original"** en la pantalla de detalle del pedido permite descargar un archivo Excel (.xlsx) con los **valores originales** del pedido, tal como fueron enviados desde la pantalla de cargar-plantilla (botón "Enviar"), **antes de cualquier edición** de COSTO UNIT., TOTAL, COMENTARIO o FECHA DE ENTREGA.

**Diferencia con "Descargar Pedido":**
- **"Descargar Pedido"**: genera el Excel con los valores **actuales** (posiblemente editados).
- **"Descargar Pedido Original"**: genera el Excel con los valores **originales** (inmutables desde el envío).

**Endpoint:** `GET /api/pedidos/{pedido_id}/descargar-pedido-original`

- **Método:** GET
- **URL:** `/api/pedidos/{pedido_id}/descargar-pedido-original` (usar `cabecera.pedido_id`).
- **Autenticación:** JWT en header `Authorization: Bearer {token}`.
- **Permisos:** `mabel.view` o `odcsap.view`.

**Respuestas:**
- **200**: Archivo Excel (.xlsx) descargado (nombre: `Descargar Pedido Original.xlsx`).
- **404** con `error: "not_found"`: Pedido no encontrado.
- **404** con `error: "sin_snapshot_original"`: El pedido existe pero no tiene snapshot original (fue creado antes de esta funcionalidad).

**Estructura del Excel descargado:**
- Logo ROLAND en celda B3
- Filas 1-4, columnas D-E: PEDIDO ROLAND NO., FECHA DE PEDIDO, FECHA DE ENTREGA (original), FORMA DE PAGO
- Filas 6-11, columnas D-E: MENSAJE, NOMBRE PROVEEDOR, COMPRADOR NOMBRE, COD COMPRADOR, ORIGEN TRASLADO, SERIE
- Fila 13: Encabezados de tabla (CODIGO INTERNO, MARCA, CODIGO DE BARRAS, DESCRIPCION SAP, PACK, PRECIO DE LISTA, DSCTO, PVP, TOTAL)
- Fila 14+: Datos de productos con valores originales
- Colores corporativos: labels con fondo #588894 y texto blanco

**Implementación en frontend:**

```tsx
const handleDescargarPedidoOriginal = (pedidoId: string) => {
  window.open(`/api/pedidos/${pedidoId}/descargar-pedido-original`, '_blank');
};

// Botón en la interfaz de detalle del pedido
<Button onClick={() => handleDescargarPedidoOriginal(cabecera.pedido_id)}>
  Descargar Pedido Original
</Button>
```

**Nota:** Solo los pedidos enviados después de la activación de esta funcionalidad tendrán snapshot original. Para pedidos anteriores, el endpoint devuelve 404 con `error: "sin_snapshot_original"`.

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

**Endpoints posibles:**

1. **`POST /api/pedidos/{pedido_id}/confirmar-para-redistribucion`** (usado por muchos frontends)
   - Cambia el estado de GESTIONAR PEDIDO a **CONFIRMADO** (`estado_id` 4).
   - **Respuesta 200:** devuelve el **pedido completo** (objeto con `cabecera`, `detalles`, etc.) ya con `cabecera.estado_id === 4` y `cabecera.estado === 'CONFIRMADO'`.
   - El frontend **debe** tomar esa respuesta y actualizar el pedido en memoria para que el botón "Confirmar" se deshabilite de inmediato.

2. **`POST /api/pedidos/{pedido_id}/crear-respuesta-desde-pedido`**
   - Toma los datos actuales del pedido (totales, costos, etc.), genera la respuesta del proveedor, la guarda y actualiza el estado a **CONFIRMADO** (id 4). Envía email a MABEL TRADING.
   - Respuesta: `status: "success"`, etc. Tras éxito, el frontend debe recargar el pedido o actualizar estado para deshabilitar el botón.

En ambos casos usar **`cabecera.pedido_id`** (UUID) en la URL. **Body:** ninguno (o vacío). **Autenticación:** JWT. **Permisos:** `odcsap.view` o `mabel.view` (confirmar-para-redistribucion); `mabel.view` (crear-respuesta-desde-pedido).

**Comportamiento en el frontend:**

| Acción | Comportamiento |
|--------|----------------|
| **Al hacer clic en "Confirmar"** | Enviar `POST /api/pedidos/{cabecera.pedido_id}/crear-respuesta-desde-pedido`. Mostrar indicador de carga (p. ej. botón deshabilitado + “Guardando…” o spinner). |
| **Si la petición es exitosa** | Actualizar el estado local del pedido con el nuevo `estado` (p. ej. `RESPUESTA_PROVEEDOR_CARGADA`) o recargar el pedido desde el backend. Deshabilitar el botón "Confirmar". Opcionalmente, según diseño: redirigir a la pantalla de redistribución del mismo pedido (como en el flujo anterior). |
| **Si la petición falla** | Mostrar mensaje de error, dejar el botón habilitado para reintentar. |

**Cuándo deshabilitar el botón "Confirmar":**

Deshabilitar (y no permitir nueva confirmación) **desde el estado CONFIRMADO en adelante**. Usar **`cabecera.estado_id`** o **`cabecera.estado`** del pedido cargado:

- **`CONFIRMADO`** (`estado_id === 4`) → pedido confirmado para redistribución; **deshabilitar**. (Es el estado que devuelve `POST .../confirmar-para-redistribucion`.)
- `RESPUESTA_PROVEEDOR_CARGADA` → respuesta ya guardada; deshabilitar.
- `CONFIRMADO_PROVEEDOR` → confirmación ya procesada; deshabilitar.
- `CONFIRMADO REDISTRIBUCION` (o `PEDIDO_CONFIRMADO` por compatibilidad) → redistribución ya confirmada; deshabilitar.
- Cualquier otro estado posterior (p. ej. `PROCESADO_SAP`, `CONFIRMADO_ENVIADO`, etc.) → deshabilitar.

**Condición recomendada en código:** deshabilitar si `cabecera.estado_id === 4` **o** `cabecera.estado === 'CONFIRMADO'` **o** cualquiera de los estados listados arriba (por id o por nombre).

**Tras hacer clic en "Confirmar":** Si el frontend usa `POST /api/pedidos/{pedido_id}/confirmar-para-redistribucion`, la respuesta **200** trae el **pedido completo** ya con estado CONFIRMADO (`estado_id` 4). El frontend **debe actualizar el pedido en memoria** con esa respuesta (reemplazar el objeto pedido o asignar `cabecera.estado_id` y `cabecera.estado` del body). Así el botón se deshabilita de inmediato al evaluar la condición anterior. Si no se actualiza el estado local con la respuesta, el botón seguirá habilitado.

**Resumen:**

- **Mostrar** el botón solo si `capabilities.can_confirm_pedido` (ya definido en 0.5.8).
- **Deshabilitar** el botón si `cabecera.estado_id === 4` o `cabecera.estado === 'CONFIRMADO'` o cualquier estado posterior (lista anterior).
- **Al hacer clic:** Llamar al endpoint de confirmar; **tras éxito, actualizar el pedido local con la respuesta del backend** (o recargar el pedido) para que el botón pase a deshabilitado.

**Al mismo tiempo que se deshabilita "Confirmar":** Las opciones de **editar** (COSTO UNIT., TOTAL, COMENTARIO) deben deshabilitarse también cuando el usuario hace clic en "Confirmar" (porque el estado pasa a CONFIRMADO). Véase 0.5.8.2.

### 0.5.8.2 Edición de COSTO UNIT., TOTAL y COMENTARIO (solo en GESTIONAR PEDIDO)

En la pantalla de detalle del pedido (`/mba3-consultas/pedidos/{id}`), los campos **COSTO UNIT.**, **TOTAL** y **COMENTARIO** de cada línea solo pueden **editarse cuando el pedido está en estado GESTIONAR PEDIDO** (`estado_id === 3` o `cabecera.estado === 'GESTIONAR PEDIDO'`).

- **Si el estado es GESTIONAR PEDIDO:** el usuario puede modificar esos campos (y el backend acepta los PATCH).
- **En cualquier otro estado** (CONFIRMADO, RESPUESTA_PROVEEDOR_CARGADA, CONFIRMADO REDISTRIBUCION, etc.): las celdas deben mostrarse **solo lectura** (deshabilitar inputs / no permitir edición). El backend rechazará con **400** y `error: "estado_no_editable"` si se intenta editar.

**Comportamiento requerido:**

1. **Al cargar la vista:** Si `cabecera.estado_id !== 3` (o `cabecera.estado !== 'GESTIONAR PEDIDO'`), deshabilitar la edición de COSTO UNIT., TOTAL y COMENTARIO en toda la tabla. El usuario puede volver a entrar a este pedido más tarde; si ya está confirmado, las celdas deben seguir en solo lectura.
2. **Al hacer clic en "Confirmar":** En el mismo momento en que se deshabilita el botón "Confirmar", **deshabilitar también** las opciones de editar (COSTO UNIT., TOTAL, COMENTARIO), porque el estado pasa a CONFIRMADO. Actualizar el pedido en memoria con la respuesta para que la condición "solo editable en GESTIONAR PEDIDO" haga que las celdas queden en solo lectura.

**Condición en código:** habilitar edición solo si `cabecera.estado_id === 3` (o `cabecera.estado === 'GESTIONAR PEDIDO'`). En cualquier otro estado, no permitir edición.

### 0.5.9 Marcar como "Despachar y Facturar" (detalle del pedido)

En la pantalla `/mba3-consultas/pedidos/{id}` (detalle del pedido), cuando el pedido está en estado **Confirmado y Enviado** (ODC enviada a SAP, solicitudes de transferencia generadas; en BD el pedido tiene `estado_id` = 12 / `estado` = `CONFIRMADO_ENVIADO`), el usuario puede marcar manualmente el pedido como **"Despachar y Facturar"** (estado indicativo, guardado en BD).

**Endpoint:** `POST /api/pedidos/{pedido_id}/marcar-despachar-y-facturar`

- **Método:** POST  
- **URL:** `/api/pedidos/{pedido_id}/marcar-despachar-y-facturar` (usar `cabecera.pedido_id`).  
- **Body:** ninguno.  
- **Autenticación:** JWT en header `Authorization: Bearer {token}`.  
- **Permisos:** `odcsap.view` o `mabel.view`.

**Condición:** Solo se permite si el pedido está en estado **Confirmado y Enviado** (`cabecera.estado_id === 12` o `cabecera.estado === 'CONFIRMADO_ENVIADO'`). Si no, el backend responde **400** con `error: "estado_no_confirmado_enviado"`.

**Comportamiento en el frontend:**

- **Mostrar** el botón/acción "Despachar y Facturar" solo cuando `cabecera.estado_id === 12` (o `cabecera.estado === 'CONFIRMADO_ENVIADO'`). No mostrarlo si el estado ya es "DESPACHAR Y FACTURAR" (`estado_id === 17`) u otro.
- **Al hacer clic:** Enviar `POST /api/pedidos/{cabecera.pedido_id}/marcar-despachar-y-facturar`. Tras éxito (200), actualizar estado local o recargar el pedido; el estado pasará a "DESPACHAR Y FACTURAR" (`estado_id` 17).

### 0.5.9.1 Botón "Finalizado" (solo en cargar-plantilla P-12.01 - 12 - 2025)

El botón **"Finalizado"** depende del estado **"Despachar y Facturar"**: solo debe mostrarse cuando el pedido tiene `estado_id === 17` (DESPACHAR Y FACTURAR) y **únicamente** en la interfaz de **cargar plantilla** para la plantilla **P-12.01 - 12 - 2025**.

- **Ruta donde debe aparecer el botón:**  
  `http://localhost:3000/mba3-consultas/cargar-plantilla/P-12.01%20-%2012%20-%202025`  
  Es decir: ruta base `/mba3-consultas/cargar-plantilla/{numero_pedido}` con `numero_pedido` = **"P-12.01 - 12 - 2025"** (URL decodificado). En ninguna otra pantalla ni en otras plantillas debe mostrarse este botón.

- **Endpoint:** `POST /api/pedidos/{pedido_id}/marcar-finalizado`
  - **Método:** POST  
  - **URL:** `/api/pedidos/{pedido_id}/marcar-finalizado` (usar `cabecera.pedido_id`).  
  - **Body:** ninguno.  
  - **Autenticación:** JWT en header `Authorization: Bearer {token}`.  
  - **Permisos:** `odcsap.view` o `mabel.view`.

- **Condición backend:** Solo se permite si el pedido está en estado **Despachar y Facturar** (`cabecera.estado_id === 17`). Si no, el backend responde **400** con `error: "estado_no_despachar_y_facturar"`.

**Comportamiento en el frontend:**

- **Mostrar** el botón "Finalizado" **solo** cuando se cumplan **ambas** condiciones:
  1. La ruta actual es `/mba3-consultas/cargar-plantilla/P-12.01%20-%2012%20-%202025` (o el `numero_pedido` de la URL decodificado es exactamente `"P-12.01 - 12 - 2025"`).
  2. El pedido está en estado **Despachar y Facturar** (`cabecera.estado_id === 17`).
- **No mostrar** el botón en detalle de pedido (`/mba3-consultas/pedidos/{id}`), ni en otras plantillas, ni en redistribución, ni en ninguna otra interfaz.
- **Al hacer clic:** Enviar `POST /api/pedidos/{cabecera.pedido_id}/marcar-finalizado`. Tras éxito (200), actualizar estado local o recargar el pedido; el estado pasará a **"FINALIZADO"** (`estado_id` 18), que es el estado final del flujo.

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

### 0.5.12.2 Upload asíncrono (Celery): actualizar la interfaz al terminar

**Problema:** Si la carga de plantilla se hace con **Celery** (`POST /api/plantillas/upload-async`), el backend responde **202** con `process_id` y el resultado no está listo hasta que la tarea termina. Si el frontend no consulta el resultado ni actualiza la UI al terminar, **la información no se carga automáticamente** en `http://localhost:3000/mba3-consultas/cargar-plantilla`.

**Solución obligatoria en el frontend:**

1. Tras recibir **202** de `POST /api/plantillas/upload-async`, guardar `process_id`.
2. **Consultar el resultado** hasta que termine:
   - **Opción A (polling):** llamar `GET /api/plantillas/resultado/{process_id}` cada 1–2 s hasta que la respuesta tenga `status === 'completed'` o `status === 'error'`.
   - **Opción B (recomendada):** abrir **SSE** `GET /api/plantillas/stream/{process_id}` y reaccionar al evento donde `status === 'completed'` o `status === 'error'`.
3. **Cuando `status === 'completed`:**
   - Con **polling:** el cuerpo de `GET /api/plantillas/resultado/{process_id}` es directamente el resultado (incluye `numero_pedido`, `correcciones_aplicadas`, etc.).
   - Con **SSE:** el evento trae `resultado` con esos mismos campos.
   - A partir de ese resultado:
     - **Refrescar la lista de pedidos:** `GET /api/plantillas/pedidos` (para que el nuevo pedido aparezca en el contenedor "Pedidos").
     - **Navegar** a `/mba3-consultas/cargar-plantilla/{encodeURIComponent(numero_pedido)}` (con `replace: true`).
     - **Cargar los datos del pedido** en esa vista (p. ej. `GET /api/plantillas/ultimo` o `GET /api/pedidos/{id}` o el endpoint que use la página) para pintar la tabla.
   - Opcional: guardar `correcciones_aplicadas` en store o `sessionStorage` por `numero_pedido` para el resaltado de códigos corregidos (ver 0.5.12 / flujo async).
4. **Cuando `status === 'error':** mostrar el mensaje de error y, si viene `validacion_sap` / `error_data`, la UI de corrección de códigos si aplica.

**Ejemplo (polling) después de recibir 202:**

```tsx
// Tras response.status === 202 y data.process_id
const processId = data.process_id;

const pollResult = async (): Promise<{ status: string; numero_pedido?: string; [k: string]: unknown }> => {
  const res = await fetch(`/api/plantillas/resultado/${processId}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const body = await res.json();
  // Cuando status === 'completed', el cuerpo ES el resultado (numero_pedido, correcciones_aplicadas, etc.)
  if (body.status === 'completed') return body;
  if (body.status === 'error') return body;
  return body; // procesando, etc.
};

let result;
while (true) {
  result = await pollResult();
  if (result.status === 'completed' || result.status === 'error') break;
  await new Promise(r => setTimeout(r, 1500));
}

if (result.status === 'error') {
  showErrorNotification(result.message || result.error || 'Error al procesar plantilla');
  setUploading(false);
  return;
}

// Éxito: actualizar interfaz
const numeroPedido = result.numero_pedido;
await refetchListaPedidos(); // GET /api/plantillas/pedidos
navigate(`/mba3-consultas/cargar-plantilla/${encodeURIComponent(numeroPedido)}`, { replace: true });
await cargarDatosPedido(numeroPedido); // cargar detalle en esta vista
setUploading(false);
showSuccessNotification('Plantilla cargada exitosamente');
```

**Checklist para que la información se cargue automáticamente al terminar Celery:**

- [ ] Si se usa `upload-async`, no tratar la respuesta 202 como éxito con datos listos.
- [ ] Implementar polling a `GET /api/plantillas/resultado/{process_id}` o SSE `GET /api/plantillas/stream/{process_id}` hasta `completed`/`error`.
- [ ] Al recibir `completed`: refrescar lista de pedidos, navegar a `cargar-plantilla/{numero_pedido}` y cargar los datos del pedido en esa interfaz.

---

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
  "correcciones_aplicadas": [
    { "codigo_original": "R225.1012.BCO", "codigo_corregido": "R225.1012.BCO-SAP" }
  ],
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

- **`correcciones_aplicadas`**: Lista de objetos `{ codigo_original, codigo_corregido }` cuando el usuario eligió una sugerencia de código y envió el formulario con "Aplicar correcciones y continuar". Usar esta lista para **resaltar la celda del código de producto corregido** (p. ej. con un color distintivo como fondo verde claro o borde) en la tabla/grilla del detalle del pedido: localizar la fila cuyo código de producto coincide con `codigo_corregido` (o la que antes mostraba `codigo_original`) y aplicar una clase CSS (ej. `celda-codigo-corregido`) a esa celda.

**Forma del payload con upload asíncrono (Celery):** Si se usa **GET** `/api/plantillas/resultado/{process_id}` cuando `status === 'completed'`, el **cuerpo de la respuesta es directamente el resultado** (no hay clave `resultado` ni `result`). Por tanto `correcciones_aplicadas` está en el objeto raíz: `response.data.correcciones_aplicadas`. Si se usa **SSE** (`/api/plantillas/stream/{process_id}`), el evento tiene el resultado anidado: `event.resultado.correcciones_aplicadas`. Para el resaltado, usar `codigo_corregido` (con trim) en el Set y comparar con `detalle.codigo_interno` (también con trim).

#### Por qué se pierde el resaltado con upload asíncrono y cómo recuperarlo

Con **upload síncrono** (`POST /api/plantillas/upload`), la respuesta llega en la misma petición y el mismo componente puede llamar a `onUploadSuccess(response)` y rellenar el Set de códigos a resaltar; la tabla se pinta en la misma vista y el resaltado se ve.

Con **upload asíncrono** (Celery), el flujo es distinto:

1. Se sube el archivo → el backend devuelve `process_id` y la UI hace polling a **GET** `/api/plantillas/resultado/{process_id}` o escucha **SSE** `/api/plantillas/stream/{process_id}`.
2. Cuando `status === 'completed'`, la respuesta (GET) o el evento (SSE) traen el **mismo** objeto que en sync: `status`, `numero_pedido`, `correcciones_aplicadas`, etc.
3. Normalmente después se hace **redirect** a `/mba3-consultas/cargar-plantilla/{numero_pedido}` (o a pedidos).
4. La **nueva** página carga el pedido con **GET** `/api/plantillas/ultimo` o **GET** `/api/pedidos/{id}`. Esos endpoints devuelven el pedido (cabecera, detalle con `codigo_interno` ya corregido), pero **no** devuelven `correcciones_aplicadas`. Esa lista solo existe en la respuesta del upload (GET resultado o SSE).
5. Por tanto, en la vista de cargar-plantilla/pedido el Set de “códigos a resaltar” está vacío y el resaltado no se aplica.

**Qué hacer en el frontend para que el resaltado vuelva a verse (flujo async):**

- En el mismo sitio donde se recibe el resultado completado (por polling o SSE), **antes de hacer el redirect**:
  1. Extraer `correcciones_aplicadas` del payload (en GET es el cuerpo de la respuesta; en SSE es `event.resultado.correcciones_aplicadas`).
  2. Guardar esa lista en un **estado que sobreviva al redirect**:
     - **Opción A (recomendada):** Store global (Pinia/Vuex), por ejemplo `correccionesParaResaltadoPorPedido[numero_pedido] = correcciones_aplicadas`, o un store dedicado “último upload con correcciones” con `numero_pedido` y la lista.
     - **Opción B:** `sessionStorage` con clave por pedido, p. ej. `sessionStorage.setItem('resaltado_codigos_' + numero_pedido, JSON.stringify(correcciones_aplicadas))`.
  3. Llamar a la misma lógica que en sync rellena el Set de códigos a resaltar (p. ej. pasar el resultado a `onUploadSuccess` o a una función que actualice el store), de modo que el estado quede escrito **antes** del `router.push`.
- En la **vista de cargar-plantilla** (o detalle del pedido) que muestra la tabla:
  - Al montar o al recibir el pedido, leer del store (o de `sessionStorage`) las `correcciones_aplicadas` para ese `numero_pedido`.
  - Construir el Set de códigos a resaltar con los `codigo_corregido` (y `codigoCorregido`) haciendo **trim**.
  - En la celda del código interno usar la misma función que en sync, p. ej. `isCodigoCorregidoHighlight(detalle.codigo_interno)` comparando con ese Set (con trim).
- Opcional: limpiar el store o `sessionStorage` al salir de la ruta o tras un tiempo, para no resaltar en visitas posteriores al mismo pedido si no aplica.

El backend ya devuelve en GET resultado y en SSE el mismo formato que el upload síncrono, incluyendo siempre `correcciones_aplicadas` (array, vacío si no hubo correcciones). La diferencia es solo que ese dato llega en la respuesta del proceso async y no en la respuesta de “cargar pedido”; por eso el frontend debe **persistir** `correcciones_aplicadas` antes del redirect y **recuperarla** en la vista donde se pinta la tabla.

**Checklist de Implementación:**

- [ ] NO redirigir a `/mba3-consultas/pedidos/{numero_pedido}` después de cargar
- [ ] Permanecer en `/mba3-consultas/cargar-plantilla/{numero_pedido}` (o actualizar URL si no tiene el número de pedido)
- [ ] Usar `replace: true` al actualizar la URL para no crear una nueva entrada en el historial
- [ ] Mostrar notificación de éxito/error
- [ ] Opcional: Recargar datos del pedido en la misma interfaz si es necesario

**Nota:** Si el usuario quiere ver el detalle completo del pedido, puede hacer clic en un botón/link que lo lleve a `/mba3-consultas/pedidos/{numero_pedido}`, pero esto debe ser una acción explícita del usuario, no una redirección automática.

### 0.5.12.1 Listado de Pedidos en Cargar Plantilla (Contenedor "Pedidos")

**Ruta:** `http://localhost:3000/mba3-consultas/cargar-plantilla`

#### Endpoint para Listar Pedidos (incluye BORRADOR)

**⚠️ IMPORTANTE:** Para el contenedor "Pedidos" en la página cargar-plantilla, **NO usar** `GET /api/pedidos` ya que este endpoint excluye pedidos en estado BORRADOR.

**Usar:** `GET /api/plantillas/pedidos`

Este endpoint está diseñado específicamente para la página cargar-plantilla y **INCLUYE** pedidos en estado BORRADOR.

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `estado` | string | No | Filtrar por estado (ej: "BORRADOR", "NUEVO_PEDIDO") |
| `numero_pedido` | string | No | Búsqueda parcial por número de pedido |
| `limit` | int | No | Límite de resultados (default: 10, max: 100) |
| `offset` | int | No | Offset para paginación (default: 0) |

**Ejemplo de llamada:**
```javascript
GET /api/plantillas/pedidos?limit=10&offset=0
```

**Respuesta:**
```json
{
  "status": "success",
  "data": [
    {
      "pedido_id": "uuid",
      "numero_pedido": "P-12.08 - 12 - 2025",
      "fecha_pedido": "2025-01-21",
      "estado": "BORRADOR",
      "estado_id": 1,
      "proveedor_nombre": "TEXTILES EL RAYO S.A.",
      "creado_en": "2025-01-21T10:30:00"
    }
  ],
  "metadata": {
    "total": 5,
    "limit": 10,
    "offset": 0,
    "has_more": false
  }
}
```

**Diferencias con `GET /api/pedidos`:**

| Aspecto | `/api/pedidos` | `/api/plantillas/pedidos` |
|---------|---------------|---------------------------|
| Incluye BORRADOR | ❌ No | ✅ Sí |
| Filtra por usuario | ❌ No (todos los usuarios) | ❌ No (todos los usuarios) |
| Uso recomendado | Listado general de pedidos | Página cargar-plantilla |

**⚠️ NOTA:** Ambos endpoints muestran pedidos de **todos los usuarios** con permiso `mabel.view`. No hay filtrado automático por usuario para permitir visibilidad compartida de pedidos en equipos.

#### Implementación en Frontend

**Al cargar la página cargar-plantilla:**
```javascript
// Llamar al endpoint correcto para listar pedidos
const loadPedidos = async () => {
  try {
    const response = await fetch('/api/plantillas/pedidos?limit=10&offset=0', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    
    if (data.status === 'success') {
      setPedidos(data.data);
      setTotal(data.metadata.total);
    }
  } catch (error) {
    console.error('Error loading pedidos:', error);
  }
};

// Llamar al montar el componente
useEffect(() => {
  loadPedidos();
}, []);
```

### 0.5.12.2 Búsqueda por Número de Pedido en Cargar Plantilla

**Ruta:** `http://localhost:3000/mba3-consultas/cargar-plantilla`

En la sección **"Filtros de búsqueda"** de la página `cargar-plantilla`, el campo **"Número de Pedido"** debe permitir buscar pedidos de forma independiente, sin requerir otros filtros.

#### Endpoint de Búsqueda

**`GET /api/plantillas/buscar`**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `numero_pedido` | string | No | Texto a buscar (búsqueda parcial). Ej: `P-12.08`, `12 - 2025` |
| `limit` | int | No | Límite de resultados (default: 20, max: 100) |

**Comportamiento:**
- **Búsqueda parcial:** Si el usuario escribe `P-12.08`, el endpoint buscará pedidos cuyo `numero_pedido` contenga ese texto (ej: `P-12.08 - 12 - 2025`, `P-12.08 - 01 - 2026`).
- **Sin parámetro:** Si no se proporciona `numero_pedido`, devuelve los últimos pedidos.
- **Incluye BORRADOR:** A diferencia de otros endpoints, este incluye pedidos en estado BORRADOR (útil para cargar-plantilla).
- **Visibilidad compartida:** Muestra pedidos de **todos los usuarios** con permiso `mabel.view` (no filtra por usuario para permitir colaboración en equipo).

**Ejemplo de Respuesta:**
```json
{
  "status": "success",
  "data": [
    {
      "pedido_id": "AEDEC52D-D007-416F-8A09-9F0D31282EEE",
      "numero_pedido": "P-12.08 - 12 - 2025",
      "fecha_pedido": "2025-01-21",
      "estado": "BORRADOR",
      "estado_id": 1,
      "proveedor_nombre": "TEXTILES EL RAYO S.A.",
      "creado_en": "2025-01-21T10:30:00"
    }
  ],
  "total": 1,
  "query": "P-12.08"
}
```

#### Implementación en Frontend

**React/TypeScript:**
```tsx
const [searchQuery, setSearchQuery] = useState('');
const [searchResults, setSearchResults] = useState([]);
const [isSearching, setIsSearching] = useState(false);

// Debounced search function
const searchPedidos = useMemo(
  () => debounce(async (query: string) => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    
    setIsSearching(true);
    try {
      const params = new URLSearchParams({ numero_pedido: query.trim() });
      const response = await fetch(`/api/plantillas/buscar?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      
      if (data.status === 'success') {
        setSearchResults(data.data);
      }
    } catch (error) {
      console.error('Error searching pedidos:', error);
    } finally {
      setIsSearching(false);
    }
  }, 300),
  [token]
);

// Handle input change
const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  const value = e.target.value;
  setSearchQuery(value);
  searchPedidos(value);
};

// Handle selection
const handleSelectPedido = (pedido: any) => {
  const numeroPedido = pedido.numero_pedido;
  navigate(`/mba3-consultas/cargar-plantilla/${encodeURIComponent(numeroPedido)}`);
};
```

**Vue.js:**
```vue
<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useDebounceFn } from '@vueuse/core';

const router = useRouter();
const searchQuery = ref('');
const searchResults = ref([]);
const isSearching = ref(false);

const searchPedidos = useDebounceFn(async (query: string) => {
  if (!query.trim()) {
    searchResults.value = [];
    return;
  }
  
  isSearching.value = true;
  try {
    const params = new URLSearchParams({ numero_pedido: query.trim() });
    const response = await fetch(`/api/plantillas/buscar?${params}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    
    if (data.status === 'success') {
      searchResults.value = data.data;
    }
  } finally {
    isSearching.value = false;
  }
}, 300);

watch(searchQuery, (value) => searchPedidos(value));

const handleSelectPedido = (pedido: any) => {
  const numeroPedido = pedido.numero_pedido;
  router.push(`/mba3-consultas/cargar-plantilla/${encodeURIComponent(numeroPedido)}`);
};
</script>
```

#### Comportamiento Esperado

1. **Campo independiente:** El campo "Número de Pedido" debe buscar sin esperar que se llenen otros filtros.
2. **Búsqueda en tiempo real:** Al escribir, se debe hacer la búsqueda automáticamente (con debounce de ~300ms).
3. **Mostrar resultados:** Mostrar un dropdown/lista con los pedidos encontrados.
4. **Selección:** Al hacer clic en un resultado, navegar a `/mba3-consultas/cargar-plantilla/{numero_pedido}`.
5. **Formato de número:** El formato típico es `P-12.08 - 12 - 2025`. La búsqueda funciona con cualquier parte del número.

#### Checklist de Implementación

- [ ] Conectar el input "Número de Pedido" al endpoint `GET /api/plantillas/buscar`
- [ ] Implementar debounce (~300ms) para evitar múltiples llamadas
- [ ] Mostrar indicador de carga mientras se busca
- [ ] Mostrar dropdown/lista con resultados
- [ ] Al seleccionar, navegar a la URL con el `numero_pedido` (usar `encodeURIComponent`)
- [ ] El campo debe funcionar independientemente de otros filtros
- [ ] Manejar caso cuando no hay resultados (mostrar mensaje apropiado)

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

### 1.2.1 Estados para Filtros de Búsqueda (Dropdown de Estado)

**Descripción:** Endpoint para alimentar el dropdown/select del filtro **"Estado"** en el contenedor "Filtros de Búsqueda" de todas las interfaces de listas de pedidos. Devuelve los estados que el usuario realmente ve en la UI, consultados desde la tabla maestra `pedido_estado`.

**Endpoint:** `GET /api/pedidos/estados`

**Autenticación:** JWT token requerido  
**Permiso:** `odcsap.view` o `mabel.view`

**Query Parameters:**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `contexto` | string | No | Contexto de la vista para filtrar estados relevantes |

**Valores de `contexto`:**

| Valor | Comportamiento | Vista asociada |
|-------|---------------|----------------|
| *(sin valor)* | Todos los estados activos (incluye BORRADOR) | Uso general |
| `"pedidos"` | Excluye BORRADOR | `/mba3-consultas/pedidos` |
| `"cargar-plantilla"` | Todos los estados activos (incluye BORRADOR) | `/mba3-consultas/cargar-plantilla` |
| `"redistribucion"` | Solo estados del flujo de redistribución (4–14, sin CANCELADO ni finales) | `/mba3-consultas/redistribucion` |

**Ejemplos:**
```
GET /api/pedidos/estados
GET /api/pedidos/estados?contexto=pedidos
GET /api/pedidos/estados?contexto=redistribucion
```

**Respuesta:**
```json
{
  "status": "success",
  "data": [
    { "id": 1, "nombre": "BORRADOR", "orden": 1 },
    { "id": 2, "nombre": "NUEVO PEDIDO", "orden": 2 },
    { "id": 3, "nombre": "GESTIONAR PEDIDO", "orden": 3 },
    { "id": 4, "nombre": "CONFIRMADO POR EL RAYO", "orden": 4 },
    { "id": 5, "nombre": "RESPUESTA_PROVEEDOR_CARGADA", "orden": 5 },
    { "id": 6, "nombre": "CONFIRMADO_PROVEEDOR", "orden": 6 },
    { "id": 9, "nombre": "REDISTRIBUIDO", "orden": 9 },
    { "id": 10, "nombre": "CONFIRMADO REDISTRIBUCION", "orden": 10 },
    { "id": 12, "nombre": "CONFIRMADO_ENVIADO", "orden": 12 },
    { "id": 17, "nombre": "DESPACHAR Y FACTURAR", "orden": 17 },
    { "id": 18, "nombre": "FINALIZADO", "orden": 18 },
    { "id": 19, "nombre": "CANCELADO", "orden": 19 },
    { "id": 20, "nombre": "CANCELADO POR EL RAYO", "orden": 20 }
  ]
}
```

#### Implementación en Frontend

**Al montar el componente de filtros:**
```javascript
// Cargar estados disponibles para el dropdown
const loadEstados = async (contexto = 'pedidos') => {
  try {
    const params = contexto ? `?contexto=${contexto}` : '';
    const response = await fetch(`/api/pedidos/estados${params}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    
    if (data.status === 'success') {
      setEstados(data.data); // Array de { id, nombre, orden }
    }
  } catch (error) {
    console.error('Error loading estados:', error);
  }
};

// Llamar al montar con el contexto de la vista actual
useEffect(() => {
  loadEstados('pedidos'); // o 'redistribucion', 'cargar-plantilla'
}, []);
```

**En el select/dropdown de filtro:**
```html
<select v-model="filtroEstado" @change="aplicarFiltros">
  <option value="">Todos los estados</option>
  <option v-for="estado in estados" :key="estado.id" :value="estado.id">
    {{ estado.nombre }}
  </option>
</select>
```

**Al aplicar el filtro de estado, enviar `estado_id` (numérico) al endpoint de listado:**
```javascript
// Usar estado_id al filtrar
const params = new URLSearchParams();
if (filtroEstado) {
  params.set('estado', filtroEstado); // envía el id numérico
}
const response = await fetch(`/api/pedidos?${params}`, { ... });
```

#### Notas importantes

- **Nombres dinámicos:** Los nombres vienen de la tabla `pedido_estado` y pueden ser editados sin afectar lógica. El frontend debe usar siempre `estado.nombre` para mostrar, nunca hardcodear nombres.
- **Filtro por `id`:** Al filtrar pedidos, enviar el `id` numérico del estado (no el nombre) al endpoint `GET /api/pedidos`.
- **Cache recomendado:** Los estados no cambian frecuentemente; se recomienda cachear la respuesta en el frontend (ej: sessionStorage o estado global).

---

### 1.3 Pedidos para Redistribución y “último pedido” (misma lógica que cargar-plantilla)

**Rutas de la interfaz Redistribución:**

- **Entrada (sin pedido):** `http://localhost:3000/mba3-consultas/redistribucion`  
  Aquí se muestra el **input de búsqueda** donde el usuario puede ingresar el número del pedido. Si no se hace nada más, el usuario tiene que buscar manualmente.
- **Vista de un pedido:** `http://localhost:3000/mba3-consultas/pedidos/{numero_pedido}/redistribucion`  
  Ejemplo: `http://localhost:3000/mba3-consultas/pedidos/P-12.24%20-%2012%20-%202025/redistribucion`. En esta URL se visualiza la información de redistribución de ese pedido.
- **Vista solo lectura (EL RAYO):** `http://localhost:3000/mba3-consultas/pedidos/{numero_pedido}/redistribucion?soloLectura=1`  
  En esta interfaz **siempre** se debe visualizar la **última redistribución confirmada** (desde estado CONFIRMADO REDISTRIBUCION en adelante). Para ello, al cargar los datos se debe llamar a **`GET /api/pedidos/{numero_pedido}/redistribucion/inicial?solo_lectura=1`**. Si el pedido tiene redistribución confirmada, el backend devuelve esa redistribución guardada en el mismo formato que el resto del flujo; si no, devuelve los datos iniciales.

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

**Importante:** La redistribución solo se puede confirmar **una vez** por pedido. Tras el primer clic exitoso en "Confirmar Redistribución", el botón debe **deshabilitarse y permanecer deshabilitado** (no se permite confirmar de nuevo).

#### Flag del Backend: `puede_confirmar_redistribucion`

**⭐ NUEVO:** El backend ahora incluye un flag explícito `puede_confirmar_redistribucion` en la respuesta de los endpoints que devuelven datos del pedido:

- `GET /api/plantillas/{numero_pedido}`
- `GET /api/plantillas/ultimo`
- Otros endpoints que devuelven el pedido completo

**Respuesta del backend:**
```json
{
  "cabecera": { "estado_id": 4, "estado": "CONFIRMADO", ... },
  "detalles": [...],
  "puede_confirmar_redistribucion": true,  // ⭐ Usar este flag
  "puede_descartar": false,
  "puede_cancelar_pedido": true
}
```

**Estados que permiten confirmar redistribución (`puede_confirmar_redistribucion: true`):**
- `estado_id = 4` (REDISTRIBUCION / CONFIRMADO POR EL RAYO)
- `estado_id = 5` (RESPUESTA_PROVEEDOR_CARGADA)
- `estado_id = 6` (CONFIRMADO_PROVEEDOR)
- `estado_id = 8` (EN_AJUSTE_MABEL)
- `estado_id = 9` (REDISTRIBUIDO)

**Estados que NO permiten confirmar redistribución (`puede_confirmar_redistribucion: false`):**
- `estado_id = 10` (CONFIRMADO REDISTRIBUCION) - ya confirmado
- `estado_id >= 11` (estados posteriores)
- `estado_id = 19` (CANCELADO) - pedido cancelado

#### Implementación Recomendada

En la pantalla de redistribución (`/mba3-consultas/pedidos/{numero_pedido}/redistribucion`):

```javascript
// ✅ RECOMENDADO: Usar el flag del backend
const isButtonDisabled = !pedido.puede_confirmar_redistribucion;

// O alternativamente, validar el estado directamente:
const isButtonDisabled = 
  pedido.cabecera.estado_id >= 10 || 
  pedido.cabecera.estado_id === 19;  // CANCELADO
```

**Comportamiento en el frontend:**

| Acción | Comportamiento |
|--------|----------------|
| **Al cargar la vista** | Usar `puede_confirmar_redistribucion` del backend para determinar si mostrar el botón habilitado o deshabilitado. |
| **Al hacer clic en "Confirmar Redistribución"** | Deshabilitar el botón **de inmediato**. Mostrar "Confirmando…" o spinner. Enviar `POST .../redistribucion/confirmar` con el body. |
| **Si la petición es exitosa** | **Mantener el botón deshabilitado** (no volver a habilitar). Recargar el pedido para obtener el flag actualizado. |
| **Si la petición falla** | Mostrar mensaje de error y **volver a habilitar el botón** para que el usuario pueda reintentar. |
| **Después de cancelar pedido** | Recargar el pedido. El flag `puede_confirmar_redistribucion` será `false` y el botón se deshabilitará automáticamente. |

**Endpoint a usar:** `POST /api/pedidos/{numero_pedido}/redistribucion/confirmar`

- **Método:** POST  
- **Body:** `RedistribucionConfirmarRequest` (p. ej. `{ "ajustes_detalle": [ ... ] }`).  
- **Respuesta exitosa:** incluye `status: "success"`, `numero_pedido`, `message`, etc. **No incluye el pedido completo**; el backend actualiza el estado del pedido a **`CONFIRMADO REDISTRIBUCION`** (`estado_id` 10).

**Resumen de implementación:**

- **Al cargar la vista:** Usar `puede_confirmar_redistribucion` del backend.
- **Después de cancelar:** Recargar el pedido para obtener el flag actualizado (`false` para CANCELADO).
- **Al hacer clic:** Deshabilitar el botón de inmediato; tras **éxito**, no volver a habilitarlo.
- **Si la petición falla:** Rehabilitar el botón y mostrar el error.

### 1.3.2 Gestión del botón "Guardar Borrador"

El botón **"Guardar Borrador"** permite al usuario guardar el progreso de su trabajo en la redistribución **sin confirmarla definitivamente**.

#### Comportamiento

| Característica | Descripción |
|---------------|-------------|
| **¿Cambia el estado del pedido?** | **NO**. Solo persiste los datos en la base de datos. |
| **¿Se puede usar múltiples veces?** | **SÍ**. El usuario puede guardar su progreso cuantas veces quiera. |
| **¿Persiste al refrescar la página?** | **SÍ**. El frontend debe recuperar el borrador al cargar la vista. |
| **¿Persiste si el token expira?** | **SÍ**. Los datos están en la BD, no en memoria. |

#### Cantidades decimales en redistribución

La API de redistribución **acepta y devuelve cantidades en decimales** (ej. `0.5`, `1.25`). El frontend debe poder **visualizar y editar** estos valores sin tratarlos como enteros.

- **GET** `.../redistribucion/inicial` y **GET** `.../redistribucion/borrador`: en cada `ajuste_detalle`, los campos `cantidad_solicitada`, `cantidad_confirmada`, `cantidad_ajustada` y cada `distribucion_tiendas[].cantidad` son **números** (pueden ser decimales). Mostrarlos con el formato adecuado (ej. 0,5 o 0.5 según locale) y permitir edición con `input type="number"` con `step="any"` o `step="0.01"`.
- **POST** `.../redistribucion/borrador` y **POST** `.../redistribucion/confirmar`: el body puede enviar decimales en las mismas propiedades. El backend valida que la suma de cantidades por tienda coincida con la cantidad confirmada usando una tolerancia de redondeo (`1e-6`), por lo que es correcto usar comparaciones con tolerancia en el frontend para “Completo” / “Listo para confirmar”.
- **Resumen:** Para que en `/mba3-consultas/pedidos/{numero_pedido}/redistribucion` se puedan ver y cambiar números a decimales, el frontend debe: (1) formatear números con decimales cuando existan (ej. hasta 4 decimales), (2) usar inputs que acepten decimales (`step="any"` o `step` según decimales elegidos), (3) usar tolerancia en comparaciones con 0 o entre suma y total para evitar fallos por redondeo de punto flotante.

**Cambios de frontend recomendados (alineados con este backend):**

- **Formatters:** función tipo `formatNumberWithDecimals(value, decimals)` (0–4 decimales, locale) para visualización; no cambia lo que se envía al backend.
- **ExcelLikeGridView:** prop `decimalPlaces` (ej. defecto 2), `step` del input según decimales (0→1, 1→0.1, …, 4→0.0001), `formatNumberWithDecimals` en celdas numéricas, `inputmode="decimal"`, commit en blur (ej. `"2."` → 2).
- **RedistribucionTiendas:** selector “Decimales: 0 1 2 3 4”, pasar `decimalPlaces` a la vista tipo Excel, mismo `step` en inputs de cantidad en vista compacta, `handleValidarYCorregirCantidad` con actualización en blur.
- **useRedistribucion:** aceptar coma como decimal (`replace(',', '.')`), entrada parcial (no commitear si termina en `'.'`/`','` hasta blur), redondeo a 4 decimales al guardar; payload al backend sigue siendo número con hasta 4 decimales.

El backend **no** exige un número fijo de decimales (ej. “siempre 2”); acepta cantidades como número con hasta 4 decimales y valida con tolerancia `1e-6`. No hay reglas que contradigan el selector 0–4 decimales ni el uso de coma/punto en el frontend.

#### Endpoints

**Guardar borrador:**

```
POST /api/pedidos/{numero_pedido}/redistribucion/borrador
```

**Body:**
```json
{
  "ajustes_detalle": [
    {
      "codigo_producto": "R225.1012.BCO",
      "descripcion": "Producto ejemplo",
      "cantidad_solicitada": 100,
      "cantidad_confirmada": 80,
      "cantidad_ajustada": 75,
      "distribucion_tiendas": [
        {"tienda_codigo": "T001", "tienda_nombre": "Tienda 1", "cantidad": 50},
        {"tienda_codigo": "T002", "tienda_nombre": "Tienda 2", "cantidad": 25}
      ],
      "costo_original": 25.50,
      "costo_ajustado": 25.50,
      "cambio_precio": false
    }
  ]
}
```

**Respuesta:**
```json
{
  "status": "success",
  "message": "Borrador guardado exitosamente",
  "pedido_id": "uuid-del-pedido",
  "numero_pedido": "P-12.06 - 12 - 2025",
  "fecha_guardado": "2025-01-15T10:30:00Z"
}
```

**Recuperar borrador (al cargar la vista):**

```
GET /api/pedidos/{numero_pedido}/redistribucion/borrador
```

**Respuesta:**
```json
{
  "status": "success",
  "ajustes_detalle": [...],
  "fecha_guardado": "2025-01-15T10:30:00Z"
}
```

**Respuesta si no hay borrador guardado:**
```json
{
  "status": "success",
  "ajustes_detalle": [],
  "fecha_guardado": null,
  "message": "No hay borrador guardado para este pedido"
}
```

#### Implementación en el Frontend

**Al cargar la vista de redistribución:**

```javascript
// 1. Cargar datos del pedido
const pedido = await fetchPedido(numeroPedido);

// 2. Intentar recuperar borrador guardado
try {
  const borrador = await fetch(`/api/pedidos/${encodeURIComponent(numeroPedido)}/redistribucion/borrador`);
  const data = await borrador.json();
  
  if (data.status === 'success' && data.ajustes_detalle?.length > 0) {
    // Restaurar los ajustes del borrador
    setAjustesDetalle(data.ajustes_detalle);
    showNotification(`Borrador recuperado (guardado el ${formatDate(data.fecha_guardado)})`);
  } else {
    // No hay borrador, usar datos iniciales del pedido
    setAjustesDetalle(pedido.detalles);
  }
} catch (error) {
  // Error al recuperar borrador, usar datos iniciales
  setAjustesDetalle(pedido.detalles);
}
```

**Al hacer clic en "Guardar Borrador":**

```javascript
const handleGuardarBorrador = async () => {
  try {
    setGuardando(true);
    
    const response = await fetch(
      `/api/pedidos/${encodeURIComponent(numeroPedido)}/redistribucion/borrador`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ ajustes_detalle: ajustesDetalle })
      }
    );
    
    const data = await response.json();
    
    if (data.status === 'success') {
      showSuccessNotification('Borrador guardado exitosamente');
    } else {
      throw new Error(data.message || 'Error al guardar borrador');
    }
  } catch (error) {
    showErrorNotification(error.message);
  } finally {
    setGuardando(false);
  }
};
```

#### Diferencia entre "Guardar Borrador" y "Confirmar Redistribución"

| Acción | Endpoint | Cambia estado | Efecto |
|--------|----------|---------------|--------|
| **Guardar Borrador** | `POST .../borrador` | **NO** | Solo persiste los ajustes. El usuario puede seguir editando. |
| **Confirmar Redistribución** | `POST .../confirmar` | **SÍ** (a estado 10) | Confirma definitivamente. No se puede modificar después. |

#### Checklist de Implementación

- [ ] Al cargar la vista, llamar a `GET .../borrador` para recuperar ajustes guardados
- [ ] Si hay borrador, mostrar notificación indicando la fecha de guardado
- [ ] Al hacer clic en "Guardar Borrador", enviar `POST .../borrador`
- [ ] Mostrar indicador de carga mientras se guarda
- [ ] Mostrar notificación de éxito/error
- [ ] El botón siempre está habilitado (no depende del estado del pedido)

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

interface ConversionPorTiendaItem {
  tienda_codigo: string;       // ej. TRL-BHO, RL-CD
  tienda_nombre: string | null;
  es_bodega: boolean;          // true si es bodega (RL-CD, OUT-CD, RG-CD)
  cantidad_asignada: number;    // unidades originales
  cantidad_sap: number;         // cantidad_asignada × unidad_conversion
}

interface ProductoSAPProcesamientoItem {
  procesamiento_detalle_id: string;
  pedido_detalle_id: string;
  codigo_interno: string;
  descripcion_producto: string | null;  // ⭐ Descripción del producto desde SAP
  item_code_sap: string | null;
  pack_sap: string | null;
  unidad_conversion: number | null;
  unidad_original: string | null;  // ⭐ Unidad del pedido (ej. DOCENA), desde pedido_detalle.pack
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
  distribucion_conversion: ConversionPorTiendaItem[] | null;  // ⭐ Conversión por tienda/bodega (trazabilidad)
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

### Conversión por tienda/bodega (`distribucion_conversion`)

Cada producto puede incluir `distribucion_conversion`: lista de conversiones por tienda y bodega para trazabilidad. Si existe, se recomienda mostrar por producto una tabla o filas con:

- **Tienda/Bodega:** `tienda_codigo` y opcionalmente `tienda_nombre`; usar `es_bodega` para etiquetar (ej. "Bodega" vs "Tienda").
- **Cantidad original:** `cantidad_asignada` (unidades del pedido).
- **Cantidad SAP:** `cantidad_sap` (= cantidad_asignada × unidad_conversion).

Así el usuario ve la conversión por cada destino en lugar de solo los totales. Si no hay distribución confirmada, `distribucion_conversion` viene `null`.

### Campo Nuevo: `descripcion_producto`

El campo `descripcion_producto` ahora está disponible en la respuesta y puede ser:
- ✅ `string` - Descripción del producto
- ❌ `null` - Si no se encontró en SAP

### Columna "Pack" (Productos Procesados)

La columna **Pack** muestra la unidad del pedido y la unidad SAP. El backend envía:

- **`unidad_original`**: Unidad del pedido (ej. DOCENA), desde `pedido_detalle.pack`. Puede ser `null`.
- **`unidad_sap`**: Unidad SAP (ej. PACK, UN). Puede ser `null`.

Los valores vacíos o en blanco se envían como `null` (no como string vacío). Para no mostrar N/A ni raya cuando no hay datos, en el frontend se recomienda:

- Si **ambos** `unidad_original` y `unidad_sap` son `null` o falsy: **no mostrar nada** en la celda (celda vacía, sin guión ni texto).
- Si solo uno tiene valor: mostrar solo ese valor (opcionalmente sin flecha).
- Si ambos tienen valor: mostrar `unidad_original → unidad_sap` como hasta ahora.

---

## 2.1 Descartar vs Cancelar Pedido

En el frontend hay **dos acciones** con comportamientos distintos:

| Acción | Pantalla | Comportamiento | Llamada API |
|--------|----------|----------------|------------|
| **Descartar** | Cargar Plantilla | **Elimina** el pedido de la base de datos. **No** envía correo a EL RAYO. | `DELETE /api/pedidos/{pedido_id}` |
| **Cancelar Pedido** | Redistribución | **Cambia el estado** del pedido a **CANCELADO** (estado_id = 19). **Sí** envía correo a EL RAYO. El pedido permanece en la BD. | `POST /api/pedidos/{pedido_id}/cancelar` |

### Descartar (Cargar Plantilla)

**Endpoint:** `DELETE /api/pedidos/{pedido_id}`

- **Comportamiento:** Elimina completamente el pedido de la base de datos.
- **Restricciones:** Solo permitido en estado **Borrador** o **Nuevo Pedido** (estado_id 1 o 2) y sin datos asociados.
- **Notificación:** **No** envía correo a EL RAYO.
- **Uso:** `descartarPedido(pedidoId)` → `DELETE /api/pedidos/{id}`

### Cancelar Pedido (Redistribución)

**Endpoint:** `POST /api/pedidos/{pedido_id}/cancelar`

- **Comportamiento:** 
  - Cambia el estado del pedido a **CANCELADO** (estado_id = 19).
  - El pedido **permanece en la base de datos** con estado CANCELADO.
  - Envía correo a EL RAYO notificando la cancelación.
- **Restricciones:** Solo permitido en estados **anteriores** a Confirmado redistribución (estado_id < 10).
- **Respuesta:** Devuelve el pedido actualizado con estado CANCELADO.
- **Uso:** `cancelarPedido(pedidoId)` → `POST /api/pedidos/{id}/cancelar`

### Cuándo deshabilitar "Cancelar Pedido"

El botón **"Cancelar Pedido"** debe deshabilitarse desde el estado **Confirmado redistribución** (estado_id ≥ 10) en adelante. Para ello el backend expone:

- **`GET /api/pedidos/{id}/distribucion`**: campo `puede_descartar` — `true` si estado_id < 10, `false` desde Confirmado redistribución en adelante.
- **`GET /api/pedidos/{id}`** (y respuestas de pedido completo): campo **`puede_cancelar_pedido`** — `true` si estado_id < 10, `false` desde Confirmado redistribución en adelante.

Usar `puede_descartar` (distribucion) o `puede_cancelar_pedido` (pedido completo) para habilitar/deshabilitar el botón "Cancelar Pedido".

---

## ✅ Estado

Todas las funcionalidades están implementadas en backend y listas para integración con frontend.
