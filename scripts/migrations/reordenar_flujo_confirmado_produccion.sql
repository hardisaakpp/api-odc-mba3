-- ============================================================================
-- Migración: Reordenar orden_flujo alrededor de "Pedido Confirmado por Producción"
-- ============================================================================
-- Descripción: "Pedido Confirmado por Producción" (OPERACIONES) quedó en
--              orden_flujo=5 desde que se agregó (migración 628), pero
--              cronológicamente ocurre justo al llegar al estado CONFIRMADO
--              POR PRODUCCION (23) — el mismo punto del flujo donde ahora
--              también puede ocurrir "Pedido Cancelado por El Rayo"
--              (MABEL_TRADING, migración 634, orden_flujo=3). Al confirmar
--              Producción se notifica primero a Administración El Rayo; solo
--              después, si El Rayo decide cancelar, se notifica a MABEL. Se
--              reordena para reflejar esa secuencia real:
--                - Pedido Confirmado por Producción: 5 -> 3
--                - Pedido Cancelado por El Rayo:      3 -> 4
--                - Pedido Cancelado (Redistribución): 4 -> 5
--              orden_flujo >= 6 no cambia. Es una operación set-based (SQL
--              Server evalúa el CASE con los valores previos a la
--              actualización, no importa el orden de las filas) y se ubica
--              por (tipo_notificacion, tipo_correo), no por el número de
--              orden_flujo, para ser segura sin importar el estado previo del
--              ambiente donde se ejecute.
-- Fecha: 2026-08-14
-- ============================================================================

PRINT '🔧 Iniciando migración: reordenar flujo alrededor de Pedido Confirmado por Producción';
GO

UPDATE notificacion_tipo_correo
    SET orden_flujo = CASE
            WHEN tipo_notificacion = 'OPERACIONES'
                 AND tipo_correo = N'Pedido Confirmado por Producción' THEN 3
            WHEN tipo_notificacion = 'MABEL_TRADING'
                 AND tipo_correo = N'Pedido Cancelado por El Rayo' THEN 4
            WHEN tipo_notificacion = 'OPERACIONES'
                 AND tipo_correo = N'Pedido Cancelado' THEN 5
            ELSE orden_flujo
        END,
        modificado_por = 'reordenar_confirmado_produccion_2026-08-14',
        modificado_fecha = GETDATE()
    WHERE (tipo_notificacion = 'OPERACIONES' AND tipo_correo IN (N'Pedido Confirmado por Producción', N'Pedido Cancelado'))
       OR (tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Cancelado por El Rayo');

PRINT '✅ Migración completada: orden_flujo reordenado (3=Confirmado por Producción, 4=Cancelado por El Rayo, 5=Cancelado)';
GO
