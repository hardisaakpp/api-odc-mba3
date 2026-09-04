-- ============================================================================
-- Script de Migración: Desactivar estados de pedido obsoletos (activo=0)
-- ============================================================================
-- Descripción: Marca activo=0 en pedido_estado para 6 estados sembrados desde
--              el inicio (create_pedido_estado_table.sql) que resultaron
--              genuinamente muertos -- ningún endpoint/servicio los alcanza:
--                - 6  CONFIRMADO_PROVEEDOR: único setter
--                  (PedidoAjusteService.procesar_confirmacion_proveedor) sin
--                  ningún caller en todo el backend.
--                - 7  RECHAZADO_PROVEEDOR, 8 EN_AJUSTE_MABEL, 11 PROCESADO_SAP,
--                  15 EN_PROCESO, 16 COMPLETADO: sin constante Python, sin una
--                  sola referencia de código (ni siquiera muerta) en todo el
--                  repo -- residuos de un diseño anterior superado por el
--                  flujo actual (CONFIRMADO_ENVIADO/PENDIENTE_LOGISTICA/
--                  ERROR_DATOS_MAESTROS, DESPACHAR_Y_FACTURAR/FINALIZADO).
--
--              NO se borra ninguna fila (evita romper las FK de
--              pedido.estado_id / pedido_estado_historial hacia
--              pedido_estado). Solo se apaga `activo`, que
--              get_estados(solo_activos=True) -- único consumidor del
--              catálogo, invocado siempre con ese default -- ya respeta para
--              alimentar el dropdown de filtro "Estado" en los 4 listados de
--              pedidos. 100% reversible con
--              UPDATE pedido_estado SET activo = 1 WHERE id IN (6,7,8,11,15,16).
--
--              Verificación de seguridad por id: antes de desactivar cada
--              estado, confirma que ningún pedido real está actualmente en
--              ese estado_id. Si existiera alguno (posible en producción
--              aunque en dev se verificó 0 para los 6), ese id en particular
--              se deja intacto (activo=1) y se imprime una advertencia, sin
--              afectar a los demás.
-- Fecha: 2026-09-03
-- ============================================================================

PRINT '🔧 Iniciando migración: Desactivar estados de pedido obsoletos';
GO

DECLARE @EstadosADesactivar TABLE (id INT, nombre NVARCHAR(100));
INSERT INTO @EstadosADesactivar (id, nombre) VALUES
    (6,  N'CONFIRMADO_PROVEEDOR'),
    (7,  N'RECHAZADO_PROVEEDOR'),
    (8,  N'EN_AJUSTE_MABEL'),
    (11, N'PROCESADO_SAP'),
    (15, N'EN_PROCESO'),
    (16, N'COMPLETADO');

DECLARE @Id INT, @Nombre NVARCHAR(100), @ConteoPedidos INT;

DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
    SELECT id, nombre FROM @EstadosADesactivar ORDER BY id;

OPEN cur;
FETCH NEXT FROM cur INTO @Id, @Nombre;

WHILE @@FETCH_STATUS = 0
BEGIN
    SELECT @ConteoPedidos = COUNT(*) FROM [dbo].[pedido] WHERE estado_id = @Id;

    IF @ConteoPedidos = 0
    BEGIN
        UPDATE [dbo].[pedido_estado]
        SET activo = 0, updated_at = GETDATE()
        WHERE id = @Id AND activo = 1;

        PRINT '✅ Estado ' + CAST(@Id AS NVARCHAR(10)) + ' (' + @Nombre + ') desactivado (sin pedidos reales en ese estado).';
    END
    ELSE
    BEGIN
        PRINT '⚠️  Estado ' + CAST(@Id AS NVARCHAR(10)) + ' (' + @Nombre + ') NO desactivado: existen ' + CAST(@ConteoPedidos AS NVARCHAR(10)) + ' pedido(s) real(es) en este estado. Revisar manualmente antes de desactivar.';
    END

    FETCH NEXT FROM cur INTO @Id, @Nombre;
END

CLOSE cur;
DEALLOCATE cur;
GO

PRINT '';
PRINT '📋 Estado final de los 6 candidatos:';
SELECT id, nombre, activo
FROM [dbo].[pedido_estado]
WHERE id IN (6, 7, 8, 11, 15, 16)
ORDER BY id;

PRINT '';
PRINT '✅ Migración completada: estados obsoletos evaluados/desactivados';
GO
