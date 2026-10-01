# Referencia de la API (generada)

> Generado el 2026-10-01 desde el OpenAPI del servicio (`MBA3 Query API` v2.1.0): **134 operaciones**. No editar a mano: ejecutar `python scripts/generar_referencia_api.py` tras cambiar endpoints.
> El permiso de cada endpoint se lee del código fuente (`require_permission`, `require_any_permission`, `require_admin`); si no hay ninguno se indica si basta un token JWT válido o si el endpoint no declara autenticación.

## Índice por grupo

- **Autenticación** — 2 operaciones
- **Consultas MBA3** — 3 operaciones
- **Cruce de Productos** — 12 operaciones
- **Historial** — 1 operaciones
- **Homologaciones SKU** — 5 operaciones
- **Integración SAP** — 3 operaciones
- **Notificaciones** — 2 operaciones
- **Notificaciones - Catálogo de Correos** — 5 operaciones
- **Notificaciones - Personas y Correos** — 4 operaciones
- **Pedidos** — 21 operaciones
- **Pedidos - Auditoría** — 1 operaciones
- **Pedidos - Confirmaciones** — 2 operaciones
- **Pedidos - Edicion** — 1 operaciones
- **Pedidos - Edición** — 3 operaciones
- **Pedidos - El Rayo** — 1 operaciones
- **Pedidos - Exportación** — 3 operaciones
- **Pedidos - Modificaciones** — 2 operaciones
- **Pedidos - ODC** — 1 operaciones
- **Pedidos - Proveedor** — 7 operaciones
- **Pedidos - Redistribución** — 16 operaciones
- **Pedidos - SAP** — 1 operaciones
- **Plantillas** — 13 operaciones
- **Plantillas - Archivos Originales** — 2 operaciones
- **Preferencias de Usuario** — 6 operaciones
- **Procesamiento** — 3 operaciones
- **Pruebas** — 1 operaciones
- **Remisiones** — 2 operaciones
- **Sistema** — 1 operaciones
- **Órdenes de Compra** — 10 operaciones

## Autenticación

### `GET /api/Auth/me`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Obtiene información del usuario autenticado actual.

Este endpoint es la **fuente de verdad única** para el frontend.
El frontend debe llamar a este endpoint al iniciar la app y usar
las capabilities para decidir qué UI mostrar.

**⚠️ Cuándo llamar a /api/auth/me:**
- Al **iniciar la app** (p. ej. en initializeAuth).
- Tras **login** y al **restaurar sesión** (token en localStorage).
- Si no se llama (o falla 401), `capabilities` queda sin cargar y botones
  como "Cargar Plantilla Excel" no se mostrarán aunque el backend los permita.

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido

**Respuesta exitosa (200):**
```json
{
  "user": {
    "id": "123",
    "username": "juan.perez",
    "email": "juan@example.com"
  },
  "roles": ["EL_RAYO_OPERADOR"],
  "permissions": ["odcsap.view", "mabel.view"],
  "capabilities": {
    "can_upload_templates": true,
    "can_cargar_plantilla_excel": true,
    "can_view_templates": true,
    "can_operate_pedidos": true,
    "can_view_odc_sap": false,
    "can_manage_order": false,
    "can_view_order_list": false,
    "mabel_view": false,
    "can_view_odc": false,
    "can_review_pedido": true,
    "can_confirm_pedido": true,
    "can_view_plantillas_originales": true
  }
}
```

**⚠️ IMPORTANTE PARA EL FRONTEND:**

El frontend debe usar **SOLO** el campo `capabilities` para decidir qué UI mostrar.

Los campos `permissions` y `roles` se incluyen **SOLO para auditoría y debugging**.
**NO deben usarse para lógica de UI.**

**Regla mental para el frontend:**
> La UI no depende del usuario ni del modo, depende de capacidades.
> Si una capacidad no existe, el botón no existe.

No se deshabilita, no se oculta por CSS, no se valida por nombre de empresa.
**No se renderiza.**

**Ejemplo correcto:**
```tsx
// ✅ CORRECTO: Usar capabilities
{capabilities.can_upload_templates && <Button>Subir Excel</Button>}
{capabilities.can_cargar_plantilla_excel && <Button>Cargar Plantilla Excel</Button>}

// ❌ INCORRECTO: No usar permissions directamente
{permissions.includes('mabel.view') && <Button>...</Button>}
```

**Pantalla detalle pedido** (`/mba3-consultas/pedidos/{id}`):
- "Cargar Plantilla Excel": `capabilities.can_cargar_plantilla_excel`
- Sidebar "Gestión ODC SAP": `capabilities.can_view_odc_sap` (true solo si permiso `odc.view`; sin admin override)
- Redistribuir, Exportar, Descargar para MBA: `capabilities.can_operate_pedidos`
- Botón "Confirmar": `capabilities.can_confirm_pedido`

**Botones "Gestionar Pedido" y "Listado de Pedidos":**
- "Gestionar Pedido": `capabilities.can_manage_order` (true solo si permiso `odcsap.view`)
- "Listado de Pedidos": `capabilities.can_view_order_list` (true solo si permiso `odcsap.view`)

**Botones del módulo MABEL** (Cargar Plantilla, Redistribución, Procesamiento SAP, Procesos, Homologaciones):
- Todos visibles **solo si** `capabilities.mabel_view === true` (permiso `mabel.view`; sin admin override).

**Botón "Listado Pedidos Originales"** (sección Información ODC):
- Visible **solo si** `capabilities.can_view_plantillas_originales === true` (permiso `mabel.view` o admin).

**Respuestas:** `200`

### `GET /api/auth/me`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Obtiene información del usuario autenticado actual.

Este endpoint es la **fuente de verdad única** para el frontend.
El frontend debe llamar a este endpoint al iniciar la app y usar
las capabilities para decidir qué UI mostrar.

**⚠️ Cuándo llamar a /api/auth/me:**
- Al **iniciar la app** (p. ej. en initializeAuth).
- Tras **login** y al **restaurar sesión** (token en localStorage).
- Si no se llama (o falla 401), `capabilities` queda sin cargar y botones
  como "Cargar Plantilla Excel" no se mostrarán aunque el backend los permita.

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido

**Respuesta exitosa (200):**
```json
{
  "user": {
    "id": "123",
    "username": "juan.perez",
    "email": "juan@example.com"
  },
  "roles": ["EL_RAYO_OPERADOR"],
  "permissions": ["odcsap.view", "mabel.view"],
  "capabilities": {
    "can_upload_templates": true,
    "can_cargar_plantilla_excel": true,
    "can_view_templates": true,
    "can_operate_pedidos": true,
    "can_view_odc_sap": false,
    "can_manage_order": false,
    "can_view_order_list": false,
    "mabel_view": false,
    "can_view_odc": false,
    "can_review_pedido": true,
    "can_confirm_pedido": true,
    "can_view_plantillas_originales": true
  }
}
```

**⚠️ IMPORTANTE PARA EL FRONTEND:**

El frontend debe usar **SOLO** el campo `capabilities` para decidir qué UI mostrar.

Los campos `permissions` y `roles` se incluyen **SOLO para auditoría y debugging**.
**NO deben usarse para lógica de UI.**

**Regla mental para el frontend:**
> La UI no depende del usuario ni del modo, depende de capacidades.
> Si una capacidad no existe, el botón no existe.

No se deshabilita, no se oculta por CSS, no se valida por nombre de empresa.
**No se renderiza.**

**Ejemplo correcto:**
```tsx
// ✅ CORRECTO: Usar capabilities
{capabilities.can_upload_templates && <Button>Subir Excel</Button>}
{capabilities.can_cargar_plantilla_excel && <Button>Cargar Plantilla Excel</Button>}

// ❌ INCORRECTO: No usar permissions directamente
{permissions.includes('mabel.view') && <Button>...</Button>}
```

**Pantalla detalle pedido** (`/mba3-consultas/pedidos/{id}`):
- "Cargar Plantilla Excel": `capabilities.can_cargar_plantilla_excel`
- Sidebar "Gestión ODC SAP": `capabilities.can_view_odc_sap` (true solo si permiso `odc.view`; sin admin override)
- Redistribuir, Exportar, Descargar para MBA: `capabilities.can_operate_pedidos`
- Botón "Confirmar": `capabilities.can_confirm_pedido`

**Botones "Gestionar Pedido" y "Listado de Pedidos":**
- "Gestionar Pedido": `capabilities.can_manage_order` (true solo si permiso `odcsap.view`)
- "Listado de Pedidos": `capabilities.can_view_order_list` (true solo si permiso `odcsap.view`)

**Botones del módulo MABEL** (Cargar Plantilla, Redistribución, Procesamiento SAP, Procesos, Homologaciones):
- Todos visibles **solo si** `capabilities.mabel_view === true` (permiso `mabel.view`; sin admin override).

**Botón "Listado Pedidos Originales"** (sección Información ODC):
- Visible **solo si** `capabilities.can_view_plantillas_originales === true` (permiso `mabel.view` o admin).

**Respuestas:** `200`

## Consultas MBA3

### `GET /consultar`

**Permiso requerido:** `mabel.view`

Endpoint CONSULTAR MBA3: Solo consulta datos desde MBA3, NO guarda en base de datos.

**Responsabilidad:** Solo consulta, separada del guardado.

Este endpoint realiza:
1. ✅ Consulta datos desde MBA3 usando query predefinida
2. ❌ NO guarda en base de datos (usar /migrar para eso)

**Parámetros:**
- use_date_filter: Si es True, filtra registros de los últimos N días
- days: Número de días hacia atrás para filtrar (solo si use_date_filter=True)

**Ejemplo de uso:**
```
GET /consultar
GET /consultar?use_date_filter=true&days=30
```

**Flujo recomendado:**
1. Llamar este endpoint para obtener datos de MBA3
2. Usar los datos retornados para llamar a `/migrar`

Returns:
    JSON con los datos de MBA3 (sin guardar en BD)

**Parámetros:**

- `use_date_filter` (query, boolean, opcional)
- `days` (query, integer, opcional)

**Respuestas:** `200`, `422`

### `POST /migrar`

**Permiso requerido:** `mabel.view`

Endpoint GUARDAR: Guarda datos en SQL Server (despacho_cabecera/detalle).

**Responsabilidad:** Solo guarda en base de datos, NO consulta MBA3.

Este endpoint realiza:
1. ✅ Guarda datos en SQL Server (despacho_cabecera/detalle)
2. ❌ NO consulta MBA3 (usar /consultar para eso)

**Body (JSON):**
```json
{
    "data": [
        {
            "CODIGO_FACTURA": "...",
            "ANULADA": "...",
            ...
        }
    ],
    "upsert": true
}
```

- data: Lista o diccionario con los datos a guardar (formato MBA3)
- upsert: Si es True, actualiza si existe; si False, inserta siempre

**Ejemplo de uso:**
```bash
POST /migrar
Content-Type: application/json

{
    "data": [...],
    "upsert": true
}
```

**Flujo recomendado:**
1. Llamar `/consultar` para obtener datos de MBA3
2. Usar los datos retornados en el body de este endpoint

    Returns:
        JSON con el status del guardado

**Cuerpo de la petición:** `application/json` → SaveDataRequest

**Respuestas:** `200`, `422`

### `GET /migrar/completo`

**Permiso requerido:** `mabel.view`

Endpoint MIGRAR COMPLETO: Ejecuta consulta predefinida y guarda en despacho_cabecera/detalle.

**Responsabilidad:** MIGRAR COMPLETO (consulta + guarda en un solo paso)

Este endpoint realiza:
1. ✅ Consulta datos desde MBA3 usando query predefinida con filtro de fecha (último año)
2. ✅ Guarda resultados en SQL Server (despacho_cabecera/detalle)
3. ❌ NO copia a orden_compra (ese paso lo hace el endpoint PROCESAR)

**Características:**
- ✅ Filtro automático: siempre trae los últimos 365 días (1 año) desde hoy
- ✅ Sin parámetros: solo ejecutar el endpoint
- ✅ Fecha relativa: calcula automáticamente desde hoy hacia atrás

**Nota:** Este endpoint realiza ambas operaciones (consulta y guardado).
Para operaciones separadas, usar:
- GET /consultar (solo consulta)
- POST /migrar (solo guarda)

**Ejemplo de uso:**
```
GET /migrar/completo
```

**Nota:** Este endpoint solo migra a despacho.
Para proceso completo (consulta + guarda + copia a ODC), usar GET /consulta/predefinida.

Returns:
    JSON con los datos de MBA3 y metadata del guardado en despacho

**Respuestas:** `200`

## Cruce de Productos

### `GET /cruce-productos/buscar-sku/mba3`

**Permiso requerido:** `mabel.view`

Busca un SKU directamente en la base de datos de MBA3.

Consulta directamente la tabla INVT_FICHA_PRINCIPAL de MBA3.

Si `incluir_sugerencias_sap=True`, además busca sugerencias similares en SAP
basándose en el código encontrado en MBA3. Esto es útil cuando un código existe
en MBA3 pero no tiene equivalente exacto en SAP, permitiendo encontrar alternativas similares.

**Ejemplo de uso:**
- Búsqueda simple: `GET /cruce-productos/buscar-sku/mba3?sku=R225.1012.BCO`
- Con sugerencias: `GET /cruce-productos/buscar-sku/mba3?sku=R225.1012.BCO&incluir_sugerencias_sap=true&limite_sugerencias=20`

Args:
    sku: Código del producto (PRODUCT_ID) a buscar
    incluir_sugerencias_sap: Si True, busca sugerencias similares en SAP
    limite_sugerencias: Límite de sugerencias a retornar (solo si incluir_sugerencias_sap=True)

Returns:
    Información del producto en MBA3 y opcionalmente sugerencias similares en SAP

**Parámetros:**

- `sku` (query, string, obligatorio) — SKU del producto a buscar en MBA3
- `incluir_sugerencias_sap` (query, boolean, opcional) — Si True, incluye sugerencias similares de SAP basadas en el código de MBA3
- `limite_sugerencias` (query, integer, opcional) — Límite máximo de sugerencias SAP a retornar (1-50, solo si incluir_sugerencias_sap=True)

**Respuestas:** `200`, `422`

### `GET /cruce-productos/buscar-sku/sap`

**Permiso requerido:** `mabel.view`

Busca un SKU directamente en la base de datos de SAP.

Consulta directamente SAP usando OPENQUERY.

Args:
    sku: Código del producto (ItemCode) a buscar en SAP

Returns:
    Información del producto en SAP si se encuentra

**Parámetros:**

- `sku` (query, string, obligatorio) — SKU (ItemCode) del producto a buscar en SAP

**Respuestas:** `200`, `422`

### `GET /cruce-productos/buscar-sku/sap/sugerencias`

**Permiso requerido:** `mabel.view`

Busca SKUs similares en SAP basándose en un SKU de referencia.

Este endpoint realiza búsqueda fuzzy/similar usando:
1. Búsqueda LIKE en ItemCode de SAP
2. Algoritmo de scoring basado en similitud de códigos y nombres
3. Retorna sugerencias ordenadas por relevancia con scores y motivos

Args:
    sku: SKU de referencia (ItemCode) para buscar sugerencias similares
    limite: Límite máximo de sugerencias (default: 20, máximo: 50)

Returns:
    Lista de sugerencias con información detallada

**Parámetros:**

- `sku` (query, string, obligatorio) — SKU (ItemCode) de referencia para buscar sugerencias similares en SAP
- `limite` (query, integer, opcional) — Límite máximo de sugerencias a retornar (1-50)

