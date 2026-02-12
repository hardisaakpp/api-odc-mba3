-- ============================================================================
-- Migración: Crear tablas pedido_original y pedido_detalle_original
-- ============================================================================
-- Descripción: Almacenan una copia inmutable de los datos del pedido y sus
--              detalles tal como fueron enviados originalmente (botón "Enviar").
--              Se usan para generar el Excel "Descargar Pedido Original" sin
--              que las ediciones posteriores (COSTO UNIT., TOTAL, COMENTARIO,
--              FECHA DE ENTREGA) afecten los valores originales.
-- Fecha: 2026-02-12
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT 'Migración: Crear tablas pedido_original y pedido_detalle_original';
PRINT '============================================================================';
PRINT '';
GO

-- ============================================================================
-- 1. Tabla: pedido_original (copia inmutable de la cabecera)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_original]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pedido_original] (
        pedido_original_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

        -- Referencia al pedido vivo
        pedido_id UNIQUEIDENTIFIER NOT NULL,

        -- Campos copiados de la tabla pedido (cabecera)
        numero_pedido NVARCHAR(50) NOT NULL,
        fecha_pedido DATE NULL,
        fecha_entrega NVARCHAR(50) NULL,
        forma_pago NVARCHAR(50) NULL,
        mensaje NVARCHAR(50) NULL,
        proveedor_nombre NVARCHAR(150) NULL,
        comprador_nombre NVARCHAR(150) NULL,
        comprador_codigo NVARCHAR(50) NULL,
        origen_traslado NVARCHAR(50) NULL,
        serie NVARCHAR(50) NULL,
        archivo_nombre NVARCHAR(255) NULL,

        -- Auditoría
        copiado_por NVARCHAR(450) NULL,
        copiado_en DATETIME DEFAULT GETDATE(),

        -- FK al pedido vivo
        CONSTRAINT FK_pedido_original_pedido
            FOREIGN KEY (pedido_id)
            REFERENCES pedido(pedido_id)
            ON DELETE CASCADE,

        -- Un solo snapshot por pedido
        CONSTRAINT UQ_pedido_original_pedido_id UNIQUE (pedido_id)
    );

    CREATE INDEX idx_pedido_original_pedido_id ON pedido_original(pedido_id);

    PRINT '  ✅ Tabla pedido_original creada exitosamente.';
END
ELSE
BEGIN
    PRINT '  ✓ La tabla pedido_original ya existe.';
END
GO

-- ============================================================================
-- 2. Tabla: pedido_detalle_original (copia inmutable de los detalles)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle_original]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pedido_detalle_original] (
        pedido_detalle_original_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

        -- Referencia al snapshot de cabecera original
        pedido_original_id UNIQUEIDENTIFIER NOT NULL,

        -- Referencia al detalle vivo (para trazabilidad)
        pedido_detalle_id UNIQUEIDENTIFIER NOT NULL,

        -- Campos copiados de pedido_detalle
        codigo_interno NVARCHAR(50) NULL,
        descripcion_sap NVARCHAR(255) NULL,
        marca NVARCHAR(50) NULL,
        codigo_barras NVARCHAR(50) NULL,
        pack NVARCHAR(50) NULL,
        costo_doc_sin_iva DECIMAL(18, 4) NULL,
        descuento_1 DECIMAL(5, 2) NULL,
        pvp DECIMAL(18, 4) NULL,
        subtotal DECIMAL(18, 2) NULL,
        total DECIMAL(18, 2) NULL,
        comentario NVARCHAR(MAX) NULL,

        -- Auditoría
        copiado_en DATETIME DEFAULT GETDATE(),

        CONSTRAINT FK_pedido_detalle_original_pedido_original
            FOREIGN KEY (pedido_original_id)
            REFERENCES pedido_original(pedido_original_id)
            ON DELETE CASCADE
    );

    CREATE INDEX idx_pedido_detalle_original_pedido_original_id
        ON pedido_detalle_original(pedido_original_id);

    CREATE INDEX idx_pedido_detalle_original_pedido_detalle_id
        ON pedido_detalle_original(pedido_detalle_id);

    PRINT '  ✅ Tabla pedido_detalle_original creada exitosamente.';
END
ELSE
BEGIN
    PRINT '  ✓ La tabla pedido_detalle_original ya existe.';
END
GO

-- ============================================================================
-- Resumen
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada: tablas pedido_original y pedido_detalle_original';
PRINT '============================================================================';
PRINT '';
PRINT 'Uso:';
PRINT '  - Al hacer clic en "Enviar" (cargar-plantilla), se copian los datos';
PRINT '    de pedido/pedido_detalle a estas tablas.';
PRINT '  - El botón "Descargar Pedido Original" genera el Excel desde aquí.';
PRINT '  - Las tablas pedido/pedido_detalle siguen siendo editables normalmente.';
GO

SET NOCOUNT OFF;
GO
