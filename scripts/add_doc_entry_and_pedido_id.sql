-- ============================================================================
-- Script: Completar Fase 5 - Campos faltantes en orden_compra_cabecera
-- ============================================================================
-- Agrega: doc_entry (INTEGER) y pedido_id (UNIQUEIDENTIFIER opcional)
-- Para soportar trazabilidad completa con SAP y flujo de pedidos confirmados
-- ============================================================================

-- Ejecuta en la base de datos actual (la de la conexión).

-- Agregar campo doc_entry (obligatorio para trazabilidad SAP)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_cabecera' 
    AND COLUMN_NAME = 'doc_entry'
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD doc_entry INT NULL;
    
    PRINT '✅ Campo doc_entry agregado a orden_compra_cabecera';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo doc_entry ya existe';
END
GO

-- Índice único para evitar duplicados de DocEntry (donde no sea NULL)
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE name = 'idx_oc_doc_entry' 
    AND object_id = OBJECT_ID('orden_compra_cabecera')
)
BEGIN
    CREATE UNIQUE INDEX idx_oc_doc_entry 
    ON orden_compra_cabecera(doc_entry) 
    WHERE doc_entry IS NOT NULL;
    
    PRINT '✅ Índice único idx_oc_doc_entry creado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Índice idx_oc_doc_entry ya existe';
END
GO

-- Agregar campo pedido_id (para vincular con pedido cuando viene de confirmación)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_cabecera' 
    AND COLUMN_NAME = 'pedido_id'
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD pedido_id UNIQUEIDENTIFIER NULL;
    
    PRINT '✅ Campo pedido_id agregado a orden_compra_cabecera';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo pedido_id ya existe';
END
GO

-- Índice para búsquedas por pedido_id
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE name = 'idx_oc_pedido_id' 
    AND object_id = OBJECT_ID('orden_compra_cabecera')
)
BEGIN
    CREATE INDEX idx_oc_pedido_id 
    ON orden_compra_cabecera(pedido_id)
    WHERE pedido_id IS NOT NULL;
    
    PRINT '✅ Índice idx_oc_pedido_id creado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Índice idx_oc_pedido_id ya existe';
END
GO

-- FK opcional a pedido (comentado por si quieres agregarlo después)
-- Descomentar solo si quieres constraint de integridad referencial
/*
IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys 
    WHERE name = 'FK_oc_pedido' 
    AND parent_object_id = OBJECT_ID('orden_compra_cabecera')
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD CONSTRAINT FK_oc_pedido 
    FOREIGN KEY (pedido_id) REFERENCES pedido(pedido_id);
    
    PRINT '✅ FK FK_oc_pedido creada';
END
ELSE
BEGIN
    PRINT 'ℹ️ FK FK_oc_pedido ya existe';
END
*/
GO

-- Verificación final (ejecutar manualmente si necesitas verificar)
-- SELECT 
--     COLUMN_NAME, 
--     DATA_TYPE, 
--     IS_NULLABLE,
--     CHARACTER_MAXIMUM_LENGTH
-- FROM INFORMATION_SCHEMA.COLUMNS
-- WHERE TABLE_NAME = 'orden_compra_cabecera'
-- ORDER BY ORDINAL_POSITION;

PRINT 'Script completado. Verifica la estructura de la tabla arriba.';
GO

