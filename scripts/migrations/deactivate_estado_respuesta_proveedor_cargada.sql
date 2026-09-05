-- ============================================================================
-- Script de Migración: Desactivar estado RESPUESTA_PROVEEDOR_CARGADA (5)
-- ============================================================================
-- Descripción: Marca activo=0 en pedido_estado para el id 5
--              (RESPUESTA_PROVEEDOR_CARGADA, mostrado como "EN_REVISION" en
--              algunos ambientes -- el nombre es solo presentación y pudo
--              editarse). Mismo patrón que las migraciones 654 y 655: el
--              código SÍ tiene un setter real, pero quedó huérfano en la
--              práctica.
--
--              El único setter (repo.update_estado(pedido_id,
--              ESTADO_RESPUESTA_PROVEEDOR_CARGADA, ...)) vive en
--              pedido_proveedor_service.py:478
--              (PedidoProveedorService.importar_respuesta_proveedor),
--              invocado desde el endpoint
--              POST /api/pedidos/{pedido_id}/cargar-respuesta-proveedor
--              (pedidos_proveedor.py:542). Ese endpoint SÍ está registrado y
--              funcionaría si se le llamara -- pero el frontend no tiene
--              ningún botón/formulario que lo invoque: el método de servicio
--              correspondiente (respuestaProveedorService.cargarRespuestaProveedor
--              / mba3ConsultasApi.cargarRespuestaProveedor) no tiene ningún
--              caller en ninguna vista/componente de scnexus-front. El flujo
--              completo "proveedor responde por Excel" (5 → 6
--              CONFIRMADO_PROVEEDOR, este último ya desactivado en la
--              migración 654 por el mismo motivo) quedó reemplazado por el
--              flujo de Redistribución actual sin que nadie retirara este
--              endpoint huérfano.
--
--              Verificado en producción (SCOdcsap, 2026-09-04) contra
--              pedido_estado_historial (7717 transiciones, cobertura desde
--              2026-02-25): CERO transiciones hacia estado_id 5 en más de
--              6 meses / 1300+ pedidos reales.
--
--              NO se borra la fila (evita romper las FK de
--              pedido.estado_id / pedido_estado_historial hacia
--              pedido_estado). Solo se apaga `activo`, respetado por
--              get_estados(solo_activos=True). 100% reversible con
--              UPDATE pedido_estado SET activo = 1 WHERE id = 5.
--
--              Verificación de seguridad: antes de desactivar, confirma que
--              ningún pedido real está actualmente en estado_id = 5. Si
--              existiera alguno, se deja intacto (activo=1) y se imprime
--              una advertencia.
-- Fecha: 2026-09-04
-- ============================================================================

PRINT '🔧 Iniciando migración: Desactivar estado RESPUESTA_PROVEEDOR_CARGADA (5)';
GO

DECLARE @ConteoPedidos INT;
SELECT @ConteoPedidos = COUNT(*) FROM [dbo].[pedido] WHERE estado_id = 5;

IF @ConteoPedidos = 0
BEGIN
    UPDATE [dbo].[pedido_estado]
    SET activo = 0, updated_at = GETDATE()
    WHERE id = 5 AND activo = 1;

    PRINT '✅ Estado 5 (RESPUESTA_PROVEEDOR_CARGADA) desactivado (sin pedidos reales en ese estado).';
END
ELSE
BEGIN
    PRINT '⚠️  Estado 5 (RESPUESTA_PROVEEDOR_CARGADA) NO desactivado: existen ' + CAST(@ConteoPedidos AS NVARCHAR(10)) + ' pedido(s) real(es) en este estado. Revisar manualmente antes de desactivar.';
END
GO

PRINT '';
PRINT '📋 Estado final:';
SELECT id, nombre, activo
FROM [dbo].[pedido_estado]
WHERE id = 5;

PRINT '';
PRINT '✅ Migración completada: estado RESPUESTA_PROVEEDOR_CARGADA evaluado/desactivado';
GO
