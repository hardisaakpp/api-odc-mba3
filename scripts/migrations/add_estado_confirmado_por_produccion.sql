-- ============================================================================
-- Script de Migración: Agregar estado CONFIRMADO POR PRODUCCION a pedido_estado
-- ============================================================================
-- Descripción: Agrega el estado CONFIRMADO POR PRODUCCION (id=23) a la tabla
--              pedido_estado (req. 1.8 - Nuevo perfil Producción El Rayo).
--              Se ubica en el flujo entre GESTIONAR PEDIDO (3) y
--              CONFIRMADO POR EL RAYO (4): Producción registra la "Cantidad a
--              producir" y confirma; luego Administración El Rayo (odcsap.view)
--              valida y confirma hacia Mabel Trading.
-- Fecha: 2026-08-12
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar estado CONFIRMADO POR PRODUCCION';
GO

-- ============================================================================
-- Agregar estado CONFIRMADO POR PRODUCCION si no existe
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 23)
BEGIN
    PRINT '➕ Agregando estado CONFIRMADO POR PRODUCCION (id=23)...';

    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo)
    VALUES (23, N'CONFIRMADO POR PRODUCCION', 23, 1);

    PRINT '✅ Estado CONFIRMADO POR PRODUCCION agregado exitosamente.';
END
ELSE
BEGIN
    PRINT '✓ El estado CONFIRMADO POR PRODUCCION ya existe.';
END
GO

-- ============================================================================
-- Verificación
-- ============================================================================
PRINT '';
PRINT '📋 Estado CONFIRMADO POR PRODUCCION:';
SELECT id, nombre, orden, activo
FROM [dbo].[pedido_estado]
WHERE id = 23;

PRINT '';
PRINT '✅ Migración completada: Estado CONFIRMADO POR PRODUCCION agregado';
GO
