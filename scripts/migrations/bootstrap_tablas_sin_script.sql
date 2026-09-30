-- ============================================================================
-- Script de Migración: Bootstrap de tablas base sin script de creación
-- ============================================================================
-- Descripción: Crea, SOLO si no existen, las tablas que el resto de migraciones
--              da por hechas pero que ningún script del repo creaba (en los
--              ambientes originales se crearon a mano):
--                - despacho_cabecera / despacho_detalle
--                - orden_compra_cabecera / orden_compra_detalle
--                - pack_conversion (ver nota abajo)
--              Sin esto, una BD vacía (ambiente local/desarrollo nuevo) falla en
--              las migraciones 101, 104-107, 650 y 653.
-- Fecha: 2026-09-24
--
-- IDEMPOTENTE: en ambientes existentes (test/producción) todas las tablas ya
-- existen y el script no hace nada.
--
-- Columnas reconstruidas a partir de los INSERT/SELECT de src/database/repositories.
-- Se omiten a propósito las columnas que agregan migraciones posteriores del
-- manifest, para que esas migraciones sigan siendo la fuente de su definición:
--   despacho_detalle.precio_unitario_sap                       -> 101
--   orden_compra_cabecera.codigo_bodega                        -> 104
--   orden_compra_detalle.codigo_bodega                         -> 105
--   orden_compra_cabecera.doc_entry, pedido_id (+FK)           -> 106
--   orden_compra_cabecera.respuesta_sap, fecha_procesado,
--     error_message, error_code, error_source, updated_at      -> 107
--   orden_compra_cabecera.job_id                               -> 650
--   orden_compra_cabecera.fecha_envio_iniciado                 -> 653
--
-- pack_conversion: create_sap_tables.sql (migración 002) la define como
-- DECIMAL(10, 9) -- máximo 9.999999999 -- pero en el mismo script inserta 12.0
-- (pack X1), lo que produce "Arithmetic overflow" en una BD vacía. Se crea aquí
-- antes con DECIMAL(19, 9) (misma escala, 10 dígitos enteros) para que el
-- IF NOT EXISTS de la 002 la encuentre y solo inserte los datos. No se edita la
-- 002 porque ya está aplicada en producción (ver cabecera del manifest).
-- ============================================================================

SET NOCOUNT ON;
GO

IF OBJECT_ID(N'[dbo].[pack_conversion]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[pack_conversion] (
        pack_id VARCHAR(10) PRIMARY KEY,
        unidad_conversion DECIMAL(19, 9) NOT NULL,
        descripcion VARCHAR(100) NULL,
        activo BIT DEFAULT 1,
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );
    CREATE INDEX idx_pack_conversion_activo ON [dbo].[pack_conversion](activo);
    PRINT '✅ Tabla pack_conversion creada';
END
GO

IF OBJECT_ID(N'[dbo].[despacho_cabecera]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[despacho_cabecera] (
        despacho_id                 UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_despacho_cabecera PRIMARY KEY,
        empresa                     NVARCHAR(50)  NULL,
        codigo_cliente              NVARCHAR(50)  NULL,
        fecha_despacho              DATETIME      NULL,
        codigo_factura              NVARCHAR(50)  NULL,
        anulada                     BIT           NOT NULL CONSTRAINT DF_despacho_cabecera_anulada DEFAULT 0,
        numero_pedido_sistema       NVARCHAR(50)  NULL,
        numero_orden                NVARCHAR(50)  NULL,
        numero_factura              NVARCHAR(50)  NULL,
        tipo_documento              NVARCHAR(50)  NULL,
        orden_compra                NVARCHAR(100) NULL,
        orden_compra_cliente        NVARCHAR(100) NULL,
        remision_facturada          BIT           NOT NULL CONSTRAINT DF_despacho_cabecera_remision DEFAULT 0,
        num_id_factura_relacionada  NVARCHAR(50)  NULL,
        fecha_factura               DATETIME      NULL,
        codigo_despacho             NVARCHAR(50)  NULL,
        codigo_bodega               NVARCHAR(50)  NULL,
        confirmado                  BIT           NOT NULL CONSTRAINT DF_despacho_cabecera_confirmado DEFAULT 0,
        creado_por                  NVARCHAR(450) NULL,
        modificado_por              NVARCHAR(450) NULL,
        modificado_fecha            DATETIME2     NULL,
        origen                      NVARCHAR(50)  NULL,
        ip_origen                   NVARCHAR(45)  NULL,
        created_at                  DATETIME      NULL CONSTRAINT DF_despacho_cabecera_created DEFAULT GETDATE(),
        updated_at                  DATETIME      NULL CONSTRAINT DF_despacho_cabecera_updated DEFAULT GETDATE()
    );
    PRINT '✅ Tabla despacho_cabecera creada';
