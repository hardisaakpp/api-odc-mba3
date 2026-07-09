-- ============================================================================
-- Script de Migración: Agregar índices faltantes para optimización
-- ============================================================================
-- Descripción: Crea índices en campos frecuentemente usados en filtros y JOINs
-- Fecha: 2026-02-06
-- Referencia: Guía de Buenas Prácticas - Sección 2 y 9 (Índices y Rendimiento)
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '🔧 Iniciando migración: Agregar índices faltantes para optimización';
PRINT '============================================================================';
GO

-- ============================================================================
-- TABLA: pedido - Índices para filtros comunes
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: pedido';

-- Índice en estado_id (usado en filtros de listados)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_pedido_estado_id' AND object_id = OBJECT_ID('pedido'))
BEGIN
    PRINT '  ➕ Creando índice idx_pedido_estado_id...';
    CREATE INDEX idx_pedido_estado_id ON pedido(estado_id);
    PRINT '  ✅ Índice idx_pedido_estado_id creado.';
END
ELSE
BEGIN
    PRINT '  ✓ Índice idx_pedido_estado_id ya existe.';
END
GO

-- Índice compuesto para búsquedas por usuario y fecha
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_pedido_creado_por_fecha' AND object_id = OBJECT_ID('pedido'))
BEGIN
    PRINT '  ➕ Creando índice idx_pedido_creado_por_fecha...';
    CREATE INDEX idx_pedido_creado_por_fecha ON pedido(creado_por, creado_en DESC);
    PRINT '  ✅ Índice idx_pedido_creado_por_fecha creado.';
END
ELSE
BEGIN
    PRINT '  ✓ Índice idx_pedido_creado_por_fecha ya existe.';
END
GO

-- ============================================================================
-- TABLA: pedido_detalle - Índices para JOINs y búsquedas
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: pedido_detalle';

-- Índice en marca (usado en filtros de productos)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_pedido_detalle_marca' AND object_id = OBJECT_ID('pedido_detalle'))
BEGIN
    PRINT '  ➕ Creando índice idx_pedido_detalle_marca...';
    CREATE INDEX idx_pedido_detalle_marca ON pedido_detalle(marca);
    PRINT '  ✅ Índice idx_pedido_detalle_marca creado.';
END
ELSE
BEGIN
    PRINT '  ✓ Índice idx_pedido_detalle_marca ya existe.';
END
GO

-- ============================================================================
-- TABLA: distribucion_confirmada - Índices para redistribución
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: distribucion_confirmada';

-- Índice en version (usado en consultas de redistribución)
IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('distribucion_confirmada') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_distribucion_confirmada_version' AND object_id = OBJECT_ID('distribucion_confirmada'))
    BEGIN
        PRINT '  ➕ Creando índice idx_distribucion_confirmada_version...';
        CREATE INDEX idx_distribucion_confirmada_version ON distribucion_confirmada(version);
        PRINT '  ✅ Índice idx_distribucion_confirmada_version creado.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Índice idx_distribucion_confirmada_version ya existe.';
    END
    
    -- Índice compuesto para consultas por pedido y versión
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_distribucion_confirmada_pedido_version' AND object_id = OBJECT_ID('distribucion_confirmada'))
    BEGIN
        PRINT '  ➕ Creando índice idx_distribucion_confirmada_pedido_version...';
        CREATE INDEX idx_distribucion_confirmada_pedido_version ON distribucion_confirmada(pedido_id, version);
        PRINT '  ✅ Índice idx_distribucion_confirmada_pedido_version creado.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Índice idx_distribucion_confirmada_pedido_version ya existe.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla distribucion_confirmada no existe, omitiendo índices.';
END
GO

