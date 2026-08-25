-- ============================================================================
-- Migración: Agregar marca a tienda
-- ============================================================================
-- Descripción: Marca (ROLAND/REGIONS/DESCUENTON) de cada tienda, sincronizada
--              desde sc_maestros.dbo.almacenes_local (columna u_marca, por
--              u_bod_tra = tienda.codigo -- whs_code en esa tabla es el
--              código del Centro de Distribución RL-CD/RG-CD/OUT-CD, no el
--              código de tienda). Base para resolver a qué bodega pertenece
--              cada tienda sin depender del heurístico de prefijo de código.
--              Se puebla de forma no bloqueante al crear la tienda
--              (get_or_create_tienda) y mediante
--              scripts/backfill_marca_tienda.py para las ya existentes.
--              Requerimiento PYTD002 (generación de 2 ODC para pedidos que
--              mezclan tiendas ROLAND y REGIONS).
-- Fecha: 2026-08-20
-- ============================================================================

SET NOCOUNT ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[tienda]')
    AND name = N'marca'
)
BEGIN
    ALTER TABLE [dbo].[tienda]
    ADD marca NVARCHAR(20) NULL;
    PRINT '  ✅ Columna marca agregada a tienda.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna marca ya existe en tienda.';
END
GO

PRINT '✅ Migración completada: add_marca_tienda';
