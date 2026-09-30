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

-- Idempotente (2026-09-24): solo actúa si alguna de las dos columnas aún no es
-- DECIMAL(18,4). El CHECK se busca por su definición y no por nombre: el que
-- crea add_respuesta_proveedor_tables.sql es anónimo y SQL Server lo nombra
-- truncado (CK__pedido_re__canti__XXXX), así que el filtro por nombre no lo
-- encontraba y el ALTER COLUMN fallaba en una BD nueva.
IF EXISTS (
    SELECT 1 FROM sys.columns c
    JOIN sys.types t ON t.user_type_id = c.user_type_id
    WHERE c.object_id = OBJECT_ID('pedido_respuesta_proveedor_detalle')
      AND c.name IN ('cantidad_solicitada_total', 'cantidad_confirmada_total')
      AND NOT (t.name = 'decimal' AND c.precision = 18 AND c.scale = 4)
)
BEGIN
    -- Eliminar CHECK de cantidad_confirmada_total >= 0 (se recreará después)
    DECLARE @ConstraintName NVARCHAR(200);
    DECLARE @Sql NVARCHAR(500);
    DECLARE cur CURSOR LOCAL FOR
        SELECT name FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID('pedido_respuesta_proveedor_detalle')
        AND definition LIKE '%\[cantidad_confirmada_total\]%' ESCAPE '\';
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
    PRINT '  ⏭️ Columnas ya en DECIMAL(18,4) o tabla inexistente. Nada que alterar.';
END
GO

PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada.';
PRINT '============================================================================';
GO

SET NOCOUNT OFF;
GO
