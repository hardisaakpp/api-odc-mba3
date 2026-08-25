# Notificaciones en tiempo real (SSE)

Documentación del sistema de notificaciones toast en tiempo real (backend → frontend) vía
Server-Sent Events (SSE). Es el mecanismo **estándar** para que, cuando un usuario realiza una
acción que cambia el estado de un pedido, los usuarios de otros roles que estén viendo un
listado reciban un toast **y** vean su interfaz actualizarse sola (sin recargar la página).

Úsalo para **cualquier acción nueva que cambie el estado de un pedido** (o de cualquier otra
entidad que se liste en pantalla) y que otro rol necesite ver reflejada en tiempo real.

## Permisos involucrados

- `mabel.view` (MABEL TRADING)
- `odcsap.view` (Administración El Rayo)
- `produccion-elrayo.view` (Producción El Rayo)

## ⚠️ Regla de oro: `notify_by_actor` NO cubre a `produccion-elrayo.view`

El mapeo de "permiso opuesto" en `notification_manager.py` (`OPPOSITE_PERMISSION`) **solo conoce
el par `mabel.view` ↔ `odcsap.view`**:

```python
OPPOSITE_PERMISSION: Dict[str, str] = {"odcsap.view": "mabel.view", "mabel.view": "odcsap.view"}
```

Esto significa que `notify_by_actor(actor_permission=X, ...)`:

- Si `X` es `mabel.view` u `odcsap.view` → notifica también al otro de ese par. ✅ funciona solo.
- Si `X` es `produccion-elrayo.view`, o si `produccion-elrayo.view` es uno de los roles que
  **necesita enterarse** de una acción hecha por `mabel.view`/`odcsap.view` → **`notify_by_actor`
  nunca lo notifica**, sin importar qué tan lógico parezca que debería. Hay que agregar una
  llamada explícita a `notification_manager.notify(target_permission="produccion-elrayo.view", ...)`.

Este fue exactamente el bug que se repitió tres veces en este proyecto (Enviar pedido, Descartar
pedido, Confirmar Producción) antes de que quedara documentado acá: se implementaba el email, se
asumía que `notify_by_actor` "ya cubría todo", y `produccion-elrayo.view` (o el permiso que le
correspondiera) se quedaba sin toast ni auto-refresh. **Antes de dar por terminada una
notificación nueva, pregúntate explícitamente: ¿algún permiso relevante queda fuera del par
mabel↔odcsap? Si sí, necesita su propia llamada a `notify()`.**

## Checklist para agregar notificación en tiempo real a un endpoint nuevo

1. Identifica el **permiso del actor** (quien ejecuta la acción) y **qué permisos necesitan
   enterarse** (quién tiene esa entidad en su listado y debe verla cambiar/desaparecer/aparecer).
2. Si el actor es `mabel.view` u `odcsap.view` y lo único que hay que notificar es el otro de ese
   par (+ otros usuarios del mismo permiso): un solo `notify_by_actor(actor_permission=..., ...)`
   basta.
3. Si `produccion-elrayo.view` es el actor, o es uno de los permisos que necesita enterarse:
   agrega además (o en vez de) un `notification_manager.notify(target_permission="produccion-elrayo.view", ...)`
   explícito. Ver ejemplo real en `src/endpoints/pedidos/pedidos_estado_endpoints.py`,
   función `_logic_confirmar_produccion`.
4. Incluye siempre `metadata={"pedido_id": ..., "numero_pedido": ..., "accion": "<nombre_accion>"}`.
   El frontend no filtra por el valor de `accion` — cualquier notificación con `metadata.accion`
   presente dispara un recargo del listado — pero un nombre descriptivo ayuda a debuggear
   (ver logs, ver qué gatilló un refresh).
5. Envuelve la notificación en `try/except` **best-effort**: nunca debe hacer fallar la acción de
   negocio si el envío SSE falla (mismo criterio que el email).
6. Dispara la notificación **después** de que el cambio de estado ya se persistió (fuera del
   `with get_db_connection_context()` si es posible, o justo antes del `return`).
7. Corre los tests existentes del endpoint antes y después (no hay tests específicos de SSE hoy;
   confirma al menos que no rompiste nada del flujo de negocio).

## Lado frontend: cómo se consume

- `src/composables/useNotificaciones.ts` abre la conexión SSE (`connect()`, llamado desde
  `MainLayout.vue` en cuanto hay sesión activa) y expone un ref global de módulo `lastNotification`.
- `handleNotification()` filtra por `target_permission` contra `authStore.hasPermission()` y
  muestra el toast solo si el usuario actual tiene ese permiso — esto ya está implementado, no
  hace falta tocarlo al agregar una acción nueva.
- Cualquier vista de listado que deba autoactualizarse importa `lastNotification` y agrega:

  ```ts
  import { lastNotification } from '@/composables/useNotificaciones'

  watch(lastNotification, (notification) => {
    if (!notification) return
    if (!notification.metadata?.accion) return
    cargarPedidos() // o la función de recarga que corresponda a esa vista
  })
  ```

  Ejemplo real: `src/modules/mba3-consultas/views/PedidosListView.vue` (usada tanto en
  `/mba3-consultas/pedidos` como en `/mba3-consultas/produccion/pedidos` — mismo componente,
  filas filtradas por el backend según el rol).
- No hace falta tocar el frontend para una acción nueva si la vista de listado relevante **ya**
  tiene este `watch` conectado (la mayoría de los listados de pedidos ya lo tienen). Solo hace
  falta agregarlo si es un listado nuevo que todavía no lo implementa.

## Flujos ya implementados (referencia viva)

