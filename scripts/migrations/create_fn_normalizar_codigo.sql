-- ============================================================================
-- Script de Migración: Crear función fn_normalizar_codigo
-- ============================================================================
-- Descripción: Crea función SQL para normalizar códigos de producto.
--              Equivalente a normalizar_codigo_producto() en src/utils.py
--              Útil para reportes, análisis y queries ad-hoc.
-- Fecha: 2026-02-06
-- Referencia: Enfoque híbrido Python/SQL para normalización
-- ============================================================================
--
-- LÓGICA:
--   1. Elimina espacios al inicio y final (LTRIM/RTRIM)
--   2. Convierte a mayúsculas (UPPER)
--   3. Elimina separadores: . - / _ espacio
--
-- EJEMPLOS:
--   'R225.1012.BCO' -> 'R2251012BCO'
--   'R225-1012-BCO' -> 'R2251012BCO'
--   'R225/1012/BCO' -> 'R2251012BCO'
--   'R225_1012_BCO' -> 'R2251012BCO'
--   'R225 1012 BCO' -> 'R2251012BCO'
--
-- NOTA: Existe versión Python equivalente en src/utils.py:normalizar_codigo_producto
--       Mantener ambas sincronizadas si se modifica la lógica.
-- ============================================================================

USE [MBA3_Consultas]
GO

PRINT '============================================================================';
PRINT '🔧 Iniciando migración: Crear función fn_normalizar_codigo';
PRINT '============================================================================';
GO

-- ============================================================================
-- Eliminar función si existe (para permitir recreación)
-- ============================================================================
IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[fn_normalizar_codigo]') AND type IN (N'FN', N'IF', N'TF'))
BEGIN
    PRINT '⚠️ Función fn_normalizar_codigo ya existe, eliminando para recrear...';
    DROP FUNCTION [dbo].[fn_normalizar_codigo];
    PRINT '✓ Función eliminada.';
END
GO

-- ============================================================================
-- Crear función fn_normalizar_codigo
-- ============================================================================
PRINT '➕ Creando función fn_normalizar_codigo...';
GO

CREATE FUNCTION [dbo].[fn_normalizar_codigo](@codigo NVARCHAR(255))
RETURNS NVARCHAR(255)
AS
BEGIN
    -- Si es NULL, devolver string vacío (igual que Python)
    IF @codigo IS NULL 
        RETURN ''
    
    -- Normalizar: TRIM + UPPER + eliminar separadores (. - / _ espacio)
    RETURN UPPER(
        REPLACE(
        REPLACE(
        REPLACE(
        REPLACE(
        REPLACE(
            LTRIM(RTRIM(@codigo)),
        '.', ''),   -- Eliminar puntos
        '-', ''),   -- Eliminar guiones
        '/', ''),   -- Eliminar barras
        '_', ''),   -- Eliminar guiones bajos
        ' ', '')    -- Eliminar espacios
    )
END
GO

PRINT '✅ Función fn_normalizar_codigo creada exitosamente.';
GO

-- ============================================================================
-- Verificar que la función funciona correctamente
-- ============================================================================
PRINT '';
PRINT '📋 Verificando función con casos de prueba:';
PRINT '';

SELECT 
    'R225.1012.BCO' AS entrada,
    [dbo].[fn_normalizar_codigo]('R225.1012.BCO') AS resultado,
    CASE WHEN [dbo].[fn_normalizar_codigo]('R225.1012.BCO') = 'R2251012BCO' THEN '✅ OK' ELSE '❌ ERROR' END AS estado
UNION ALL
SELECT 
    'R225-1012-BCO',
    [dbo].[fn_normalizar_codigo]('R225-1012-BCO'),
    CASE WHEN [dbo].[fn_normalizar_codigo]('R225-1012-BCO') = 'R2251012BCO' THEN '✅ OK' ELSE '❌ ERROR' END
UNION ALL
SELECT 
    'R225/1012/BCO',
    [dbo].[fn_normalizar_codigo]('R225/1012/BCO'),
    CASE WHEN [dbo].[fn_normalizar_codigo]('R225/1012/BCO') = 'R2251012BCO' THEN '✅ OK' ELSE '❌ ERROR' END
UNION ALL
SELECT 
    'R225_1012_BCO',
    [dbo].[fn_normalizar_codigo]('R225_1012_BCO'),
    CASE WHEN [dbo].[fn_normalizar_codigo]('R225_1012_BCO') = 'R2251012BCO' THEN '✅ OK' ELSE '❌ ERROR' END
UNION ALL
SELECT 
    'R225 1012 BCO',
    [dbo].[fn_normalizar_codigo]('R225 1012 BCO'),
    CASE WHEN [dbo].[fn_normalizar_codigo]('R225 1012 BCO') = 'R2251012BCO' THEN '✅ OK' ELSE '❌ ERROR' END
UNION ALL
SELECT 
    '  espacios  ',
    [dbo].[fn_normalizar_codigo]('  espacios  '),
    CASE WHEN [dbo].[fn_normalizar_codigo]('  espacios  ') = 'ESPACIOS' THEN '✅ OK' ELSE '❌ ERROR' END
UNION ALL
SELECT 
    NULL,
    [dbo].[fn_normalizar_codigo](NULL),
    CASE WHEN [dbo].[fn_normalizar_codigo](NULL) = '' THEN '✅ OK' ELSE '❌ ERROR' END;
GO

-- ============================================================================
-- Ejemplo de uso con datos reales (si existe la tabla)
-- ============================================================================
PRINT '';
PRINT '📋 Ejemplo de uso con pedido_detalle (si existe):';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') AND type = N'U')
BEGIN
    SELECT TOP 5
        codigo_interno AS codigo_original,
        [dbo].[fn_normalizar_codigo](codigo_interno) AS codigo_normalizado
    FROM [dbo].[pedido_detalle]
    WHERE codigo_interno IS NOT NULL;
END
ELSE
BEGIN
    PRINT '(Tabla pedido_detalle no existe, omitiendo ejemplo)';
END
GO

-- ============================================================================
-- Resumen
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada: fn_normalizar_codigo creada';
PRINT '';
PRINT 'USO:';
PRINT '  SELECT dbo.fn_normalizar_codigo(''R225.1012.BCO'')  --> R2251012BCO';
PRINT '';
PRINT 'EN REPORTES:';
PRINT '  SELECT dbo.fn_normalizar_codigo(codigo_interno) AS codigo_norm';
PRINT '  FROM pedido_detalle';
PRINT '============================================================================';
GO
