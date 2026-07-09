-- ============================================================================
-- Script SQL para documentar estado CONFIRMADO_ENVIADO (FASE 6)
-- ============================================================================
-- Este estado se asigna a un pedido cuando TODAS sus ODC han sido enviadas
-- exitosamente a SAP y notificadas al proveedor.
-- 
-- Condiciones para asignar CONFIRMADO_ENVIADO:
-- - Todas las ODC asociadas al pedido están en estado ENVIADA
-- - Todas las ODC tienen DocEntry válido (no NULL, no 0)
-- - No hay ODC en estado PENDIENTE o ERROR
-- 
-- Este estado representa el cierre operativo del pedido en el sistema.
-- ============================================================================

-- Nota: El estado se maneja como string en la columna 'estado' de la tabla 'pedido'
-- No se requiere modificación de esquema, solo documentación.

PRINT 'Estado CONFIRMADO_ENVIADO disponible para uso en tabla pedido.';
PRINT 'Asegúrese de que la columna estado existe (ver add_estado_pedido.sql)';
PRINT '';
PRINT 'Estados posibles del pedido:';
PRINT '  - PENDIENTE_CONFIRMACION_PROVEEDOR (estado inicial)';
PRINT '  - CONFIRMADO_PROVEEDOR';
PRINT '  - RECHAZADO_PROVEEDOR';
PRINT '  - EN_PROCESO';
PRINT '  - COMPLETADO';
PRINT '  - CONFIRMADO_ENVIADO (FASE 6: todas las ODC enviadas a SAP)';
GO

