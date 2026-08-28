-- ============================================================================
-- Migración: Crear tablas solicitud_transferencia_bodega / _detalle
-- Descripción: Persiste el resultado de las Inventory Transfer Requests enviadas
--              a SAP entre bodegas (OCSAPService._enviar_itrs_por_bodega), hoy solo
--              devueltas en la respuesta HTTP y nunca guardadas en base de datos --
--              por eso ni la reconciliación automática ni un reintento manual pueden
--              detectar una ITR de bodega que falló.
-- Fecha: 2026-08-28
-- ============================================================================
-- Tablas separadas de solicitud_transferencia / solicitud_transferencia_detalle
-- a propósito: el reintento automático de tiendas (SolicitudTransferenciaRepository.
-- get_tiendas_pendientes_reintento_st, get_oc_ids_con_tiendas_pendientes) asume que
-- "el último registro de solicitud_transferencia para una oc_id" es siempre un envío
-- a tiendas. Si una ITR de bodega compartiera esa tabla, podría convertirse en "el
-- último" y hacer que ese reintento lea las filas equivocadas. Con tablas propias,
-- las ITR de bodega quedan visibles para auditoría/reconciliación sin tocar ninguna
-- query existente de reintento de tiendas.
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'solicitud_transferencia_bodega')
BEGIN
    CREATE TABLE solicitud_transferencia_bodega (
        solicitud_transferencia_bodega_id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID() PRIMARY KEY,
        pedido_id UNIQUEIDENTIFIER NULL,
        oc_id UNIQUEIDENTIFIER NULL,
        oc_doc_num INT NULL,
        bodega_origen NVARCHAR(20) NULL,
        total_bodegas INT NOT NULL DEFAULT 0,
        transferencias_creadas INT NOT NULL DEFAULT 0,
        transferencias_errores INT NOT NULL DEFAULT 0,
        success BIT NOT NULL DEFAULT 0,
        resultado_json NVARCHAR(MAX) NULL,
        creado_fecha DATETIME2 NOT NULL DEFAULT GETDATE()
    );

    CREATE INDEX IX_solicitud_transferencia_bodega_pedido_id
        ON solicitud_transferencia_bodega(pedido_id);

    CREATE INDEX IX_solicitud_transferencia_bodega_oc_id
        ON solicitud_transferencia_bodega(oc_id);

    CREATE INDEX IX_solicitud_transferencia_bodega_creado_fecha
        ON solicitud_transferencia_bodega(creado_fecha);

    PRINT 'Tabla solicitud_transferencia_bodega creada correctamente.';
END
ELSE
BEGIN
    PRINT 'Tabla solicitud_transferencia_bodega ya existe.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'solicitud_transferencia_bodega_detalle')
BEGIN
    CREATE TABLE solicitud_transferencia_bodega_detalle (
        solicitud_transferencia_bodega_detalle_id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID() PRIMARY KEY,
        solicitud_transferencia_bodega_id UNIQUEIDENTIFIER NOT NULL,
        bodega_codigo NVARCHAR(20) NOT NULL,
        estado NVARCHAR(20) NOT NULL,  -- 'Creada' | 'Error'
        doc_num INT NULL,              -- DocNum de SAP (ITR) si éxito
        doc_entry INT NULL,            -- DocEntry de SAP (ITR) si éxito
        error_mensaje NVARCHAR(500) NULL,
        creado_fecha DATETIME2 NOT NULL DEFAULT GETDATE(),
        CONSTRAINT FK_solicitud_transferencia_bodega_detalle_solicitud
            FOREIGN KEY (solicitud_transferencia_bodega_id)
            REFERENCES solicitud_transferencia_bodega(solicitud_transferencia_bodega_id)
    );

    CREATE INDEX IX_solicitud_transferencia_bodega_detalle_solicitud_id
        ON solicitud_transferencia_bodega_detalle(solicitud_transferencia_bodega_id);

    CREATE INDEX IX_solicitud_transferencia_bodega_detalle_bodega
        ON solicitud_transferencia_bodega_detalle(bodega_codigo);

    PRINT 'Tabla solicitud_transferencia_bodega_detalle creada correctamente.';
END
ELSE
BEGIN
    PRINT 'Tabla solicitud_transferencia_bodega_detalle ya existe.';
END
GO