-- ============================================================================
-- TABLA: orden_compra_cabecera - Índices para consultas de OC
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: orden_compra_cabecera';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND type = 'U')
BEGIN
    -- Índice en estado (filtros de estado de OC)
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_orden_compra_estado' AND object_id = OBJECT_ID('orden_compra_cabecera'))
    BEGIN
        PRINT '  ➕ Creando índice idx_orden_compra_estado...';
        CREATE INDEX idx_orden_compra_estado ON orden_compra_cabecera(estado);
        PRINT '  ✅ Índice idx_orden_compra_estado creado.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Índice idx_orden_compra_estado ya existe.';
    END
    
    -- Índice en pedido_id (JOIN con pedido)
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_orden_compra_pedido_id' AND object_id = OBJECT_ID('orden_compra_cabecera'))
    BEGIN
        PRINT '  ➕ Creando índice idx_orden_compra_pedido_id...';
        CREATE INDEX idx_orden_compra_pedido_id ON orden_compra_cabecera(pedido_id);
        PRINT '  ✅ Índice idx_orden_compra_pedido_id creado.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Índice idx_orden_compra_pedido_id ya existe.';
    END
    
    -- Índice en doc_entry (búsquedas por documento SAP)
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_orden_compra_doc_entry' AND object_id = OBJECT_ID('orden_compra_cabecera'))
    BEGIN
        PRINT '  ➕ Creando índice idx_orden_compra_doc_entry...';
        CREATE INDEX idx_orden_compra_doc_entry ON orden_compra_cabecera(doc_entry);
        PRINT '  ✅ Índice idx_orden_compra_doc_entry creado.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Índice idx_orden_compra_doc_entry ya existe.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla orden_compra_cabecera no existe, omitiendo índices.';
END
GO

-- ============================================================================
-- TABLA: sap_integration_logs - Índices para consultas de historial
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: sap_integration_logs';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('sap_integration_logs') AND type = 'U')
BEGIN
    -- Índice en timestamp_log (ordenamiento por fecha)
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_sap_logs_timestamp' AND object_id = OBJECT_ID('sap_integration_logs'))
    BEGIN
        PRINT '  ➕ Creando índice idx_sap_logs_timestamp...';
        CREATE INDEX idx_sap_logs_timestamp ON sap_integration_logs(timestamp_log DESC);
        PRINT '  ✅ Índice idx_sap_logs_timestamp creado.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Índice idx_sap_logs_timestamp ya existe.';
    END
    
    -- Índice en nivel_log (filtros por severidad)
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_sap_logs_nivel' AND object_id = OBJECT_ID('sap_integration_logs'))
    BEGIN
        PRINT '  ➕ Creando índice idx_sap_logs_nivel...';
        CREATE INDEX idx_sap_logs_nivel ON sap_integration_logs(nivel_log);
        PRINT '  ✅ Índice idx_sap_logs_nivel creado.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Índice idx_sap_logs_nivel ya existe.';
    END
    
    -- Índice en oc_id (búsquedas por orden de compra)
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_sap_logs_oc_id' AND object_id = OBJECT_ID('sap_integration_logs'))
    BEGIN
        PRINT '  ➕ Creando índice idx_sap_logs_oc_id...';
        CREATE INDEX idx_sap_logs_oc_id ON sap_integration_logs(oc_id);
        PRINT '  ✅ Índice idx_sap_logs_oc_id creado.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Índice idx_sap_logs_oc_id ya existe.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla sap_integration_logs no existe, omitiendo índices.';
END
GO

-- ============================================================================
-- TABLA: pedido_respuesta_proveedor - Índices para respuestas
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: pedido_respuesta_proveedor';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('pedido_respuesta_proveedor') AND type = 'U')
BEGIN
    -- Índice en pedido_id (JOIN con pedido)
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_respuesta_proveedor_pedido_id' AND object_id = OBJECT_ID('pedido_respuesta_proveedor'))
    BEGIN
        PRINT '  ➕ Creando índice idx_respuesta_proveedor_pedido_id...';
        CREATE INDEX idx_respuesta_proveedor_pedido_id ON pedido_respuesta_proveedor(pedido_id);
        PRINT '  ✅ Índice idx_respuesta_proveedor_pedido_id creado.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Índice idx_respuesta_proveedor_pedido_id ya existe.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla pedido_respuesta_proveedor no existe, omitiendo índices.';
END
GO

-- ============================================================================
-- Resumen de índices creados
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada: Índices faltantes agregados';
PRINT '============================================================================';
PRINT '';
PRINT '📊 Resumen de índices por tabla:';
PRINT '  - pedido: estado_id, creado_por+fecha';
PRINT '  - pedido_detalle: marca';
PRINT '  - distribucion_confirmada: version, pedido_id+version';
PRINT '  - orden_compra_cabecera: estado, pedido_id, doc_entry';
PRINT '  - sap_integration_logs: timestamp, nivel, oc_id';
PRINT '  - pedido_respuesta_proveedor: pedido_id';
GO

SET NOCOUNT OFF;
GO