END
GO

IF OBJECT_ID(N'[dbo].[despacho_detalle]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[despacho_detalle] (
        detalle_id            UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_despacho_detalle PRIMARY KEY DEFAULT NEWID(),
        despacho_id           UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT FK_despacho_detalle_cabecera REFERENCES [dbo].[despacho_cabecera](despacho_id),
        sku                   NVARCHAR(100)  NULL,
        cantidad_docena_mba3  DECIMAL(18, 4) NULL,
        subtotal_sap          DECIMAL(18, 4) NULL,
        cantidad_pack_sap     DECIMAL(18, 4) NULL,
        unidad_sap            NVARCHAR(20)   NULL,
        precio_unitario_mba3  DECIMAL(18, 4) NULL,
        descuento             DECIMAL(18, 4) NULL,
        total_linea_mba3      DECIMAL(18, 4) NULL,
        impuesto              DECIMAL(18, 4) NULL,
        nombre_producto       NVARCHAR(255)  NULL,
        tipo_linea            NVARCHAR(50)   NULL,
        creado_por            NVARCHAR(450)  NULL,
        modificado_por        NVARCHAR(450)  NULL,
        modificado_fecha      DATETIME2      NULL,
        origen                NVARCHAR(50)   NULL,
        ip_origen             NVARCHAR(45)   NULL,
        created_at            DATETIME       NULL DEFAULT GETDATE(),
        updated_at            DATETIME       NULL DEFAULT GETDATE()
    );
    CREATE INDEX idx_despacho_detalle_despacho_id ON [dbo].[despacho_detalle](despacho_id);
    PRINT '✅ Tabla despacho_detalle creada';
END
GO

IF OBJECT_ID(N'[dbo].[orden_compra_cabecera]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[orden_compra_cabecera] (
        oc_id                UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_orden_compra_cabecera PRIMARY KEY DEFAULT NEWID(),
        despacho_id          UNIQUEIDENTIFIER NULL,
        proveedor            NVARCHAR(100)  NULL,
        fecha_generacion     DATETIME       NULL,
        referencia_despacho  NVARCHAR(100)  NULL,
        estado               NVARCHAR(50)   NULL,
        numero_oc_sap        NVARCHAR(50)   NULL,
        creado_por           NVARCHAR(450)  NULL,
        modificado_por       NVARCHAR(450)  NULL,
        modificado_fecha     DATETIME2      NULL,
        origen               NVARCHAR(50)   NULL,
        ip_origen            NVARCHAR(45)   NULL,
        created_at           DATETIME       NULL DEFAULT GETDATE()
    );
    PRINT '✅ Tabla orden_compra_cabecera creada';
END
GO

IF OBJECT_ID(N'[dbo].[orden_compra_detalle]', N'U') IS NULL
BEGIN
    -- FK a cabecera: orden_compra_repository.delete_orden_compra borra primero los
    -- detalles "por restricciones de FK", así que la FK existe en producción.
    CREATE TABLE [dbo].[orden_compra_detalle] (
        oc_detalle_id       UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_orden_compra_detalle PRIMARY KEY DEFAULT NEWID(),
        oc_id               UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT FK_orden_compra_detalle_cabecera REFERENCES [dbo].[orden_compra_cabecera](oc_id),
        sku_sap             NVARCHAR(100)  NULL,
        cantidad_sap        DECIMAL(18, 4) NULL,
        unidad_sap          NVARCHAR(20)   NULL,
        referencia_detalle  NVARCHAR(100)  NULL,
        precio_unitario     DECIMAL(18, 4) NULL,
        total_linea         DECIMAL(18, 4) NULL,
        cantidad_origen     DECIMAL(18, 4) NULL,
        creado_por          NVARCHAR(450)  NULL,
        modificado_por      NVARCHAR(450)  NULL,
        modificado_fecha    DATETIME2      NULL,
        origen              NVARCHAR(50)   NULL,
        ip_origen           NVARCHAR(45)   NULL,
        created_at          DATETIME       NULL DEFAULT GETDATE(),
        updated_at          DATETIME       NULL DEFAULT GETDATE()
    );
    CREATE INDEX idx_orden_compra_detalle_oc_id ON [dbo].[orden_compra_detalle](oc_id);
    PRINT '✅ Tabla orden_compra_detalle creada';
END
GO

SET NOCOUNT OFF;
GO
