# Notificaciones en tiempo real (SSE)

Documentación del sistema de notificaciones toast vía Server-Sent Events (SSE) entre backend y frontend.

## Comportamiento actual (escalable)

- **Permisos involucrados:** `mabel.view` (MABEL TRADING) y `odcsap.view` (EL RAYO).
- Cuando un usuario realiza una acción (ej.: andrea@ con `mabel.view` envía un pedido):
  - Se notifica a **todos los usuarios con el mismo permiso** excepto al autor (ej.: carlos@ con `mabel.view` recibe el toast; andrea@ no).
  - Se notifica a **todos los usuarios del permiso opuesto** (ej.: usuarios con `odcsap.view`).
- Cuando un usuario con `odcsap.view` realiza una acción (ej.: confirmar pedido), se notifica a otros con `odcsap.view` (excl. autor) y a todos con `mabel.view`.

Así, varios usuarios con el mismo permiso reciben toasts entre sí y siguen recibiendo notificaciones del otro rol.

## Contrato técnico

### Endpoint SSE

- **GET** `/notificaciones/stream`  
  - Autenticación: JWT (Bearer).  
  - El usuario se suscribe con sus permisos; el backend asocia la conexión al `username` del JWT para poder excluir al autor al notificar al mismo permiso.

### Formato del evento `notification`

Cada evento SSE de tipo `notification` envía un JSON con:

| Campo               | Tipo   | Descripción                                              |
|---------------------|--------|----------------------------------------------------------|
| `id`                | string | UUID de la notificación                                  |
| `type`              | string | `success`, `error`, `info`, `warning` (tipo de toast)    |
| `title`             | string | Título del toast                                         |
| `message`           | string | Mensaje descriptivo                                      |
| `target_permission` | string | Permiso al que va dirigida (`mabel.view` o `odcsap.view`) |
| `timestamp`         | number | Timestamp Unix                                           |
| `metadata`          | object | Datos adicionales (ej. `pedido_id`, `numero_pedido`, `accion`) |

El frontend debe mostrar el toast solo si el usuario actual tiene el permiso indicado en `target_permission` (ya implementado en el frontend).

### Uso en backend: `notify_by_actor`

Para notificar por una acción de un usuario se usa:

```python
await notification_manager.notify_by_actor(
    actor_permission="mabel.view",   # permiso de quien hace la acción
    actor_username=user.get("username") or user.get("sub") or "unknown",
    title="...",
    message="...",
    notification_type=NotificationType.INFO,
    metadata={"pedido_id": "...", "numero_pedido": "...", "accion": "..."},
)
```

- **actor_permission:** permiso del usuario que realiza la acción (`mabel.view` o `odcsap.view`).
- **actor_username:** identificador del usuario (para no enviarle la notificación en el canal de su mismo permiso).

El manager envía:

1. Al **mismo permiso** (`actor_permission`), excluyendo al `actor_username`.
2. Al **permiso opuesto** (`odcsap.view` ↔ `mabel.view`), a todos.

Cada evento se envía con el `target_permission` correspondiente al canal (mismo u opuesto), para que el frontend pueda filtrar por permiso correctamente.

## Implementación interna

- **subscribe(permissions, username):** registra la conexión SSE por permiso y asocia la cola al `username`.
- **notify(..., exclude_username=None):** envía a todos los listeners del `target_permission` excepto los que coinciden con `exclude_username`.
- **notify_by_actor(actor_permission, actor_username, ...):** llama a `notify` dos veces (mismo permiso con exclusión del autor y permiso opuesto sin exclusión).

Referencia: `src/utils/notification_manager.py` y `src/endpoints/notificaciones.py`.
