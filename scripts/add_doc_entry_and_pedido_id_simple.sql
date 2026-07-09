-- ============================================================================
-- Script SIMPLIFICADO: Completar Fase 5 - Campos faltantes
-- ============================================================================
-- Versión simplificada que funciona mejor con pyodbc
-- Ejecuta directamente los ALTER TABLE sin IF NOT EXISTS
-- ============================================================================

USE store_control;
GO

-- Agregar campo doc_entry
BEGIN TRY
    ALTER TABLE orden_compra_cabecera
    ADD doc_entry INT NULL;
    PRINT 'Campo doc_entry agregado a orden_compra_cabecera';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 4922  -- Error: Cannot add column because it already exists
        PRINT 'Campo doc_entry ya existe';
    ELSE
        THROW;
END CATCH
GO

-- Agregar campo pedido_id
BEGIN TRY
    ALTER TABLE orden_compra_cabecera
    ADD pedido_id UNIQUEIDENTIFIER NULL;
    PRINT 'Campo pedido_id agregado a orden_compra_cabecera';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 4922  -- Error: Cannot add column because it already exists
        PRINT 'Campo pedido_id ya existe';
    ELSE
        THROW;
END CATCH
GO

-- Crear índice único en doc_entry (si no existe)
BEGIN TRY
    CREATE UNIQUE INDEX idx_oc_doc_entry 
    ON orden_compra_cabecera(doc_entry) 
    WHERE doc_entry IS NOT NULL;
    PRINT 'Indice unico idx_oc_doc_entry creado';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 1913  -- Error: Index already exists
        PRINT 'Indice idx_oc_doc_entry ya existe';
    ELSE
        THROW;
END CATCH
GO

-- Crear índice en pedido_id (si no existe)
BEGIN TRY
    CREATE INDEX idx_oc_pedido_id 
    ON orden_compra_cabecera(pedido_id)
    WHERE pedido_id IS NOT NULL;
    PRINT 'Indice idx_oc_pedido_id creado';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 1913  -- Error: Index already exists
        PRINT 'Indice idx_oc_pedido_id ya existe';
    ELSE
        THROW;
END CATCH
GO

PRINT 'Script completado exitosamente';
GO

