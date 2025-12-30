-- ============================================================================
-- Documentación de estados actualizados para pedido (FASE 3)
-- ============================================================================
-- Estados válidos ahora son:
-- - PENDIENTE_CONFIRMACION_PROVEEDOR (inicial, Fase 2)
-- - RESPUESTA_PROVEEDOR_CARGADA (Fase 3: respuesta cargada, pendiente revisión)
-- - EN_REVISION (bajo revisión interna)
-- - CONFIRMADO_PROVEEDOR (aprobado después de revisión)
-- - RECHAZADO_PROVEEDOR
-- - EN_PROCESO
-- - COMPLETADO
-- 
-- NOTA: No requiere ALTER TABLE, solo documentación.
-- El campo estado ya existe y es NVARCHAR(50), acepta cualquier valor.
-- ============================================================================

-- Este script es solo documentación. No ejecuta cambios en la BD.
-- Los estados se usan en el código Python al actualizar el estado del pedido.

PRINT 'Documentación de estados actualizada. No se requieren cambios en la estructura de la BD.';
GO

