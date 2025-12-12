-- ============================================================================
-- Script SQL para crear tabla de logs de integración SAP
-- ============================================================================
-- Este script crea la tabla necesaria para almacenar todos los logs
-- generados durante el proceso de integración con SAP Service Layer
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[sap_integration_logs]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[sap_integration_logs] (
        log_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Información del proceso
        proceso_id UNIQUEIDENTIFIER NULL,  -- ID único del proceso completo (mismo para todas las OCs del mismo request)
        timestamp_log DATETIME NOT NULL DEFAULT GETDATE(),
        nivel_log VARCHAR(20) NOT NULL,  -- INFO, WARNING, ERROR, DEBUG
        mensaje NVARCHAR(MAX) NOT NULL,
        
        -- Información del usuario y fuente
        usuario VARCHAR(100) NULL,
        fuente VARCHAR(50) NULL,  -- API, WEB, etc.
        
        -- Información de la OC
        oc_id UNIQUEIDENTIFIER NULL,
        referencia_despacho VARCHAR(50) NULL,
        proveedor VARCHAR(100) NULL,
        
        -- Información de SAP (si aplica)
        doc_entry INT NULL,
        doc_num INT NULL,
        error_code VARCHAR(20) NULL,  -- Código de error de SAP (ej: -4013)
        error_source VARCHAR(50) NULL,  -- SAP, BACKEND, SAP_CONNECTION
        success BIT NULL,  -- true si fue exitoso, false si error, NULL si no aplica
        
        -- Información adicional (JSON para detalles completos)
        detalles_adicionales NVARCHAR(MAX) NULL,  -- JSON con información adicional (sap_response, sap_error_details, etc.)
        
        -- Metadata
        created_at DATETIME DEFAULT GETDATE()
    );
    
    -- Crear índices para búsquedas rápidas
    CREATE INDEX idx_sap_integration_logs_proceso_id ON sap_integration_logs(proceso_id);
    CREATE INDEX idx_sap_integration_logs_oc_id ON sap_integration_logs(oc_id);
    CREATE INDEX idx_sap_integration_logs_timestamp ON sap_integration_logs(timestamp_log);
    CREATE INDEX idx_sap_integration_logs_nivel ON sap_integration_logs(nivel_log);
    CREATE INDEX idx_sap_integration_logs_referencia ON sap_integration_logs(referencia_despacho);
    CREATE INDEX idx_sap_integration_logs_success ON sap_integration_logs(success);
    
    PRINT 'Tabla sap_integration_logs creada exitosamente';
END
ELSE
BEGIN
    PRINT 'Tabla sap_integration_logs ya existe';
END
GO

PRINT 'Script completado exitosamente';
GO














