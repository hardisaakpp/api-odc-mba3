-- ============================================================================
-- Script de Migración: Agregar correo "Pedido Confirmado por Producción" al catálogo
-- ============================================================================
-- Descripción: Nuevo correo (req. 1.8, botón "Confirmar Producción"): se envía a
--              Administración El Rayo (OPERACIONES) cuando Producción confirma un
--              pedido, transición GESTIONAR_PEDIDO (3) -> CONFIRMADO_POR_PRODUCCION (23).
--
--              Se ubica en el flujo (orden_flujo) justo después de "Plantilla Excel
--              Procesada" (1) y antes de "Redistribución Confirmada por MABEL TRADING"
--              (que pasa de 5 a 6): renumera +1 los correos con orden_flujo >= 5 para
--              liberar el puesto 5. Es una operación set-based (SQL Server evalúa el
--              SET con los valores previos a la actualización), segura sin importar
--              el orden de las filas.
-- Fecha: 2026-08-13
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar correo Pedido Confirmado por Producción';
GO

IF NOT EXISTS (
    SELECT 1 FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Pedido Confirmado por Producción'
)
BEGIN
    UPDATE notificacion_tipo_correo
        SET orden_flujo = orden_flujo + 1
        WHERE orden_flujo >= 5;

    INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, orden_flujo, creado_por)
    VALUES (
        'OPERACIONES',
        N'Pedido Confirmado por Producción',
        N'Se envía a Administración El Rayo cuando Producción confirma un pedido (botón "Confirmar Producción"); el pedido pasa de Gestionar Pedido a Confirmado por Producción',
        5,
        'seed_confirmado_produccion_2026-08-13'
    );

    PRINT '✅ Correo "Pedido Confirmado por Producción" agregado y flujo renumerado.';
END
ELSE
BEGIN
    PRINT '✓ El correo "Pedido Confirmado por Producción" ya existe.';
END
GO

PRINT '';
PRINT '✅ Migración completada: correo Pedido Confirmado por Producción';
GO
