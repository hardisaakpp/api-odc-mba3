-- ============================================================================
-- Migración: Agregar correo "Diferencia en Pedido" al catálogo (MABEL_TRADING)
-- ============================================================================
-- Descripción: Nuevo correo (req. 1.2, Gestión de pedidos parciales): se envía a
--              MABEL TRADING cuando Administración El Rayo (odcsap.view) confirma un
--              pedido cuyo Total quedó por debajo de la cantidad originalmente
--              solicitada en la plantilla Excel (cantidad_solicitada_original) y elige
--              "Confirmar pedido, generar nuevo pedido con la diferencia" en el modal
--              de POST /api/pedidos/{pedido_id}/confirmar-con-diferencia. El pedido
--              nuevo ("hijo", numero_pedido = "<original>.NN") queda en estado
--              PRODUCCION POSPUESTA (22).
--
--              orden_flujo = 12: siguiente puesto libre tras el 11 que dejó vacante
--              consolidar_correo_oc_listo_despacho (migración 640).
-- Fecha: 2026-08-17
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar correo Diferencia en Pedido';
GO

IF NOT EXISTS (
    SELECT 1 FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Diferencia en Pedido'
)
BEGIN
    INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, orden_flujo, creado_por)
    VALUES (
        'MABEL_TRADING',
        N'Diferencia en Pedido',
        N'Se envía a MABEL TRADING cuando Administración El Rayo confirma un pedido con cantidades por debajo de lo solicitado originalmente y genera un pedido nuevo con la diferencia (estado Producción Pospuesta)',
        12,
        'add_diferencia_pedido_2026-08-17'
    );

    PRINT '✅ Correo "Diferencia en Pedido" agregado en orden_flujo = 12.';
END
ELSE
BEGIN
    PRINT '✓ El correo "Diferencia en Pedido" ya existe.';
END
GO

PRINT '';
PRINT '✅ Migración completada: correo Diferencia en Pedido';
GO
