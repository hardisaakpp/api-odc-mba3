# HTTP 202 del middleware SAP en la creación de ITR — no es un error definitivo

## Contexto del problema

El middleware `.NET` (`../middleware/api-middleware-sap`) absorbe la saturación del SAP
Service Layer: si una petición no responde en 10s, en vez de fallar la **encola**
(`docs/job-queue.md` del middleware) y responde:

```json
HTTP 202 Accepted
{ "jobId": "3fa85f64-...", "status": "ENCOLADO" }
```

El job sigue reintentándose en segundo plano (15s/30s/60s/120s/240s) hasta `COMPLETADO`
o `ERROR`. Antes de este fix, `_MiddlewareSAPServiceLayerClient.create_stock_transfer`
(`src/database/clients/sap_service_layer_client.py`) trataba cualquier código distinto
de 200/201 como error definitivo — el 202 caía al mismo branch que un error real de SAP,
con el mensaje literal `"HTTP 202"`. El reintento automático interno (`retry_utils.
retry_operation`) se detenía en el primer intento ("Error no reintentable; se detiene"),
y el botón manual "Reintentar ST" reenviaba la creación **a ciegas**.

**Riesgo del reenvío a ciegas:** si el job encolado original terminaba completándose en
SAP *después* de que el usuario reintentara, se creaban **dos ITR** para la misma
transferencia (bug reportado en producción para la tienda TRL-PSC / Portal Shopping).

## Solución implementada

1. **El cliente distingue "encolado" de "error"** (`sap_service_layer_client.py`):
   `create_stock_transfer` retorna `{"success": False, "queued": True, "job_id": ...,
   "status_code": 202}` en vez de un error genérico. Nuevo método `get_job_status(job_id)`
   → `GET /api/v1/jobs/{job_id}`.

2. **Se persiste el `job_id`** (`solicitud_transferencia_detalle.job_id`, migración
   `615_add_job_id_solicitud_transferencia_detalle`) con `estado = 'Encolada'` (nuevo
   valor, junto a `'Creada'`/`'Error'`).

3. **Antes de reintentar, se consulta el job en vez de reenviar**
   (`StockTransferService._resolver_jobs_encolados_pendientes`, invocado desde
   `crear_solicitudes_transferencia_desde_pedido` cuando `verificar_ya_existente_en_sap=True`,
   es decir, en todo reintento — manual o vía Celery):
   - Job `COMPLETADO` → se adopta el DocEntry/DocNum (mismo mecanismo que la
     verificación preventiva contra SAP por comentario, `_buscar_itrs_existentes_en_sap`),
     **no se crea una ITR nueva**.
   - Job `ENCOLADO`/`PROCESANDO` → esa tienda se excluye del reintento este ciclo
     (no se reenvía nada); si son *todas* las tiendas objetivo, el resultado es
     `status: "en_cola"` (no `"success"` engañoso con 0 creadas).
   - Job `ERROR` o no consultable → la tienda queda libre para un intento normal
     (comportamiento idéntico al de antes de este fix).

4. **La escalación automática a técnicos ya no dispara por un 202**
   (`celery_reconciliar_transferencias._tiene_error_no_transitorio` ignora resultados
   `queued=True`: es transitorio por definición, se resuelve solo).

5. **Notificaciones por correo** (`email_notifier.py`) muestran una etiqueta distinta
   ("Encolada", ámbar) en vez de "Error" (rojo) para no alarmar sin motivo a El Rayo/Mabel.

## Fuera de alcance de este fix

- ~~`create_purchase_order` (envío de ODC) puede recibir el mismo 202 del middleware y
  sigue tratándolo como error genérico~~ — **resuelto**, ver
  `docs/RESOLUCION_ODC_ENCOLADA_202.md` (incidente real: ODC 24711 encolada + 24712
  duplicada por reintento manual, mismo patrón aplicado aquí).
- `get_inventory_transfer_requests_by_comment` (usado por la verificación preventiva
  contra SAP) también puede recibir 202 y hoy lo trata como "sin resultados" (no
  bloqueante, cae a crear normalmente) — el job-id tracking de este fix cubre
  exactamente el hueco que esa verificación no puede ver (job aún en cola, nada que
  buscar todavía en SAP).

## Archivos tocados

| Archivo | Cambio |
|---|---|
| `src/database/clients/sap_service_layer_client.py` | 202 → `queued`, nuevo `get_job_status` |
| `src/database/clients/sap_service_layer_client_direct.py` | `get_job_status` stub (paridad de interfaz, siempre `None`) |
| `scripts/migrations/add_job_id_solicitud_transferencia_detalle.sql` | Columna `job_id` |
| `src/database/repositories/solicitud_transferencia_repository.py` | `_insert_one_detalle` (estado `Encolada`), `get_tiendas_pendientes_reintento_st` (incluye `Encolada`), nuevo `get_tiendas_encoladas_con_job_id` |
| `src/database/services/stock_transfer_service.py` | `_resolver_jobs_encolados_pendientes`, `_enviar_itrs_a_sap` (branch `queued`), `reintentar_pendientes` (status `en_cola`) |
| `src/endpoints/ordenes_compra.py` | Mapeo de status externo `en_cola` |
| `src/tasks/celery_reconciliar_transferencias.py` | `_tiene_error_no_transitorio` ignora `queued` |
| `src/utils/email_notifier.py` | Badge "Encolada" en notificaciones |
| `scnexus-front/.../OrdenCompraTable.vue` | Toast informativo para status `en_cola` |

---
**Fecha:** 2026-08-05
