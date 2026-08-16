-- ============================================================================
-- Migración: Corregir descripción del correo "Pedido Descartado" en el catálogo
-- ============================================================================
-- Descripción: La descripción original ("Se envía a El Rayo al descartar/eliminar
--              un pedido en Borrador o Nuevo Pedido") no coincide con el
--              comportamiento real del código (_descartar_o_cancelar_pedido_handler,
--              pedidos_cancelar_endpoints.py): descartar en BORRADOR nunca envía
--              este correo, a propósito — en ese estado el pedido nunca se le
--              "envió" a El Rayo/Producción (eso ocurre recién al pasar a NUEVO
--              PEDIDO). Se acota la descripción al único flujo real desde el
--              frontend (Cargar Plantilla / Nuevo Pedido): "Cancelar Pedido"
--              desde Redistribución usa el correo distinto "Pedido Cancelado"
--              (el parámetro notificar_el_rayo=true del DELETE existe en el
--              backend pero ningún botón del frontend lo invoca hoy). Este
--              cambio corrige únicamente el texto descriptivo del catálogo
--              (admin de correos); no altera ninguna lógica de envío.
-- Fecha: 2026-08-14
-- ============================================================================

PRINT '🔧 Iniciando migración: corregir descripción de "Pedido Descartado"';
GO

UPDATE notificacion_tipo_correo
    SET descripcion = N'Se envía a El Rayo al descartar un pedido en estado Nuevo Pedido, desde Cargar Plantilla.',
        modificado_por = 'fix_descripcion_2026-08-14',
        modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Pedido Descartado';

PRINT '✅ Migración completada: descripción de "Pedido Descartado" corregida';
GO
