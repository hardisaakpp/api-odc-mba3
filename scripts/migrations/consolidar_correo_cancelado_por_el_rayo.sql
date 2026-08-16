-- ============================================================================
-- Migración: Consolidar "Pedido Cancelado por El Rayo" en una sola fila (MABEL_TRADING)
-- ============================================================================
-- Descripción: La fila PRODUCCION_ELRAYO para este correo (agregada en la
--              migración 637) quedó redundante: desde que existe "Personas y
--              Correos" (notificacion_persona_correo), cualquier persona se
--              vincula directamente a una fila del catálogo sin importar su
--              equipo — no hace falta una fila por audiencia para controlar
--              destinatarios. Tener 2 filas con el mismo asunto generaba
--              confusión: en el catálogo se veían como "correo repetido", y en
--              el checkbox de "Personas y Correos" la misma etiqueta
--              ("Pedido Cancelado por El Rayo") aparecía 2 veces.
--
--              Este correo es un buen candidato para consolidar porque el
--              asunto y el cuerpo son idénticos para ambas audiencias (ver
--              _build_pedido_cancelado_por_el_rayo_email en email_notifier.py:
--              no bifurca por tipo_notificacion). "OC y Solicitudes de
--              Transferencia - Listo para Despacho" tiene el mismo patrón de
--              2 filas pero NO se toca en esta migración: hay que revisar
--              primero si su contenido también es igual para ambas audiencias
--              antes de decidir si aplica la misma consolidación.
--
--              Pasos:
--              1) Re-vincula a MABEL_TRADING (fila sobreviviente) las personas
--                 que solo estaban vinculadas a PRODUCCION_ELRAYO para este
--                 correo, sin duplicar el vínculo si la persona ya estaba en
--                 ambas (UNIQUE (email, tipo_correo_id)).
--              2) Elimina la fila PRODUCCION_ELRAYO del catálogo; el
--                 ON DELETE CASCADE de notificacion_persona_correo limpia
--                 cualquier vínculo remanente (personas ya presentes también
--                 en MABEL_TRADING).
--              3) Actualiza la descripción de la fila MABEL_TRADING para que
--                 ya no dependa de la fila retirada.
--              orden_flujo=5 queda vacante (mismo criterio que las
--              migraciones 632/634: no se renumera el resto del catálogo).
--
--              El código de envío (email_notifier.py) se simplifica en el
--              mismo cambio: _build_unique_recipients(["MABEL_TRADING",
--              "PRODUCCION_ELRAYO"], ...) pasa a un solo
--              get_destinatarios_por_correo("MABEL_TRADING", ...). Es seguro
--              aplicar esta migración de datos antes, después o junto con ese
--              cambio de código: mientras el código viejo siga consultando
--              ambos tipos, "PRODUCCION_ELRAYO" simplemente devolverá 0
--              destinatarios (ya migrados a MABEL_TRADING) y la unión sigue
--              siendo la misma lista completa; y con el código nuevo, todos
--              los destinatarios ya están bajo MABEL_TRADING.
-- Fecha: 2026-08-14
-- ============================================================================

PRINT '🔧 Iniciando migración: consolidar "Pedido Cancelado por El Rayo" en MABEL_TRADING';
GO

DECLARE @id_mabel INT = (
    SELECT id FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Cancelado por El Rayo'
);
DECLARE @id_produccion INT = (
    SELECT id FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'PRODUCCION_ELRAYO' AND tipo_correo = N'Pedido Cancelado por El Rayo'
);

IF @id_mabel IS NULL
BEGIN
    PRINT '⚠️ No se encontró la fila MABEL_TRADING para "Pedido Cancelado por El Rayo"; no se aplica ningún cambio (revisar catálogo).';
END
ELSE IF @id_produccion IS NULL
BEGIN
    PRINT '✓ La fila PRODUCCION_ELRAYO ya no existe: el correo ya está consolidado.';
END
ELSE
BEGIN
    -- Re-vincula a MABEL_TRADING las personas que solo estaban en PRODUCCION_ELRAYO;
    -- evita violar el UNIQUE (email, tipo_correo_id) si la persona ya estaba en ambas.
    UPDATE notificacion_persona_correo
        SET tipo_correo_id = @id_mabel
        WHERE tipo_correo_id = @id_produccion
          AND email NOT IN (
              SELECT email FROM notificacion_persona_correo WHERE tipo_correo_id = @id_mabel
          );

    PRINT '✅ Personas de Producción El Rayo re-vinculadas a la fila MABEL_TRADING.';

    -- Elimina la fila PRODUCCION_ELRAYO; ON DELETE CASCADE limpia cualquier
    -- vínculo remanente (personas ya presentes también en MABEL_TRADING).
    DELETE FROM notificacion_tipo_correo WHERE id = @id_produccion;

    PRINT '✅ Fila PRODUCCION_ELRAYO eliminada del catálogo.';

    UPDATE notificacion_tipo_correo
        SET descripcion = N'Se envía a quienes estén vinculados a este correo en Personas y Correos (incluye a MABEL TRADING y a Producción El Rayo, que confirmó el pedido originalmente) cuando Administración El Rayo cancela un pedido desde Detalle del Pedido (botón "Cancelar Pedido"), disponible solo en estado Confirmado por Producción',
            modificado_por = 'consolidar_correo_cancelado_por_el_rayo_2026-08-14',
            modificado_fecha = GETDATE()
        WHERE id = @id_mabel;

    PRINT '✅ Descripción de la fila MABEL_TRADING actualizada.';
END
GO

-- ============================================================================
-- Verificación
-- ============================================================================
PRINT '';
PRINT '📋 Estado del correo "Pedido Cancelado por El Rayo" en el catálogo:';
SELECT id, tipo_notificacion, tipo_correo, descripcion, orden_flujo, activo
FROM notificacion_tipo_correo
WHERE tipo_correo = N'Pedido Cancelado por El Rayo';

PRINT '';
PRINT '✅ Migración completada: correo "Pedido Cancelado por El Rayo" consolidado en 1 fila';
GO
