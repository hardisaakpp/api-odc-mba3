# Estados del pedido: tabla maestra y migración

## Resumen

Los estados del pedido se identifican por **`estado_id`** (número). El **nombre** es solo presentación y puede ser editado por el usuario sin afectar lógica ni históricos.

- **Verdad absoluta:** `estado_id` (1, 2, 3, …).
- **Presentación:** `estado_nombre` (editable en tabla `pedido_estado`).
- **Estado inicial** al subir Excel o crear pedido: **siempre `estado_id = 1`** (BORRADOR).

---

## Tabla maestra `pedido_estado`

| id | nombre (editable) | orden | Uso típico |
|----|-------------------|-------|------------|
| 1  | BORRADOR | 1  | Estado inicial (ex PENDIENTE_CONFIRMACION_PROVEEDOR) |
| 2  | NUEVO PEDIDO | 2  | Enviado a EL RAYO (notificación enviada) |
| 3  | GESTIONAR PEDIDO | 3  | Al hacer clic en Ver Detalle desde tabla Pedidos |
| 4  | CONFIRMADO | 4  | Redistribución (tras confirmar respuesta EL RAYO) |
| 5  | RESPUESTA_PROVEEDOR_CARGADA | 5  | Respuesta del proveedor cargada |
| 6  | CONFIRMADO_PROVEEDOR | 6  | Aprobado por proveedor |
| 7  | RECHAZADO_PROVEEDOR | 7  | Rechazado por proveedor |
| 8  | EN_AJUSTE_MABEL | 8  | En ajuste MABEL (redistribución) |
| 9  | REDISTRIBUIDO | 9  | Redistribución aplicada |
| 10 | CONFIRMADO REDISTRIBUCION | 10 | Pedido confirmado (redistribución confirmada) |
| 11 | PROCESADO_SAP | 11 | Procesado en SAP |
| 12 | CONFIRMADO_ENVIADO | 12 | Todas las ODC enviadas a SAP |
| 13 | PENDIENTE_LOGISTICA | 13 | OC OK, ST pendiente/error |
| 14 | ERROR_DATOS_MAESTROS | 14 | Error en datos maestros |
| 15 | EN_PROCESO | 15 | En proceso |
| 16 | COMPLETADO | 16 | Completado |
| 17 | DESPACHAR Y FACTURAR | 17 | Manual: desde Confirmado y Enviado (ODC enviada a SAP) |
| 18 | FINALIZADO | 18 | Estado final del flujo; solo desde Despachar y Facturar |
| 19 | CANCELADO | 19 | Pedido cancelado por MABEL TRADING desde Redistribución |
| 20 | CANCELADO POR EL RAYO | 20 | Cancelado por EL RAYO desde Gestionar pedido |
| 21 | ERROR ENVIO SAP REINTENTO | 21 | Fallo al enviar ODC a SAP (típ. conexión / transitorio); permite reintentar |

El **id es semántico** (no depende del orden en BD). El **orden** es solo para visualización (listas, filtros).

---

## Mapping: string legacy → estado_id

Para migración y compatibilidad temporal:

| String legacy (columna `estado`) | estado_id |
|----------------------------------|-----------|
| PENDIENTE_CONFIRMACION_PROVEEDOR | 1 (BORRADOR) |
| BORRADOR                         | 1 |
| NUEVO_PEDIDO                    | 2 |
| GESTIONAR_PEDIDO                | 3 |
| EN_REVISION                     | 4 (REDISTRIBUCION) |
| REDISTRIBUCION                  | 4 |
| CONFIRMADO                      | 4 |
| RESPUESTA_PROVEEDOR_CARGADA     | 5 |
| CONFIRMADO_PROVEEDOR            | 6 |
| RECHAZADO_PROVEEDOR             | 7 |
| EN_AJUSTE_MABEL                 | 8 |
| REDISTRIBUIDO                   | 9 |
| PEDIDO_CONFIRMADO               | 10 |
| CONFIRMADO REDISTRIBUCION       | 10 |
| PROCESADO_SAP                   | 11 |
| CONFIRMADO_ENVIADO              | 12 |
| PENDIENTE_LOGISTICA             | 13 |
| ERROR_DATOS_MAESTROS            | 14 |
| EN_PROCESO                      | 15 |
| COMPLETADO                      | 16 |
| DESPACHAR Y FACTURAR            | 17 |
| DESPACHAR_Y_FACTURAR            | 17 |
| FINALIZADO                      | 18 |
| CANCELADO                       | 19 |
| CANCELADO POR EL RAYO           | 20 |
| ERROR ENVIO SAP REINTENTO       | 21 |
| ERROR_ENVIO_SAP_REINTENTO       | 21 |
| *(cualquier otro o NULL)*       | 1 (BORRADOR) |

