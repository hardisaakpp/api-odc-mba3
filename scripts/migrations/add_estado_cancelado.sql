-- ============================================================================
-- Script de Migración: Agregar estado CANCELADO a pedido_estado
-- ============================================================================
-- Descripción: Agrega el estado CANCELADO (id=19) a la tabla pedido_estado
-- Fecha: 2026-02-04
-- ============================================================================

USE [MBA3_Consultas]
GO

PRINT '🔧 Iniciando migración: Agregar estado CANCELADO';
GO

-- ============================================================================
-- Agregar estado CANCELADO si no existe
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 19)
BEGIN
    PRINT '➕ Agregando estado CANCELADO (id=19)...';
    
    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo)
    VALUES (19, N'CANCELADO', 19, 1);
    
    PRINT '✅ Estado CANCELADO agregado exitosamente.';
END
ELSE
BEGIN
    PRINT '✓ El estado CANCELADO ya existe.';
END
GO

-- ============================================================================
-- Verificar que el estado se creó correctamente
-- ============================================================================
PRINT '';
PRINT '📋 Estado CANCELADO:';
SELECT id, nombre, orden, activo 
FROM [dbo].[pedido_estado] 
WHERE id = 19;
GO

PRINT '';
PRINT '✅ Migración completada: Estado CANCELADO agregado';
GO
