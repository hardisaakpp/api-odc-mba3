-- ============================================================================
-- Script de Migración: Reordenar pedido_estado.orden según el flujo real
-- ============================================================================
-- Descripción: `orden` nació como copia de `id` (create_pedido_estado_table.sql
--              y cada migración add_estado_*.sql siguiente le asignan
--              orden = id), así que refleja el orden en que cada estado se
--              agregó al catálogo, NO la secuencia real del flujo de negocio.
--              Por ejemplo, CONFIRMADO POR PRODUCCION (23) se agregó después
--              pero ocurre entre GESTIONAR PEDIDO (3) y CONFIRMADO POR EL
--              RAYO (4) -- su propia migración (621) ya lo documenta así,
--              pero nunca se le asignó un `orden` acorde.
--
--              Este script reasigna `orden` (1..16) solo a los 16 estados
--              ACTIVOS, seguiendo la secuencia real (rama principal primero,
--              ramas de excepción/cancelación pegadas al punto donde ocurren):
--
--               1  BORRADOR (1)                    -- carga inicial de Excel
--               2  NUEVO PEDIDO (2)                 -- notificado a EL RAYO
--               3  GESTIONAR PEDIDO (3)             -- Producción El Rayo gestiona
--               4  CONFIRMADO POR PRODUCCION (23)   -- Producción confirma
--               5  CANCELADO POR EL RAYO (20)       -- rama terminal desde 23
--               6  CONFIRMADO POR EL RAYO (4)       -- listo para redistribución
--               7  PRODUCCION POSPUESTA (22)        -- rama: diferencia a resolver
--               8  LISTO PARA REDISTRIBUCION (25)   -- "Aceptar" en 22, sigue el flujo
--               9  RECHAZADO (24)                   -- "Rechazar" en 22, terminal
--               10 CANCELADO (19)                   -- rama terminal (Cancelar Pedido)
--               11 CONFIRMADO REDISTRIBUCION (10)   -- PASO 1 (Proceso Completo SAP) ok
--               12 ERROR ENVIO SAP REINTENTO (21)   -- PASO 3 (enviar OC a SAP) falló
--               13 PENDIENTE_LOGISTICA (13)         -- OC ok, ST falló
--               14 CONFIRMADO_ENVIADO (12)          -- OC + ST ok
--               15 DESPACHAR Y FACTURAR (17)        -- manual, desde Confirmado y Enviado
--               16 FINALIZADO (18)                  -- estado final
--
--              Los estados inactivos (5,6,7,8,9,11,14,15,16 -- ver migraciones
--              654/655/656) NO se tocan: no aparecen en ningún dropdown
--              (get_estados siempre filtra por activo=1), así que su `orden`
--              es irrelevante y se deja como estaba, sin reescribir historia.
--
--              100% reversible: cada UPDATE es independiente por id; para
--              revertir, reasignar orden = id para estos mismos 16 ids.
-- Fecha: 2026-09-04
-- ============================================================================

PRINT '🔧 Iniciando migración: Reordenar pedido_estado.orden según el flujo real';
GO

DECLARE @Secuencia TABLE (id INT PRIMARY KEY, orden_nuevo INT);
INSERT INTO @Secuencia (id, orden_nuevo) VALUES
    (1,  1),   -- BORRADOR
    (2,  2),   -- NUEVO PEDIDO
    (3,  3),   -- GESTIONAR PEDIDO
    (23, 4),   -- CONFIRMADO POR PRODUCCION
    (20, 5),   -- CANCELADO POR EL RAYO
    (4,  6),   -- CONFIRMADO POR EL RAYO
    (22, 7),   -- PRODUCCION POSPUESTA
    (25, 8),   -- LISTO PARA REDISTRIBUCION
    (24, 9),   -- RECHAZADO
    (19, 10),  -- CANCELADO
    (10, 11),  -- CONFIRMADO REDISTRIBUCION
    (21, 12),  -- ERROR ENVIO SAP REINTENTO
    (13, 13),  -- PENDIENTE_LOGISTICA
    (12, 14),  -- CONFIRMADO_ENVIADO
    (17, 15),  -- DESPACHAR Y FACTURAR
    (18, 16);  -- FINALIZADO

UPDATE pe
SET pe.orden = s.orden_nuevo,
    pe.updated_at = GETDATE()
FROM [dbo].[pedido_estado] pe
INNER JOIN @Secuencia s ON s.id = pe.id;

PRINT '✅ Reordenados ' + CAST(@@ROWCOUNT AS NVARCHAR(10)) + ' estado(s).';
GO

PRINT '';
PRINT '📋 Orden final (activos primero):';
SELECT id, nombre, orden, activo
FROM [dbo].[pedido_estado]
ORDER BY activo DESC, orden ASC;

PRINT '';
PRINT '✅ Migración completada: pedido_estado.orden refleja el flujo real';
GO