---

## API: respuesta recomendada

Devolver siempre **id + nombre** para que el front no invente etiquetas:

```json
{
  "estado_id": 1,
  "estado_nombre": "BORRADOR"
}
```

El nombre debe venir de la tabla `pedido_estado` (JOIN o caché) para reflejar cambios del usuario.

---

## Plan de migración (sin downtime)

### Prerrequisitos

1. Ejecutar **`create_pedido_estado_table.sql`** (crea tabla y datos iniciales).
2. Asegurar que no quede ningún valor de `pedido.estado` sin mapear (ver mapping arriba).

### Fase 1: agregar estado_id sin romper nada

1. Ejecutar **`migrate_pedido_estado_id.sql`**:
   - Agrega columna `pedido.estado_id` (INT NULL).
   - Pobla `estado_id` desde `estado` (string) con el mapping explícito.
   - Asigna default `estado_id = 1` para nuevas filas.
   - Crea FK a `pedido_estado(id)` e índice en `estado_id`.
2. **No eliminar** la columna `estado` todavía: permite rollback y reportes antiguos.

### Fase 2: adaptar backend

1. Usar constantes de **`src/database/pedido_estados.py`** en toda la lógica:
   - Asignar estado inicial: `estado_id = ESTADO_BORRADOR` (1).
   - Actualizar estado: `update_estado(pedido_id, estado_id)`.
   - Validaciones: comparar por `estado_id` (p. ej. `estado_id in ESTADOS_VALIDOS_PARA_ODC`).
2. En lecturas: JOIN con `pedido_estado` y devolver `estado_id` + `estado_nombre` en la cabecera del pedido.
3. Filtros por estado: usar `estado_id` en lugar de string.

### Fase 3 (opcional): retirar columna estado

1. Cuando todo el código y reportes usen solo `estado_id`:
   - Eliminar columna `pedido.estado`.
   - Actualizar scripts/documentación que la referencien.

### Verificación post-migración

- No debe haber filas en `pedido` con `estado_id` NULL.
- El script de migración incluye un chequeo final; si aparece advertencia, revisar valores de `estado` no mapeados.

---

## Constantes en backend (Python)

Referencia única en **`src/database/pedido_estados.py`**:

- `ESTADO_BORRADOR = 1`, `ESTADO_RESPUESTA_PROVEEDOR_CARGADA = 2`, …
- `ESTADO_INICIAL = ESTADO_BORRADOR`
- Conjuntos: `ESTADOS_PERMITEN_REDISTRIBUCION`, `ESTADOS_VALIDOS_PARA_ODC`, `ESTADOS_BLOQUEADOS_PROVEEDOR`
- `estado_id_desde_legacy(estado_string)` para compatibilidad durante la transición.

No usar strings hardcodeados en lógica; usar siempre `estado_id` y estas constantes.

---

## Reintento de envío ODC a SAP (UI)

La visibilidad del botón **"Reintentar envío ODC a SAP"** se calcula en backend (`pedido_permite_reintento_envio_odc_sap`) con esta prioridad:

