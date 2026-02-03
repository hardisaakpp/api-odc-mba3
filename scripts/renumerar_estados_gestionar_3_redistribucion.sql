-- ============================================================================
-- Renombrar EN_REVISION → REDISTRIBUCION (id=4) y asignar GESTIONAR PEDIDO a id=3
-- ============================================================================
-- Resultado: 3=GESTIONAR PEDIDO, 4=REDISTRIBUCION, 5=RESPUESTA_PROVEEDOR_CARGADA, ..., 16=COMPLETADO
-- ============================================================================

-- Paso 1: Renombrar EN_REVISION a REDISTRIBUCION (id=4 no cambia)
UPDATE [dbo].[pedido_estado] SET nombre = N'REDISTRIBUCION' WHERE id = 4;
PRINT 'Nombre id=4 actualizado a REDISTRIBUCION.';
GO

-- Paso 2: Renumerar pedido.estado_id (liberar 3 para GESTIONAR, desplazar 3..15 → 5..16, 16→3)
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'[dbo].[pedido]') AND name = 'estado_id')
BEGIN
    UPDATE pedido SET estado_id = 99 WHERE estado_id = 3;
    UPDATE pedido SET estado_id = 3  WHERE estado_id = 16;
    UPDATE pedido SET estado_id = 16 WHERE estado_id = 15;
    UPDATE pedido SET estado_id = 15 WHERE estado_id = 14;
    UPDATE pedido SET estado_id = 14 WHERE estado_id = 13;
    UPDATE pedido SET estado_id = 13 WHERE estado_id = 12;
    UPDATE pedido SET estado_id = 12 WHERE estado_id = 11;
    UPDATE pedido SET estado_id = 11 WHERE estado_id = 10;
    UPDATE pedido SET estado_id = 10 WHERE estado_id = 9;
    UPDATE pedido SET estado_id = 9  WHERE estado_id = 8;
    UPDATE pedido SET estado_id = 8  WHERE estado_id = 7;
    UPDATE pedido SET estado_id = 7  WHERE estado_id = 6;
    UPDATE pedido SET estado_id = 6  WHERE estado_id = 5;
    UPDATE pedido SET estado_id = 5  WHERE estado_id = 99;
    PRINT 'pedido.estado_id renumerado.';
END
GO

-- Paso 3: Renumerar pedido_estado (mismo orden: 3↔16, 3→5, 5→6, ..., 15→16)
UPDATE pedido_estado SET id = 99, orden = 99 WHERE id = 3;
UPDATE pedido_estado SET id = 3,  orden = 3  WHERE id = 16;
UPDATE pedido_estado SET id = 16, orden = 16 WHERE id = 15;
UPDATE pedido_estado SET id = 15, orden = 15 WHERE id = 14;
UPDATE pedido_estado SET id = 14, orden = 14 WHERE id = 13;
UPDATE pedido_estado SET id = 13, orden = 13 WHERE id = 12;
UPDATE pedido_estado SET id = 12, orden = 12 WHERE id = 11;
UPDATE pedido_estado SET id = 11, orden = 11 WHERE id = 10;
UPDATE pedido_estado SET id = 10, orden = 10 WHERE id = 9;
UPDATE pedido_estado SET id = 9,  orden = 9  WHERE id = 8;
UPDATE pedido_estado SET id = 8,  orden = 8  WHERE id = 7;
UPDATE pedido_estado SET id = 7,  orden = 7  WHERE id = 6;
UPDATE pedido_estado SET id = 6,  orden = 6  WHERE id = 5;
UPDATE pedido_estado SET id = 5,  orden = 5  WHERE id = 99;
PRINT 'pedido_estado renumerado: 3=GESTIONAR PEDIDO, 4=REDISTRIBUCION, 5=RESPUESTA_PROVEEDOR_CARGADA, ...';
GO
