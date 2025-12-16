-- ============================================================================
-- Script SQL para crear tabla remision_cabecera
-- ============================================================================
-- Esta tabla almacena exclusivamente documentos de remisión desde MBA3
-- que no tienen detalles (ObjDatosFactura IS NULL)
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[remision_cabecera]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[remision_cabecera] (
        remision_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        empresa VARCHAR(50) NOT NULL,
        codigo_cliente VARCHAR(50) NOT NULL,
        fecha_remision DATE NOT NULL,
        codigo_factura VARCHAR(100) NOT NULL,
        anulada BIT DEFAULT 0,
        numero_pedido_sistema INT NULL,
        numero_orden INT NULL,
        numero_factura INT NOT NULL,
        tipo_documento VARCHAR(10) NOT NULL DEFAULT 'REM',
        orden_compra VARCHAR(50) NULL,
        orden_compra_cliente VARCHAR(50) NULL,
        remision_facturada BIT DEFAULT 0,
        factura_impresa BIT DEFAULT 0,
        confirmado BIT DEFAULT 0,
        fecha_factura DATE NULL,
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        
        -- Constraint para asegurar unicidad por código de factura
        CONSTRAINT UQ_remision_cabecera_codigo_factura UNIQUE (codigo_factura)
    );
    
    -- Crear índices para búsquedas rápidas
    CREATE INDEX idx_remision_cabecera_codigo_factura ON remision_cabecera(codigo_factura);
    CREATE INDEX idx_remision_cabecera_empresa ON remision_cabecera(empresa);
    CREATE INDEX idx_remision_cabecera_codigo_cliente ON remision_cabecera(codigo_cliente);
    CREATE INDEX idx_remision_cabecera_fecha_remision ON remision_cabecera(fecha_remision);
    CREATE INDEX idx_remision_cabecera_confirmado ON remision_cabecera(confirmado);
    CREATE INDEX idx_remision_cabecera_remision_facturada ON remision_cabecera(remision_facturada);
    CREATE INDEX idx_remision_cabecera_factura_impresa ON remision_cabecera(factura_impresa);
    CREATE INDEX idx_remision_cabecera_anulada ON remision_cabecera(anulada);
    
    PRINT 'Tabla remision_cabecera creada exitosamente';
END
ELSE
BEGIN
    PRINT 'Tabla remision_cabecera ya existe';
END
GO

PRINT 'Script completado exitosamente';
GO