**Respuestas:** `200`, `422`

### `GET /cruce-productos/estado-sincronizacion`

**Permiso requerido:** `mabel.view`

Obtiene el estado actual de sincronización de maestros MBA3 y SAP.

Retorna información sobre:
- Última sincronización exitosa (fecha y hora en ISO 8601)
- Estado actual: "exitoso", "error", "en_proceso", o null si no hay registros
- Mensaje descriptivo del estado

⚠️ Nota: Si hay una sincronización EN_PROGRESO con más de 2 horas,
   se considera inconsistente (proceso colgado) y se retorna como error.

Returns:
    {
        "status": "success",
        "data": {
            "mba3": {"ultima_sync": ..., "estado": ..., "mensaje": ...},
            "sap":  {"ultima_sync": ..., "estado": ..., "mensaje": ...}
        }
    }

**Respuestas:** `200`

### `POST /cruce-productos/iniciar`

**Permiso requerido:** `mabel.view`

Inicia un cruce de productos en background usando Celery.

Este endpoint:
1. Crea un proceso con ID único
2. Ejecuta el cruce en background usando Celery
3. Devuelve el process_id para seguir el progreso

Para seguir el progreso, usa:
- GET /cruce-productos/stream/{process_id} (SSE)
- GET /cruce-productos/resultado/{process_id} (polling)

Si Redis/Celery no están disponibles, se ejecuta el cruce en primer plano
y se devuelve 200 con el resultado completo ("fallback": "sync").

Returns:
    Si async: 202 con process_id.
    Si fallback sync: 200 con "data", "message", "fallback": "sync".

**Respuestas:** `200`

### `GET /cruce-productos/realizar-cruce`

**Permiso requerido:** `mabel.view`

Realiza un cruce completo entre productos de MBA3 y SAP.

Identifica:
- Homologados exactos: PRODUCT_ID === ItemCode
- Homologables: normalizar(PRODUCT_ID) === normalizar(ItemCode) pero códigos diferentes
- Solo en MBA3: productos que no tienen match en SAP
- Solo en SAP: productos que no tienen match en MBA3

Returns:
    Resultado del cruce con estadísticas y listas de productos

**Respuestas:** `200`

### `GET /cruce-productos/resultado/{process_id}`

**Permiso requerido:** `mabel.view`

Obtiene el resultado final del cruce (por si se perdió el stream SSE).

Este endpoint es útil para:
- Recuperar resultados después de perder conexión SSE
- Verificar estado de un proceso sin mantener conexión abierta
- Implementar polling como alternativa a SSE

Args:
    process_id: ID del proceso obtenido de POST /cruce-productos/iniciar

Returns:
    - Si completado: resultado completo del cruce
    - Si en proceso: estado actual
    - Si error: mensaje de error

**Parámetros:**

- `process_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `POST /cruce-productos/sincronizar-maestros`

**Permiso requerido:** `mabel.view`

Sincroniza ambos maestros de productos (MBA3 y SAP) desde ERPs a staging.

Este endpoint ejecuta ambos procesos en secuencia:
1. Consulta productos MBA3 desde API
2. Consulta productos SAP desde OPENQUERY
3. Normaliza códigos y guarda/actualiza en tablas staging
4. Registra estadísticas en sync_control

**Estrategia de sincronización:**
- Por defecto: Sincronización incremental (continúa desde el último producto procesado)
- Si la tabla está vacía o tiene < 100 productos: Sincronización completa automática
- Con `force_full=true`: Fuerza sincronización completa desde el inicio

⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.

**Parámetros:**
- `force_full` (bool, default: false): Si true, fuerza sincronización completa desde el inicio.
  Útil cuando eliminas datos para pruebas o necesitas re-sincronizar todo.

**Ejemplos:**
- Sincronización incremental: `POST /cruce-productos/sincronizar-maestros`
- Sincronización completa: `POST /cruce-productos/sincronizar-maestros?force_full=true`

Para sincronizar solo MBA3 o solo SAP, usar los endpoints específicos:
- POST /cruce-productos/sincronizar-maestros/mba3
- POST /cruce-productos/sincronizar-maestros/sap

Returns:
    Estadísticas de sincronización para MBA3 y SAP

**Parámetros:**

- `force_full` (query, boolean, opcional) — Forzar sincronización completa desde el inicio (útil para pruebas o cuando se eliminan datos)

**Respuestas:** `200`, `422`

### `POST /cruce-productos/sincronizar-maestros/mba3`

**Permiso requerido:** `mabel.view`

Sincroniza maestros de productos MBA3 desde API a staging.

Este endpoint SIEMPRE reemplaza la información existente:
1. Consulta TODOS los productos MBA3 desde API (tabla INVT_FICHA_PRINCIPAL)
2. Normaliza códigos y guarda/actualiza en producto_mba3_staging
3. Elimina productos que ya no existen en MBA3
4. Registra estadísticas en sync_control

⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.

Returns:
    Estadísticas de sincronización para MBA3 (incluye registros_eliminados)

**Respuestas:** `200`

### `POST /cruce-productos/sincronizar-maestros/sap`

**Permiso requerido:** `mabel.view`

Sincroniza maestros de productos SAP desde OPENQUERY a staging.

Este endpoint:
1. Consulta productos SAP desde OPENQUERY
2. Normaliza códigos y guarda/actualiza en producto_sap_staging
3. Registra estadísticas en sync_control

⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.

Returns:
    Estadísticas de sincronización para SAP

**Respuestas:** `200`

### `GET /cruce-productos/stream/{process_id}`

**Permiso requerido:** `mabel.view`

Stream de progreso usando Server-Sent Events (SSE).

Este endpoint envía eventos de progreso en tiempo real mientras
se ejecuta el cruce de productos.

**Autenticación:**
- El token JWT debe enviarse en el header Authorization (no en query string)
- El frontend debe usar fetch() con ReadableStream o un polyfill de EventSource

**Eventos enviados:**
- Cada segundo mientras el proceso está en ejecución
- Solo cuando hay cambios en el estado (comparación por updated_at y version)
- Evento final cuando el proceso completa o falla

**Formato de eventos:**
```
data: {"status": "processing", "step": "exactos", "progress": 50, ...}
```

Args:
    process_id: ID del proceso obtenido de POST /cruce-productos/iniciar

Returns:
    Stream de eventos SSE con formato text/event-stream

**Parámetros:**

- `process_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `GET /cruce-productos/sugerencias`

**Permiso requerido:** `mabel.view`

Obtiene sugerencias de homologación para productos que no tienen match exacto.

**IMPORTANTE - Flujo requerido:**

1. **Primero**: Ejecutar `POST /cruce-productos/iniciar` para iniciar el cruce
2. **Esperar**: El cruce completa (seguir progreso con `GET /cruce-productos/stream/{process_id}`)
3. **Luego**: Llamar a este endpoint para obtener sugerencias

**Este endpoint NO ejecuta el cruce.** Reutiliza el último cruce completado
desde Redis. Si no existe un cruce reciente (menos de 15 minutos), devuelve error 412.

**Códigos de respuesta:**
- `200`: Sugerencias generadas exitosamente
- `412`: No existe cruce reciente (ejecute el cruce primero)
- `500`: Error al generar sugerencias

**TTL del cruce:**
- Los resultados del cruce se mantienen válidos por 15 minutos
- Un nuevo cruce invalida automáticamente el anterior
- Si se sincronizan maestros (MBA3/SAP), se recomienda ejecutar nuevo cruce

**Características de las sugerencias:**
- Score normalizado (0.0 - 1.0) para usar como porcentaje en frontend
- Score original (para debugging)
- Motivos del match (explicación del por qué se sugiere)
- Máximo 5 sugerencias por producto MBA3
- Solo sugerencias con score >= 0.5 (umbral mínimo)

Returns:
    Lista de productos MBA3 con sus sugerencias ordenadas por score

**Respuestas:** `200`

## Historial

### `GET /historial-ordenes`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Endpoint HISTORIAL-ORDENES: Obtiene el historial de integración de órdenes de compra con SAP.

⭐ **Recomendado para Frontend**

Este endpoint permite consultar el historial completo de integraciones con SAP,
incluyendo éxitos, errores y detalles de cada proceso.

**Query Parameters:**
- `oc_id` (string, opcional) - Filtrar por UUID de orden de compra
- `referencia_despacho` (string, opcional) - Filtrar por referencia de despacho
- `proveedor` (string, opcional) - Filtrar por código de proveedor
- `fecha_desde` (string, opcional) - Filtrar desde fecha (YYYY-MM-DD)
- `fecha_hasta` (string, opcional) - Filtrar hasta fecha (YYYY-MM-DD)
- `nivel_log` (string, opcional) - Filtrar por nivel (INFO, ERROR, WARNING)
- `success` (boolean, opcional) - Filtrar por éxito (true) o error (false)
- `limit` (int, default: 50) - Límite de registros por página
- `offset` (int, default: 0) - Offset para paginación

**Ejemplo:**
```
GET /historial-ordenes?proveedor=P1790389219001&limit=20&offset=0
GET /historial-ordenes?fecha_desde=2025-12-01&fecha_hasta=2025-12-03&success=true
```

**Respuesta:**
```json
{
  "status": "success",
  "data": [...],
  "metadata": {
    "total": 150,
    "limit": 50,
    "offset": 0,
    "has_more": true
  }
}
```

Returns:
    JSON con historial de órdenes y metadata de paginación

**Parámetros:**

- `oc_id` (query, string, opcional) — Filtrar por UUID de orden de compra
- `referencia_despacho` (query, string, opcional) — Filtrar por referencia de despacho
- `proveedor` (query, string, opcional) — Filtrar por código de proveedor
- `fecha_desde` (query, string, opcional) — Filtrar desde fecha (YYYY-MM-DD)
- `fecha_hasta` (query, string, opcional) — Filtrar hasta fecha (YYYY-MM-DD)
- `nivel_log` (query, string, opcional) — Filtrar por nivel (INFO, ERROR, WARNING)
- `success` (query, boolean, opcional) — Filtrar por éxito (true) o error (false)
- `limit` (query, integer, opcional) — Límite de registros por página
- `offset` (query, integer, opcional) — Offset para paginación

**Respuestas:** `200`, `422`

## Homologaciones SKU

### `GET /api/homologaciones-sku`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Obtiene lista de homologaciones SKU con filtros y paginación.

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido

**Parámetros de query:**
- `page` (int): Número de página (default: 1)
- `pageSize` (int): Tamaño de página (default: 10, max: 100)
- `estado` (string): Filtro por estado (PENDIENTE | HOMOLOGADO | ERROR)
- `tiene_diferencias` (boolean): Filtro por diferencias
- `tiene_datos_sap` (boolean): Filtro por datos SAP
- `sku` (string): Búsqueda por SKU (busca en MBA3 y SAP) - tiene prioridad sobre search
- `search` (string): Búsqueda general en SKU y nombres de producto (MBA3 y SAP)

**Respuesta exitosa (200):**
```json
{
  "status": "success",
  "data": [
    {
      "homologacion_id": "uuid-123",
      "sku_mba3": "SKU001",
      "nombre_producto_mba3": "Producto Ejemplo",
      "precio_unitario_mba3": 100.50,
      "cantidad_docena_mba3": 12,
      "total_linea_mba3": 1206.00,
      "sku_sap": "SKU001-SAP",
      "nombre_producto_sap": "Producto SAP",
      "precio_unitario_sap": 100.00,
      "cantidad_pack_sap": 10,
      "unidad_sap": "UN",
      "subtotal_sap": 1000.00,
      "estado": "PENDIENTE",
      "tiene_diferencias": true,
      "tiene_datos_sap": true
    }
  ],
  "metadata": {
    "count": 150,
    "total_pendientes": 50,
    "total_homologados": 80,
    "total_errores": 20,
    "filters": {}
  },
  "total": 150,
  "page": 1,
  "pageSize": 10,
  "totalPages": 15
}
```

**Parámetros:**

- `page` (query, integer, opcional) — Número de página
- `pageSize` (query, integer, opcional) — Tamaño de página
- `estado` (query, string, opcional) — Filtro por estado (PENDIENTE, HOMOLOGADO, ERROR)
- `tiene_diferencias` (query, boolean, opcional) — Filtro por diferencias MBA3 vs SAP
- `tiene_datos_sap` (query, boolean, opcional) — Filtro por presencia de datos SAP
- `sku` (query, string, opcional) — Búsqueda por SKU (MBA3 o SAP)
- `search` (query, string, opcional) — Búsqueda general en SKU y nombres de producto (MBA3 y SAP)

**Respuestas:** `200`, `422`

### `POST /api/homologaciones-sku`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Crea una nueva homologación SKU.

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido
- `Content-Type: application/json`

**Body (sku_mba3 es requerido, los demás campos son opcionales):**
```json
{
  "sku_mba3": "SKU001",
  "nombre_producto_mba3": "Producto Ejemplo MBA3",
  "precio_unitario_mba3": 100.50,
  "cantidad_docena_mba3": 12.0,
  "total_linea_mba3": 1206.00,
  "sku_sap": "SKU001-SAP",
  "nombre_producto_sap": "Producto SAP",
  "precio_unitario_sap": 100.00,
  "cantidad_pack_sap": 10.0,
  "unidad_sap": "UN",
  "subtotal_sap": 1000.00,
  "estado": "PENDIENTE",
  "detalle_id": "detalle-123",
  "despacho_id": "despacho-456"
}
```

**Respuesta exitosa (201):**
```json
{
  "status": "success",
  "data": {
    "homologacion_id": "uuid-123",
    // ... objeto completo creado
  },
  "message": "Homologación creada correctamente"
}
```

**Errores posibles:**
- 400: Error de validación
- 401: No autenticado
- 500: Error interno

**Cuerpo de la petición:** `application/json` → HomologacionSkuCreateRequest

**Respuestas:** `200`, `422`

### `POST /api/homologaciones-sku/bulk-update`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Actualiza múltiples homologaciones en lote.

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido
- `Content-Type: application/json`

**Body:**
```json
{
  "updates": [
    {
      "homologacion_id": "uuid-123",
      "data": {
        "sku_sap": "SKU001-SAP",
        "precio_unitario_sap": 105.00,
        "estado": "HOMOLOGADO"
      }
    },
    {
      "homologacion_id": "uuid-456",
      "data": {
        "sku_sap": "SKU002-SAP",
        "estado": "HOMOLOGADO"
      }
    }
  ]
}
```

**Respuesta exitosa (200):**
```json
{
  "status": "success",
  "data": {
    "actualizadas": 2,
    "errores": 0,
    "detalles": [
      {
        "homologacion_id": "uuid-123",
        "success": true
      },
      {
        "homologacion_id": "uuid-456",
        "success": true
      }
    ]
  }
}
```

**Cuerpo de la petición:** `application/json` → HomologacionSkuBulkUpdateRequest

**Respuestas:** `200`, `422`

### `POST /api/homologaciones-sku/sincronizar`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Sincroniza homologaciones desde los despachos.

Este endpoint analiza todos los productos en `despacho_detalle`,
compara con datos de SAP, y detecta diferencias para crear o
actualizar registros de homologación.

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido

**Body:** vacío (no se requiere)

**Respuesta exitosa (200):**
```json
{
  "status": "success",
  "data": {
    "homologaciones_encontradas": 25,
    "homologaciones_nuevas": 10,
    "homologaciones_actualizadas": 15,
    "mensaje": "Sincronización completada"
  }
}
```

