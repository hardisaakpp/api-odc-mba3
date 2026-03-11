-- ============================================================================
-- Migración: Crear tabla solicitud_transferencia_detalle
-- Descripción: Persiste por cada tienda el resultado de la Solicitud de Transferencia
--              (Tienda, Nombre, Estado, DocNum) — misma información que se envía por correo.
-- Fecha: 2026-03-10
-- ============================================================================
-- Nota: Crea solicitud_transferencia si no existe (tabla padre), para que la migración
--       funcione en cualquier entorno aunque no se haya ejecutado 611.5 antes.
-- ============================================================================

-- 1) Asegurar que existe la tabla padre solicitud_transferencia
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'solicitud_transferencia')
BEGIN
    CREATE TABLE solicitud_transferencia (
        solicitud_transferencia_id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID() PRIMARY KEY,
        pedido_id UNIQUEIDENTIFIER NOT NULL,
        oc_id UNIQUEIDENTIFIER NULL,
        oc_doc_num INT NULL,
        bodega_origen NVARCHAR(20) NULL,
        total_tiendas INT NOT NULL DEFAULT 0,
        transferencias_creadas INT NOT NULL DEFAULT 0,
        transferencias_errores INT NOT NULL DEFAULT 0,
        success BIT NOT NULL DEFAULT 0,
        resultado_json NVARCHAR(MAX) NULL,
        payloads_sap_json NVARCHAR(MAX) NULL,
        creado_fecha DATETIME2 NOT NULL DEFAULT GETDATE()
    );
    CREATE INDEX IX_solicitud_transferencia_pedido_id ON solicitud_transferencia(pedido_id);
    CREATE INDEX IX_solicitud_transferencia_oc_id ON solicitud_transferencia(oc_id);
    CREATE INDEX IX_solicitud_transferencia_creado_fecha ON solicitud_transferencia(creado_fecha);
    PRINT 'Tabla solicitud_transferencia creada correctamente.';
END

-- 2) Crear tabla detalle con FK a solicitud_transferencia
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'solicitud_transferencia_detalle')
BEGIN
    CREATE TABLE solicitud_transferencia_detalle (
        solicitud_transferencia_detalle_id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID() PRIMARY KEY,
        solicitud_transferencia_id UNIQUEIDENTIFIER NOT NULL,
        tienda_codigo NVARCHAR(20) NOT NULL,
        tienda_nombre NVARCHAR(255) NULL,
        estado NVARCHAR(20) NOT NULL,  -- 'Creada' | 'Error'
        doc_num INT NULL,             -- DocNum de SAP (ITR) si éxito
        doc_entry INT NULL,           -- DocEntry de SAP (ITR) si éxito
        error_mensaje NVARCHAR(500) NULL,
        creado_fecha DATETIME2 NOT NULL DEFAULT GETDATE(),
        CONSTRAINT FK_solicitud_transferencia_detalle_solicitud
            FOREIGN KEY (solicitud_transferencia_id) REFERENCES solicitud_transferencia(solicitud_transferencia_id)
    );

    CREATE INDEX IX_solicitud_transferencia_detalle_solicitud_id
        ON solicitud_transferencia_detalle(solicitud_transferencia_id);

    CREATE INDEX IX_solicitud_transferencia_detalle_tienda
        ON solicitud_transferencia_detalle(tienda_codigo);

    PRINT 'Tabla solicitud_transferencia_detalle creada correctamente.';
END
ELSE
BEGIN
    PRINT 'Tabla solicitud_transferencia_detalle ya existe.';
END
GO
