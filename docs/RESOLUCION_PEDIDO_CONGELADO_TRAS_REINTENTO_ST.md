# Pedido congelado en PENDIENTE_LOGISTICA/ERROR_DATOS_MAESTROS tras un reintento exitoso de ST

## Contexto del problema

`PedidoCierreService.cerrar_pedido_si_corresponde` es el único punto que decide el
estado final del pedido según el resultado de su ODC y sus Solicitudes de
Transferencia (ITR): OC OK + ST OK → `CONFIRMADO_ENVIADO`; OC OK + ST con error →
`PENDIENTE_LOGISTICA` (o `ERROR_DATOS_MAESTROS` si el error es de datos maestros).

Ese método solo se invocaba desde el flujo de envío original de la ODC
(`OCSAPService.enviar_oc_a_sap`). Cuando la primera Solicitud de Transferencia
fallaba, el pedido quedaba en `PENDIENTE_LOGISTICA` — correcto en ese momento. Pero
si más tarde alguien reintentaba la ST (botón "Reintentar ST" manual, o la
reconciliación automática) y esta vez tenía éxito, **nada volvía a llamar a
`cerrar_pedido_si_corresponde`**. El pedido quedaba congelado para siempre en
`PENDIENTE_LOGISTICA`, aunque en SAP la ODC y la ST ya estuvieran correctamente
creadas y el usuario viera "Redistribución completa y válida" en la UI.

## Incidentes reales

| # | Pedido | ODC / ITR | Fecha | Cómo se resolvió |
|---|---|---|---|---|
| 1 | PDES-08.26.2026.XM | — | 2026-08-21 | Detectado durante desarrollo; motivó el fix (ver abajo) |
| 2 | PDES-08.13.2026.PR ("13. PEDIDO DESCUENTON LLANO GRANDE") | ODC `1201976` (doc_entry 60823) / ITR `70246195` tienda TOUT-LLG | 2026-08-27 | **Corrección manual de datos en producción** (el fix de código aún no estaba desplegado ahí) — ver procedimiento abajo |

## Solución implementada (ya en código, **pendiente de desplegar a producción**)

Rama `feature/odc-segunda-fase`, no presente en `main` a la fecha del incidente #2
(2026-08-27):

1. **`SolicitudTransferenciaRepository.get_resumen_agregado_por_oc_id(oc_id)`**
   (`src/database/repositories/solicitud_transferencia_repository.py`): agrega el
   resultado de TODOS los batches de ST de una OC (envío original + reintentos), no
   solo el último — por tienda, se queda con la fila `'Creada'` si tuvo éxito en
   *cualquier* intento.

2. **`StockTransferService._reevaluar_cierre_pedido_tras_reintento(pedido_id,
   oc_id)`** (`src/database/services/stock_transfer_service.py`, ~línea 1651): se
   invoca al final de un reintento de ST exitoso (`reintentar_solicitud_transferencia`
   y equivalentes), usa el resumen agregado de arriba y vuelve a llamar a
   `PedidoCierreService.cerrar_pedido_si_corresponde`. No crítico: si falla, solo
   loggea un warning — no rompe la respuesta del reintento.

3. `PedidoCierreService.cerrar_pedido_si_corresponde` en sí no cambió — el fix es
   asegurar que se vuelva a llamar, no la lógica de decisión.

## Procedimiento manual mientras el fix no esté desplegado

Si vuelve a aparecer (pedido con "Redistribución completa y válida" pero estado
`PENDIENTE_LOGISTICA`/`ERROR_DATOS_MAESTROS` en la UI):

1. **Diagnóstico read-only** — ubicar el pedido y verificar OC + ST reales (evitar
   `PedidoRepository.get_pedido_completo_por_numero`, que en el esquema de
   producción falla con `Invalid column name 'fecha_facturacion'`; usar en su lugar
   un `SELECT` mínimo sobre `pedido`/`pedido_estado`):
   ```sql
   SELECT p.pedido_id, p.numero_pedido, p.estado_id, pe.nombre
   FROM pedido p LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
   WHERE p.numero_pedido = ?;
   ```
   Luego `OrdenCompraRepository.get_by_pedido_id` + `evaluar_cierre_pedido` (OC), y
   `SolicitudTransferenciaRepository.get_resumen_agregado_por_oc_id` (ST) — ambos son
   compatibles con el esquema de producción (no referencian `job_id`, que solo existe
   desde HEAD).

2. **Confirmar** que `evaluar_cierre_pedido().puede_cerrar == True` y que el resumen
   de ST no tiene `transferencias_errores > 0`.

3. **Aplicar el fix puntual** con `PedidoRepository.update_estado(pedido_id,
   ESTADO_CONFIRMADO_ENVIADO, audit_context=get_system_audit_context("..."))` — este
   método sí es seguro contra el esquema viejo: verifica con
   `INFORMATION_SCHEMA.COLUMNS` si existen `estado_id`/`estado` antes de escribir, y
   omite el insert en `pedido_estado_historial` si la tabla no existe (aunque en
   producción sí existe, quedó registrada la transición manual).

No usar `cerrar_pedido_si_corresponde` completo contra producción sin antes probar
cada lectura intermedia — varios métodos de lectura del repositorio de pedido en HEAD
ya no son compatibles con el esquema actual de producción (ver
`docs/`/memoria [[prod_deployment_lag]]).

## Fuera de alcance de este documento

- Desplegar `feature/odc-segunda-fase` a producción (pendiente, no es un cambio de
  datos).
- Cualquier otro pedido que pueda estar en el mismo estado ahora mismo sin haberse
  detectado — este documento no incluye una consulta masiva de barrido; si se
  necesita, construirla a partir del procedimiento manual de arriba.

## Archivos tocados por el fix de código

| Archivo | Cambio |
|---|---|
| `src/database/repositories/solicitud_transferencia_repository.py` | `get_resumen_agregado_por_oc_id` |
| `src/database/services/stock_transfer_service.py` | `_reevaluar_cierre_pedido_tras_reintento`, invocado tras reintento de ST exitoso |

---
**Fecha:** 2026-08-27 (incidente #2, corrección manual de datos)
