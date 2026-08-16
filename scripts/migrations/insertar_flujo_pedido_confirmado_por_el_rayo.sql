-- ============================================================================
-- Migración: Insertar "Pedido Confirmado por El Rayo" en la secuencia de flujo
-- ============================================================================
-- Descripción: "Pedido Confirmado por El Rayo" (MABEL_TRADING) se agregó al
--              catálogo en la migración 629 (correos legacy de
--              email_notifier_pedido.py) con orden_flujo=NULL, así que no
--              aparecía en la secuencia numerada "Plantilla Excel -> ODC a
--              SAP" del admin, aunque el código sigue enviándolo de verdad:
--              se dispara al hacer clic en "Confirmar" (botón habilitado solo
--              en CONFIRMADO POR PRODUCCION=23, ver crear_respuesta_desde_pedido
--              en pedidos_proveedor.py), que pasa el pedido a REDISTRIBUCION
--              (4) y notifica a MABEL TRADING.
--
--              Cronológicamente es la contraparte de éxito de "Pedido
--              Cancelado por El Rayo" (orden_flujo=4, migración 634): al
--              llegar a CONFIRMADO POR PRODUCCION, El Rayo o cancela (4) o
--              confirma (este correo). Se inserta en orden_flujo=5 y se
--              recorren +1 los siguientes (Pedido Cancelado, Redistribución
--              Confirmada, Orden de Compra Generada, OC y ST Despacho x2,
--              Error en OC y ST), mismo patrón que la migración 628.
--
--              Guardado con IF NOT EXISTS (por posición ya correcta) para que
--              sea seguro repetir la ejecución sin volver a desplazar todo.
-- Fecha: 2026-08-14
-- ============================================================================

PRINT '🔧 Iniciando migración: insertar Pedido Confirmado por El Rayo en el flujo (orden_flujo=5)';
GO

IF NOT EXISTS (
    SELECT 1 FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Confirmado por El Rayo' AND orden_flujo = 5
)
BEGIN
    UPDATE notificacion_tipo_correo
        SET orden_flujo = orden_flujo + 1,
            modificado_por = 'insertar_confirmado_por_el_rayo_2026-08-14',
            modificado_fecha = GETDATE()
        WHERE orden_flujo >= 5;

    UPDATE notificacion_tipo_correo
        SET orden_flujo = 5,
            modificado_por = 'insertar_confirmado_por_el_rayo_2026-08-14',
            modificado_fecha = GETDATE()
        WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Confirmado por El Rayo';

    PRINT '✅ "Pedido Confirmado por El Rayo" insertado en orden_flujo=5; siguientes correos recorridos +1.';
END
ELSE
BEGIN
    PRINT '✓ "Pedido Confirmado por El Rayo" ya está en orden_flujo=5.';
END
GO
