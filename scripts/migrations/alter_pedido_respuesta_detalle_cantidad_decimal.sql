-- ============================================================================
-- Migración: Cantidades en pedido_respuesta_proveedor_detalle de INT a DECIMAL
-- ============================================================================
-- Descripción: Permite cantidades decimales (ej. 0.5) en respuesta del proveedor.
--              cantidad_confirmada_total recibe el TOTAL del flujo anterior (pedido
--              detalle); debe almacenar el valor tal cual, sin redondear a entero.
--              Ejecutar este script en la BD para que las cantidades no se trunquen.
-- Fecha: 2026-03-02
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT 'Migración: pedido_respuesta_proveedor_detalle cantidades → DECIMAL(18,4)';
PRINT '============================================================================';
GO

IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'pedido_respuesta_proveedor_detalle')
BEGIN
    -- Eliminar CHECK de cantidad_confirmada_total >= 0 (se recreará después)
    DECLARE @ConstraintName NVARCHAR(200);
    DECLARE @Sql NVARCHAR(500);
    DECLARE cur CURSOR LOCAL FOR
        SELECT name FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID('pedido_respuesta_proveedor_detalle')
        AND name LIKE '%cantidad_confirmada%';
    OPEN cur;
    FETCH NEXT FROM cur INTO @ConstraintName;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @Sql = 'ALTER TABLE pedido_respuesta_proveedor_detalle DROP CONSTRAINT ' + QUOTENAME(@ConstraintName);
        EXEC sp_executesql @Sql;
        PRINT '  ✓ Constraint ' + @ConstraintName + ' eliminada.';
        FETCH NEXT FROM cur INTO @ConstraintName;
    END
    CLOSE cur;
    DEALLOCATE cur;

    -- Cambiar columnas a DECIMAL(18,4)
    ALTER TABLE [dbo].[pedido_respuesta_proveedor_detalle]
    ALTER COLUMN cantidad_solicitada_total DECIMAL(18, 4) NOT NULL;
    PRINT '  ✅ cantidad_solicitada_total → DECIMAL(18,4).';

    ALTER TABLE [dbo].[pedido_respuesta_proveedor_detalle]
    ALTER COLUMN cantidad_confirmada_total DECIMAL(18, 4) NOT NULL;
    PRINT '  ✅ cantidad_confirmada_total → DECIMAL(18,4).';

    -- Recrear CHECK: cantidad_confirmada_total >= 0
    IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('pedido_respuesta_proveedor_detalle') AND name = 'CK_respuesta_detalle_cantidad_confirmada_no_negativa')
    BEGIN
        ALTER TABLE [dbo].[pedido_respuesta_proveedor_detalle]
        ADD CONSTRAINT CK_respuesta_detalle_cantidad_confirmada_no_negativa CHECK (cantidad_confirmada_total >= 0);
        PRINT '  ✅ Constraint CHECK (cantidad_confirmada_total >= 0) agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla pedido_respuesta_proveedor_detalle no existe. Nada que alterar.';
END
GO

PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada.';
PRINT '============================================================================';
GO

SET NOCOUNT OFF;
GO
