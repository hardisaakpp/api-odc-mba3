-- ============================================================================
-- Script de Migración: Agregar estado LISTO PARA REDISTRIBUCION a pedido_estado
-- ============================================================================
-- Descripción: Agrega el estado LISTO PARA REDISTRIBUCION (id=25) a la tabla
--              pedido_estado. Botón "Aceptar" sobre un pedido "hijo" en
--              PRODUCCION POSPUESTA (22): Mabel Trading acepta la diferencia
--              pospuesta y la envía directo a la cola de redistribución, sin
--              pasar por "Confirmado por El Rayo" (4). Solo debe ser visible en
--              el listado de Redistribución (ver _filtro_redistribucion /
--              excluir_listo_para_redistribucion en pedido_cabecera_repository.py).
-- Fecha: 2026-08-19
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar estado LISTO PARA REDISTRIBUCION';
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 25)
BEGIN
    PRINT '➕ Agregando estado LISTO PARA REDISTRIBUCION (id=25)...';

    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo)
    VALUES (25, N'LISTO PARA REDISTRIBUCION', 25, 1);

    PRINT '✅ Estado LISTO PARA REDISTRIBUCION agregado exitosamente.';
END
ELSE
BEGIN
    PRINT '✓ El estado LISTO PARA REDISTRIBUCION ya existe.';
END
GO

PRINT '';
PRINT '📋 Estado LISTO PARA REDISTRIBUCION:';
SELECT id, nombre, orden, activo
FROM [dbo].[pedido_estado]
WHERE id = 25;

PRINT '';
PRINT '✅ Migración completada: Estado LISTO PARA REDISTRIBUCION agregado';
GO
