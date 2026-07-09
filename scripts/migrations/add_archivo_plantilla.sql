-- ============================================================================
-- Migración: Crear tabla archivo_plantilla
-- Descripción: Almacena referencias a archivos Excel originales en storage (MinIO/S3)
-- Fecha: 2024-02-05
-- ============================================================================

-- ============================================================================
-- VERIFICAR SI LA TABLA YA EXISTE
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'archivo_plantilla')
BEGIN
    -- ============================================================================
    -- CREAR TABLA archivo_plantilla
    -- ============================================================================
    CREATE TABLE archivo_plantilla (
        -- Identificador único del archivo
        archivo_id INT IDENTITY(1,1) PRIMARY KEY,
        
        -- Relación con el pedido (UNIQUEIDENTIFIER para coincidir con tabla pedido)
        pedido_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Información del archivo original
        nombre_original NVARCHAR(255) NOT NULL,
        
        -- Ruta en el storage (MinIO/S3)
        -- Formato: plantillas/{año}/{mes}/{pedido_id}/{timestamp}_{nombre}
        storage_path NVARCHAR(500) NOT NULL,
        
        -- Tipo MIME del archivo
        content_type NVARCHAR(100) DEFAULT 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        
        -- Tamaño del archivo en bytes
        tamaño_bytes BIGINT NOT NULL,
        
        -- Usuario que subió el archivo
        subido_por NVARCHAR(100) NOT NULL,
        
        -- Fecha y hora de subida
        fecha_subida DATETIME2 DEFAULT GETDATE(),
        
        -- Indica si el archivo está activo (soft delete)
        activo BIT DEFAULT 1,
        
        -- Número de descargas realizadas
        descargas INT DEFAULT 0,
        
        -- Última fecha de descarga
        ultima_descarga DATETIME2 NULL,
        
        -- Usuario de última descarga
        ultimo_descargador NVARCHAR(100) NULL,
        
        -- Constraint: Foreign key a pedido
        CONSTRAINT FK_archivo_plantilla_pedido 
            FOREIGN KEY (pedido_id) 
            REFERENCES pedido(pedido_id)
            ON DELETE CASCADE
    );
    
    PRINT '✅ Tabla archivo_plantilla creada exitosamente';
END
ELSE
BEGIN
    PRINT '⏭️ Tabla archivo_plantilla ya existe, saltando creación';
END
GO

-- ============================================================================
-- CREAR ÍNDICES
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_archivo_plantilla_pedido_id')
BEGIN
    CREATE INDEX IX_archivo_plantilla_pedido_id 
    ON archivo_plantilla(pedido_id);
    
    PRINT '✅ Índice IX_archivo_plantilla_pedido_id creado';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_archivo_plantilla_storage_path')
BEGIN
    CREATE UNIQUE INDEX IX_archivo_plantilla_storage_path 
    ON archivo_plantilla(storage_path);
    
    PRINT '✅ Índice IX_archivo_plantilla_storage_path creado';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_archivo_plantilla_fecha_subida')
BEGIN
    CREATE INDEX IX_archivo_plantilla_fecha_subida 
    ON archivo_plantilla(fecha_subida DESC);
    
    PRINT '✅ Índice IX_archivo_plantilla_fecha_subida creado';
END
GO

-- ============================================================================
-- COMENTARIOS DE DOCUMENTACIÓN
-- ============================================================================
-- Esta tabla almacena referencias a los archivos Excel originales que los usuarios
-- suben a través del endpoint /api/plantillas/upload.
--
-- Los archivos físicos se almacenan en MinIO/S3, y esta tabla solo guarda:
-- - La referencia (storage_path) para poder recuperar el archivo
-- - Metadatos del archivo (nombre, tamaño, quien lo subió, etc.)
-- - Información de auditoría (descargas, fechas, etc.)
--
-- Flujo:
-- 1. Usuario sube Excel → Backend procesa y guarda datos en pedido/pedido_detalle
-- 2. Backend guarda archivo original en MinIO/S3
-- 3. Backend registra referencia en archivo_plantilla
-- 4. Otro usuario puede descargar el archivo original via /api/plantillas/{pedido_id}/descargar-original
--
-- Configuración requerida en .env:
-- ENABLE_FILE_STORAGE=true
-- FILE_STORAGE_ENDPOINT=http://localhost:9000
-- FILE_STORAGE_ACCESS_KEY=minioadmin
-- FILE_STORAGE_SECRET_KEY=minioadmin
-- FILE_STORAGE_BUCKET=plantillas-excel
-- ============================================================================
