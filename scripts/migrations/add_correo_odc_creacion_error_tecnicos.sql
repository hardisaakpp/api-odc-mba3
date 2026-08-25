-- ============================================================================
-- Migración: Agregar correo "Error al crear ODC en SAP (reconciliación automática)"
-- al catálogo (TECNICOS)
-- ============================================================================
-- Descripción: La reconciliación automática de ODC ENCOLADAS (HTTP 202 del
--              middleware al crear la Purchase Order, ver
--              src/tasks/celery_reconciliar_ordenes_compra.py) puede descubrir,
--              sin que haya un humano mirando la pantalla, que el job encolado
--              terminó en un error real de SAP al reintentarlo. Sin este correo
--              nadie se enteraba: la ODC quedaba en estado ERROR visible solo si
--              alguien entraba a revisarla manualmente.
--              No se reutiliza el correo existente "Error en OC y Solicitudes de
--              Transferencia" porque su contenido está armado específicamente
--              para errores de Solicitudes de Transferencia (muestra
--              "transferencias creadas/fallidas"), que no aplica a un error de
--              creación de la ODC misma.
--              orden_flujo = NULL (igual que "Error en Migración Automática" /
--              "Advertencia de Capacidad": no es parte de la secuencia de un
--              pedido, es una alerta de un proceso en segundo plano).
-- Fecha: 2026-08-25
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar correo Error al crear ODC en SAP (reconciliación automática)';
GO

IF NOT EXISTS (
    SELECT 1 FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'TECNICOS' AND tipo_correo = N'Error al crear ODC en SAP (reconciliación automática)'
)
BEGIN
    INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, orden_flujo, creado_por)
    VALUES (
        'TECNICOS',
        N'Error al crear ODC en SAP (reconciliación automática)',
        N'Se envía cuando la reconciliación automática de una ODC encolada (HTTP 202 del middleware) reintenta el envío y SAP lo rechaza con un error real, no transitorio',
        NULL,
        'add_odc_creacion_error_2026-08-25'
    );

    PRINT '✅ Correo "Error al crear ODC en SAP (reconciliación automática)" agregado al catálogo TECNICOS.';
END
ELSE
BEGIN
    PRINT '✓ El correo "Error al crear ODC en SAP (reconciliación automática)" ya existe.';
END
GO

PRINT '';
PRINT '✅ Migración completada: correo Error al crear ODC en SAP (reconciliación automática)';
GO
