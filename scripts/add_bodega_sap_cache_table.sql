-- ============================================================================
-- Script para agregar tabla bodega_sap_cache
-- ============================================================================
-- Esta tabla almacena información de bodegas/tiendas consultadas desde SAP
-- para evitar consultas repetidas y mejorar el rendimiento
-- Fecha: 2026-01-15
-- ============================================================================

-- Tabla de cache para información de bodegas/tiendas SAP
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[bodega_sap_cache]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[bodega_sap_cache] (
        cache_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        whs_code VARCHAR(50) NOT NULL,                      -- Código de bodega/tienda (WhsCode)
        whs_name NVARCHAR(255) NULL,                        -- Nombre de bodega/tienda en SAP (WhsName)
        es_bodega BIT NULL,                                 -- Si es bodega central (RL-CD, OUT-CD, REG-CD) o tienda
        ultima_consulta DATETIME NULL,                      -- Cuándo se consultó SAP por última vez
        activo BIT DEFAULT 1,                               -- Si está activo en SAP
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        
        -- Constraint para asegurar unicidad por código
        CONSTRAINT UQ_bodega_sap_cache_whs_code UNIQUE (whs_code)
    );
    
    -- Crear índices para búsquedas rápidas
    CREATE INDEX idx_bodega_sap_cache_whs_code ON bodega_sap_cache(whs_code);
    CREATE INDEX idx_bodega_sap_cache_es_bodega ON bodega_sap_cache(es_bodega);
    CREATE INDEX idx_bodega_sap_cache_activo ON bodega_sap_cache(activo);
    CREATE INDEX idx_bodega_sap_cache_ultima_consulta ON bodega_sap_cache(ultima_consulta);
    
    PRINT '✅ Tabla bodega_sap_cache creada exitosamente';
END
ELSE
BEGIN
    PRINT '⚠️ Tabla bodega_sap_cache ya existe';
END
GO

PRINT 'Script completado exitosamente';
GO
