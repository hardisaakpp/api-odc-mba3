-- ============================================================================
-- Migración: Consolidar "OC y Solicitudes de Transferencia - Listo para Despacho" en una sola fila (OPERACIONES)
-- ============================================================================
-- Descripción: Mismo patrón que la migración 638 (consolidar_correo_cancelado_por_el_rayo),
--              que dejó pendiente revisar este correo por separado. Este correo tenía 2
--              filas en el catálogo (OPERACIONES y MABEL_TRADING) desde el seed inicial
--              (migración 624), únicamente para poder asignar destinatarios por audiencia
--              en "Personas y Correos". Se verificó que el envío real ya es un solo correo
--              con el mismo asunto y cuerpo para ambas audiencias
--              (send_oc_ready_for_dispatch_notification en email_notifier.py, que llamaba
--              a _build_unique_recipients(["OPERACIONES", "MABEL_TRADING"], _CORREO_DESPACHO)
--              sin bifurcar contenido por tipo_notificacion). Con notificacion_persona_correo
--              ya no hace falta una fila de catálogo por audiencia para controlar
--              destinatarios, así que la segunda fila es redundante y generaba el mismo
--              "correo repetido" visual que el catálogo mostraba para Cancelado por El Rayo.
--
--              Se conserva la fila OPERACIONES (orden_flujo=10): es la audiencia principal
--              según el docstring de la función (HU-04: alertar al personal de El Rayo para
--              proceder con despacho y facturación); MABEL_TRADING se notifica en copia.
--              Pasos, igual que la migración 638:
--              1) Re-vincula a OPERACIONES las personas que solo estaban vinculadas a la
--                 fila MABEL_TRADING para este correo, sin duplicar el vínculo si la
--                 persona ya estaba en ambas (UNIQUE (email, tipo_correo_id)).
--              2) Elimina la fila MABEL_TRADING del catálogo; el ON DELETE CASCADE de
--                 notificacion_persona_correo limpia cualquier vínculo remanente.
--              3) Actualiza la descripción de la fila OPERACIONES sobreviviente para que
--                 ya no dependa de la fila retirada.
--              orden_flujo=11 queda vacante (mismo criterio que las migraciones
--              632/634/638: no se renumera el resto del catálogo).
--
--              El código de envío (email_notifier.py) se simplifica en el mismo cambio:
--              _build_unique_recipients(["OPERACIONES", "MABEL_TRADING"], ...) pasa a un
--              solo get_destinatarios_por_correo("OPERACIONES", ...). Es seguro aplicar
--              esta migración de datos antes, después o junto con ese cambio de código:
--              mientras el código viejo siga consultando ambos tipos, "MABEL_TRADING"
--              simplemente devolverá 0 destinatarios (ya migrados a OPERACIONES) y la
--              unión sigue siendo la misma lista completa; y con el código nuevo, todos
--              los destinatarios ya están bajo OPERACIONES.
-- Fecha: 2026-08-16
-- ============================================================================

PRINT '🔧 Iniciando migración: consolidar "OC y Solicitudes de Transferencia - Listo para Despacho" en OPERACIONES';
GO

DECLARE @id_operaciones INT = (
    SELECT id FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'OC y Solicitudes de Transferencia - Listo para Despacho'
);
DECLARE @id_mabel INT = (
    SELECT id FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'OC y Solicitudes de Transferencia - Listo para Despacho'
);

IF @id_operaciones IS NULL
BEGIN
    PRINT '⚠️ No se encontró la fila OPERACIONES para "OC y Solicitudes de Transferencia - Listo para Despacho"; no se aplica ningún cambio (revisar catálogo).';
END
ELSE IF @id_mabel IS NULL
BEGIN
    PRINT '✓ La fila MABEL_TRADING ya no existe: el correo ya está consolidado.';
END
ELSE
BEGIN
    -- Re-vincula a OPERACIONES las personas que solo estaban en MABEL_TRADING;
    -- evita violar el UNIQUE (email, tipo_correo_id) si la persona ya estaba en ambas.
    UPDATE notificacion_persona_correo
        SET tipo_correo_id = @id_operaciones
        WHERE tipo_correo_id = @id_mabel
          AND email NOT IN (
              SELECT email FROM notificacion_persona_correo WHERE tipo_correo_id = @id_operaciones
          );

    PRINT '✅ Personas de MABEL_TRADING re-vinculadas a la fila OPERACIONES.';

    -- Elimina la fila MABEL_TRADING; ON DELETE CASCADE limpia cualquier
    -- vínculo remanente (personas ya presentes también en OPERACIONES).
    DELETE FROM notificacion_tipo_correo WHERE id = @id_mabel;

    PRINT '✅ Fila MABEL_TRADING eliminada del catálogo.';

    UPDATE notificacion_tipo_correo
        SET descripcion = N'Se envía a quienes estén vinculados a este correo en Personas y Correos (incluye a Administración El Rayo y a MABEL TRADING) cuando la OC y las Solicitudes de Transferencia ya fueron generadas en SAP y se puede proceder con despacho y facturación',
            modificado_por = 'consolidar_correo_oc_listo_despacho_2026-08-16',
            modificado_fecha = GETDATE()
        WHERE id = @id_operaciones;

    PRINT '✅ Descripción de la fila OPERACIONES actualizada.';
END
GO

-- ============================================================================
-- Verificación
-- ============================================================================
PRINT '';
PRINT '📋 Estado del correo "OC y Solicitudes de Transferencia - Listo para Despacho" en el catálogo:';
SELECT id, tipo_notificacion, tipo_correo, descripcion, orden_flujo, activo
FROM notificacion_tipo_correo
WHERE tipo_correo = N'OC y Solicitudes de Transferencia - Listo para Despacho';

PRINT '';
PRINT '✅ Migración completada: correo "OC y Solicitudes de Transferencia - Listo para Despacho" consolidado en 1 fila';
GO
