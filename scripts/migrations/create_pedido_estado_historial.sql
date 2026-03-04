-- ============================================================================
-- Script de Migración: Crear tabla pedido_estado_historial
-- ============================================================================
-- Descripción: Bitácora de transiciones de estado de pedidos.
--              Registra SOLO cambios de estado (no ediciones de datos).
--              Permite reconstruir el ciclo de vida completo de un pedido.
-- Fecha: 2026-02-06
-- Referencia: Propuesta de bitácora completa de transiciones de estado
-- ============================================================================
--
-- PRINCIPIO DE DISEÑO:
--   - pedido           → estado actual (fuente de verdad operativa)
--   - pedido_estado_historial → historial de transiciones (trazabilidad)
--
-- CAMPOS:
--   - estado_anterior_id / estado_nuevo_id: transición registrada
--   - fecha_cambio: momento exacto de la transición
--   - usuario_cambio: quién realizó la transición
--   - origen: fuente de la transición (WEB, API, SISTEMA, EXCEL, etc.)
--   - ip_origen: dirección IP del cliente
--   - accion: tipo de transición (MANUAL, AUTO, SISTEMA)
--   - comentario: observación opcional
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT '  Migración: Crear tabla pedido_estado_historial';
PRINT '============================================================================';
PRINT '';
GO

-- ============================================================================
-- Crear tabla pedido_estado_historial
-- ============================================================================
IF NOT EXISTS (
    SELECT *
    FROM sys.objects
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_estado_historial]')
      AND type IN (N'U')
)
BEGIN
    CREATE TABLE [dbo].[pedido_estado_historial] (
        id                  UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        pedido_id           UNIQUEIDENTIFIER NOT NULL,

        -- Transición
        estado_anterior_id  INT NULL,       -- NULL solo para la creación inicial
        estado_nuevo_id     INT NOT NULL,

        -- Auditoría
        fecha_cambio        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        usuario_cambio      NVARCHAR(450) NULL,
        origen              NVARCHAR(50) NULL,   -- WEB, API, SISTEMA, EXCEL, CELERY
        ip_origen           NVARCHAR(45) NULL,

        -- Contexto
        accion              NVARCHAR(20) NULL DEFAULT 'MANUAL',  -- MANUAL, AUTO, SISTEMA
        comentario          NVARCHAR(500) NULL,

        -- Foreign keys
        CONSTRAINT FK_pedido_estado_historial_pedido
            FOREIGN KEY (pedido_id)
            REFERENCES pedido(pedido_id)
            ON DELETE CASCADE,

        CONSTRAINT FK_pedido_estado_historial_estado_anterior
            FOREIGN KEY (estado_anterior_id)
            REFERENCES pedido_estado(id)
            ON DELETE NO ACTION,

        CONSTRAINT FK_pedido_estado_historial_estado_nuevo
            FOREIGN KEY (estado_nuevo_id)
            REFERENCES pedido_estado(id)
            ON DELETE NO ACTION
    );

    -- Índice principal: consultas por pedido ordenadas cronológicamente
    CREATE INDEX idx_peh_pedido_fecha
        ON pedido_estado_historial(pedido_id, fecha_cambio ASC);

    -- Índice para búsquedas por estado destino (ej: "todos los pedidos que pasaron a CANCELADO")
    CREATE INDEX idx_peh_estado_nuevo
        ON pedido_estado_historial(estado_nuevo_id, fecha_cambio DESC);

    -- Índice para auditoría por usuario
    CREATE INDEX idx_peh_usuario
        ON pedido_estado_historial(usuario_cambio, fecha_cambio DESC);

    -- Índice para filtrar por fecha (reportes de actividad)
    CREATE INDEX idx_peh_fecha
        ON pedido_estado_historial(fecha_cambio DESC);

    PRINT '  ✅ Tabla pedido_estado_historial creada exitosamente.';
END
ELSE
BEGIN
    PRINT '  ✓ La tabla pedido_estado_historial ya existe.';
END
GO

-- ============================================================================
-- Documentación
-- ============================================================================
IF EXISTS (
    SELECT *
    FROM sys.objects
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_estado_historial]')
      AND type IN (N'U')
)
BEGIN
    -- Evitar error si ya existe la propiedad extendida
    IF NOT EXISTS (
        SELECT 1
        FROM sys.extended_properties
        WHERE major_id = OBJECT_ID(N'[dbo].[pedido_estado_historial]')
          AND minor_id = 0
          AND name = N'MS_Description'
    )
    BEGIN
        EXEC sp_addextendedproperty
            @name = N'MS_Description',
            @value = N'Bitácora de transiciones de estado de pedidos. Registra cada cambio de estado_id con fecha, usuario y origen. Permite reconstruir el ciclo de vida completo de un pedido.',
            @level0type = N'SCHEMA', @level0name = N'dbo',
            @level1type = N'TABLE', @level1name = N'pedido_estado_historial';
    END
END
GO

-- ============================================================================
-- Verificación
-- ============================================================================
PRINT '';
PRINT '📋 Estructura de pedido_estado_historial:';
SELECT
    c.name          AS columna,
    t.name          AS tipo,
    c.max_length    AS longitud,
    CASE WHEN c.is_nullable = 1 THEN 'SÍ' ELSE 'NO' END AS nullable,
    ISNULL(dc.definition, '')  AS default_value
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
WHERE c.object_id = OBJECT_ID(N'[dbo].[pedido_estado_historial]')
ORDER BY c.column_id;
GO

PRINT '';
PRINT '📋 Índices creados:';
SELECT
    i.name AS indice,
    STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS columnas
FROM sys.indexes i
INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
WHERE i.object_id = OBJECT_ID(N'[dbo].[pedido_estado_historial]')
  AND i.name IS NOT NULL
GROUP BY i.name;
GO

PRINT '';
PRINT '============================================================================';
PRINT '  ✅ Migración completada: pedido_estado_historial';
PRINT '============================================================================';
GO

SET NOCOUNT OFF;
GO