**Proceso de sincronización:**
1. Lee todos los productos de `despacho_detalle`
2. Busca información SAP correspondiente en `producto_sap_cache`
3. Detecta diferencias entre SKUs, precios, cantidades
4. Crea nuevas homologaciones o actualiza existentes
5. Calcula flags `tiene_diferencias` y `tiene_datos_sap`
6. Asigna estado (PENDIENTE si hay diferencias, HOMOLOGADO si coincide)

**Respuestas:** `200`

### `PUT /api/homologaciones-sku/{homologacion_id}`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Actualiza una homologación SKU específica.

**Parámetros:**
- `homologacion_id`: UUID de la homologación a actualizar

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido
- `Content-Type: application/json`

**Body (todos los campos son opcionales):**
```json
{
  "sku_sap": "SKU001-SAP",
  "nombre_producto_sap": "Producto SAP Actualizado",
  "precio_unitario_sap": 105.00,
  "cantidad_pack_sap": 12,
  "unidad_sap": "UN",
  "subtotal_sap": 1260.00,
  "estado": "HOMOLOGADO"
}
```

**Respuesta exitosa (200):**
```json
{
  "status": "success",
  "data": {
    "homologacion_id": "uuid-123",
    // ... objeto completo actualizado
  },
  "message": "Homologación actualizada correctamente"
}
```

**Errores posibles:**
- 400: Error de validación
- 401: No autenticado
- 404: Homologación no encontrada
- 500: Error interno

**Parámetros:**

- `homologacion_id` (path, string, obligatorio)

**Cuerpo de la petición:** `application/json` → HomologacionSkuUpdateRequest

**Respuestas:** `200`, `422`

## Integración SAP

### `POST /integrar-sap`

**Permiso requerido:** `mabel.view`

Endpoint INTEGRAR-SAP: Envía órdenes de compra a SAP Service Layer.

