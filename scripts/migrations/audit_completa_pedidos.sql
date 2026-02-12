-- ============================================================================
-- Migración: Auditoría Completa para Pedidos
-- Versión: 606
-- Fecha: 2026-02-12
-- Descripción: Cerrar brechas de auditoría en el sistema de pedidos.
--   1. Agregar valor_anterior/valor_nuevo a pedido_detalle_modificacion_columna
--   2. Agregar campos de auditoría a redistribucion_borrador
--   3. Crear tabla pedido_audit_log (log centralizado de auditoría)
-- ============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- 1. Agregar valor_anterior y valor_nuevo a pedido_detalle_modificacion_columna
-- ────────────────────────────────────────────────────────────────────────────
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'pedido_detalle_modificacion_columna'
      AND COLUMN_NAME = 'valor_anterior'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle_modificacion_columna]
        ADD valor_anterior NVARCHAR(MAX) NULL;
    PRINT '✅ Columna valor_anterior agregada a pedido_detalle_modificacion_columna';
END
ELSE
    PRINT '⏭️ Columna valor_anterior ya existe en pedido_detalle_modificacion_columna';
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'pedido_detalle_modificacion_columna'
      AND COLUMN_NAME = 'valor_nuevo'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle_modificacion_columna]
        ADD valor_nuevo NVARCHAR(MAX) NULL;
    PRINT '✅ Columna valor_nuevo agregada a pedido_detalle_modificacion_columna';
END
ELSE
    PRINT '⏭️ Columna valor_nuevo ya existe en pedido_detalle_modificacion_columna';
GO

-- ────────────────────────────────────────────────────────────────────────────
-- 2. Agregar campos de auditoría completa a redistribucion_borrador
-- ────────────────────────────────────────────────────────────────────────────
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'redistribucion_borrador'
      AND COLUMN_NAME = 'modificado_por'
)
BEGIN
    ALTER TABLE [dbo].[redistribucion_borrador]
        ADD modificado_por NVARCHAR(450) NULL;
    PRINT '✅ Columna modificado_por agregada a redistribucion_borrador';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'redistribucion_borrador'
      AND COLUMN_NAME = 'modificado_fecha'
)
BEGIN
    ALTER TABLE [dbo].[redistribucion_borrador]
        ADD modificado_fecha DATETIME NULL;
    PRINT '✅ Columna modificado_fecha agregada a redistribucion_borrador';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'redistribucion_borrador'
      AND COLUMN_NAME = 'origen'
)
BEGIN
    ALTER TABLE [dbo].[redistribucion_borrador]
        ADD origen NVARCHAR(50) NULL;
    PRINT '✅ Columna origen agregada a redistribucion_borrador';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'redistribucion_borrador'
      AND COLUMN_NAME = 'ip_origen'
)
BEGIN
    ALTER TABLE [dbo].[redistribucion_borrador]
        ADD ip_origen NVARCHAR(45) NULL;
    PRINT '✅ Columna ip_origen agregada a redistribucion_borrador';
END
GO

-- ────────────────────────────────────────────────────────────────────────────
-- 3. Crear tabla pedido_audit_log (log centralizado)
-- ────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID(N'[dbo].[pedido_audit_log]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[pedido_audit_log] (
        id                  UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        pedido_id           UNIQUEIDENTIFIER NOT NULL,
        entidad             NVARCHAR(100) NOT NULL,
        entidad_id          NVARCHAR(100) NULL,
        accion              NVARCHAR(20) NOT NULL,
        campo_modificado    NVARCHAR(100) NULL,
        valor_anterior      NVARCHAR(MAX) NULL,
        valor_nuevo         NVARCHAR(MAX) NULL,
        usuario             NVARCHAR(450) NOT NULL,
        fecha               DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        origen              NVARCHAR(50) NULL,
        ip_origen           NVARCHAR(45) NULL,
        comentario          NVARCHAR(500) NULL,

        CONSTRAINT FK_pedido_audit_log_pedido
            FOREIGN KEY (pedido_id) REFERENCES pedido(pedido_id) ON DELETE CASCADE
    );

    CREATE INDEX idx_pedido_audit_log_pedido
        ON [dbo].[pedido_audit_log] (pedido_id);

    CREATE INDEX idx_pedido_audit_log_fecha
        ON [dbo].[pedido_audit_log] (fecha);

    CREATE INDEX idx_pedido_audit_log_usuario
        ON [dbo].[pedido_audit_log] (usuario);

    CREATE INDEX idx_pedido_audit_log_entidad
        ON [dbo].[pedido_audit_log] (entidad, entidad_id);

    PRINT '✅ Tabla pedido_audit_log creada con índices';
END
ELSE
    PRINT '⏭️ Tabla pedido_audit_log ya existe';
GO

PRINT '✅ Migración audit_completa_pedidos completada';
GO
