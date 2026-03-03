-- ============================================================================
-- Migración: Cambiar cantidad en pedido_detalle_tienda de INT a DECIMAL
-- ============================================================================
-- Descripción: Permite cantidades decimales en la distribución por tienda
--              (ej. 0.5, 1.5, 2.25) en lugar de solo enteros.
--              Sin esta migración, valores como 0.5 se truncarían a 0.
-- Cuándo ejecutar: Si la tabla fue creada con cantidad INT (instalaciones
--                  antiguas o scripts previos). Las nuevas instalaciones con
--                  create_pedido_tables.sql ya usan DECIMAL(18,4).
-- Fecha: 2026-03-02
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT 'Migración: pedido_detalle_tienda.cantidad → DECIMAL(18,4)';
PRINT '============================================================================';
GO

IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'pedido_detalle_tienda')
BEGIN
    -- Eliminar constraint(s) CHECK existentes en la tabla (p. ej. cantidad > 0)
    DECLARE @ConstraintName NVARCHAR(200);
    DECLARE @Sql NVARCHAR(500);
    DECLARE cur CURSOR LOCAL FOR
        SELECT name FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID('pedido_detalle_tienda');
    OPEN cur;
    FETCH NEXT FROM cur INTO @ConstraintName;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @Sql = 'ALTER TABLE pedido_detalle_tienda DROP CONSTRAINT ' + QUOTENAME(@ConstraintName);
        EXEC sp_executesql @Sql;
        PRINT '  ✓ Constraint ' + @ConstraintName + ' eliminada.';
        FETCH NEXT FROM cur INTO @ConstraintName;
    END
    CLOSE cur;
    DEALLOCATE cur;

    -- Cambiar tipo de columna a DECIMAL(18,4)
    ALTER TABLE [dbo].[pedido_detalle_tienda]
    ALTER COLUMN cantidad DECIMAL(18, 4) NOT NULL;
    PRINT '  ✅ Columna cantidad alterada a DECIMAL(18,4).';

    -- Recrear CHECK: cantidad debe ser >= 0 (permite 0, 0.5, 1, etc.)
    ALTER TABLE [dbo].[pedido_detalle_tienda]
    ADD CONSTRAINT CK_pedido_detalle_tienda_cantidad_no_negativa CHECK (cantidad >= 0);
    PRINT '  ✅ Constraint CHECK (cantidad >= 0) agregada.';
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla pedido_detalle_tienda no existe. Nada que alterar.';
END
GO

PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada.';
PRINT '============================================================================';
GO

SET NOCOUNT OFF;
GO