**Responsabilidad:** INTEGRAR (endpoint #4 de los 4 requeridos)

Este endpoint realiza:
1. ❌ NO consulta (ya lo hizo CONSULTAR)
2. ❌ NO guarda en despacho (ya lo hizo MIGRAR)
3. ❌ NO copia a OC (ya lo hizo PROCESAR)
4. ✅ Envía ODCs con estado "PENDIENTE" a SAP Service Layer
5. ✅ Actualiza estado a "ENVIADA" o "ERROR" según resultado

**Características:**
- ✅ Puede enviar 1 o varios ODC en una sola llamada
- ✅ Si se proporciona `oc_id`: envía las ODC(s) especificada(s) por UUID
- ✅ Si se proporciona `referencia_despacho`: busca y envía las ODC(s) por referencia
- ✅ Si NO se proporciona ningún parámetro: busca y envía la primera ODC pendiente
- ✅ Convierte cada ODC a formato JSON de SAP Service Layer
- ✅ Envía cada ODC directamente a SAP Service Layer (sin middleware)
- ✅ Actualiza estado a "ENVIADA" o "ERROR" según resultado
- ✅ Retorna información detallada de cada ODC procesada

**Query Parameters:**
- `oc_id` (opcional, múltiple): UUID de la orden de compra. Puede especificarse múltiples veces.
- `referencia_despacho` (opcional, múltiple): Número de factura/despacho. Puede especificarse múltiples veces.

**Ejemplos de uso:**
```
# Enviar una OC específica por UUID
POST /integrar-sap?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325

# Enviar múltiples OC por UUID
POST /integrar-sap?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325&oc_id=ABC123-DEF456-GHI789

# Buscar OC específica por referencia
POST /integrar-sap?referencia_despacho=900125353

# Buscar múltiples OC por referencia
POST /integrar-sap?referencia_despacho=900125353&referencia_despacho=900125354

# Procesar primera OC pendiente (comportamiento por defecto)
POST /integrar-sap
```

**Nota:** Este endpoint asume que las ODCs ya están creadas con estado "PENDIENTE".
Para proceso completo (consulta + guarda + copia + integración), usar los 4 endpoints en secuencia.

**Flujo recomendado:**
1. GET /consultar - Solo consulta
2. GET /migrar - Consulta + Guarda en despacho
3. GET /procesar-oc - Copia despachos a ODC (estado: PENDIENTE)
4. POST /integrar-sap - Envía ODC a SAP Service Layer

**Estados de ODC:**
- `PENDIENTE`: Creada pero no enviada a SAP (estado inicial)
- `ENVIANDO`: Envío a SAP en curso ahora mismo (se fija aquí antes de la
  prevalidación/envío; el caller nunca lo pasa como parámetro)
- `ENVIADA`: Enviada exitosamente a SAP (se actualiza aquí)
- `ERROR`: Error al enviar a SAP (se actualiza aquí)
- `ENCOLADA`: SAP saturado, HTTP 202 con job pendiente de resolver

**Configuración requerida:**
- Variables de entorno en `.env`:
  - `SAP_SERVICE_LAYER_URL`
  - `SAP_SERVICE_LAYER_USERNAME`
  - `SAP_SERVICE_LAYER_PASSWORD`
  - `SAP_SERVICE_LAYER_DATABASE`

Returns:
    JSON con metadata del proceso de envío a SAP

**Parámetros:**

- `oc_id` (query, lista de string, opcional) — UUID(s) de la(s) orden(es) de compra a enviar. Puede especificarse múltiples veces (ej: ?oc_id=xxx&oc_id=yyy).
- `referencia_despacho` (query, lista de string, opcional) — Referencia(s) del despacho (número de factura) para buscar OC(s) específica(s). Puede especificarse múltiples veces (ej: ?referencia_despacho=xxx&referencia_despacho=yyy). Si no se proporciona oc_id ni referencia_despacho, se procesa la primera OC pendiente.

**Respuestas:** `200`, `422`

### `GET /sap/test`

**Permiso requerido:** Sin autenticación declarada en el endpoint (público, o validada por otro mecanismo)

Endpoint de prueba para consultar información de un producto desde SAP.

Este endpoint permite probar la integración con SAP sin necesidad de procesar
una factura completa. Consulta información del producto y muestra el resultado.

**Parámetros:**
- `sku`: SKU del producto a consultar (requerido)

**Ejemplo de uso:**
```
GET /sap/test?sku=5-0012.9
```

**Respuesta:**
- Información del producto desde SAP (ItemCode, ItemName, U_IXX_PACK)
- Información del cache si está disponible
- Unidad de conversión calculada

Returns:
    JSON con información del producto desde SAP o error si falla

**Parámetros:**

- `sku` (query, string, obligatorio) — SKU del producto a consultar en SAP (ej: 5-0012.9)

**Respuestas:** `200`, `422`

### `GET /sap/test/direct`

**Permiso requerido:** Sin autenticación declarada en el endpoint (público, o validada por otro mecanismo)

Endpoint de prueba para consulta directa a SAP (sin usar cache).

Este endpoint consulta directamente a SAP sin verificar el cache primero.
Útil para forzar una consulta nueva y verificar que la conexión funciona.

**Parámetros:**
- `sku`: SKU del producto a consultar (requerido)

**Ejemplo de uso:**
```
GET /sap/test/direct?sku=5-0012.9
```

Returns:
    JSON con información del producto desde SAP (sin cache)

**Parámetros:**

- `sku` (query, string, obligatorio) — SKU del producto a consultar directamente en SAP

**Respuestas:** `200`, `422`

## Notificaciones

### `GET /notificaciones/status`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Estado del sistema de notificaciones.

Muestra la cantidad de listeners activos por permiso.
Útil para debugging y monitoreo.

**Respuestas:** `200`

### `GET /notificaciones/stream`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Conexión SSE para recibir notificaciones en tiempo real.

El usuario se suscribe automáticamente a las notificaciones
dirigidas a sus permisos (ej: odcsap.view, mabel.view).

**Eventos SSE:**
- `notification`: Nueva notificación para mostrar como toast
- `heartbeat`: Mantiene la conexión viva (cada 30s)
- `connected`: Confirmación de conexión exitosa

**Formato del evento `notification`:**
```json
{
    "id": "uuid",
    "type": "success|error|info|warning",
    "title": "Título del toast",
    "message": "Mensaje descriptivo",
    "target_permission": "odcsap.view",
    "timestamp": 1234567890.123,
    "metadata": {
        "numero_pedido": "P-12.03 - 12 - 2025",
        "pedido_id": "uuid"
    }
}
```

**Respuestas:** `200`

## Notificaciones - Catálogo de Correos

### `GET /api/notificaciones/tipos-correo`

**Permiso requerido:** rol **Admin**

Lista el catálogo de correos y los tipos de notificación distintos activos. Solo Admin.

**Respuestas:** `200`

### `POST /api/notificaciones/tipos-correo`

**Permiso requerido:** rol **Admin**

Agrega una fila al catálogo de correos. Solo Admin.

**Cuerpo de la petición:** `application/json` → CrearTipoCorreoRequest

**Respuestas:** `200`, `422`

### `PATCH /api/notificaciones/tipos-correo/{tipo_correo_id}`

**Permiso requerido:** rol **Admin**

Activa o desactiva una fila del catálogo de correos. Solo Admin.

**Parámetros:**

- `tipo_correo_id` (path, integer, obligatorio)

**Cuerpo de la petición:** `application/json` → ActualizarActivoTipoCorreoRequest

**Respuestas:** `200`, `422`

### `DELETE /api/notificaciones/tipos-correo/{tipo_correo_id}`

**Permiso requerido:** rol **Admin**

Elimina definitivamente una fila del catálogo de correos. Solo Admin.

**Parámetros:**

- `tipo_correo_id` (path, integer, obligatorio)

**Respuestas:** `200`, `422`

### `GET /api/notificaciones/tipos-correo/{tipo_correo_id}/preview`

**Permiso requerido:** rol **Admin**

Vista previa (asunto + HTML de ejemplo) de un correo del catálogo. Solo Admin.

**Parámetros:**

- `tipo_correo_id` (path, integer, obligatorio)

**Respuestas:** `200`, `422`

## Notificaciones - Personas y Correos

### `GET /api/notificaciones/personas-correo`

**Permiso requerido:** rol **Admin**

Lista todos los vínculos persona-correo. Solo Admin.

**Respuestas:** `200`

### `POST /api/notificaciones/personas-correo`

**Permiso requerido:** rol **Admin**

Vincula una persona a un correo del catálogo. Solo Admin.

**Cuerpo de la petición:** `application/json` → CrearLinkRequest

**Respuestas:** `200`, `422`

### `DELETE /api/notificaciones/personas-correo/persona/{email}`

**Permiso requerido:** rol **Admin**

Elimina a una persona por completo (todos sus correos vinculados). Solo Admin.

**Parámetros:**

- `email` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `DELETE /api/notificaciones/personas-correo/{link_id}`

**Permiso requerido:** rol **Admin**

Desvincula un correo específico de una persona. Solo Admin.

**Parámetros:**

- `link_id` (path, integer, obligatorio)

**Respuestas:** `200`, `422`

## Pedidos

### `GET /api/pedidos`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Lista pedidos con filtros y paginación.
Los pedidos en estado BORRADOR no se incluyen (solo NUEVO PEDIDO y posteriores).

**HU-02 y HU-07: Visualizar estado de pedidos con filtros**

Este endpoint permite a los usuarios de Mabel Trading y El Rayo visualizar
los pedidos con múltiples filtros y seguimiento del estado.

**Query Parameters:**
- `estado` (string, opcional) - Filtrar por estado (ej: "PENDIENTE_CONFIRMACION_PROVEEDOR", "CONFIRMADO_PROVEEDOR")
- `fecha_desde` (string, opcional) - Filtrar desde fecha (YYYY-MM-DD)
- `fecha_hasta` (string, opcional) - Filtrar hasta fecha (YYYY-MM-DD)
- `tipo_fecha` (string, opcional) - Columna de fecha a filtrar: "pedido" (default), "creacion", "modificacion", "entrega" o "facturacion"
- `proveedor_nombre` (string, opcional) - Búsqueda parcial por nombre de proveedor
- `numero_pedido` (string, opcional) - Búsqueda parcial por número de pedido
- `creado_por` (string, opcional) - Búsqueda parcial por usuario que creó el pedido
- `modificado_por` (string, opcional) - Búsqueda parcial por usuario que modificó por última vez el pedido
- `limit` (int, default: 50) - Límite de registros por página
- `offset` (int, default: 0) - Offset para paginación
- `solo_redistribucion` (string, opcional) - Si "true", solo pedidos aptos para redistribución
  (estado >= "CONFIRMADO POR EL RAYO" y != "CANCELADO"). Para la vista /redistribucion.
- `solo_produccion_elrayo` (string, opcional) - Si "true", restringe a NUEVO_PEDIDO/GESTIONAR_PEDIDO.
  Para la pantalla /mba3-consultas/produccion/pedidos (req. 1.8).

**Ejemplo:**
```
GET /api/pedidos?estado=PENDIENTE_CONFIRMACION_PROVEEDOR&limit=20&offset=0
GET /api/pedidos?fecha_desde=2025-01-01&fecha_hasta=2025-01-31&proveedor_nombre=RAYO
GET /api/pedidos?solo_redistribucion=true&limit=10  # Para vista de redistribución
```

**Respuesta:**
```json
{
    "status": "success",
    "data": [
        {
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "fecha_pedido": "2025-01-21",
            "proveedor_nombre": "TEXTILES EL RAYO S.A.",
            "estado": "PENDIENTE_CONFIRMACION_PROVEEDOR",
            ...
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

Returns:
    JSON con lista de pedidos y metadata de paginación

**Parámetros:**

- `solo_redistribucion` (query, string, opcional) — Si 'true', solo pedidos aptos para redistribución (estado >= CONFIRMADO POR EL RAYO, excluye CANCELADO y CANCELADO POR EL RAYO)
- `solo_pendientes_accion` (query, string, opcional) — Si 'true', solo pedidos que requieren acción (pendiente confirmación / respuesta proveedor / confirmado proveedor)
- `solo_produccion_elrayo` (query, string, opcional) — Si 'true', restringe a NUEVO_PEDIDO/GESTIONAR_PEDIDO (pantalla Producción El Rayo, req. 1.8)
- `estado` (query, string, opcional) — Filtrar por estado del pedido
- `fecha_desde` (query, string, opcional) — Filtrar desde fecha (YYYY-MM-DD)
- `fecha_hasta` (query, string, opcional) — Filtrar hasta fecha (YYYY-MM-DD)
- `tipo_fecha` (query, string, opcional) — Columna sobre la que aplica fecha_desde/fecha_hasta: 'pedido' (default), 'creacion', 'modificacion', 'entrega' o 'facturacion'
- `proveedor_nombre` (query, string, opcional) — Buscar por nombre de proveedor (parcial)
- `numero_pedido` (query, string, opcional) — Buscar por número de pedido (parcial)
- `creado_por` (query, string, opcional) — Filtrar por usuario que creó el pedido (parcial)
- `modificado_por` (query, string, opcional) — Filtrar por usuario que modificó por última vez el pedido (parcial)
- `limit` (query, integer, opcional) — Límite de registros por página
- `offset` (query, integer, opcional) — Offset para paginación
- `page` (query, integer, opcional) — Número de página (1-based, alternativa a offset)
- `page_size` (query, integer, opcional) — Tamaño de página (snake_case)
- `pageSize` (query, integer, opcional) — Tamaño de página (camelCase)

**Respuestas:** `200`, `401`, `403`, `404`, `500`, `422`

### `POST /api/pedidos`

**Permiso requerido:** `mabel.view`

Crea un pedido manualmente desde la pantalla web (HU-01 - Carga por Pantalla).

Este endpoint permite crear pedidos directamente desde la interfaz web
sin necesidad de subir un archivo Excel.

Returns:
    JSON con resultado completo de creacion del pedido

**Cuerpo de la petición:** `application/json` → CrearPedidoRequest

**Respuestas:** `200`, `422`

### `GET /api/pedidos/confirmados`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Lista pedidos para la pantalla Revisar Redistribución, ordenados por creado_en DESC.

**Filtro de estados:** Solo incluye pedidos enviados.

**Estado incluido:**
- CONFIRMADO_ENVIADO (12)

**Query Parameters:**
- `page` (int, default: 1) - Número de página
- `page_size` o `pageSize` (int, default: 50) - Registros por página
- `redistribucion_confirmada` - Si "true", solo pedidos en estado CONFIRMADO REDISTRIBUCION
- `limit` / `offset` - Alternativa para paginación (si se usan, ignoran page/page_size)

**Formato de respuesta (compatible con frontend):**
- `data`: array de pedidos; cada uno con `cabecera: { pedido_id, numero_pedido, fecha_pedido, estado, ... }`
- `total`, `page`, `pageSize`, `totalPages`

**Parámetros:**

- `fecha_desde` (query, string, opcional) — Filtrar desde fecha (YYYY-MM-DD)
- `fecha_hasta` (query, string, opcional) — Filtrar hasta fecha (YYYY-MM-DD)
- `tipo_fecha` (query, string, opcional) — Columna sobre la que aplica fecha_desde/fecha_hasta: 'pedido' (default), 'creacion', 'modificacion', 'entrega' o 'facturacion'
- `proveedor_nombre` (query, string, opcional) — Búsqueda parcial por proveedor
- `numero_pedido` (query, string, opcional) — Búsqueda parcial por número de pedido
- `creado_por` (query, string, opcional) — Búsqueda parcial por usuario creador
- `modificado_por` (query, string, opcional) — Búsqueda parcial por usuario que modificó por última vez el pedido
- `redistribucion_confirmada` (query, string, opcional) — Si 'true', solo pedidos con redistribución ya confirmada (estado CONFIRMADO REDISTRIBUCION)
- `limit` (query, integer, opcional) — Límite de registros por página
- `offset` (query, integer, opcional) — Offset para paginación
- `page` (query, integer, opcional) — Número de página (1-based, alternativa a offset)
- `page_size` (query, integer, opcional) — Tamaño de página (snake_case)
- `pageSize` (query, integer, opcional) — Tamaño de página (camelCase)

**Respuestas:** `200`, `422`

### `GET /api/pedidos/creadores`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Devuelve la lista de usuarios (creado_por) que han creado al menos un
pedido, para el <select> de "Creado Por" del contenedor "Filtros de
Búsqueda". Antes era un input de texto libre; se reemplazó por un
selector para no obligar al usuario a adivinar qué escribir.

**Ejemplo:**
```
GET /api/pedidos/creadores
```

**Respuesta:**
```json
{
    "status": "success",
    "data": ["ana.torres@mabeltrading.com.ec", "SYSTEM", "cortiz@mabeltrading.com.ec"]
}
```

Returns:
    JSON con lista de valores distintos de creado_por

**Respuestas:** `200`, `401`, `403`, `404`, `500`

### `GET /api/pedidos/estados`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Devuelve la lista de estados de pedido disponibles para el dropdown
del contenedor "Filtros de Búsqueda".

Este endpoint alimenta los selects/dropdowns de filtro por estado en todas
las interfaces de listas de pedidos. Devuelve únicamente los estados que
el usuario visualiza en la UI, consultados directamente de la tabla
maestra `pedido_estado`.

**Query Parameters:**
- `contexto` (string, opcional) - Determina qué estados incluir:
  - Sin valor / `null`: todos los estados activos
  - `"pedidos"`: excluye BORRADOR (para /mba3-consultas/pedidos)
  - `"cargar-plantilla"`: incluye BORRADOR (para /mba3-consultas/cargar-plantilla)
  - `"redistribucion"`: solo estados del flujo de redistribución
    (CONFIRMADO POR EL RAYO en adelante, sin CANCELADO ni finales)

**Ejemplo:**
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
        ...
    ]
}
```

Returns:
    JSON con lista de estados disponibles para el filtro

**Parámetros:**

- `contexto` (query, string, opcional) — Contexto de la vista para filtrar estados relevantes. Valores posibles: 'pedidos' (excluye BORRADOR), 'cargar-plantilla' (incluye BORRADOR, solo del flujo de carga), 'redistribucion' (solo estados aptos para redistribucion), 'produccion' (solo NUEVO_PEDIDO/GESTIONAR_PEDIDO, pantalla Producción El Rayo, req. 1.8). Si no se indica, devuelve todos los estados activos.

**Respuestas:** `200`, `401`, `403`, `404`, `500`, `422`

### `GET /api/pedidos/existe`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Verifica si existe al menos un pedido guardado en la base de datos.

Este endpoint es útil para el frontend para determinar si debe mostrar
el botón "Gestionar Pedido" o cualquier otra funcionalidad relacionada
con pedidos existentes.

**Respuesta:**
```json
{
    "status": "success",
    "tiene_pedidos": true,
    "message": "Existen pedidos en el sistema"
}
```

Returns:
    JSON indicando si hay pedidos guardados

**Respuestas:** `200`

### `GET /api/pedidos/modificadores`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Devuelve la lista de usuarios (modificado_por) que han modificado al
menos un pedido, para el <select> de "Modificado Por" del contenedor
"Filtros de Búsqueda".

**Ejemplo:**
```
GET /api/pedidos/modificadores
```

**Respuesta:**
```json
{
    "status": "success",
    "data": ["ana.torres@mabeltrading.com.ec", "SYSTEM", "cortiz@mabeltrading.com.ec"]
}
```

Returns:
    JSON con lista de valores distintos de modificado_por

**Respuestas:** `200`, `401`, `403`, `404`, `500`

### `GET /api/pedidos/ultimo-redistribucion`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Obtiene el último pedido para la pantalla Revisar Redistribución.

**Filtro de estados:** Solo incluye pedidos enviados.

**Estado incluido:**
- CONFIRMADO_ENVIADO (12)

Para la pantalla Revisar Redistribución: al entrar en /redistribucion sin número de pedido,
el front llama a este endpoint y, si hay resultado, redirige a
/pedidos/{numero_pedido}/redistribucion.

**Query Parameters:**
- `solo_usuario` (bool, default: true) - Si true, último pedido del usuario; si false, último global.

**Respuesta:** Objeto con cabecera básica (pedido_id, numero_pedido, estado, ...) o null.

**Comportamiento por permiso:**
- Usuario con solo odcsap.view (EL RAYO): se ignora solo_usuario y se devuelve siempre
  el último pedido visible en el sistema (sin filtrar por creado_por).
- Usuario con mabel.view (MABEL): se respeta solo_usuario (true = último del usuario,
  false = último global).

**Parámetros:**

- `solo_usuario` (query, boolean, opcional) — Si true, último pedido apto para redistribución del usuario; si false, último en todo el sistema

**Respuestas:** `200`, `422`

### `DELETE /api/pedidos/{pedido_id}`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Eliminar un pedido (Descartar o Cancelar Pedido).

**Dos flujos en el frontend:**

1. **Descartar (Cargar Plantilla)**: llamar sin `notificar_el_rayo` o con `notificar_el_rayo=false`.
   - Interfaz: `/cargar-plantilla/{numero_pedido}`
   - Estados permitidos: **BORRADOR (1)** y **NUEVO PEDIDO (2)**
   - Si el estado es **BORRADOR (1)**: NO envia email (solo elimina).
   - Si el estado es **NUEVO PEDIDO (2)**: envia email a EL RAYO notificando el descarte.

2. **Cancelar Pedido (Redistribucion)**: llamar con `notificar_el_rayo=true`.
   - Interfaz: `/redistribucion`
   - Borra el pedido **y** envia correo a EL RAYO.
   - Permitido solo en estados **anteriores** a Confirmado redistribucion (estado_id < 10).

**Nota:** Para cancelar desde **Detalle del Pedido** (estado CONFIRMADO POR PRODUCCION),
usar el endpoint `/api/pedidos/{pedido_id}/cancelar-por-el-rayo` en su lugar
(ya no borra el pedido: cambia su estado a CANCELADO POR EL RAYO).

**Restricciones:**
- No se permite si el pedido tiene respuesta de proveedor, redistribucion confirmada u orden de compra

**Respuestas:**
- **204**: Pedido eliminado correctamente
- **400**: Pedido no esta en estado permitido
- **404**: Pedido no encontrado
- **409**: Pedido tiene informacion asociada

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido a eliminar
- `notificar_el_rayo` (query, boolean, opcional) — Si True, envia correo a EL RAYO notificando la cancelacion (usar solo desde 'Cancelar Pedido' en Redistribucion). Si False, determina automaticamente si notificar segun el estado del pedido.

**Respuestas:** `204`, `422`

### `POST /api/pedidos/{pedido_id}/aceptar-produccion-pospuesta`

**Permiso requerido:** `mabel.view`

Aceptar la diferencia pospuesta de un pedido "hijo" (boton "Aceptar").

**Usado desde:** Detalle del pedido / Cargar Plantilla, boton "Aceptar" sobre
un pedido en PRODUCCION POSPUESTA (estado_id = 22).

**Comportamiento:**
- Cambia el estado del pedido a LISTO PARA REDISTRIBUCION (estado_id = 25).
- El pedido entra directo a la cola de redistribucion (vista /redistribucion),
  sin pasar por "Confirmado por El Rayo".

**Restricciones:**
- Solo permitido si el pedido esta en PRODUCCION POSPUESTA (estado_id = 22).

**Respuestas:**
- **200**: Pedido aceptado correctamente, devuelve el pedido actualizado.
- **404**: Pedido no encontrado.
- **400**: Pedido no esta en estado Produccion Pospuesta.
- **500**: Error interno.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido a aceptar

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/cancelar`

**Permiso requerido:** `mabel.view`

Cancelar un pedido (cambiar estado a CANCELADO y notificar a EL RAYO).

**Usado desde:**
- Vista Redistribucion, boton "Cancelar Pedido".
- Detalle del pedido / Cargar Plantilla, boton "Rechazar" sobre un pedido
  "hijo" en PRODUCCION POSPUESTA (estado_id = 22): en ese caso el destino
  es RECHAZADO (estado_id = 24) en vez de CANCELADO, sin correo a EL RAYO.

**Comportamiento:**
- Cambia el estado del pedido a CANCELADO (estado_id = 19), o a RECHAZADO
  (estado_id = 24) si el pedido estaba en PRODUCCION POSPUESTA.
- Envia correo a EL RAYO notificando la cancelacion (no aplica para RECHAZADO).
- **No elimina** el pedido de la base de datos.

**Restricciones:**
- Solo permitido en estados anteriores a Confirmado redistribucion (estado_id < 10).
- El boton debe estar deshabilitado desde Confirmado redistribucion en adelante.

**Respuestas:**
- **200**: Pedido cancelado correctamente, devuelve el pedido actualizado.
- **404**: Pedido no encontrado.
- **400**: Pedido no esta en estado permitido para cancelar.
- **500**: Error interno.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido a cancelar

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/cancelar-por-el-rayo`

**Permiso requerido:** `odcsap.view`

Cancelar un pedido desde la interfaz de Detalle del Pedido (boton "Cancelar Pedido").

**Uso exclusivo:**
- Interfaz: **Detalle del Pedido** (`/pedidos/{pedido_id}`)
- Permiso: **odcsap.view** (Administracion El Rayo) unicamente
- Estado permitido: **CONFIRMADO POR PRODUCCION (23)** unicamente, una vez que
  Produccion ya confirmo el pedido (req. 1.8 segunda fase)
- Comportamiento: Cambia estado a CANCELADO POR EL RAYO (20) y notifica a MABEL
  TRADING y a Produccion El Rayo (ella habia confirmado el pedido)

**Notificaciones:**
- ✅ Se envia correo a MABEL TRADING y a Produccion El Rayo ("Pedido Cancelado
  por El Rayo", catalogo MABEL_TRADING + PRODUCCION_ELRAYO)
- ✅ Se envia notificacion en tiempo real a MABEL TRADING y a Produccion El Rayo

**Diferencia con "Cancelar Pedido" de MABEL:**
- "Cancelar Pedido" (MABEL): Desde Redistribucion, estados < 10, cambia a CANCELADO (19)
- "Cancelar Pedido" (EL RAYO): Desde Detalle, estado 23 (Confirmado por Produccion)
  solamente, cambia a CANCELADO POR EL RAYO (20)

**Respuestas:**
- **200**: Pedido cancelado correctamente
- **400**: Pedido no esta en estado CONFIRMADO POR PRODUCCION (23)
- **404**: Pedido no encontrado

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido a cancelar

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/confirmar-para-redistribucion`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Confirmar pedido para redistribución (ESTADO_REDISTRIBUCION).

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/confirmar-produccion`

**Permiso requerido:** `produccion-elrayo.view`

Confirma el pedido desde Producción El Rayo (req. 1.8, botón "Confirmar Producción",
exclusivo de produccion-elrayo.view).

Solo válido en estado GESTIONAR PEDIDO (3); transiciona a CONFIRMADO POR PRODUCCION
(23) y notifica por correo a Administración El Rayo (odcsap.view). Administración
El Rayo continúa el flujo normal desde ahí con el botón "Confirmar" existente.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/descargar-csv`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Descargar informacion del pedido en formato Excel (.xlsx).

**Uso:**
- Interfaz: Detalle del Pedido (`/pedidos/{pedido_id}`)
- Boton: "Descargar Excel"
- Estado requerido: **CONFIRMADO (4)** (ESTADO_REDISTRIBUCION)

**Contenido del Excel:**
- Informacion de cabecera del pedido
- Detalles de todos los articulos
- Distribuciones por tienda

**Formato:**
- Archivo Excel (.xlsx) con 3 hojas:
  - Hoja 1: Informacion de cabecera
  - Hoja 2: Detalles de articulos
  - Hoja 3: Distribucion por tiendas

**Respuestas:**
- **200**: Archivo Excel descargado correctamente
- **400**: Pedido no esta en estado CONFIRMADO (4)
- **404**: Pedido no encontrado

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido a descargar

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/descargar-excel`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Descargar informacion del pedido en formato Excel (.xlsx).

**Uso:**
- Interfaz: Detalle del Pedido (`/pedidos/{pedido_id}`)
- Boton: "Descargar Excel"
- Estado requerido: **CONFIRMADO (4)** (ESTADO_REDISTRIBUCION)

**Contenido del Excel:**
- Informacion de cabecera del pedido
- Detalles de todos los articulos
- Distribuciones por tienda

**Formato:**
- Archivo Excel (.xlsx) con 3 hojas:
  - Hoja 1: Informacion de cabecera
  - Hoja 2: Detalles de articulos
  - Hoja 3: Distribucion por tiendas

**Respuestas:**
- **200**: Archivo Excel descargado correctamente
- **400**: Pedido no esta en estado CONFIRMADO (4)
- **404**: Pedido no encontrado

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido a descargar

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/enviar`

**Permiso requerido:** `mabel.view`

Enviar pedido a EL RAYO: cambia estado de BORRADOR a NUEVO_PEDIDO y envía notificación por correo.

Solo se permite para pedidos en estado BORRADOR (estado_id = 1).
Valida que el pedido tenga detalles. Si el correo falla, el pedido se marca como enviado
igualmente; la respuesta incluye email_enviado: true/false.

- **404**: Pedido no encontrado.
- **400**: Pedido no en BORRADOR o sin detalles.
- **200**: Pedido enviado (estado actualizado; email_enviado indica si el correo se envió).

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido a enviar a EL RAYO

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/gestionar`

**Permiso requerido:** `odcsap.view` o `mabel.view` o `produccion-elrayo.view` (cualquiera de ellos)

Marca el pedido como GESTIONAR PEDIDO (al hacer clic en "Ver Detalle" desde la tabla Pedidos).
Si el pedido está en estado NUEVO PEDIDO, actualiza a GESTIONAR PEDIDO y devuelve el pedido completo.
Si ya está en otro estado, solo devuelve el pedido sin cambiar estado.

Incluye produccion-elrayo.view (req. 1.8 segunda fase): NUEVO_PEDIDO/GESTIONAR_PEDIDO
son los únicos 2 estados que este perfil gestiona.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/marcar-despachar-y-facturar`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Marca el pedido como Despachar y Facturar.

- Actualiza el estado a DESPACHAR_Y_FACTURAR.
- Envía notificación en tiempo real a otros EL RAYO.
- Envía correo a MABEL TRADING informando que el pedido fue marcado como
  "Despachar y Facturar" (best-effort; si falla el email no se rompe el flujo).

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/marcar-finalizado`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Marca el pedido como FINALIZADO.

- Actualiza el estado a FINALIZADO.
- Envía notificación en tiempo real a otros EL RAYO.
- Envía correo a EL RAYO (OPERACIONES) notificando que MABEL TRADING
  finalizó el pedido (best-effort; si falla el email no se rompe el flujo).

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

### `POST /pedidos/importar-excel`

**Permiso requerido:** `mabel.view`

Importa y parsea un archivo Excel de pedido en formato v1.0.

**Formato esperado (Template_Pedido_Inicial_v1.0.xlsx):**
- **Hoja 1: "cabecera"** - Formato clave-valor (Campo | Valor | Ejemplo)
- **Hoja 2: "detalle"** - Formato tabular con:
  - Columnas A-I: Informacion del producto (CODIGO PRODUCTO, CODIGO BARRAS, DESCRIPCION, etc.)
  - Columnas J-L: Bodegas centrales (RL-CD, OUT-CD, RG-CD) - NO incluidas en SUBTOTAL
  - Columnas M+: Tiendas individuales - SI incluidas en SUBTOTAL (parsea hasta ultima columna con informacion)

**Solo parsing tecnico:** lee, normaliza y valida estructura.
NO aplica reglas de negocio, NO consolida duplicados.
NO calcula SUBTOTAL ni TOTAL - solo parsea los valores que contiene el Excel.

**Validaciones tecnicas:**
- Extension: .xlsx
- Tamano maximo: 10 MB
- Hojas obligatorias: "cabecera" y "detalle" (en minusculas)
- Columnas obligatorias en detalle: CODIGO PRODUCTO (columna A)
- Parsea desde columna M (indice 12) hasta la ultima columna con informacion

**Estructura de respuesta:**
```json
{
    "cabecera": {...},
    "resumen": {
        "filasLeidas": 120,
        "filasValidas": 115,
        "filasInvalidas": 5
    },
    "errores": [...],
    "data": [...]
}
```

Returns:
    JSON con resultado del parsing tecnico incluyendo cabecera y detalle

**Parámetros:**

- `hoja_cabecera` (query, string, opcional) — Nombre de la hoja de cabecera (default: 'cabecera')
- `hoja_detalle` (query, string, opcional) — Nombre de la hoja de detalle (default: 'detalle')
- `validar_sap` (query, boolean, opcional) — Validar codigos de producto contra SAP
- `sap_obligatorio` (query, boolean, opcional) — Si True, errores de SAP bloquean la importacion. Si False, solo genera warnings

**Cuerpo de la petición:** `multipart/form-data` → Body_importar_excel_pedido_pedidos_importar_excel_post

**Respuestas:** `200`, `422`

## Pedidos - Auditoría

### `GET /api/pedidos/{numero_pedido}/audit-log`

**Permiso requerido:** `odcsap.view` o `mabel.view` o `produccion-elrayo.view` (cualquiera de ellos)

Obtiene el historial completo de auditoría (pedido_audit_log) de un pedido:
quién hizo cada cambio, cuándo, y valor anterior/nuevo. Más reciente primero.
Requiere odcsap.view, mabel.view o produccion-elrayo.view (a produccion-elrayo.view
se le ocultan los cambios de costo unitario, RN-03).

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido o pedido_id (UUID); el backend acepta ambos.

**Respuestas:** `200`, `422`

## Pedidos - Confirmaciones

### `GET /api/pedidos/{pedido_id}/confirmaciones-rayo`

**Permiso requerido:** `odcsap.view`

Obtiene el historial de confirmaciones realizadas por EL RAYO para un pedido.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido
- `limit` (query, integer, opcional) — Número máximo de confirmaciones a retornar (opcional)

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/confirmaciones-rayo/{confirmacion_id}`

**Permiso requerido:** `odcsap.view`

Obtiene el detalle completo de una confirmación específica de EL RAYO.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido
- `confirmacion_id` (path, string, obligatorio) — UUID de la confirmación

**Respuestas:** `200`, `422`

## Pedidos - Edicion

### `PUT /api/pedidos/{pedido_id}`

**Permiso requerido:** `odcsap.view` o `mabel.view` o `produccion-elrayo.view` (cualquiera de ellos)

Modifica la cabecera de un pedido (HU-03 - Modificacion de pedidos).

Este endpoint permite modificar los datos de la cabecera del pedido.

Returns:
    JSON con resultado de la modificacion

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Cuerpo de la petición:** `application/json` → ModificarPedidoCabeceraRequest

**Respuestas:** `200`, `422`

## Pedidos - Edición

### `PATCH /api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/comentario`

**Permiso requerido:** `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Actualiza el comentario de una línea de detalle del pedido. Requiere odcsap.view o produccion-elrayo.view.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido o pedido_id (UUID); el backend acepta ambos.
- `pedido_detalle_id` (path, string, obligatorio) — UUID del detalle del pedido

**Cuerpo de la petición:** `application/json` → ActualizarComentarioRequest

**Respuestas:** `200`, `422`

### `PATCH /api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/costo`

**Permiso requerido:** `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Actualiza el costo unitario de una línea de detalle del pedido. Requiere odcsap.view o produccion-elrayo.view (estado GESTIONAR PEDIDO o CONFIRMADO POR PRODUCCIÓN). Devuelve totales recalculados.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido o pedido_id (UUID); el backend acepta ambos.
- `pedido_detalle_id` (path, string, obligatorio) — UUID del detalle del pedido

**Cuerpo de la petición:** `application/json` → ActualizarCostoRequest

**Respuestas:** `200`, `422`

### `PATCH /api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/total`

**Permiso requerido:** `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Actualiza el total de una línea de detalle del pedido. Requiere odcsap.view o produccion-elrayo.view (estado GESTIONAR PEDIDO o CONFIRMADO POR PRODUCCIÓN). Devuelve totales recalculados.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido o pedido_id (UUID); el backend acepta ambos.
- `pedido_detalle_id` (path, string, obligatorio) — UUID del detalle del pedido

**Cuerpo de la petición:** `application/json` → ActualizarTotalRequest

**Respuestas:** `200`, `422`

## Pedidos - El Rayo

### `GET /api/pedidos/{pedido_id}/exportar-plano-mba`

**Permiso requerido:** `odcsap.view`

Exporta un pedido en formato plano (.txt) para importar en MBA.

**HU-08**: Permite a usuarios de El Rayo descargar el pedido en archivo plano
para subirlo en el sistema MBA.

**Formato de archivo**

Genera un archivo .txt compatible con el formato de importación de
**Pedidos de Clientes** de MBA (ENTERPRISE SOFTWARE SOLUTIONS):

- **35 columnas** separadas por TAB
- **19 líneas de encabezado** (se eliminan automáticamente al importar en MBA)
- Una línea por producto, con la cantidad consolidada de todas sus tiendas
  (o una línea por combinación producto-tienda si se pide `consolidado=false`)

**Parámetros de configuración (valores por defecto para "Descargar para MBA")**

Del sistema se toman: Pedido Manual, Orden Compra Cliente, Código Producto,
Precio Final. Columnas fijas: A=secuencial, B=número pedido (agrupa),
C=CLI1795, G=moneda US, AI=secuencial.

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| codigo_cliente | CLI1795 | Código del cliente en MBA |
| codigo_subcliente | (vacío) | Subcategoría del cliente (opcional) |
| moneda | US | Divisa local (dólar) |
| vendedor | (vacío) | Código del vendedor |

Requiere que el pedido esté en estado **CONFIRMADO Y ENVIADO** (la ODC ya fue
enviada y aceptada por SAP), ya que la columna 12 depende del DocNum de SAP.

Columna H (Bodega) es fija: siempre se exporta como `BPT`.
Columna 20 (Sucursal) es fija: siempre se exporta como `PRI`.
Columna 10 (Pedido Manual): número de pedido interno.
Columna 12 (Orden Compra Cliente): DocNum de la Orden de Compra ya enviada a SAP
(tabla orden_compra_cabecera.numero_oc_sap). Vacía si el pedido no tiene una OC
con DocNum registrado.
Columnas 5 y 6 (Fecha Pedido / Fecha Entrega): ambas usan la fecha en que el
pedido pasó a estado CONFIRMADO POR EL RAYO (clic en "Confirmar" en el detalle
del pedido), no la fecha capturada originalmente en el Excel. Si el pedido no
tiene ese registro en la bitácora de estados, se exportan vacías (00/00/0000).

**Modos de exportación**

- **consolidado=True** (predeterminado): Consolida las cantidades y genera una
  línea por producto. Como la columna Sucursal es fija (`PRI`), una línea por
  tienda ya no aporta información distinguible entre tiendas.
- **consolidado=False**: Genera una línea por cada combinación producto-tienda
  (sin agrupar), por si se necesita esa granularidad para otro fin.

**Ejemplo de línea generada**

```
91      3       CLI0495 GO05    29/10/2025      31/10/2025      US      BPT     JPC     CQ287341                1524                                            TRUE    FALSE   PRI     R469.911.CCL    6       FALSE   6.16    TRUE                                                            0       FALSE   91
```

Returns:
    Archivo .txt descargable en formato MBA

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido o número de pedido
- `codigo_cliente` (query, string, opcional) — Código de cliente MBA (por defecto CLI1795)
- `codigo_subcliente` (query, string, opcional) — Código de subcliente MBA (dejar vacío si no aplica)
- `moneda` (query, string, opcional) — Moneda/divisa local (por defecto US dólar)
- `vendedor` (query, string, opcional) — Código de vendedor MBA
- `numero_pedido_mba` (query, integer, opcional) — Número de pedido temporal para agrupar líneas en MBA (col. B)
- `consolidado` (query, boolean, opcional) — Si True, consolida cantidades por producto; si False, una línea por tienda/sucursal
- `incluir_encabezado` (query, boolean, opcional) — Incluir las 19 líneas de encabezado del formato MBA
- `codigo_bodega` (query, string, opcional) — Código de bodega (ej. RL-CD, RG-CD) para pedidos con más de una ODC -- limita la exportación a esa bodega y usa el DocNum de su propia ODC. Omitir en pedidos con una sola ODC.

**Respuestas:** `200`, `422`

## Pedidos - Exportación

### `GET /api/pedidos/{pedido_id}/descargar-pedido`

**Permiso requerido:** `mabel.view` o `odcsap.view` (cualquiera de ellos)

Descarga un pedido como archivo Excel con el formato de "Descargar Pedido".

Genera un archivo Excel (.xlsx) con una sola hoja llamada "datos" que combina
una cabecera tipo formulario con una tabla de detalle de productos.

**Uso:**
- Interfaz: Detalle del Pedido (`/pedidos/{pedido_id}`)
- Botón: "Descargar Pedido"
- Estado requerido: **GESTIONAR PEDIDO (3)** o superior

**Estructura del Excel:**
- Filas 1-4: Cabecera del pedido (columnas D y E)
- Filas 5-11: Información complementaria (columnas D y E)
- Fila 13: Encabezados de la tabla de productos (columnas B a J)
- Fila 14+: Datos de productos

**Respuestas:**
- **200**: Archivo Excel descargado correctamente
- **400**: Pedido no está en estado GESTIONAR PEDIDO o superior
- **404**: Pedido no encontrado

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/descargar-pedido-original`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Descarga el pedido **con los valores originales** (antes de ediciones).

Genera un archivo Excel (.xlsx) idéntico en formato al de "Descargar Pedido"
(logo ROLAND, colores corporativos, misma estructura), pero lee los datos
de las tablas `pedido_original` y `pedido_detalle_original`, que almacenan
una copia inmutable de los valores al momento del envío.

**Uso:**
- Interfaz: Detalle del Pedido (`/pedidos/{pedido_id}`)
- Botón: "Descargar Pedido Original"
- Estado requerido: **GESTIONAR PEDIDO (3)** o superior

**Estructura del Excel:**
- Filas 1-4: Cabecera del pedido (columnas D y E)
- Filas 5-11: Información complementaria (columnas D y E)
- Fila 13: Encabezados de la tabla de productos (columnas B a J)
- Fila 14+: Datos de productos con valores originales

**Respuestas:**
- **200**: Archivo Excel descargado correctamente
- **404**: Pedido no encontrado o sin snapshot original

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/margen/exportar-excel`

**Permiso requerido:** `mabel.view` o `odcsap.view` (cualquiera de ellos)

Exporta el Análisis de Margen de Rentabilidad por producto (req. 1.4/1.5).

Una fila por producto del pedido con PVP, Costo (columna informativa de la
plantilla Excel, req. 1.4), Costo Unitario (insumo real del cálculo) y el
Margen de Rentabilidad (`1 - (Costo Unitario / (PVP / 1.15))`).

**Uso:**
- Interfaz: Cargar Plantilla / pantalla de carga por producto
- Botón: "Descargar Análisis de Margen"

Sin restricción de estado: disponible en cuanto el pedido tiene productos
cargados. **No** incluye el permiso `produccion-elrayo.view` (RN-03: ese
perfil no debe acceder a costos, precios ni márgenes).

**Respuestas:**
- **200**: Archivo Excel descargado correctamente
- **404**: Pedido no encontrado

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido o número de pedido

**Respuestas:** `200`, `422`

## Pedidos - Modificaciones

### `GET /api/pedidos/{numero_pedido}/modificaciones-columnas`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Obtiene las modificaciones de columnas para un pedido.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido o pedido_id (UUID); el backend acepta ambos.

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{numero_pedido}/modificaciones-columnas`

**Permiso requerido:** `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Guarda o actualiza las modificaciones de columnas para un pedido. Requiere odcsap.view o produccion-elrayo.view.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido o pedido_id (UUID); el backend acepta ambos.

**Cuerpo de la petición:** `application/json` → GuardarModificacionesColumnasRequest

**Respuestas:** `200`, `422`

## Pedidos - ODC

### `POST /api/pedidos/{identificador}/crear-orden-compra`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Crea una orden de compra desde un pedido confirmado (botón «Generar ODC»).

Al crear/actualizar la ODC se genera también el JSON que se enviará a SAP Service Layer.
La respuesta incluye `sap_request_json` con ese payload (CardCode, DocumentLines con ItemCode
y WarehouseCode) para mostrarlo en UI o depurar errores -2028.

**Parámetros:**

- `identificador` (path, string, obligatorio) — UUID del pedido o número de pedido (ej: 'P-12.55 - 12 - 2025')

**Respuestas:** `200`, `422`

## Pedidos - Proveedor

### `POST /api/pedidos/{pedido_id}/cargar-respuesta-proveedor`

**Permiso requerido:** `mabel.view`

Carga la respuesta del proveedor desde un archivo Excel.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Cuerpo de la petición:** `multipart/form-data` → Body_cargar_respuesta_proveedor_api_pedidos__pedido_id__cargar_respuesta_proveedor_post

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/confirmar-con-diferencia`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Req. 1.2 (pedidos parciales, + N hijos): opción "Confirmar pedido, generar
nuevo pedido con la diferencia" del modal de diferencia de producción. Confirma
el pedido padre una sola vez (mismo flujo que crear-respuesta-desde-pedido,
notificando por correo a MABEL_TRADING con "Pedido Confirmado por El Rayo",
igual que los otros dos casos de confirmación) y crea uno o más pedidos hijo
(numero_pedido = "<padre>.NN"), cada uno con la porción de la diferencia y la
fecha de entrega indicadas en body.hijos, en estado PRODUCCION POSPUESTA. El
reparto entre hijos debe cubrir exactamente el 100% de cada línea con
diferencia (400 "reparto_invalido" si no cuadra). A diferencia de los otros dos
casos, este correo incluye además una sección "Acción Requerida" con un enlace
por cada pedido hijo generado, guiando a MABEL TRADING a revisarlos en Cargar
Plantilla y decidir Aceptar/Rechazar.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Cuerpo de la petición:** `application/json` → ConfirmarConDiferenciaRequest

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/crear-respuesta-desde-pedido`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Guarda los cambios de EL RAYO, crea la respuesta del proveedor y deja el pedido en
estado CONFIRMADO (confirmar = ir a redistribución).

Req. 1.2 (endurecimiento 2026-08-17): rechaza (400, error
'diferencia_produccion_no_reconocida') si el pedido tiene productos con Total por
debajo de cantidad_solicitada_original y el body no envía diferencia_reconocida=true.
Antes esta regla vivía solo como gate de UI -- ver
docs/requeriments/PYTD002_ODC-MABEL-RAYO_SEGUIMIENTO.md.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Cuerpo de la petición:** `application/json` → ConfirmarRespuestaRequest

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/diferencia-produccion`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Req. 1.2 (pedidos parciales): indica si algún producto del pedido tiene un
Total actual por debajo de la cantidad_solicitada_original (plantilla Excel).
El frontend lo consulta al hacer clic en "Confirmar" para decidir si mostrar
el modal de diferencia de producción.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/enviar-respuesta-proveedor`

**Permiso requerido:** `mabel.view`

Recibe la respuesta del proveedor desde el formulario web.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Cuerpo de la petición:** `application/json` → RespuestaProveedorRequest

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/exportar-para-proveedor`

**Permiso requerido:** `mabel.view`

Exporta un pedido a Excel para que el proveedor lo complete.

**Formato exportado:**
- Hoja RESUMEN: Totales solicitados por producto (consolidado) - **OBLIGATORIO completar**
- Hoja DETALLE_TIENDAS: Distribución por tienda - **OPCIONAL** (solo si el proveedor quiere especificar)
- Hoja INSTRUCCIONES: Guía de uso

**Modelo de respuesta:**
- El proveedor responde principalmente por PRODUCTO (consolidado)
- Puede opcionalmente especificar distribución por tienda
- Si no especifica por tienda, el sistema distribuye proporcionalmente

Returns:
    Archivo Excel descargable

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/formulario-proveedor`

**Permiso requerido:** `mabel.view`

Obtiene los datos del pedido formateados para el formulario web del proveedor.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

## Pedidos - Redistribución

### `GET /api/pedidos/proceso-sap/resultado/{process_id}`

**Permiso requerido:** `mabel.view`

Obtiene el resultado del proceso completo SAP ejecutado en segundo plano.
Usar el process_id devuelto por POST .../proceso-completo-sap-async.

**Parámetros:**

- `process_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `GET /api/pedidos/proceso-sap/stream/{process_id}`

**Permiso requerido:** `mabel.view`

Stream SSE del progreso del proceso completo SAP.
Mismo formato que plantillas/stream y cruce-productos/stream.

**Parámetros:**

- `process_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `GET /api/pedidos/tiendas/buscar`

**Permiso requerido:** `mabel.view`

Busca tiendas activas del catálogo maestro por nombre o código.

**Parámetros:**

- `q` (query, string, opcional) — Texto a buscar en código o nombre de tienda (búsqueda parcial)
- `limit` (query, integer, opcional) — Límite de resultados

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{numero_pedido}/proceso-completo-sap`

**Permiso requerido:** `mabel.view`

Proceso completo: Redistribución + Generar ODC + Enviar a SAP.

La lógica pesada (BD, SAP, email) se ejecuta en un thread separado
para no bloquear el event loop de asyncio (~40s de operaciones síncronas).
Para ejecución en segundo plano con Celery, usar POST .../proceso-completo-sap-async.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido

**Cuerpo de la petición:** `application/json` → RedistribucionConfirmarRequest

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{numero_pedido}/proceso-completo-sap-async`

**Permiso requerido:** `mabel.view`

Encola el proceso completo SAP (Redistribución + ODC + Envío a SAP) en Celery.

Responde de inmediato con 202 y process_id. El resultado se consulta con
GET /api/pedidos/proceso-sap/resultado/{process_id} o
GET /api/pedidos/proceso-sap/stream/{process_id}.

Si Redis/Celery no están disponibles o no hay workers, se ejecuta automáticamente
en primer plano y se devuelve 200 con el resultado ("fallback": "sync",
process_id: null, async: false). Con force_sync=true se ejecuta siempre en
primer plano (200 + resultado, misma forma que sync).

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido
- `force_sync` (query, boolean, opcional) — Si True, ejecuta en primer plano y devuelve 200 con el resultado (útil si el worker no está disponible)

**Cuerpo de la petición:** `application/json` → RedistribucionConfirmarRequest

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{numero_pedido}/redistribucion/ajustar-bodegas`

**Permiso requerido:** `mabel.view`

Retorna los datos de redistribución sin ajustar automáticamente las bodegas.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido

**Cuerpo de la petición:** `application/json` → RedistribucionConfirmarRequest

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{numero_pedido}/redistribucion/borrador`

**Permiso requerido:** `mabel.view` o `odcsap.view` (cualquiera de ellos)

Obtiene el borrador de redistribución guardado.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{numero_pedido}/redistribucion/borrador`

**Permiso requerido:** `mabel.view`

Guarda un borrador de redistribución.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido

**Cuerpo de la petición:** `application/json` → GuardarBorradorRequest

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{numero_pedido}/redistribucion/confirmar`

**Permiso requerido:** `mabel.view`

Confirma una redistribución (compatible con frontend).

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido

**Cuerpo de la petición:** `application/json` → RedistribucionConfirmarRequest

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{numero_pedido}/redistribucion/inicial`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Obtiene los datos iniciales para la redistribución sincronizados con el pedido actualizado.

**Parámetros:**

- `numero_pedido` (path, string, obligatorio) — Número del pedido
- `solo_lectura` (query, string, opcional) — Si es '1' o 'true', devuelve la última redistribución confirmada (para vista solo lectura)

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/confirmar-redistribucion`

**Permiso requerido:** `mabel.view`

Confirma una redistribución, cambiando su estado a 'CONFIRMADO'.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Cuerpo de la petición:** `application/json` → ConfirmarRedistribucionRequest

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/distribucion`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Obtiene la distribución confirmada de un pedido.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido
- `version` (query, integer, opcional) — Versión específica (si no se especifica, obtiene la última)

**Respuestas:** `200`, `422`

### `POST /api/pedidos/{pedido_id}/redistribuir`

**Permiso requerido:** `mabel.view`

Crea una nueva redistribución para un pedido.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Cuerpo de la petición:** `application/json` → RedistribuirPedidoRequest

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/reporte-diferencias`

**Permiso requerido:** `mabel.view` o `odcsap.view` (cualquiera de ellos)

Obtiene el reporte de diferencias de una redistribución.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido
- `version` (query, integer, opcional) — Versión específica (si no se especifica, analiza la última)

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/reporte-diferencias/excel`

**Permiso requerido:** `mabel.view` o `odcsap.view` (cualquiera de ellos)

Exporta el reporte de diferencias a Excel.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido
- `version` (query, integer, opcional) — Versión específica (si no se especifica, analiza la última)

**Respuestas:** `200`, `422`

### `GET /api/pedidos/{pedido_id}/traslados/exportar-excel`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Exportar las Solicitudes de Traslado del pedido en formato Excel (.xlsx).

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido
- `version` (query, integer, opcional) — Versión específica (si no se especifica, obtiene la última)

**Respuestas:** `200`, `422`

## Pedidos - SAP

### `GET /api/pedidos/{pedido_id}/procesamiento-sap`

**Permiso requerido:** `mabel.view`

Obtiene información de procesamiento SAP de un pedido.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — UUID del pedido

**Respuestas:** `200`, `422`

## Plantillas

### `GET /api/plantillas/archivos/{archivo_id}/descargar-original`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Descarga un archivo Excel original por su ID de archivo.

**Parámetros:**

- `archivo_id` (path, integer, obligatorio) — ID del archivo original

**Respuestas:** `200`, `422`

### `GET /api/plantillas/buscar`

**Permiso requerido:** `mabel.view`

Busca pedidos por número de pedido (búsqueda parcial).

**Parámetros:**

- `numero_pedido` (query, string, opcional) — Número de pedido a buscar (búsqueda parcial)
- `limit` (query, integer, opcional) — Límite de resultados

**Respuestas:** `200`, `422`

### `GET /api/plantillas/pedidos`

**Permiso requerido:** `mabel.view`

Lista pedidos para la página cargar-plantilla (incluye estado BORRADOR).

**Parámetros:**

- `estado` (query, string, opcional) — Filtrar por estado del pedido
- `numero_pedido` (query, string, opcional) — Buscar por número de pedido (parcial)
- `limit` (query, integer, opcional) — Límite de registros por página
- `offset` (query, integer, opcional) — Offset para paginación
- `solo_pendientes_accion` (query, string, opcional) — Si 'true', solo pedidos que requieren acción del proveedor
- `creado_por` (query, string, opcional) — Búsqueda parcial por usuario que creó el pedido
- `modificado_por` (query, string, opcional) — Búsqueda parcial por usuario que modificó por última vez el pedido
- `fecha_desde` (query, string, opcional) — Filtrar desde fecha (YYYY-MM-DD)
- `fecha_hasta` (query, string, opcional) — Filtrar hasta fecha (YYYY-MM-DD)
- `tipo_fecha` (query, string, opcional) — Columna sobre la que aplica fecha_desde/fecha_hasta: 'pedido' (default), 'creacion', 'modificacion', 'entrega' o 'facturacion'

**Respuestas:** `200`, `422`

### `GET /api/plantillas/resultado/{process_id}`

**Permiso requerido:** `mabel.view`

Obtiene el resultado del procesamiento async de una plantilla.

**Parámetros:**

- `process_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `GET /api/plantillas/sap-info-productos`

**Permiso requerido:** `mabel.view`

Devuelve Pack, PVP (Precio Minorista) y código de barras de SAP para los
códigos indicados.

Pensado para el modal de corrección de plantillas: cuando el usuario elige
una sugerencia para un código inválido, permite saber en el momento si esa
elección va a implicar además una discrepancia de Pack/PVP, y resolver todo
en una sola ronda en vez de descubrirlo en el reintento siguiente.

Los códigos no resueltos vuelven con `encontrado: false` y un `motivo`
(`no_existe` | `inactivo` | `mismatch` | `null`); nunca tumban la consulta.

**Parámetros:**

- `codigos` (query, string, obligatorio) — Códigos SAP separados por coma (máx. 100). Ej: R311.AMAZ-4-1012,R311.SIE-20.1012

**Respuestas:** `200`, `422`

### `GET /api/plantillas/storage/health`

**Permiso requerido:** `mabel.view`

Verifica el estado del servicio de almacenamiento de archivos.

**Respuestas:** `200`

### `GET /api/plantillas/stream/{process_id}`

**Permiso requerido:** `mabel.view`

Stream SSE del progreso del procesamiento de plantilla.

**Parámetros:**

- `process_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `GET /api/plantillas/ultimo`

**Permiso requerido:** `mabel.view`

Obtiene el último pedido cargado por el usuario autenticado.

**Parámetros:**

- `incluir_respuesta` (query, boolean, opcional) — Incluir respuesta del proveedor si existe

**Respuestas:** `200`, `422`

### `POST /api/plantillas/upload`

**Permiso requerido:** `mabel.view`

Sube y valida una plantilla Excel para procesamiento.

**Parámetros:**

- `validar` (query, boolean, opcional) — Validar datos antes de guardar
- `bloquea_con_errores` (query, boolean, opcional) — Bloquear guardado si hay errores críticos
- `exportar_log` (query, boolean, opcional) — Incluir log de validación en respuesta (base64)
- `modo_tiendas` (query, string, opcional) — Modo de validación de tiendas: 'validar_estricto' (recomendado) | 'crear_si_no_existe' (legacy) | 'sincronizar_maestro' (admin)
- `confirmar_sincronizacion` (query, boolean, opcional) — REQUERIDO si modo_tiendas='sincronizar_maestro'. Confirma que deseas DESACTIVAR tiendas no presentes en Excel

**Cuerpo de la petición:** `multipart/form-data` → Body_upload_plantilla_api_plantillas_upload_post

**Respuestas:** `200`, `422`

### `POST /api/plantillas/upload-async`

**Permiso requerido:** `mabel.view`

Sube una plantilla Excel para procesamiento en segundo plano (Celery).
Responde de inmediato con process_id; el resultado se consulta con
GET /api/plantillas/resultado/{process_id} o GET /api/plantillas/stream/{process_id}.

Si Redis/Celery, el worker o el almacenamiento temporal no están disponibles,
ejecuta el procesamiento en primer plano como fallback sync. Con force_sync=true
se ejecuta siempre en primer plano (200 + resultado, misma forma que sync).

**Parámetros:**

- `validar` (query, boolean, opcional) — Validar datos antes de guardar
- `bloquea_con_errores` (query, boolean, opcional) — Bloquear guardado si hay errores críticos
- `modo_tiendas` (query, string, opcional) — Modo de validación de tiendas
- `confirmar_sincronizacion` (query, boolean, opcional) — Requerido si modo_tiendas='sincronizar_maestro'
- `force_sync` (query, boolean, opcional) — Si True, ejecuta en primer plano y devuelve 200 con el resultado (útil si el worker no está disponible)

**Cuerpo de la petición:** `multipart/form-data` → Body_upload_plantilla_async_api_plantillas_upload_async_post

**Respuestas:** `200`, `422`

### `GET /api/plantillas/{identificador}`

**Permiso requerido:** `odcsap.view` o `mabel.view` o `produccion-elrayo.view` (cualquiera de ellos)

Obtiene un pedido completo con cabecera, detalles y distribuciones por tienda.
Acepta número de pedido (recomendado) o UUID (para compatibilidad).
Opcionalmente incluye la respuesta del proveedor.

**Path Parameters:**
- `identificador` (string, requerido) - Puede ser:
  - Número de pedido (business key, ej: 'P-12.48 - 12 - 2025') ⭐ RECOMENDADO
  - UUID del pedido (ej: 'AEDEC52D-D007-416F-8A09-9F0D31282EEE') ⚠️ Compatibilidad

**Query Parameters:**
- `incluir_respuesta` (bool, default: false): Si true, incluye respuesta del proveedor si existe

**Respuesta exitosa:**
```json
{
    "cabecera": {...},
    "detalles": [...],
    "totales": {
        "total_costo_unitario": 1234.56,
        "total_subtotal": 1234.56,
        "total_total": 1500.00
    },
    "respuesta_proveedor": {...}
}
```
Los totales se calculan en backend (no se persisten en BD) para que todos los usuarios vean la misma suma.

Returns:
    JSON con pedido completo

**Parámetros:**

- `identificador` (path, string, obligatorio) — Número de pedido (ej: 'P-12.48 - 12 - 2025') o UUID del pedido (para compatibilidad)
- `incluir_respuesta` (query, boolean, opcional) — Incluir respuesta del proveedor si existe

**Respuestas:** `200`, `422`

### `GET /api/plantillas/{pedido_id}/descargar-original`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Descarga el archivo Excel original subido para un pedido.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — ID del pedido (GUID)

**Respuestas:** `200`, `422`

### `GET /api/plantillas/{pedido_id}/info-archivo`

**Permiso requerido:** `mabel.view` o `odcsap.view` o `produccion-elrayo.view` (cualquiera de ellos)

Obtiene información sobre el archivo Excel original de un pedido.

**Parámetros:**

- `pedido_id` (path, string, obligatorio) — ID del pedido (GUID)

**Respuestas:** `200`, `422`

## Plantillas - Archivos Originales

### `GET /api/plantillas/archivos`

**Permiso requerido:** `mabel.view` o `odcsap.view` (cualquiera de ellos)

Lista los archivos Excel originales subidos por el usuario, paginado.

**Parámetros:**

- `limit` (query, integer, opcional) — Límite de registros por página
- `offset` (query, integer, opcional) — Registros a saltar (paginación)
- `solo_activos` (query, boolean, opcional) — Solo mostrar archivos activos
- `busqueda` (query, string, opcional) — Filtra por número de pedido o nombre de archivo

**Respuestas:** `200`, `422`

### `DELETE /api/plantillas/archivos/{archivo_id}`

**Permiso requerido:** `mabel.view` o `odcsap.view` (cualquiera de ellos)

Elimina un archivo Excel original (soft delete por defecto).

**Parámetros:**

- `archivo_id` (path, integer, obligatorio) — ID del archivo a eliminar
- `eliminar_fisicamente` (query, boolean, opcional) — Si es true, elimina también del storage (MinIO)

**Respuestas:** `200`, `422`

## Preferencias de Usuario

### `GET /api/users/preferences`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Obtiene todas las preferencias del usuario actual.

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido

**Respuesta exitosa (200):**
```json
{
  "preferences": {
    "despachos": {
      "visibleColumns": ["codigo_factura", "numero_factura"],
      "columnOrder": ["codigo_factura", "numero_factura"],
      "filters": {},
      "pageSize": 10
    },
    "ordenes-compra": {
      "visibleColumns": ["oc_id", "fecha_generacion"],
      "columnOrder": ["oc_id", "fecha_generacion"],
      "filters": {},
      "pageSize": 10
    }
  }
}
```

**Respuestas:** `200`

### `GET /api/users/preferences/sidebar`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Obtiene las preferencias del sidebar para el usuario actual.

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido

**Respuesta exitosa (200):**
```json
{
  "preferences": {
    "collapsed": true
  }
}
```

**Si no existen preferencias:**
```json
{
  "preferences": null
}
```

**Respuestas:** `200`

### `POST /api/users/preferences/sidebar`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Guarda o actualiza las preferencias del sidebar.

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido
- `Content-Type: application/json`

**Body:**
```json
{
  "preferences": {
    "collapsed": false
  }
}
```

**Respuesta exitosa (200):**
```json
{
  "success": true,
  "message": "Preferencias del sidebar guardadas correctamente"
}
```

**Cuerpo de la petición:** `application/json` → SaveSidebarPreferencesRequest

**Respuestas:** `200`, `422`

### `GET /api/users/preferences/{table_id}`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Obtiene las preferencias de una tabla específica para el usuario actual.

**Parámetros:**
- `table_id`: ID de la tabla (despachos, ordenes-compra, historial-ordenes, remisiones, productos-pedido)

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido

**Respuesta exitosa (200):**
```json
{
  "preferences": {
    "visibleColumns": ["codigo_factura", "numero_factura"],
    "columnOrder": ["codigo_factura", "numero_factura"],
    "filters": {},
    "pageSize": 10
  }
}
```

**Si no existen preferencias:**
```json
{
  "preferences": null
}
```

**Parámetros:**

- `table_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `POST /api/users/preferences/{table_id}`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Guarda o actualiza las preferencias de una tabla específica.

**Parámetros:**
- `table_id`: ID de la tabla (despachos, ordenes-compra, historial-ordenes, remisiones, productos-pedido)

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido
- `Content-Type: application/json`

**Body:**
```json
{
  "preferences": {
    "visibleColumns": ["codigo_factura", "numero_factura", "empresa"],
    "columnOrder": ["codigo_factura", "empresa", "numero_factura"],
    "filters": {},
    "pageSize": 10
  }
}
```

**Respuesta exitosa (200):**
```json
{
  "success": true,
  "message": "Preferencias guardadas correctamente"
}
```

**Parámetros:**

- `table_id` (path, string, obligatorio)

**Cuerpo de la petición:** `application/json` → SavePreferencesRequest

**Respuestas:** `200`, `422`

### `DELETE /api/users/preferences/{table_id}`

**Permiso requerido:** Solo un token JWT válido (el endpoint no exige un permiso específico)

Elimina las preferencias de una tabla específica.

**Parámetros:**
- `table_id`: ID de la tabla (despachos, ordenes-compra, historial-ordenes, remisiones, productos-pedido)

**Headers requeridos:**
- `Authorization: Bearer {token}` - Token JWT válido

**Respuesta exitosa (200):**
```json
{
  "success": true,
  "message": "Preferencias eliminadas correctamente"
}
```

**Parámetros:**

- `table_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

## Procesamiento

### `GET /despachos/count`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Endpoint para obtener el conteo y información detallada de despachos con sus órdenes de compra.

**Responsabilidad:** Consultar estado (solo lectura)

**Características:**
- ✅ Cuenta despachos en despacho_cabecera que NO tienen OC asociada
- ✅ Devuelve información detallada de todas las tablas relacionadas:
  - despacho_cabecera (información de cabecera del despacho)
  - despacho_detalle (líneas de detalle del despacho)
  - orden_compra_cabecera (información de cabecera de OC si existe)
  - orden_compra_detalle (líneas de detalle de OC si existe)
- ✅ Útil para mostrar información completa en el frontend
- ✅ Permisos: solo lectura (view), no requiere execute

**Query Parameters:**
- `limit` (int, opcional) - Número máximo de registros a retornar

**Ejemplo de uso:**
```
GET /despachos/count
GET /despachos/count?limit=10
```

**Respuesta:**
```json
{
  "count": 5,
  "disponible": true,
  "despachos": [...]
}
```

**Nota:** Este endpoint solo consulta el estado, no ejecuta ningún proceso.
Para procesar los despachos, usar el endpoint GET /procesar-oc.

Returns:
    JSON con conteo, disponibilidad e información detallada de despachos y OCs

**Parámetros:**

- `limit` (query, integer, opcional) — Número máximo de registros a retornar (opcional)

**Respuestas:** `200`, `422`

### `GET /despachos/{despacho_id}/detalles`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Endpoint para obtener los detalles de un despacho específico.

**Responsabilidad:** Consultar estado (solo lectura)

**Características:**
- ✅ Obtiene todos los detalles (líneas) de un despacho específico
- ✅ Retorna información completa de cada línea de detalle
- ✅ Permisos: solo lectura (view), no requiere execute

**Path Parameters:**
- `despacho_id` (string, requerido) - UUID del despacho

**Ejemplo de uso:**
```
GET /despachos/DD7D7A51-9E57-44D4-9A8F-4A05427A8325/detalles
```

**Respuesta:**
```json
{
  "status": "success",
  "despacho_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
  "detalles": [...],
  "count": 1
}
```

Returns:
    JSON con los detalles del despacho

**Parámetros:**

- `despacho_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `GET /procesar-oc`

**Permiso requerido:** `mabel.view`

Endpoint PROCESAR-OC: Copia despachos a orden de compra.

**Responsabilidad:** PROCESAR (endpoint #3 de los 4 requeridos)

Este endpoint realiza:
1. ❌ NO consulta (ya lo hizo CONSULTAR)
2. ❌ NO guarda en despacho (ya lo hizo MIGRAR)
3. ✅ Copia despachos existentes a orden_compra_cabecera/detalle
4. ❌ NO envía a SAP (ese paso lo hace el endpoint INTEGRAR)

**Modo de uso:**
1. **Sin parámetros**: Procesa TODOS los despachos sin OC
   ```
   GET /procesar-oc
   ```

2. **Con un despacho_id**: Procesa solo un despacho específico
   ```
   GET /procesar-oc?despacho_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325
   ```

3. **Con múltiples despacho_id**: Procesa varios despachos seleccionados
   ```
   GET /procesar-oc?despacho_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325&despacho_id=ABC123-DEF456-GHI789
   ```

**Query Parameters:**
- `despacho_id` (string, opcional, múltiple) - UUID del despacho. Puede especificarse múltiples veces.

**Características:**
- ✅ Busca despachos en despacho_cabecera que NO tienen OC asociada (modo todos)
- ✅ Permite procesar despachos específicos seleccionados (modo selectivo)
- ✅ Copia cada despacho a orden_compra_cabecera/detalle
- ✅ Mapea empresa → proveedor desde tabla cliente
- ✅ Usa upsert: actualiza si existe OC, crea si no existe
- ✅ Crea las ODC con estado "PENDIENTE" (listas para enviar a SAP)
- ✅ Verifica post-commit que los datos estén sincronizados
- ✅ Retorna `process_id` único para trazabilidad

**Nota:** Este endpoint asume que los despachos ya están guardados en despacho_cabecera/detalle.
Para proceso completo (consulta + guarda + copia + integración), usar los 4 endpoints en secuencia.

**Flujo recomendado:**
1. GET /consultar - Solo consulta
2. GET /migrar - Consulta + Guarda en despacho
3. GET /procesar-oc - Copia despachos a ODC (estado: PENDIENTE)
4. POST /integrar-sap - Envía ODC a SAP usando middleware

**Estados de ODC:**
- `PENDIENTE`: Creada pero no enviada a SAP (estado inicial)
- `ENVIADA`: Enviada exitosamente a SAP (se actualiza en endpoint INTEGRAR)
- `ERROR`: Error al enviar a SAP (se actualiza en endpoint INTEGRAR)

**Respuesta:**
- HTTP Status: Siempre 200 si el proceso terminó (éxito o error parcial)
- Estado real: Ver `metadata.oc_status.status`:
  - `'completed'`: Todas las OCs se crearon exitosamente
  - `'partial'`: Algunas OCs se crearon, otras fallaron
  - `'error'`: Todas las OCs fallaron
  - `'processing'`: Proceso asíncrono (futuro, no usado actualmente)
- `process_id`: ID único para trazabilidad y debugging
- `despachos_actualizados`: true si `tiene_odc` está actualizado (verificado post-commit)
- `datos_sincronizados`: true si las OCs están disponibles para consulta

**IMPORTANTE:** El frontend debe guiarse por `metadata.oc_status.status`, NO por el HTTP status code.

Returns:
    JSON con estructura mejorada:
    {
        "status": "success" | "error",
        "process_id": "odc-YYYY-MM-DD-UUID",
        "message": "...",
        "data": {
            "oc_ids": [...],
            "despachos_procesados": [...],
            "oc_creadas": N,
            "oc_errores": N
        },
        "metadata": {
            "oc_status": {
                "status": "completed" | "partial" | "error",
                "despachos_actualizados": true | false,
                "datos_sincronizados": true | false,
                "detalles": [...]
            },
            "timestamp": "ISO-8601"
        }
    }

**Parámetros:**

- `despacho_id` (query, lista de string, opcional) — UUID(s) del despacho a procesar. Puede especificarse múltiples veces (ej: ?despacho_id=xxx&despacho_id=yyy). Si no se proporciona, procesa todos los despachos sin OC.

**Respuestas:** `200`, `422`

## Pruebas

### `GET /pruebas`

**Permiso requerido:** `mabel.view`

Endpoint de PRUEBAS: Ejecuta el proceso completo de los 3 primeros endpoints.

Este endpoint realiza el proceso completo (para pruebas):
1. ✅ Consulta datos desde MBA3 usando query predefinida (CONSULTAR)
2. ✅ Guarda resultados en SQL Server (despacho_cabecera/detalle) (MIGRAR)
3. ✅ Copia despachos a orden_compra_cabecera/detalle (PROCESAR)
4. ❌ NO envía a SAP (ese paso lo hace el endpoint INTEGRAR)

**Uso:** Endpoint de pruebas que ejecuta todo el flujo completo de los 3 primeros endpoints.

**Características:**
- ✅ Query integrada en el backend (no requiere SQL del frontend)
- ✅ Ejecuta consultas contra MBA3 automáticamente
- ✅ Guarda resultados en SQL Server (upsert)
- ✅ Copia automáticamente a orden_compra_cabecera/detalle
- ✅ Crea las ODC con estado "PENDIENTE" (listas para enviar a SAP)
- ✅ Logs detallados para debugging

**Ejemplo de uso:**
```
GET /pruebas
```

**Query predefinida:**
```sql
SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 AND ObjDatosFactura IS NOT NULL
```

**Respuesta incluye:**
- `data`: Resultados de MBA3
- `metadata.save_status`: Estado del guardado en despacho
- `metadata.oc_status`: Estado de copia a orden de compra

**Headers de respuesta:**
- `X-Saved-To-DB`: Estado del guardado
- `X-DB-Facturas`: Número de facturas guardadas
- `X-OC-Status`: Estado de copia a ODC
- `X-OC-Creadas`: Número de OCs creadas

**Nota:** Este endpoint ejecuta los 3 primeros pasos del flujo completo.
Para enviar a SAP, usar el endpoint POST /integrar-sap (cuando esté disponible).

Returns:
    JSON con datos de MBA3 y metadata del proceso completo

**Respuestas:** `200`

## Remisiones

### `GET /remisiones`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Endpoint para obtener remisiones desde la base de datos con paginación.

**Características:**
- ✅ Consulta desde la tabla `remision_cabecera` (ya guardada)
- ✅ Paginación con `page` y `pageSize`
- ✅ Ordenamiento por fecha más reciente primero
- ✅ Permisos: `odcsap.view` o `mabel.view`

**Query Parameters:**
- `page` (int, default: 1) - Número de página (empezando en 1)
- `pageSize` (int, default: 10, max: 100) - Tamaño de página

**Ejemplo:**
```
GET /remisiones?page=1&pageSize=10
GET /remisiones?page=2&pageSize=20
```

**Respuesta:**
```json
{
  "status": "success",
  "data": [...],
  "metadata": {
    "count": 100
  },
  "total": 100,
  "page": 1,
  "pageSize": 10,
  "totalPages": 10
}
```

Returns:
    JSON con remisiones paginadas

**Parámetros:**

- `page` (query, integer, opcional) — Número de página (empezando en 1)
- `pageSize` (query, integer, opcional) — Tamaño de página (máximo 100)

**Respuestas:** `200`, `422`

### `GET /remisiones/consultar`

**Permiso requerido:** `mabel.view`

Endpoint para consultar documentos de remisión desde MBA3 y guardar solo cabeceras.

**Características:**
- ✅ Consulta documentos de remisión desde MBA3 (sin detalles)
- ✅ Guarda solo cabeceras en `remision_cabecera` (NO guarda detalles)
- ✅ Filtro automático: siempre trae los últimos N días desde hoy (constante MIGRATE_DATE_FILTER_DAYS)
- ✅ Sin parámetros: solo ejecutar el endpoint
- ✅ Fecha relativa: calcula automáticamente desde hoy hacia atrás
- ✅ Estos documentos no tienen `ObjDatosFactura`, por lo que no se crean registros en `despacho_detalle`

**Query utilizada:**
Consulta documentos de remisión con:
- TIPO_DOCUMENTO='REM'
- CONFIRMADO='false'
- Remision_Facturada='false'
- ObjDatosFactura IS NULL (sin detalles)
- FACTURA_IMPRESA='false'
- ANULADA='false'
- FECHA_FACTURA >= (fecha calculada según MIGRATE_DATE_FILTER_DAYS)

**Ejemplo de uso:**
```
GET /remisiones/consultar
```

**Nota:** Este endpoint guarda automáticamente en la base de datos.
Usa la misma configuración de filtro de fecha que los procesos manual y automático.

Returns:
    JSON con los datos de remisiones y metadata del guardado

**Respuestas:** `200`

## Sistema

### `GET /health`

**Permiso requerido:** Sin autenticación declarada en el endpoint (público, o validada por otro mecanismo)

Endpoint de health check.

Returns:
    JSON con status "ok" y timestamp ISO8601

**Respuestas:** `200`

## Órdenes de Compra

### `GET /ordenes-compra`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Endpoint ORDENES-COMPRA: Lista órdenes de compra con paginación en servidor.

**Query Parameters:**
- `page` (int, default: 1) - Número de página
- `pageSize` o `page_size` (int, default: 50, máx. 100) - Registros por página
- `estado` (string, opcional) - Filtrar por estado (PENDIENTE, ENVIANDO, ENVIADA, ERROR, ENCOLADA)
- `referencia_despacho`, `numero_oc_sap`, `search` - Filtros opcionales en servidor
- `solo_pendiente_reintento` (bool, opcional) - Solo ODCs con alguna acción de reintento pendiente

**Ejemplo:**
```
GET /ordenes-compra?estado=PENDIENTE&page=1&pageSize=20
GET /ordenes-compra?solo_pendiente_reintento=true&page=1&pageSize=20
```

**Respuesta (compatible con frontend / pedidos confirmados):**
```json
{
  "status": "success",
  "data": [...],
  "total": 150,
  "page": 1,
  "pageSize": 20,
  "totalPages": 8,
  "metadata": {
    "count": 20,
    "estado_filter": "PENDIENTE",
    "solo_pendiente_reintento": false
  }
}
```

**Parámetros:**

- `page` (query, integer, opcional) — Número de página (1-based)
- `page_size` (query, integer, opcional) — Tamaño de página (snake_case)
- `pageSize` (query, integer, opcional) — Tamaño de página (camelCase)
- `estado` (query, string, opcional) — Filtrar por estado (PENDIENTE, ENVIANDO, ENVIADA, ERROR, ENCOLADA)
- `referencia_despacho` (query, string, opcional) — Búsqueda parcial por referencia de despacho
- `numero_oc_sap` (query, string, opcional) — Búsqueda parcial por número OC SAP / doc_entry
- `search` (query, string, opcional) — Búsqueda parcial en referencia o número SAP
- `solo_pendiente_reintento` (query, boolean, opcional) — Si es true, solo trae ODCs donde el frontend mostraría el botón 'Reintentar' (PENDIENTE/ERROR) o 'Reintentar ST' (ENVIADA con tiendas pendientes de reintento ITR), sin importar la antigüedad.

**Respuestas:** `200`, `422`

### `DELETE /ordenes-compra`

**Permiso requerido:** `mabel.view`

Endpoint para eliminar múltiples órdenes de compra.

**Responsabilidad:** Eliminar órdenes de compra (múltiples)

**Características:**
- ✅ Elimina múltiples órdenes de compra en una sola operación
- ✅ Elimina primero los detalles y luego las cabeceras (por restricciones FK)
- ✅ Retorna información detallada de cada eliminación
- ✅ No permite eliminar ODC creadas desde despachos (tienen despacho_id)
- ✅ Continúa procesando aunque alguna falle
- ✅ Permisos: requiere permiso de eliminación

**Query Parameters:**
- `oc_id` (string, opcional, múltiple) - UUID de la orden de compra. Puede especificarse múltiples veces.

**Ejemplo de uso:**
```
DELETE /ordenes-compra?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325&oc_id=ABC123-DEF456-GHI789
```

**Respuesta:**
```json
{
  "status": "success",
  "message": "Proceso completado: 2 órdenes eliminadas de 2 solicitadas",
  "metadata": {
    "total_solicitadas": 2,
    "eliminadas": 2,
    "errores": 0,
    "no_encontradas": 0,
    "detalles": [...]
  }
}
```

Returns:
    JSON con el resultado de la eliminación de múltiples órdenes

**Parámetros:**

- `oc_id` (query, lista de string, opcional) — UUID(s) de la(s) orden(es) de compra a eliminar. Puede especificarse múltiples veces (ej: ?oc_id=id1&oc_id=id2).

**Respuestas:** `200`, `422`

### `GET /ordenes-compra/logs`

**Permiso requerido:** `mabel.view`

Endpoint ORDENES-COMPRA/LOGS: Obtiene el historial de logs de integración de órdenes de compra con SAP.

⭐ **Endpoint para Frontend - Historial de Órdenes**

Este endpoint permite consultar el historial completo de integraciones con SAP,
usando paginación basada en página (page/pageSize) en lugar de offset/limit.

**Query Parameters:**
- `page` (int, default: 1) - Número de página (empezando en 1)
- `pageSize` (int, default: 50) - Tamaño de página (registros por página)
- `oc_id` (string, opcional) - Filtrar por UUID de orden de compra
- `referencia_despacho` (string, opcional) - Filtrar por referencia de despacho
- `proveedor` (string, opcional) - Filtrar por código de proveedor
- `fecha_desde` (string, opcional) - Filtrar desde fecha (YYYY-MM-DD)
- `fecha_hasta` (string, opcional) - Filtrar hasta fecha (YYYY-MM-DD)
- `nivel_log` (string, opcional) - Filtrar por nivel (INFO, ERROR, WARNING)
- `success` (boolean, opcional) - Filtrar por éxito (true) o error (false)

**Ejemplo:**
```
GET /ordenes-compra/logs?page=1&pageSize=100
GET /ordenes-compra/logs?proveedor=P1790389219001&page=1&pageSize=50
GET /ordenes-compra/logs?fecha_desde=2025-12-01&fecha_hasta=2025-12-03&success=true
```

**Respuesta:**
```json
{
  "status": "success",
  "data": [...],
  "metadata": {
    "total": 150,
    "page": 1,
    "pageSize": 50,
    "totalPages": 3,
    "has_more": true
  }
}
```

Returns:
    JSON con historial de logs de órdenes y metadata de paginación

**Parámetros:**

- `page` (query, integer, opcional) — Número de página (empezando en 1)
- `pageSize` (query, integer, opcional) — Tamaño de página (registros por página)
- `oc_id` (query, string, opcional) — Filtrar por UUID de orden de compra
- `referencia_despacho` (query, string, opcional) — Filtrar por referencia de despacho
- `proveedor` (query, string, opcional) — Filtrar por código de proveedor
- `fecha_desde` (query, string, opcional) — Filtrar desde fecha (YYYY-MM-DD)
- `fecha_hasta` (query, string, opcional) — Filtrar hasta fecha (YYYY-MM-DD)
- `nivel_log` (query, string, opcional) — Filtrar por nivel (INFO, ERROR, WARNING)
- `success` (query, boolean, opcional) — Filtrar por éxito (true) o error (false)

**Respuestas:** `200`, `422`

### `DELETE /ordenes-compra/{oc_id}`

**Permiso requerido:** `mabel.view`

Endpoint para eliminar una orden de compra específica.

**Responsabilidad:** Eliminar orden de compra (solo lectura)

**Características:**
- ✅ Elimina la orden de compra completa (detalles y cabecera)
- ✅ Elimina primero los detalles y luego la cabecera (por restricciones FK)
- ✅ Retorna error si la orden no existe
- ✅ No permite eliminar ODC creadas desde despachos (tienen despacho_id)
- ✅ Permisos: requiere permiso de eliminación

**Path Parameters:**
- `oc_id` (string, requerido) - UUID de la orden de compra a eliminar

**Ejemplo de uso:**
```
DELETE /ordenes-compra/DD7D7A51-9E57-44D4-9A8F-4A05427A8325
```

**Respuesta exitosa:**
```json
{
  "status": "success",
  "message": "Orden de compra eliminada exitosamente",
  "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
  "detalles_eliminados": 5
}
```

**Respuesta si no existe:**
```json
{
  "status": "error",
  "message": "Orden de compra no encontrada",
  "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325"
}
```

**Respuesta si no se puede eliminar (creada desde despacho):**
```json
{
  "status": "error",
  "message": "No se puede eliminar una orden de compra creada desde un despacho",
  "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
  "despacho_id": "ABC123-DEF456-GHI789"
}
```

Returns:
    JSON con el resultado de la eliminación

**Parámetros:**

- `oc_id` (path, string, obligatorio)

**Respuestas:** `200`, `422`

### `PUT /ordenes-compra/{oc_id}/detalle/{oc_detalle_id}/sku`

**Permiso requerido:** `mabel.view`

Endpoint para actualizar el SKU de un detalle de orden de compra.

Este endpoint permite corregir el SKU de una línea de detalle de una ODC,
útil cuando hay errores al enviar a SAP debido a SKUs incorrectos.

**Path Parameters:**
- `oc_id` (string, requerido) - UUID de la orden de compra
- `oc_detalle_id` (string, requerido) - UUID del detalle de orden de compra

**Body Parameters:**
- `nuevo_sku` (string, requerido) - Nuevo SKU (ItemCode) de SAP
- `validar_en_sap` (boolean, default: true) - Si True, valida que el SKU exista en SAP antes de actualizar

**Ejemplo de uso:**
```
PUT /ordenes-compra/DD7D7A51-9E57-44D4-9A8F-4A05427A8325/detalle/ABC123-DEF456-GHI789/sku
{
    "nuevo_sku": "5-0012.9",
    "validar_en_sap": true
}
```

**Respuesta exitosa:**
```json
{
    "status": "success",
    "message": "SKU actualizado exitosamente",
    "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
    "oc_detalle_id": "ABC123-DEF456-GHI789",
    "sku_anterior": "5-0012.8",
    "sku_nuevo": "5-0012.9",
    "sku_validado_en_sap": true
}
```

**Respuesta si el SKU no existe en SAP (si validar_en_sap=true):**
```json
{
    "status": "error",
    "message": "El SKU no existe en SAP",
    "sku": "5-0012.9"
}
```

**Parámetros:**

- `oc_id` (path, string, obligatorio) — UUID de la orden de compra
- `oc_detalle_id` (path, string, obligatorio) — UUID del detalle de orden de compra

**Cuerpo de la petición:** `application/json` → Body_actualizar_sku_detalle_ordenes_compra__oc_id__detalle__oc_detalle_id__sku_put

**Respuestas:** `200`, `422`

### `GET /ordenes-compra/{oc_id}/detalles`

**Permiso requerido:** `mabel.view`

Endpoint para obtener los detalles (líneas) de una orden de compra específica.

Este endpoint retorna todas las líneas de detalle de una ODC, incluyendo
información sobre SKUs, cantidades, precios, etc.

**Path Parameters:**
- `oc_id` (string, requerido) - UUID de la orden de compra

**Ejemplo de uso:**
```
GET /ordenes-compra/DD7D7A51-9E57-44D4-9A8F-4A05427A8325/detalles
```

**Respuesta exitosa:**
```json
{
    "status": "success",
    "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
    "detalles": [
        {
            "oc_detalle_id": "ABC123-...",
            "oc_id": "DD7D7A51-...",
            "sku_sap": "5-0012.9",
            "cantidad_sap": 10.0,
            "unidad_sap": "X3",
            "precio_unitario": 150.0,
            "total_linea": 1500.0,
            "cantidad_origen": 30.0
        },
        ...
    ],
    "count": 5
}
```

**Respuesta si no existe:**
```json
{
    "status": "error",
    "message": "Orden de compra no encontrada",
    "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325"
}
```

**Parámetros:**

- `oc_id` (path, string, obligatorio) — UUID de la orden de compra

**Respuestas:** `200`, `422`

### `GET /ordenes-compra/{oc_id}/integracion-sap`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Obtiene el detalle de integración SAP de una OC (envío a SAP + solicitudes de transferencia).
Misma estructura que la respuesta de proceso-completo-sap, para reutilizar en el modal
cuando se abre desde el botón "Num ODC" en la tabla.

**Path Parameters:**
- `oc_id` (string, requerido) - UUID de la orden de compra

**Respuesta:** envio_sap (con numero_oc_sap, doc_entry, doc_num, solicitudes_transferencia)
y solicitudes_transferencia (resultados, itrs_por_tienda) para mostrar la sección ITR completa.

**Parámetros:**

- `oc_id` (path, string, obligatorio) — UUID de la orden de compra

**Respuestas:** `200`, `422`

### `GET /ordenes-compra/{oc_id}/integracion-sap/excel`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Descarga un Excel simple (2 hojas) con la misma información del correo
"OC y Solicitudes de Transferencia - Listo para Despacho": datos de la OC
en la primera hoja y, en la segunda, DOCNUM / NOMBRE TIENDA / CODIGO TIENDA
de cada solicitud de transferencia generada.

**Path Parameters:**
- `oc_id` (string, requerido) - UUID de la orden de compra

**Parámetros:**

- `oc_id` (path, string, obligatorio) — UUID de la orden de compra

**Respuestas:** `200`, `422`

### `GET /ordenes-compra/{oc_id}/pdf`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Endpoint para descargar el PDF de una orden de compra.

Genera y retorna el documento PDF de la ODC con toda la información
de cabecera, detalles de productos, resumen financiero y firmas.

**Path Parameters:**
- `oc_id` (string, requerido) - UUID de la orden de compra

**Ejemplo de uso:**
```
GET /ordenes-compra/DD7D7A51-9E57-44D4-9A8F-4A05427A8325/pdf
```

**Parámetros:**

- `oc_id` (path, string, obligatorio) — UUID de la orden de compra

**Respuestas:** `200`, `422`

### `POST /ordenes-compra/{oc_id}/reintentar-st`

**Permiso requerido:** `odcsap.view` o `mabel.view` (cualquiera de ellos)

Reintenta únicamente Solicitudes de Transferencia (ITR) fallidas para una ODC ya enviada.

Reglas:
- No reenvía ODC.
- Solo procesa tiendas fallidas del último batch ST de la OC.

**Parámetros:**

- `oc_id` (path, string, obligatorio) — UUID de la orden de compra

**Respuestas:** `200`, `422`
