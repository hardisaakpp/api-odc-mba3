-- ============================================================================
-- Migración: "Pedido Cancelado por El Rayo" también notifica a Producción El Rayo
-- ============================================================================
-- Descripción: Cuando Administración El Rayo (odcsap.view) cancela un pedido
--              desde Detalle del Pedido, Producción El Rayo debe enterarse:
--              fue ella quien confirmó el pedido originalmente (botón
--              "Confirmar Producción"). Se sigue el mismo patrón ya usado
--              para "OC y Solicitudes de Transferencia - Listo para Despacho"
--              (una fila por audiencia, mismo tipo_correo, cada una con nota
--              cruzada a la otra) — el envío real ahora consulta
--              destinatarios de ambos tipo_notificacion con
--              _build_unique_recipients(["MABEL_TRADING", "PRODUCCION_ELRAYO"], ...).
--
--              Se agrega la fila PRODUCCION_ELRAYO en orden_flujo=5 (justo
--              después de "Pedido Cancelado por El Rayo" en 4, antes de
--              "Pedido Confirmado por El Rayo"), recorriendo +1 el resto de
--              la secuencia. Guardado con IF NOT EXISTS para ser seguro de
--              repetir.
-- Fecha: 2026-08-14
-- ============================================================================

PRINT '🔧 Iniciando migración: agregar audiencia Producción El Rayo a "Pedido Cancelado por El Rayo"';
GO

UPDATE notificacion_tipo_correo
    SET descripcion = N'Se envía a MABEL TRADING cuando Administración El Rayo cancela un pedido desde Detalle del Pedido (botón "Cancelar Pedido"), disponible solo en estado Confirmado por Producción. También llega a Producción El Rayo',
        modificado_por = 'add_produccion_elrayo_cancelado_2026-08-14',
        modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Cancelado por El Rayo';

IF NOT EXISTS (
    SELECT 1 FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'PRODUCCION_ELRAYO' AND tipo_correo = N'Pedido Cancelado por El Rayo'
)
BEGIN
    UPDATE notificacion_tipo_correo
        SET orden_flujo = orden_flujo + 1,
            modificado_por = 'add_produccion_elrayo_cancelado_2026-08-14',
            modificado_fecha = GETDATE()
        WHERE orden_flujo >= 5;

    INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, orden_flujo, creado_por)
    VALUES (
        'PRODUCCION_ELRAYO',
        N'Pedido Cancelado por El Rayo',
        N'Se envía a Producción El Rayo cuando Administración El Rayo cancela un pedido que Producción ya había confirmado. También llega a MABEL_TRADING',
        5,
        'add_produccion_elrayo_cancelado_2026-08-14'
    );

    PRINT '✅ Fila PRODUCCION_ELRAYO agregada en orden_flujo=5; siguientes correos recorridos +1.';
END
ELSE
BEGIN
    PRINT '✓ La fila PRODUCCION_ELRAYO para "Pedido Cancelado por El Rayo" ya existe.';
END
GO
