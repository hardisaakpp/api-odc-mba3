-- ============================================================================
-- Script para agregar campos de respuesta SAP a orden_compra_cabecera
-- ============================================================================
-- Este script agrega los campos necesarios para persistir la respuesta de SAP
-- directamente en la tabla orden_compra_cabecera
-- ============================================================================

USE store_control;
GO

-- Agregar campo respuesta_sap (mensaje o respuesta de SAP)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_cabecera' 
    AND COLUMN_NAME = 'respuesta_sap'
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD respuesta_sap NVARCHAR(MAX) NULL;
    
    PRINT '✅ Campo respuesta_sap agregado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo respuesta_sap ya existe';
END
GO

-- Agregar campo fecha_procesado (timestamp cuando se envió a SAP)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_cabecera' 
    AND COLUMN_NAME = 'fecha_procesado'
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD fecha_procesado DATETIME NULL;
    
    PRINT '✅ Campo fecha_procesado agregado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo fecha_procesado ya existe';
END
GO

-- Agregar campo error_message (mensaje de error si falla)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_cabecera' 
    AND COLUMN_NAME = 'error_message'
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD error_message NVARCHAR(MAX) NULL;
    
    PRINT '✅ Campo error_message agregado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo error_message ya existe';
END
GO

-- Agregar campo error_code (código de error de SAP)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_cabecera' 
    AND COLUMN_NAME = 'error_code'
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD error_code VARCHAR(50) NULL;
    
    PRINT '✅ Campo error_code agregado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo error_code ya existe';
END
GO

-- Agregar campo error_source (origen del error: SAP, BACKEND, SAP_CONNECTION)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_cabecera' 
    AND COLUMN_NAME = 'error_source'
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD error_source VARCHAR(50) NULL;
    
    PRINT '✅ Campo error_source agregado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo error_source ya existe';
END
GO

-- Agregar campo updated_at (timestamp de última actualización)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_cabecera' 
    AND COLUMN_NAME = 'updated_at'
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD updated_at DATETIME DEFAULT GETDATE() NULL;
    
    PRINT '✅ Campo updated_at agregado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo updated_at ya existe';
END
GO

-- Crear índice en estado para búsquedas más rápidas (si no existe)
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE name = 'IX_orden_compra_cabecera_estado' 
    AND object_id = OBJECT_ID('orden_compra_cabecera')
)
BEGIN
    CREATE INDEX IX_orden_compra_cabecera_estado 
    ON orden_compra_cabecera(estado);
    
    PRINT '✅ Índice en estado creado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Índice en estado ya existe';
END
GO

-- Crear índice en referencia_despacho para búsquedas más rápidas (si no existe)
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE name = 'IX_orden_compra_cabecera_referencia_despacho' 
    AND object_id = OBJECT_ID('orden_compra_cabecera')
)
BEGIN
    CREATE INDEX IX_orden_compra_cabecera_referencia_despacho 
    ON orden_compra_cabecera(referencia_despacho);
    
    PRINT '✅ Índice en referencia_despacho creado';
END
ELSE
BEGIN
    PRINT 'ℹ️ Índice en referencia_despacho ya existe';
END
GO

PRINT '';
PRINT '✅ Script completado exitosamente';
PRINT 'La tabla orden_compra_cabecera ahora tiene los campos necesarios para persistir respuestas SAP';



