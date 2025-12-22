-- ============================================================================
-- Script SQL para Validar Homologación de Productos
-- ============================================================================
-- Este script identifica productos de MBA3 que NO están homologados en SAP
-- 
-- Un producto NO está homologado si:
-- 1. Existe en despacho_detalle (viene de MBA3)
-- 2. NO existe en producto_sap_cache (nunca se consultó en SAP o no existe)
--
-- Uso: Ejecutar este script para obtener un reporte de productos que requieren
--      homologación en SAP
-- ============================================================================

-- ============================================================================
-- VISTA 1: Productos NO Homologados (Resumen General)
-- ============================================================================
-- Muestra todos los productos de MBA3 que no están en el cache de SAP
-- Ordenados por frecuencia de uso (más usados primero)
-- ============================================================================
PRINT '============================================================================';
PRINT 'REPORTE DE PRODUCTOS NO HOMOLOGADOS';
PRINT '============================================================================';
PRINT '';

SELECT 
    dd.sku AS 'SKU',
    dd.nombre_producto AS 'Nombre Producto',
    COUNT(*) AS 'Veces Usado en Facturas',
    SUM(dd.cantidad_docena_mba3) AS 'Total Docenas',
    SUM(dd.total_linea_mba3) AS 'Total Valor (MBA3)',
    MIN(dc.fecha_despacho) AS 'Primera Aparición',
    MAX(dc.fecha_despacho) AS 'Última Aparición',
    CASE 
        WHEN psc.sku IS NULL THEN 'NO HOMOLOGADO'
        ELSE 'HOMOLOGADO'
    END AS 'Estado'
FROM despacho_detalle dd
INNER JOIN despacho_cabecera dc ON dd.despacho_id = dc.despacho_id
LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
WHERE dd.sku IS NOT NULL 
  AND dd.sku != ''
  AND psc.sku IS NULL  -- NO está en cache SAP (no homologado)
GROUP BY dd.sku, dd.nombre_producto
ORDER BY COUNT(*) DESC, dd.sku;
GO

-- ============================================================================
-- VISTA 2: Estadísticas Generales
-- ============================================================================
-- Muestra resumen de productos homologados vs no homologados
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT 'ESTADÍSTICAS GENERALES';
PRINT '============================================================================';
PRINT '';

SELECT 
    'Total Productos Únicos en MBA3' AS 'Métrica',
    COUNT(DISTINCT dd.sku) AS 'Cantidad'
FROM despacho_detalle dd
WHERE dd.sku IS NOT NULL AND dd.sku != ''

UNION ALL

SELECT 
    'Productos Homologados (en cache SAP)' AS 'Métrica',
    COUNT(DISTINCT psc.sku) AS 'Cantidad'
FROM producto_sap_cache psc
WHERE psc.activo = 1

UNION ALL

SELECT 
    'Productos NO Homologados' AS 'Métrica',
    COUNT(DISTINCT dd.sku) AS 'Cantidad'
FROM despacho_detalle dd
LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
WHERE dd.sku IS NOT NULL 
  AND dd.sku != ''
  AND psc.sku IS NULL

UNION ALL

SELECT 
    'Porcentaje de Homologación' AS 'Métrica',
    CAST(
        (COUNT(DISTINCT CASE WHEN psc.sku IS NOT NULL THEN dd.sku END) * 100.0 / 
         NULLIF(COUNT(DISTINCT dd.sku), 0)) AS DECIMAL(5, 2)
    ) AS 'Cantidad'
FROM despacho_detalle dd
LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
WHERE dd.sku IS NOT NULL AND dd.sku != '';
GO

-- ============================================================================
-- VISTA 3: Productos NO Homologados por Empresa
-- ============================================================================
-- Agrupa productos no homologados por empresa (si aplica)
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT 'PRODUCTOS NO HOMOLOGADOS POR EMPRESA';
PRINT '============================================================================';
PRINT '';

SELECT 
    dc.empresa AS 'Empresa',
    dd.sku AS 'SKU',
    dd.nombre_producto AS 'Nombre Producto',
    COUNT(*) AS 'Veces Usado',
    SUM(dd.cantidad_docena_mba3) AS 'Total Docenas'
