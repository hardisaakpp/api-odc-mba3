-- ============================================================================
-- Script de Migración: Desactivar estados REDISTRIBUIDO (9) y ERROR_DATOS_MAESTROS (14)
-- ============================================================================
-- Descripción: Marca activo=0 en pedido_estado para 2 estados que SÍ tienen
--              código real que los asignaría, pero cuyo camino de código está
--              huérfano/muerto en la práctica -- distinto del caso de la
--              migración 654 (6 estados sin ningún setter, ni siquiera muerto).
--
--              - 9  REDISTRIBUIDO: el único setter real
--                (repo_pedido.update_estado(pedido_id, ESTADO_REDISTRIBUIDO, ...))
--                vive en endpoints_core.py (_handle_redistribuir_pedido:134,
--                _handle_confirmar_redistribucion:217), expuesto en las rutas
--                POST /api/pedidos/{pedido_id}/redistribuir y
--                POST /api/pedidos/{pedido_id}/confirmar-redistribucion.
--                El frontend NO llama a esas rutas: usa
--                POST /api/pedidos/{numero_pedido}/redistribucion/confirmar
--                (endpoints_frontend.py) y
--                POST /api/pedidos/{numero_pedido}/proceso-completo-sap
--                (endpoints_proceso.py::_paso1_confirmar_redistribucion),
--                ninguno de los cuales importa siquiera ESTADO_REDISTRIBUIDO --
--                ambos van directo a ESTADO_PEDIDO_CONFIRMADO (10).
--
--              - 14 ERROR_DATOS_MAESTROS: pedido_cierre_service.py:177 solo lo
--                asigna si resultado_st["error_type"] == "datos_maestros". Ese
--                valor únicamente lo produce
--                stock_transfer_service._lanzar_error_datos_maestros (línea 539),
--                invocado desde _validate_stock_before_st (línea 566) -- función
--                cuyo propio docstring dice "⚠️ DEPRECADO PARA ITR: ... SAP NO
--                requiere validación de stock para crear ITR" y que NO tiene
--                ningún caller en todo el repo. El flujo real de ITR usa
--                _validate_itr_minimal (línea 1700), que solo valida formato
--                básico y nunca produce error_type="datos_maestros".
--
--              Verificado en producción (SCOdcsap, 2026-09-04) contra
--              pedido_estado_historial (7717 transiciones, cobertura desde
--              2026-02-25): CERO transiciones hacia estado_id 9 o 14 en más de
--              6 meses / 1300+ pedidos reales -- consistente con código
--              huérfano, no con "aún no ha ocurrido".
--
--              NO se borra ninguna fila (evita romper las FK de
--              pedido.estado_id / pedido_estado_historial hacia
--              pedido_estado). Solo se apaga `activo`, que
--              get_estados(solo_activos=True) -- único consumidor del
--              catálogo, invocado siempre con ese default -- ya respeta para
--              alimentar el dropdown de filtro "Estado" en los 4 listados de
--              pedidos. 100% reversible con
--              UPDATE pedido_estado SET activo = 1 WHERE id IN (9,14).
--
--              Verificación de seguridad por id: antes de desactivar cada
--              estado, confirma que ningún pedido real está actualmente en
--              ese estado_id. Si existiera alguno, ese id en particular se
--              deja intacto (activo=1) y se imprime una advertencia, sin
--              afectar al otro.
-- Fecha: 2026-09-04
-- ============================================================================

PRINT '🔧 Iniciando migración: Desactivar estados REDISTRIBUIDO y ERROR_DATOS_MAESTROS';
GO

DECLARE @EstadosADesactivar TABLE (id INT, nombre NVARCHAR(100));
INSERT INTO @EstadosADesactivar (id, nombre) VALUES
    (9,  N'REDISTRIBUIDO'),
    (14, N'ERROR_DATOS_MAESTROS');

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
PRINT '📋 Estado final de los 2 candidatos:';
SELECT id, nombre, activo
FROM [dbo].[pedido_estado]
WHERE id IN (9, 14)
ORDER BY id;

PRINT '';
PRINT '✅ Migración completada: estados REDISTRIBUIDO y ERROR_DATOS_MAESTROS evaluados/desactivados';
GO
