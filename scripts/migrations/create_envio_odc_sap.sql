-- ============================================================================
-- Migración: Crear tabla envio_odc_sap
-- Descripción: Persiste el snapshot de cada "Enviar ODC a SAP" (información
--              que se envía por correo: OC + solicitudes de transferencia + fecha).
-- Fecha: 2026-03-10
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'envio_odc_sap')
BEGIN
    CREATE TABLE envio_odc_sap (
        envio_odc_sap_id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID() PRIMARY KEY,
        oc_id UNIQUEIDENTIFIER NOT NULL,
        pedido_id UNIQUEIDENTIFIER NOT NULL,
        numero_oc_sap NVARCHAR(20) NULL,   -- DocNum (ej: 22523)
        doc_entry INT NULL,                -- DocEntry (ej: 43366)
        proveedor NVARCHAR(50) NULL,       -- CardCode (ej: P1790389219001)
        referencia NVARCHAR(100) NULL,     -- Referencia/Pedido (ej: PREG-02.03.2026)
        numero_pedido NVARCHAR(100) NULL,  -- Número legible del pedido
        solicitud_transferencia_id UNIQUEIDENTIFIER NULL,  -- FK al batch de solicitudes
        total_transferencias INT NOT NULL DEFAULT 0,
        transferencias_creadas INT NOT NULL DEFAULT 0,
        fecha_envio DATETIME2 NOT NULL DEFAULT GETDATE(),
        CONSTRAINT FK_envio_odc_sap_solicitud
            FOREIGN KEY (solicitud_transferencia_id) REFERENCES solicitud_transferencia(solicitud_transferencia_id)
    );

    CREATE INDEX IX_envio_odc_sap_oc_id ON envio_odc_sap(oc_id);
    CREATE INDEX IX_envio_odc_sap_pedido_id ON envio_odc_sap(pedido_id);
    CREATE INDEX IX_envio_odc_sap_fecha ON envio_odc_sap(fecha_envio);

    PRINT 'Tabla envio_odc_sap creada correctamente.';
END
ELSE
BEGIN
    PRINT 'Tabla envio_odc_sap ya existe.';
END
GO
