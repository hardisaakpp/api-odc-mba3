-- ============================================================================
-- Migración: Estado ERROR ENVIO SAP REINTENTO (id = 21)
-- ============================================================================
-- Pedido en Confirmado redistribución cuyo envío de ODC a SAP falló de forma
-- típicamente recuperable (conexión / transitorio). Permite reintentar desde la UI.
-- Fecha: 2026-04-09
-- ============================================================================

PRINT 'Migración: add_estado_error_envio_sap_reintento';
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 21)
BEGIN
    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo)
    VALUES (21, N'ERROR ENVIO SAP REINTENTO', 21, 1);
    PRINT 'Estado 21 (ERROR ENVIO SAP REINTENTO) insertado.';
END
ELSE
BEGIN
    PRINT 'Estado 21 ya existe; no se inserta.';
END
GO

-- Opcional: alinear pedidos ya en 10 con ODC en ERROR por mensaje de conexión (ejecutar con criterio acordado)
/*
UPDATE p
SET p.estado_id = 21
FROM pedido p
INNER JOIN orden_compra_cabecera oc ON oc.pedido_id = p.pedido_id
WHERE p.estado_id = 10
  AND oc.estado = N'ERROR'
  AND (
    oc.respuesta_sap LIKE N'%conexión%' OR oc.respuesta_sap LIKE N'%conexion%'
    OR oc.error_message LIKE N'%conexión%' OR oc.error_message LIKE N'%conexion%'
  );
*/

PRINT 'Migración add_estado_error_envio_sap_reintento completada.';
GO
