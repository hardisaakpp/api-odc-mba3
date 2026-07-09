-- Crea tabla de borradores de redistribución
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'redistribucion_borrador'
)
BEGIN
    CREATE TABLE redistribucion_borrador (
        id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        pedido_id UNIQUEIDENTIFIER NOT NULL,
        numero_pedido NVARCHAR(100) NOT NULL,
        ajustes_detalle NVARCHAR(MAX) NOT NULL,
        creado_por NVARCHAR(450) NULL,
        fecha_guardado DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_borrador_pedido 
            FOREIGN KEY (pedido_id) 
            REFERENCES pedido(pedido_id) 
            ON DELETE CASCADE
    );

    CREATE INDEX idx_borrador_pedido_id ON redistribucion_borrador(pedido_id);
    CREATE INDEX idx_borrador_numero_pedido ON redistribucion_borrador(numero_pedido);
END
