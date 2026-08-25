# HTTP 202 del middleware SAP en la creación de ODC — no es un error definitivo

## Contexto del problema

Mismo mecanismo que `docs/RESOLUCION_ITR_ENCOLADA_202.md` (léase primero), pero para
la creación de la Purchase Order (ODC) en vez de la Solicitud de Transferencia (ITR).
Ese fix explícitamente dejó la ODC fuera de alcance; este documento cubre su cierre.

`create_purchase_order` (`sap_service_layer_client.py`) no distinguía el 202 (SAP
saturado, middleware encola el job) de un error real: cualquier código distinto de
200/201 caía al mismo branch de error genérico, con el mensaje literal `"HTTP 202"`.
La ODC quedaba marcada `estado = "ERROR"` sin persistir el `job_id` (la columna ni
existía en `orden_compra_cabecera`), perdiendo todo rastro de que en realidad solo
estaba encolada.

**Incidente real en producción:** pedido "prueba 124" generó la ODC 24710 (éxito). La
segunda ODC del mismo pedido (mixto, 2 bodegas) recibió 202 y quedó marcada "ERROR",
pero el job se completó en SAP en segundo plano como ODC 24711. La UI ofreció el botón
"Reintentar" (porque veía estado "ERROR", no distinguía el 202); el usuario le dio clic
y el reintento —vía `PedidoOCService.crear_ocs_desde_pedido_confirmado`, que hace
*upsert* de la cabecera de la ODC sin mirar su estado real— reseteó la ODC a
`"PENDIENTE"`, borró y reinsertó sus detalles, y la reenvió a SAP, generando la ODC
**24712 duplicada** con sus 23 Solicitudes de Transferencia también duplicadas.

## Solución implementada

Mismo patrón que ITR, aplicado a la creación de la ODC:

1. **El cliente distingue "encolado" de "error"** (`sap_service_layer_client.py`):
   `create_purchase_order` retorna `{"success": False, "queued": True, "job_id": ...,
   "status_code": 202}` en vez de un error genérico (mismo shape que ya tenía
   `create_stock_transfer`).

2. **Se persiste el `job_id`** (`orden_compra_cabecera.job_id`, migración `650_
   add_job_id_orden_compra_cabecera`) con `estado = 'ENCOLADA'` (nuevo valor, junto a
   `PENDIENTE/ENVIADA/ERROR`). `OrdenCompraRepository.update_estado` limpia `job_id`
   automáticamente en cualquier transición que no sea hacia `ENCOLADA`.

3. **Antes de reintentar, se consulta el job en vez de reenviar**
   (`OCSAPService._resolver_job_encolado_previo`, invocado al inicio de
   `enviar_oc_a_sap` para cualquier ODC en estado `ENCOLADA` — reintento manual o vía
   Celery):
   - Job `COMPLETADO` con `docEntry` → se adopta vía `_procesar_oc_exitosa` (crea sus
     ITR/ST, notifica, cierra el pedido), **no se crea una ODC nueva**.
   - Job `ENCOLADO`/`PROCESANDO` → se detiene ahí, `retry_recommended=False`, sin
     tocar la BD.
   - Job `ERROR` (motivo real de SAP) o no consultable → se loggea el motivo real (a
     diferencia de ITR, que lo descarta silenciosamente — aquí sí se persiste en
     `respuesta_sap` antes de liberar la ODC para un intento normal).

4. **Se cerró el hueco real que permitió el duplicado**
   (`PedidoOCService._crear_una_oc`): si la ODC existente para ese pedido/bodega ya
   está `ENVIADA` o `ENCOLADA`, el *upsert* la reutiliza tal cual — no resetea su
   estado ni borra/reinserta sus detalles. `OCSAPService.enviar_oc_a_sap` además trata
   una ODC `ENVIADA` como no-op idempotente (nada que reenviar) en vez de rechazarla.

5. **El correo de despacho ya no depende de que TODAS las ODC del pedido tengan
   éxito** (`endpoints_proceso.py::_respuesta_fallo_sap`): antes, una ODC encolada (o
   con error real) hacía que ninguna ODC del pedido recibiera su correo de despacho,
   ni siquiera la que sí tuvo éxito.

