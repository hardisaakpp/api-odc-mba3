-- ============================================================================
-- Migración: agregar estado_id a pedido (sin eliminar estado todavía)
-- ============================================================================
-- PRERREQUISITO: Ejecutar antes create_pedido_estado_table.sql
--
-- Pasos:
--   1. Agregar columna estado_id (INT NULL).
--   2. Poblar estado_id desde estado (string) según mapping.
--   3. Establecer default estado_id = 1 para nuevas filas.
--   4. Opcional: FK a pedido_estado(id).
--
-- La columna estado (string) se mantiene temporalmente para rollback seguro.
-- Eliminarla en una fase posterior cuando el código use solo estado_id.
-- ============================================================================

-- Paso 1: Agregar estado_id si no existe
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido]') AND name = 'estado_id'
)
BEGIN
    ALTER TABLE [dbo].[pedido]
    ADD estado_id INT NULL;

    PRINT 'Columna pedido.estado_id agregada.';
END
ELSE
BEGIN
    PRINT 'Columna pedido.estado_id ya existe.';
END
GO

-- Paso 2: Poblar estado_id desde estado (string) - mapping explícito
-- Cualquier valor no mapeado o NULL → estado_id = 1 (BORRADOR)
UPDATE [dbo].[pedido]
SET estado_id = CASE
    WHEN estado = N'PENDIENTE_CONFIRMACION_PROVEEDOR' THEN 1
    WHEN estado = N'BORRADOR'                        THEN 1
    WHEN estado = N'NUEVO_PEDIDO' THEN 2
    WHEN estado = N'NUEVO PEDIDO' THEN 2
    WHEN estado = N'GESTIONAR_PEDIDO' THEN 3
    WHEN estado = N'GESTIONAR PEDIDO' THEN 3
    WHEN estado = N'EN_REVISION' THEN 4
    WHEN estado = N'REDISTRIBUCION' THEN 4
    WHEN estado = N'RESPUESTA_PROVEEDOR_CARGADA'     THEN 5
    WHEN estado = N'CONFIRMADO_PROVEEDOR'            THEN 6
    WHEN estado = N'RECHAZADO_PROVEEDOR'            THEN 7
    WHEN estado = N'EN_AJUSTE_MABEL'                 THEN 8
    WHEN estado = N'REDISTRIBUIDO'                   THEN 9
    WHEN estado = N'PEDIDO_CONFIRMADO'               THEN 10
    WHEN estado = N'PROCESADO_SAP'                   THEN 11
    WHEN estado = N'CONFIRMADO_ENVIADO'             THEN 12
    WHEN estado = N'PENDIENTE_LOGISTICA'             THEN 13
    WHEN estado = N'ERROR_DATOS_MAESTROS'            THEN 14
    WHEN estado = N'EN_PROCESO'                      THEN 15
    WHEN estado = N'COMPLETADO'                      THEN 16
    ELSE 1
END
WHERE estado_id IS NULL;

PRINT 'estado_id poblado desde estado (string).';
GO

-- Paso 3: Default para nuevas filas (estado_id = 1 = BORRADOR)
IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID(N'[dbo].[pedido]')
      AND parent_column_id = (SELECT column_id FROM sys.columns WHERE object_id = OBJECT_ID(N'[dbo].[pedido]') AND name = 'estado_id')
)
BEGIN
    ALTER TABLE [dbo].[pedido]
    ADD CONSTRAINT DF_pedido_estado_id DEFAULT (1) FOR estado_id;

    PRINT 'Default estado_id = 1 aplicado.';
END
ELSE
BEGIN
    PRINT 'Default estado_id ya existe.';
END
GO

-- Paso 4: FK a pedido_estado (opcional, recomendado)
IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys
    WHERE name = 'FK_pedido_estado' AND parent_object_id = OBJECT_ID(N'[dbo].[pedido]')
)
BEGIN
    ALTER TABLE [dbo].[pedido]
    ADD CONSTRAINT FK_pedido_estado
    FOREIGN KEY (estado_id) REFERENCES [dbo].[pedido_estado](id);

    PRINT 'FK FK_pedido_estado creada.';
END
ELSE
BEGIN
    PRINT 'FK FK_pedido_estado ya existe.';
END
GO

-- Índice para filtros por estado_id
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'idx_pedido_estado_id' AND object_id = OBJECT_ID(N'[dbo].[pedido]')
)
BEGIN
    CREATE INDEX idx_pedido_estado_id ON [dbo].[pedido](estado_id);
    PRINT 'Índice idx_pedido_estado_id creado.';
END
GO

-- Verificación: no debe haber pedidos con estado_id NULL
IF EXISTS (SELECT 1 FROM [dbo].[pedido] WHERE estado_id IS NULL)
    PRINT '⚠️ ATENCIÓN: Hay pedidos con estado_id NULL. Revisar mapping.';
ELSE
    PRINT '✅ Migración completada. Todos los pedidos tienen estado_id asignado.';
GO