FROM despacho_detalle dd
INNER JOIN despacho_cabecera dc ON dd.despacho_id = dc.despacho_id
LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
WHERE dd.sku IS NOT NULL 
  AND dd.sku != ''
  AND psc.sku IS NULL
GROUP BY dc.empresa, dd.sku, dd.nombre_producto
ORDER BY dc.empresa, COUNT(*) DESC;
GO

-- ============================================================================
-- VISTA 4: Productos NO Homologados - Detalle por Factura
-- ============================================================================
-- Muestra en qué facturas específicas aparecen los productos no homologados
-- Útil para identificar el impacto en el negocio
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT 'DETALLE: Facturas con Productos NO Homologados';
PRINT '============================================================================';
PRINT '';

SELECT TOP 100  -- Limitar a 100 registros para no saturar
    dc.codigo_factura AS 'Código Factura',
    dc.empresa AS 'Empresa',
    dc.fecha_despacho AS 'Fecha',
    dd.sku AS 'SKU',
    dd.nombre_producto AS 'Nombre Producto',
    dd.cantidad_docena_mba3 AS 'Cantidad (Docenas)',
    dd.total_linea_mba3 AS 'Total Línea'
FROM despacho_detalle dd
INNER JOIN despacho_cabecera dc ON dd.despacho_id = dc.despacho_id
LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
WHERE dd.sku IS NOT NULL 
  AND dd.sku != ''
  AND psc.sku IS NULL
ORDER BY dc.fecha_despacho DESC, dc.codigo_factura;
GO

-- ============================================================================
-- VISTA 5: Lista Simple de SKUs NO Homologados
-- ============================================================================
-- Lista simple de SKUs para copiar/pegar o usar en otros procesos
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT 'LISTA SIMPLE DE SKUs NO HOMOLOGADOS';
PRINT '============================================================================';
PRINT '';

SELECT DISTINCT
    dd.sku AS 'SKU'
FROM despacho_detalle dd
LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
WHERE dd.sku IS NOT NULL 
  AND dd.sku != ''
  AND psc.sku IS NULL
ORDER BY dd.sku;
GO

-- ============================================================================
-- VISTA 6: Productos con Conversión SAP Incompleta
-- ============================================================================
-- Identifica productos que están en cache pero no tienen conversión completa
-- (tienen pack_sap pero no unidad_conversion, o viceversa)
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT 'PRODUCTOS CON CONVERSIÓN SAP INCOMPLETA';
PRINT '============================================================================';
PRINT '';

SELECT 
    psc.sku AS 'SKU',
    psc.item_name AS 'Nombre en SAP',
    psc.pack_sap AS 'Pack SAP',
    psc.unidad_conversion AS 'Unidad Conversión',
    psc.grupo_articulos AS 'Grupo Artículos',
    psc.ultima_consulta AS 'Última Consulta',
    CASE 
        WHEN psc.pack_sap IS NULL THEN 'Sin Pack SAP'
        WHEN psc.unidad_conversion IS NULL THEN 'Sin Unidad Conversión'
        WHEN psc.grupo_articulos IS NULL THEN 'Sin Grupo Artículos'
        ELSE 'Otro'
    END AS 'Problema'
FROM producto_sap_cache psc
WHERE psc.activo = 1
  AND (
    psc.pack_sap IS NULL 
    OR psc.unidad_conversion IS NULL
    OR psc.grupo_articulos IS NULL
  )
ORDER BY psc.sku;
GO

PRINT '';
PRINT '============================================================================';
PRINT 'REPORTE COMPLETADO';
PRINT '============================================================================';
PRINT '';
PRINT 'NOTAS:';
PRINT '- Los productos NO HOMOLOGADOS son aquellos que existen en despacho_detalle';
PRINT '  pero NO están en producto_sap_cache (nunca consultados en SAP o no existen)';
PRINT '- Para homologar un producto, debe crearse en SAP con el mismo ItemCode (SKU)';
PRINT '- Después de crear en SAP, el sistema lo detectará automáticamente en la';
PRINT '  próxima consulta o migración';
PRINT '';
GO


















