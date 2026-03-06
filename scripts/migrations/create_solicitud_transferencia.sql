-- ============================================================================
-- Migración: Crear tabla solicitud_transferencia
-- Descripción: Persiste el resultado de la generación de Solicitudes de Transferencia
--              (Inventory Transfer Requests) enviadas a SAP.
-- Fecha: 2026-03-06
-- ============================================================================
-- Almacena: pedido_id, oc_id, resultado por tienda, payloads enviados a SAP,
--           total creadas/errores, y JSON completo para auditoría.
-- ============================================================================

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

    CREATE INDEX IX_solicitud_transferencia_pedido_id
        ON solicitud_transferencia(pedido_id);

    CREATE INDEX IX_solicitud_transferencia_oc_id
        ON solicitud_transferencia(oc_id);

    CREATE INDEX IX_solicitud_transferencia_creado_fecha
        ON solicitud_transferencia(creado_fecha);

    PRINT 'Tabla solicitud_transferencia creada correctamente.';
END
ELSE
BEGIN
    PRINT 'Tabla solicitud_transferencia ya existe.';
END
GO
