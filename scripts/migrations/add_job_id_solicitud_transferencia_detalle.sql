-- ============================================================================
-- Migración: Agregar job_id a solicitud_transferencia_detalle
-- ============================================================================
-- Descripción: El middleware SAP encola una ITR (HTTP 202 + jobId) cuando el
--              Service Layer está saturado, en vez de fallar. Antes de esta
--              migración ese 202 se persistía como estado='Error' definitivo,
--              y el botón "Reintentar ST" reenviaba la creación a ciegas —
--              riesgo real de ITR duplicada si el job original encolado
--              terminaba completándose en segundo plano después del reenvío.
--              Con job_id persistido, el reintento consulta primero
--              GET /api/v1/jobs/{jobId} antes de volver a crear.
-- Nuevo valor de estado: 'Encolada' (job en curso, aún sin resolver).
-- Fecha: 2026-08-05
-- ============================================================================

SET NOCOUNT ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[solicitud_transferencia_detalle]')
    AND name = N'job_id'
)
BEGIN
    ALTER TABLE [dbo].[solicitud_transferencia_detalle]
    ADD job_id NVARCHAR(64) NULL;
    PRINT '  ✅ Columna job_id agregada a solicitud_transferencia_detalle.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna job_id ya existe en solicitud_transferencia_detalle.';
END
GO

PRINT '✅ Migración completada: add_job_id_solicitud_transferencia_detalle';
