-- Índices para listado paginado GET /ordenes-compra (filtro por estado + orden created_at DESC)
-- Ejecutar en SQL Server tras desplegar paginación en API.

PRINT 'Migración: índices listado orden_compra_cabecera';
PRINT '';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND type = 'U')
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'idx_orden_compra_estado_created_at'
          AND object_id = OBJECT_ID('orden_compra_cabecera')
    )
    BEGIN
        PRINT '  ➕ idx_orden_compra_estado_created_at...';
        CREATE INDEX idx_orden_compra_estado_created_at
            ON orden_compra_cabecera (estado, created_at DESC);
        PRINT '  ✅ Creado.';
    END
    ELSE
        PRINT '  ✓ idx_orden_compra_estado_created_at ya existe.';

    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'idx_orden_compra_referencia_despacho'
          AND object_id = OBJECT_ID('orden_compra_cabecera')
    )
    BEGIN
        PRINT '  ➕ idx_orden_compra_referencia_despacho...';
        CREATE INDEX idx_orden_compra_referencia_despacho
            ON orden_compra_cabecera (referencia_despacho);
        PRINT '  ✅ Creado.';
    END
    ELSE
        PRINT '  ✓ idx_orden_compra_referencia_despacho ya existe.';

    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'idx_orden_compra_created_at'
          AND object_id = OBJECT_ID('orden_compra_cabecera')
    )
    BEGIN
        PRINT '  ➕ idx_orden_compra_created_at...';
        CREATE INDEX idx_orden_compra_created_at
            ON orden_compra_cabecera (created_at DESC);
        PRINT '  ✅ Creado.';
    END
    ELSE
        PRINT '  ✓ idx_orden_compra_created_at ya existe.';
END
ELSE
    PRINT '  ⚠️ Tabla orden_compra_cabecera no existe.';

PRINT '';
PRINT 'Fin migración listado OC.';
