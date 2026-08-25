-- ============================================================================
-- Migración: Agregar job_id a orden_compra_cabecera
-- ============================================================================
-- Descripción: El middleware SAP encola una Purchase Order (HTTP 202 + jobId)
--              cuando el Service Layer está saturado, en vez de fallar. Antes
--              de esta migración ese 202 se persistía como estado='ERROR'
--              definitivo, y el botón "Reintentar" reenviaba la creación a
--              ciegas -- riesgo real de ODC duplicada si el job original
--              encolado terminaba completándose en segundo plano después del
--              reenvío (ya ocurrió en producción: ODC 24711 encolada + 24712
--              duplicada por reintento manual).
--              Con job_id persistido, el reintento consulta primero
--              GET /api/v1/jobs/{jobId} antes de volver a crear (mismo patrón
--              ya aplicado a solicitud_transferencia_detalle, migración 615).
-- Nuevo valor de estado: 'ENCOLADA' (job en curso, aún sin resolver).
-- Fecha: 2026-08-25
-- ============================================================================

SET NOCOUNT ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[orden_compra_cabecera]')
    AND name = N'job_id'
)
BEGIN
    ALTER TABLE [dbo].[orden_compra_cabecera]
    ADD job_id NVARCHAR(64) NULL;
    PRINT '  ✅ Columna job_id agregada a orden_compra_cabecera.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna job_id ya existe en orden_compra_cabecera.';
END
GO

PRINT '✅ Migración completada: add_job_id_orden_compra_cabecera';