1. **Estado del pedido**
   - Permitido en `CONFIRMADO REDISTRIBUCION` (`estado_id = 10`) y `ERROR ENVIO SAP REINTENTO` (`estado_id = 21`).
2. **Estado de ODC**
   - Si alguna ODC está en `PENDIENTE` => habilitar.
   - Si alguna ODC está en `ERROR` => evaluar reglas de reintento.
3. **Reglas para ODC en ERROR** (orden de evaluación)
   - **Por código SAP (`error_code`)**: allowlist explícita de negocio.
     - Actualmente: `-1116` (caso recurrente: *Presupuesto excedido RL*).
   - **Por origen**: `error_source = SAP_CONNECTION`.
   - **Fallback por texto**: heurística por mensaje (conectividad/timeout y casos operativos soportados).

### Casos recurrentes habilitados actualmente

- Caídas / timeouts / problemas de conexión con Service Layer.
- `Código SAP: -1116` (Presupuesto excedido RL).

---

## Cierre del pedido tras ODC + ST (`PedidoCierreService`)

`PedidoCierreService.cerrar_pedido_si_corresponde` es la única función que decide si un
pedido pasa a `CONFIRMADO_ENVIADO` (12), o se queda en `PENDIENTE_LOGISTICA` (13) /
`ERROR_DATOS_MAESTROS` (14) — ver `src/database/services/pedido_cierre_service.py`.

⭐ Regla:
- Todas las ODC del pedido `ENVIADA` + ST exitosas → `CONFIRMADO_ENVIADO`.
- ODC `ENVIADA` pero alguna ST falló → `PENDIENTE_LOGISTICA` (o `ERROR_DATOS_MAESTROS` si
  el fallo es por datos maestros en SAP).
- Alguna ODC no está `ENVIADA` (pendiente o en error) → no se toca el estado del pedido.

Se invoca desde:
- El envío original de la ODC (`oc_sap_service.enviar_oc_a_sap` → `_cerrar_pedido_desde_resultado_oc`).
- Cualquier reintento de ST — manual (`POST /ordenes-compra/{oc_id}/reintentar-st`) o
  automático (`celery_reconciliar_transferencias`) — ambos pasan por
  `StockTransferService.reintentar_pendientes`, que al final vuelve a evaluar el cierre
  con `_reevaluar_cierre_pedido_tras_reintento`, usando el resumen agregado de **todos**
  los batches de ST de la ODC (no solo el último intento).

**Importante:** `PENDIENTE_LOGISTICA` / `ERROR_DATOS_MAESTROS` no son estados
permanentes — si un reintento de ST posterior tiene éxito, el pedido debe pasar a
`CONFIRMADO_ENVIADO` automáticamente. (Bug real corregido el 24/08/2026: antes de agregar
la llamada anterior, un reintento exitoso de ST no volvía a evaluar el cierre del pedido,
así que quedaba congelado en `PENDIENTE_LOGISTICA` para siempre aunque en SAP la ODC y la
ST ya estuvieran correctamente enviadas — caso real: pedido `PDES-08.26.2026.XM`, hubo que
corregirlo manualmente en BD.)

### Reintento de Solicitud de Transferencia (ST/ITR)

El botón **"Reintentar ST"** (distinto del botón de reintento de ODC de la sección
anterior) se calcula en `_enrich_oc_actions` (`src/endpoints/ordenes_compra.py`):

```
mostrar_reintentar_st = estado == "ENVIADA" and pendientes > 0
```

`pendientes` viene de `SolicitudTransferenciaRepository.get_st_pendiente_reintento_count`,
que cuenta tiendas en `Error`/`Encolada` del último batch de ST (con fallback al
`resultado_json` de la cabecera si no hay filas de detalle). Si la ST ya se reintentó con
éxito, `pendientes = 0` y el botón desaparece — es el comportamiento correcto una vez
resuelto, no un bug (fácil de confundir con el caso anterior: revisar primero si la ST ya
tuvo éxito en un intento posterior antes de asumir que el botón "debería" aparecer).
