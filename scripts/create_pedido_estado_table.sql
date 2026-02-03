-- ============================================================================
-- Script: Crear tabla maestra pedido_estado (estados por id, nombre editable)
-- ============================================================================
-- Los estados del pedido se identifican por estado_id (número). El nombre
-- es solo presentación y puede ser editado por el usuario sin afectar lógica.
-- estado_id = 1 es siempre el estado inicial (BORRADOR) al subir Excel.
-- ============================================================================

-- Tabla: pedido_estado (maestro de estados)
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_estado]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pedido_estado] (
        id INT NOT NULL PRIMARY KEY,
        nombre NVARCHAR(100) NOT NULL,
        orden INT NOT NULL DEFAULT 0,
        activo BIT NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),

        CONSTRAINT UQ_pedido_estado_nombre UNIQUE (nombre)
    );

    CREATE INDEX idx_pedido_estado_orden ON pedido_estado(orden);
    CREATE INDEX idx_pedido_estado_activo ON pedido_estado(activo);

    PRINT 'Tabla pedido_estado creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'La tabla pedido_estado ya existe.';
END
GO

-- Datos iniciales: id semántico, nombre editable (orden por flujo típico)
IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado])
BEGIN
    SET NOCOUNT ON;

    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo) VALUES
        (1,  N'BORRADOR',                        1,  1),  -- ex PENDIENTE_CONFIRMACION_PROVEEDOR
        (2,  N'RESPUESTA_PROVEEDOR_CARGADA',    2,  1),
        (3,  N'EN_REVISION',                    3,  1),
        (4,  N'CONFIRMADO_PROVEEDOR',            4,  1),
        (5,  N'RECHAZADO_PROVEEDOR',            5,  1),
        (6,  N'EN_AJUSTE_MABEL',                 6,  1),
        (7,  N'REDISTRIBUIDO',                   7,  1),
        (8,  N'PEDIDO_CONFIRMADO',               8,  1),
        (9,  N'PROCESADO_SAP',                   9,  1),
        (10, N'CONFIRMADO_ENVIADO',             10,  1),
        (11, N'PENDIENTE_LOGISTICA',            11,  1),
        (12, N'ERROR_DATOS_MAESTROS',            12,  1),
        (13, N'EN_PROCESO',                     13,  1),
        (14, N'COMPLETADO',                      14,  1);

    SET NOCOUNT OFF;
    PRINT 'Datos iniciales de pedido_estado insertados.';
END
ELSE
BEGIN
    PRINT 'pedido_estado ya tiene datos; no se insertan de nuevo.';
END
GO