6. **`pedido_cierre_service.py`** cuenta `ENCOLADA` como su propio estado (no cae en
   ningún branch antes de este fix), con mensaje explícito ("esperando confirmación de
   SAP") en `razon_no_cierre`.

7. **Reconciliación automática vía Celery, siempre activa**
   (`src/tasks/celery_reconciliar_ordenes_compra.py`, mirror de
   `celery_reconciliar_transferencias.py`, intervalo `RECONCILIAR_OC_INTERVALO_MINUTOS`
   = `5` por defecto): resuelve las ODC `ENCOLADA` sin esperar un clic manual. A
   diferencia de la reconciliación de ST (gateada por
   `ENABLE_RECONCILIACION_ST_AUTOMATICA`, apagada por defecto), esta **no depende de
   ningún flag** — es parte de la lógica normal del envío a SAP, siempre corre.

   Si el job resuelve en un error real no transitorio, notifica a técnicos por correo
   (`send_oc_creacion_error_notification_tecnicos`, nueva plantilla propia — no
   reutiliza la de ST porque su contenido está armado alrededor de Solicitudes de
   Transferencia y mostraría "0/0" sin explicar el error real). Requiere la migración
   `651_add_correo_odc_creacion_error_tecnicos` (catálogo `notificacion_tipo_correo`)
   y que un admin vincule destinatarios TECNICOS a ese nuevo tipo de correo desde la
   UI de notificaciones (igual que cualquier tipo de correo nuevo del catálogo; la
   migración solo registra el tipo, no asigna destinatarios). Un reintento manual
   fallido no envía este correo — ya es visible de inmediato para quien lo hizo.

8. **Frontend** (`IntegracionSAPModal.vue`): rama ámbar "SAP está procesando esta OC"
   para `bloque.detalle.queued`, distinta del rojo "Error al enviar OC". El CTA de
   reintento deja de mostrarse porque el backend ya no pone `retry_recommended=True`
   para este caso.

## Fuera de alcance de este fix

- Las ODC 24711/24712 ya duplicadas en SAP no se corrigen por código — es una
  corrección de datos en SAP (anular o nota de crédito de la 24712 y sus 23 ST),
  acción manual.
- No se backporteó a ST la mejora de persistir el motivo real de un job que termina
  en `ERROR` (`stock_transfer_service.py` sigue descartándolo silenciosamente).
- No hay dedup/pausa de reenvío del correo de escalamiento (a diferencia de ST, que
  usa una marca en Redis con TTL de 24h): no hace falta, porque una ODC que resuelve
  en error real sale del estado `ENCOLADA` (pasa a `ERROR`) y no vuelve a evaluarse
  en el próximo ciclo de reconciliación — cada ODC solo puede disparar este correo
  una vez por ocurrencia.

## Archivos tocados

| Archivo | Cambio |
|---|---|
| `src/database/clients/sap_service_layer_client.py` | 202 → `queued` en `create_purchase_order` |
| `scripts/migrations/add_job_id_orden_compra_cabecera.sql` (650) | Columna `job_id` |
| `src/database/repositories/orden_compra_repository.py` | `job_id` en `get_existing_cabecera`/`update_estado`, nuevo `get_oc_ids_encoladas` |
| `src/database/services/oc_sap_service.py` | `_resolver_job_encolado_previo`, `_manejar_fallo_envio_sap` (branch `queued`), no-op para `ENVIADA` |
| `src/database/services/pedido_oc_service.py` | `_crear_una_oc` no resetea ODC `ENVIADA`/`ENCOLADA` |
| `src/database/services/pedido_cierre_service.py` | Branch `ENCOLADA` |
| `src/endpoints/pedidos/redistribucion/endpoints_proceso.py` | Propaga `queued`, correo de despacho por ODC exitosa independiente de hermanas |
| `src/models.py` | `ProcesoCompletoSAPDetalleODC.queued` |
| `src/config.py`, `src/celery_app.py`, `src/tasks/celery_reconciliar_ordenes_compra.py` | Reconciliación automática, siempre activa (sin flag) |
| `src/utils/email_notifier.py`, `src/utils/email_preview.py` | `send_oc_creacion_error_notification_tecnicos` + preview |
| `scripts/migrations/add_correo_odc_creacion_error_tecnicos.sql` (651) | Catálogo `notificacion_tipo_correo` (TECNICOS) |
| `scnexus-front/.../types.ts`, `IntegracionSAPModal.vue`, `ProcesoCompletoView.vue` | Rama visual `queued`, sin CTA de reintento |

---
**Fecha:** 2026-08-25