| Acción (botón)                 | Endpoint                                          | Actor permission         | Notifica a (además del actor) | `accion` metadata          |
|---------------------------------|----------------------------------------------------|--------------------------|--------------------------------|-----------------------------|
| Enviar pedido                   | `POST /api/pedidos/{id}/enviar`                     | `mabel.view`              | `odcsap.view` + `produccion-elrayo.view` (explícito) | `pedido_enviado`            |
| Gestionar pedido                | (marcar como gestionar)                             | `odcsap.view`              | `mabel.view`                    | `pedido_en_gestion`         |
| Descartar / Cancelar pedido     | `DELETE /api/pedidos/{id}`                          | `mabel.view`              | `odcsap.view` + `produccion-elrayo.view` (explícito, si estado visible a Producción) | `pedido_descartado`         |
| Confirmar para redistribución   | `POST /api/pedidos/{id}/confirmar-para-redistribucion` | `odcsap.view`           | `mabel.view`                    | `confirmar_redistribucion`  |
| **Confirmar Producción**        | `POST /api/pedidos/{id}/confirmar-produccion`       | `produccion-elrayo.view`  | `odcsap.view` (explícito)       | `confirmar_produccion`      |
| Despachar y Facturar            | (marcar como despachar y facturar)                  | `odcsap.view`              | `mabel.view`                    | `despachar_y_facturar`      |
| Finalizar                       | (marcar como finalizado)                            | `odcsap.view`              | `mabel.view`                    | `finalizar`                 |
| Cancelar pedido por EL RAYO     | `POST /api/pedidos/{id}/cancelar-por-el-rayo`       | `odcsap.view`              | `mabel.view` + `produccion-elrayo.view` (explícito) | `pedido_cancelado_por_el_rayo` |
| Confirmar respuesta proveedor   | (respuesta proveedor confirmada)                    | `odcsap.view`              | `mabel.view`                    | `pedido_confirmado_rayo`    |
| Confirmar redistribución (borrador) | (redistribución confirmada)                     | (sistema/`mabel.view`)     | `odcsap.view` (explícito)       | `redistribucion_confirmada` |
| ODC enviada a SAP               | (envío de orden de compra)                          | (sistema)                  | `odcsap.view` (explícito)       | `odc_enviada_sap`           |

Las filas marcadas "(explícito)" son las que requirieron un `notify()` adicional por la regla de
oro de arriba — todas las demás usan únicamente `notify_by_actor`.

## Contrato técnico

### Endpoint SSE

- **GET** `/notificaciones/stream`
  - Autenticación: JWT (Bearer).
  - El usuario se suscribe con sus permisos relevantes (`mabel.view`, `odcsap.view`,
    `produccion-elrayo.view`; usuarios `Admin` se suscriben a los tres); el backend asocia la
    conexión al `username` del JWT para poder excluir al autor al notificar al mismo permiso.

### Formato del evento `notification`

| Campo               | Tipo   | Descripción                                              |
|----------------------|--------|-----------------------------------------------------------|
| `id`                 | string | UUID de la notificación                                   |
| `type`               | string | `success`, `error`, `info`, `warning` (tipo de toast)      |
| `title`              | string | Título del toast                                           |
| `message`            | string | Mensaje descriptivo                                        |
| `target_permission`  | string | Permiso al que va dirigida (uno de los tres permisos)      |
| `timestamp`          | number | Timestamp Unix                                              |
| `metadata`           | object | Datos adicionales (`pedido_id`, `numero_pedido`, `accion`) |

El frontend muestra el toast solo si el usuario actual tiene el permiso indicado en
`target_permission` (ya implementado, no requiere cambios al agregar una acción nueva).

### API de `notification_manager`

```python
# Notifica al mismo permiso del actor (excl. autor) + al permiso opuesto (mabel<->odcsap) si existe.
await notification_manager.notify_by_actor(
    actor_permission="mabel.view",
    actor_username=user.get("username") or user.get("sub") or "unknown",
    title="...",
    message="...",
    notification_type=NotificationType.INFO,
    metadata={"pedido_id": "...", "numero_pedido": "...", "accion": "..."},
)

# Notifica directamente a un permiso específico, sin pasar por el mapeo de "opuesto".
# Es la única forma de llegar a produccion-elrayo.view.
await notification_manager.notify(
    target_permission="produccion-elrayo.view",
    title="...",
    message="...",
    notification_type=NotificationType.INFO,
    metadata={"pedido_id": "...", "numero_pedido": "...", "accion": "..."},
)
```

### Implementación interna

- **subscribe(permissions, username):** registra la conexión SSE por permiso y asocia la cola al `username`.
- **notify(target_permission, ..., exclude_username=None):** envía a todos los listeners de ese permiso, excepto los que coincidan con `exclude_username`.
- **notify_by_actor(actor_permission, actor_username, ...):** llama a `notify` dos veces (mismo permiso con exclusión del autor, y permiso opuesto sin exclusión — solo si `actor_permission` está en `OPPOSITE_PERMISSION`).

Referencia: `src/utils/notification_manager.py` y `src/endpoints/notificaciones.py`.

## Limitación conocida

El bus de notificaciones es un diccionario **en memoria, por proceso** (no respaldado por Redis
ni ninguna store compartida). Hoy la API corre en un solo proceso uvicorn (sin `--workers`, sin
réplicas) tanto en dev como en producción, así que esto no es un problema práctico actual. Si
algún día se escala la API a más de un worker/réplica, un cliente conectado al proceso A no vería
eventos originados en el proceso B — habría que migrar a un pub/sub compartido (Redis, ya usado
para Celery, sería la opción natural).
