-- ============================================================================
-- Migración: Agregar fecha_envio_iniciado a orden_compra_cabecera
-- ============================================================================
-- Descripción: Soporte para el nuevo estado 'ENVIANDO' de orden_compra_cabecera.estado
--              (columna NVARCHAR libre, sin CHECK constraint -- el valor nuevo en sí
--              no requiere migración). Esta columna persiste CUÁNDO empezó el intento
--              de envío más reciente, para que la reconciliación periódica
--              (celery_reconciliar_ordenes_compra.py) pueda detectar una ODC ENVIANDO
--              "estancada" (proceso caído a mitad del envío a SAP -- OOM/reinicio de
--              pod -- sin que ningún camino de salida haya llegado a fijar un estado
--              terminal) comparando esta fecha contra ENVIANDO_ESTANCADO_UMBRAL_MINUTOS
--              (src/config.py), y para dar contexto de soporte/depuración del intento
--              más reciente.
--              A diferencia de job_id (migración 650), esta columna NO se limpia al
--              salir de ENVIANDO: un valor viejo es inofensivo porque nada lo lee sin
--              filtrar también por estado = 'ENVIANDO'.
-- Fecha: 2026-08-31
-- ============================================================================

SET NOCOUNT ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[orden_compra_cabecera]')
    AND name = N'fecha_envio_iniciado'
)
BEGIN
    ALTER TABLE [dbo].[orden_compra_cabecera]
    ADD fecha_envio_iniciado DATETIME NULL;
    PRINT '  ✅ Columna fecha_envio_iniciado agregada a orden_compra_cabecera.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna fecha_envio_iniciado ya existe en orden_compra_cabecera.';
END
GO

PRINT '✅ Migración completada: add_fecha_envio_iniciado_orden_compra_cabecera';
