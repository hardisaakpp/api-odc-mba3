-- ============================================================================
-- Migración: Cantidades en distribucion_confirmada e historial de INT a DECIMAL
-- ============================================================================
-- Descripción: Permite cantidades decimales (ej. 0.5) en la redistribución
--              confirmada. Al hacer "Enviar ODC a SAP", los valores se guardan
--              en distribucion_confirmada; si son INT, 0.5 se trunca a 0 y
--              el proceso SAP omite el producto. Con DECIMAL(18,4) se conservan
--              las cifras decimales y el procesamiento SAP incluye esos ítems.
-- Cuándo ejecutar: En instalaciones donde distribucion_confirmada fue creada
--                  con el script original (columnas INT).
-- Fecha: 2026-03-03
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT 'Migración: distribucion_confirmada + historial cantidades → DECIMAL(18,4)';
PRINT '============================================================================';
GO

-- ============================================================================
-- 1. Tabla distribucion_confirmada
-- ============================================================================
IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'distribucion_confirmada')
BEGIN
    PRINT '';
    PRINT '📋 Tabla: distribucion_confirmada';

    -- Eliminar CHECK existentes en cantidad_solicitada, cantidad_confirmada, cantidad_asignada
    DECLARE @ConstraintName NVARCHAR(200);
    DECLARE @Sql NVARCHAR(500);
    DECLARE cur CURSOR LOCAL FOR
        SELECT name FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID('distribucion_confirmada');
    OPEN cur;
    FETCH NEXT FROM cur INTO @ConstraintName;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @Sql = 'ALTER TABLE distribucion_confirmada DROP CONSTRAINT ' + QUOTENAME(@ConstraintName);
        EXEC sp_executesql @Sql;
        PRINT '  ✓ Constraint ' + @ConstraintName + ' eliminada.';
        FETCH NEXT FROM cur INTO @ConstraintName;
    END
    CLOSE cur;
    DEALLOCATE cur;

    -- Cambiar columnas a DECIMAL(18,4)
    ALTER TABLE [dbo].[distribucion_confirmada]
    ALTER COLUMN cantidad_solicitada DECIMAL(18, 4) NOT NULL;
    PRINT '  ✅ cantidad_solicitada → DECIMAL(18,4).';

    ALTER TABLE [dbo].[distribucion_confirmada]
    ALTER COLUMN cantidad_confirmada DECIMAL(18, 4) NOT NULL;
    PRINT '  ✅ cantidad_confirmada → DECIMAL(18,4).';

    ALTER TABLE [dbo].[distribucion_confirmada]
    ALTER COLUMN cantidad_asignada DECIMAL(18, 4) NOT NULL;
    PRINT '  ✅ cantidad_asignada → DECIMAL(18,4).';

    -- Recrear CHECK: cantidades >= 0
    IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('distribucion_confirmada') AND name = 'CK_distribucion_confirmada_cantidades_no_negativas')
    BEGIN
        ALTER TABLE [dbo].[distribucion_confirmada]
        ADD CONSTRAINT CK_distribucion_confirmada_cantidades_no_negativas
        CHECK (cantidad_solicitada >= 0 AND cantidad_confirmada >= 0 AND cantidad_asignada >= 0);
        PRINT '  ✅ Constraint CHECK (cantidades >= 0) agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla distribucion_confirmada no existe. Nada que alterar.';
END
GO

-- ============================================================================
-- 2. Tabla distribucion_confirmada_historial
-- ============================================================================
IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'distribucion_confirmada_historial')
BEGIN
    PRINT '';
    PRINT '📋 Tabla: distribucion_confirmada_historial';

    ALTER TABLE [dbo].[distribucion_confirmada_historial]
    ALTER COLUMN cantidad_asignada_anterior DECIMAL(18, 4) NULL;
    PRINT '  ✅ cantidad_asignada_anterior → DECIMAL(18,4).';

    ALTER TABLE [dbo].[distribucion_confirmada_historial]
    ALTER COLUMN cantidad_asignada_nuevo DECIMAL(18, 4) NULL;
    PRINT '  ✅ cantidad_asignada_nuevo → DECIMAL(18,4).';
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla distribucion_confirmada_historial no existe. Nada que alterar.';
END
GO

PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada.';
PRINT '============================================================================';
GO

SET NOCOUNT OFF;
GO
