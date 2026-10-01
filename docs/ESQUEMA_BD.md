# Esquema de la base de datos (generado)

> Generado el 2026-10-01 leyendo la base `store_control` (43 tablas). No editar a mano: ver `scripts/generar_esquema_bd.py` para regenerarlo. Los tipos, nulabilidad, valores por defecto y claves vienen del catálogo del motor, no de los scripts de migración.
> Qué hace cada migración y en qué orden se aplican: [CATALOGO_MIGRACIONES.md](CATALOGO_MIGRACIONES.md). Descripción funcional de las tablas de pedidos y sus campos Excel: [ESTRUCTURA_BD_PEDIDOS.md](ESTRUCTURA_BD_PEDIDOS.md).

## Índice de tablas

- `UserPreferences` — 9 columnas
- `archivo_plantilla` — 16 columnas
- `bodega_sap_cache` — 8 columnas
- `despacho_cabecera` — 25 columnas
- `despacho_detalle` — 21 columnas
- `distribucion_confirmada` — 21 columnas
- `distribucion_confirmada_historial` — 16 columnas
- `envio_odc_sap` — 12 columnas
- `notificacion_persona_correo` — 6 columnas
- `notificacion_tipo_correo` — 10 columnas
- `orden_compra_cabecera` — 24 columnas
- `orden_compra_detalle` — 17 columnas
- `pack_conversion` — 6 columnas
- `pedido` — 22 columnas
- `pedido_audit_log` — 13 columnas
- `pedido_confirmacion_rayo` — 8 columnas
- `pedido_confirmacion_rayo_detalle` — 13 columnas
- `pedido_detalle` — 28 columnas
- `pedido_detalle_modificacion_columna` — 8 columnas
- `pedido_detalle_original` — 18 columnas
- `pedido_detalle_tienda` — 13 columnas
- `pedido_estado` — 6 columnas
- `pedido_estado_historial` — 10 columnas
- `pedido_original` — 15 columnas
- `pedido_respuesta_proveedor` — 11 columnas
- `pedido_respuesta_proveedor_detalle` — 12 columnas
- `pedido_respuesta_proveedor_detalle_tienda` — 6 columnas
- `pedido_sap_procesamiento_detalle` — 20 columnas
- `producto_mba3_staging` — 12 columnas
- `producto_sap_cache` — 15 columnas
- `producto_sap_staging` — 12 columnas
- `productos_no_homologados_notificados` — 8 columnas
- `redistribucion_borrador` — 10 columnas
- `remision_cabecera` — 23 columnas
- `sap_integration_logs` — 17 columnas
- `schema_migrations` — 6 columnas
- `sku_homologacion` — 24 columnas
- `solicitud_transferencia` — 12 columnas
- `solicitud_transferencia_bodega` — 11 columnas
- `solicitud_transferencia_bodega_detalle` — 8 columnas
- `solicitud_transferencia_detalle` — 10 columnas
- `sync_control` — 13 columnas
- `tienda` — 12 columnas

## Tablas

### `UserPreferences`

**Clave primaria:** `Id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `Id` | int (identity) | no |  |
| `UserId` | nvarchar(450) | no |  |
| `TableId` | nvarchar(100) | no |  |
| `VisibleColumns` | nvarchar(MAX) | no |  |
| `ColumnOrder` | nvarchar(MAX) | no |  |
| `Filters` | nvarchar(MAX) | sí |  |
| `PageSize` | int | sí |  |
| `UpdatedAt` | datetime2(7) | no | `getutcdate()` |
| `CreatedAt` | datetime2(7) | no | `getutcdate()` |

### `archivo_plantilla`

**Clave primaria:** `archivo_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `archivo_id` | int (identity) | no |  |
| `pedido_id` | uniqueidentifier | no |  |
| `nombre_original` | nvarchar(255) | no |  |
| `storage_path` | nvarchar(500) | no |  |
| `content_type` | nvarchar(100) | sí | `'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'` |
| `tamaño_bytes` | bigint | no |  |
| `subido_por` | nvarchar(100) | no |  |
| `fecha_subida` | datetime2(7) | sí | `getdate()` |
| `activo` | bit | sí | `1` |
| `descargas` | int | sí | `0` |
| `ultima_descarga` | datetime2(7) | sí |  |
| `ultimo_descargador` | nvarchar(100) | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime2(7) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`

### `bodega_sap_cache`

**Clave primaria:** `cache_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `cache_id` | uniqueidentifier | no | `newid()` |
| `whs_code` | varchar(50) | no |  |
| `whs_name` | nvarchar(255) | sí |  |
| `es_bodega` | bit | sí |  |
| `ultima_consulta` | datetime | sí |  |
| `activo` | bit | sí | `1` |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |

### `despacho_cabecera`

**Clave primaria:** `despacho_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `despacho_id` | uniqueidentifier | no |  |
| `empresa` | nvarchar(50) | sí |  |
| `codigo_cliente` | nvarchar(50) | sí |  |
| `fecha_despacho` | datetime | sí |  |
| `codigo_factura` | nvarchar(50) | sí |  |
| `anulada` | bit | no | `0` |
| `numero_pedido_sistema` | nvarchar(50) | sí |  |
| `numero_orden` | nvarchar(50) | sí |  |
| `numero_factura` | nvarchar(50) | sí |  |
| `tipo_documento` | nvarchar(50) | sí |  |
| `orden_compra` | nvarchar(100) | sí |  |
| `orden_compra_cliente` | nvarchar(100) | sí |  |
| `remision_facturada` | bit | no | `0` |
| `num_id_factura_relacionada` | nvarchar(50) | sí |  |
| `fecha_factura` | datetime | sí |  |
| `codigo_despacho` | nvarchar(50) | sí |  |
| `codigo_bodega` | nvarchar(50) | sí |  |
| `confirmado` | bit | no | `0` |
| `creado_por` | nvarchar(450) | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime2(7) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |

### `despacho_detalle`

**Clave primaria:** `detalle_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `detalle_id` | uniqueidentifier | no | `newid()` |
| `despacho_id` | uniqueidentifier | no |  |
| `sku` | nvarchar(100) | sí |  |
| `cantidad_docena_mba3` | decimal(18,4) | sí |  |
| `subtotal_sap` | decimal(18,4) | sí |  |
| `cantidad_pack_sap` | decimal(18,4) | sí |  |
| `unidad_sap` | nvarchar(20) | sí |  |
| `precio_unitario_mba3` | decimal(18,4) | sí |  |
| `descuento` | decimal(18,4) | sí |  |
| `total_linea_mba3` | decimal(18,4) | sí |  |
| `impuesto` | decimal(18,4) | sí |  |
| `nombre_producto` | nvarchar(255) | sí |  |
| `tipo_linea` | nvarchar(50) | sí |  |
| `creado_por` | nvarchar(450) | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime2(7) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |
| `precio_unitario_sap` | decimal(18,4) | sí |  |

**Claves foráneas:** `despacho_id` → `despacho_cabecera.despacho_id`

### `distribucion_confirmada`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `pedido_detalle_id` | uniqueidentifier | no |  |
| `tienda_id` | uniqueidentifier | no |  |
| `cantidad_solicitada` | decimal(18,4) | no |  |
| `cantidad_confirmada` | decimal(18,4) | no |  |
| `cantidad_asignada` | decimal(18,4) | no |  |
| `costo_unitario_original` | decimal(18,4) | sí |  |
| `costo_unitario_ajustado` | decimal(18,4) | sí |  |
| `subtotal_original` | decimal(18,2) | sí |  |
| `subtotal_ajustado` | decimal(18,2) | sí |  |
| `version` | int | no | `1` |
| `estado` | nvarchar(50) | no | `'PENDIENTE'` |
| `creado_por` | nvarchar(450) | sí |  |
| `fecha_creacion` | datetime | sí | `getdate()` |
| `modificado_por` | nvarchar(450) | sí |  |
| `fecha_modificacion` | datetime | sí |  |
| `agregada_manualmente` | bit | no | `0` |
| `origen` | nvarchar(50) | sí |  |
| `confirmado_por` | nvarchar(450) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`; `pedido_detalle_id` → `pedido_detalle.pedido_detalle_id`; `tienda_id` → `tienda.tienda_id`

### `distribucion_confirmada_historial`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | uniqueidentifier | no | `newid()` |
| `distribucion_confirmada_id` | uniqueidentifier | no |  |
| `accion` | nvarchar(50) | no |  |
| `version_anterior` | int | sí |  |
| `version_nueva` | int | sí |  |
| `cantidad_asignada_anterior` | decimal(18,4) | sí |  |
| `costo_unitario_ajustado_anterior` | decimal(18,4) | sí |  |
| `subtotal_ajustado_anterior` | decimal(18,2) | sí |  |
| `estado_anterior` | nvarchar(50) | sí |  |
| `cantidad_asignada_nuevo` | decimal(18,4) | sí |  |
| `costo_unitario_ajustado_nuevo` | decimal(18,4) | sí |  |
| `subtotal_ajustado_nuevo` | decimal(18,2) | sí |  |
| `estado_nuevo` | nvarchar(50) | sí |  |
| `usuario` | nvarchar(450) | sí |  |
| `fecha_cambio` | datetime | sí | `getdate()` |
| `observaciones` | nvarchar(1000) | sí |  |

**Claves foráneas:** `distribucion_confirmada_id` → `distribucion_confirmada.id`

### `envio_odc_sap`

**Clave primaria:** `envio_odc_sap_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `envio_odc_sap_id` | uniqueidentifier | no | `newid()` |
| `oc_id` | uniqueidentifier | no |  |
| `pedido_id` | uniqueidentifier | no |  |
| `numero_oc_sap` | nvarchar(20) | sí |  |
| `doc_entry` | int | sí |  |
| `proveedor` | nvarchar(50) | sí |  |
| `referencia` | nvarchar(100) | sí |  |
| `numero_pedido` | nvarchar(100) | sí |  |
| `solicitud_transferencia_id` | uniqueidentifier | sí |  |
| `total_transferencias` | int | no | `0` |
| `transferencias_creadas` | int | no | `0` |
| `fecha_envio` | datetime2(7) | no | `getdate()` |

**Claves foráneas:** `solicitud_transferencia_id` → `solicitud_transferencia.solicitud_transferencia_id`

### `notificacion_persona_correo`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | int (identity) | no |  |
| `nombre` | nvarchar(255) | no |  |
| `email` | nvarchar(255) | no |  |
| `tipo_correo_id` | int | no |  |
| `creado_fecha` | datetime2(7) | no | `getdate()` |
| `creado_por` | nvarchar(255) | sí |  |

**Claves foráneas:** `tipo_correo_id` → `notificacion_tipo_correo.id`

### `notificacion_tipo_correo`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | int (identity) | no |  |
| `tipo_notificacion` | nvarchar(50) | no |  |
| `tipo_correo` | nvarchar(200) | no |  |
| `descripcion` | nvarchar(500) | sí |  |
| `orden_flujo` | int | sí |  |
| `activo` | bit | no | `1` |
| `creado_fecha` | datetime2(7) | no | `getdate()` |
| `modificado_fecha` | datetime2(7) | sí |  |
| `creado_por` | nvarchar(255) | sí |  |
| `modificado_por` | nvarchar(255) | sí |  |

### `orden_compra_cabecera`

**Clave primaria:** `oc_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `oc_id` | uniqueidentifier | no | `newid()` |
| `despacho_id` | uniqueidentifier | sí |  |
| `proveedor` | nvarchar(100) | sí |  |
| `fecha_generacion` | datetime | sí |  |
| `referencia_despacho` | nvarchar(100) | sí |  |
| `estado` | nvarchar(50) | sí |  |
| `numero_oc_sap` | nvarchar(50) | sí |  |
| `creado_por` | nvarchar(450) | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime2(7) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |
| `created_at` | datetime | sí | `getdate()` |
| `codigo_bodega` | nvarchar(50) | sí |  |
| `doc_entry` | int | sí |  |
| `pedido_id` | uniqueidentifier | sí |  |
| `respuesta_sap` | nvarchar(MAX) | sí |  |
| `fecha_procesado` | datetime | sí |  |
| `error_message` | nvarchar(MAX) | sí |  |
| `error_code` | varchar(50) | sí |  |
| `error_source` | varchar(50) | sí |  |
| `updated_at` | datetime | sí | `getdate()` |
| `job_id` | nvarchar(64) | sí |  |
| `fecha_envio_iniciado` | datetime | sí |  |

### `orden_compra_detalle`

**Clave primaria:** `oc_detalle_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `oc_detalle_id` | uniqueidentifier | no | `newid()` |
| `oc_id` | uniqueidentifier | no |  |
| `sku_sap` | nvarchar(100) | sí |  |
| `cantidad_sap` | decimal(18,4) | sí |  |
| `unidad_sap` | nvarchar(20) | sí |  |
| `referencia_detalle` | nvarchar(100) | sí |  |
| `precio_unitario` | decimal(18,4) | sí |  |
| `total_linea` | decimal(18,4) | sí |  |
| `cantidad_origen` | decimal(18,4) | sí |  |
| `creado_por` | nvarchar(450) | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime2(7) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |
| `codigo_bodega` | nvarchar(50) | sí |  |

**Claves foráneas:** `oc_id` → `orden_compra_cabecera.oc_id`

### `pack_conversion`

**Clave primaria:** `pack_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `pack_id` | varchar(10) | no |  |
| `unidad_conversion` | decimal(19,9) | no |  |
| `descripcion` | varchar(100) | sí |  |
| `activo` | bit | sí | `1` |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |

### `pedido`

**Clave primaria:** `pedido_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `pedido_id` | uniqueidentifier | no | `newid()` |
| `numero_pedido` | nvarchar(100) | no |  |
| `fecha_pedido` | date | sí |  |
| `fecha_entrega` | nvarchar(50) | sí |  |
| `forma_pago` | nvarchar(50) | sí |  |
| `mensaje` | nvarchar(500) | sí |  |
| `proveedor_nombre` | nvarchar(150) | sí |  |
| `comprador_nombre` | nvarchar(150) | sí |  |
| `comprador_codigo` | nvarchar(50) | sí |  |
| `origen_traslado` | nvarchar(50) | sí |  |
| `serie` | nvarchar(50) | sí |  |
| `archivo_nombre` | nvarchar(255) | no |  |
| `creado_por` | nvarchar(450) | sí |  |
| `creado_en` | datetime | sí | `getdate()` |
| `estado` | nvarchar(50) | sí | `'PENDIENTE_CONFIRMACION_PROVEEDOR'` |
| `estado_id` | int | sí | `1` |
| `fecha_facturacion` | date | sí |  |
| `pedido_padre_id` | uniqueidentifier | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime2(7) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |

**Claves foráneas:** `estado_id` → `pedido_estado.id`; `pedido_padre_id` → `pedido.pedido_id`

### `pedido_audit_log`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `entidad` | nvarchar(100) | no |  |
| `entidad_id` | nvarchar(100) | sí |  |
| `accion` | nvarchar(20) | no |  |
| `campo_modificado` | nvarchar(100) | sí |  |
| `valor_anterior` | nvarchar(MAX) | sí |  |
| `valor_nuevo` | nvarchar(MAX) | sí |  |
| `usuario` | nvarchar(450) | no |  |
| `fecha` | datetime2(7) | no | `sysutcdatetime()` |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |
| `comentario` | nvarchar(500) | sí |  |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`

### `pedido_confirmacion_rayo`

**Clave primaria:** `confirmacion_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `confirmacion_id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `respuesta_id` | uniqueidentifier | sí |  |
| `confirmado_por` | nvarchar(450) | no |  |
| `fecha_confirmacion` | datetime | sí | `getdate()` |
| `total_detalles_modificados` | int | sí | `0` |
| `detalles_modificados` | nvarchar(MAX) | sí |  |
| `observaciones_generales` | nvarchar(MAX) | sí |  |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`; `respuesta_id` → `pedido_respuesta_proveedor.respuesta_id`

### `pedido_confirmacion_rayo_detalle`

**Clave primaria:** `confirmacion_detalle_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `confirmacion_detalle_id` | uniqueidentifier | no | `newid()` |
| `confirmacion_id` | uniqueidentifier | no |  |
| `pedido_detalle_id` | uniqueidentifier | no |  |
| `costo_anterior` | decimal(18,2) | sí |  |
| `total_anterior` | decimal(18,2) | sí |  |
| `comentario_anterior` | nvarchar(MAX) | sí |  |
| `costo_nuevo` | decimal(18,2) | sí |  |
| `total_nuevo` | decimal(18,2) | sí |  |
| `comentario_nuevo` | nvarchar(MAX) | sí |  |
| `cambio_costo` | bit | sí | `0` |
| `cambio_total` | bit | sí | `0` |
| `cambio_comentario` | bit | sí | `0` |
| `codigo_producto` | nvarchar(100) | sí |  |

**Claves foráneas:** `confirmacion_id` → `pedido_confirmacion_rayo.confirmacion_id`; `pedido_detalle_id` → `pedido_detalle.pedido_detalle_id`

### `pedido_detalle`

**Clave primaria:** `pedido_detalle_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `pedido_detalle_id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `codigo_interno` | nvarchar(50) | sí |  |
| `descripcion_sap` | nvarchar(255) | sí |  |
| `marca` | nvarchar(50) | sí |  |
| `codigo_barras` | nvarchar(50) | sí |  |
| `pack` | nvarchar(50) | sí |  |
| `costo_doc_sin_iva` | decimal(18,4) | sí |  |
| `descuento_1` | decimal(5,2) | sí |  |
| `pvp` | decimal(18,4) | sí |  |
| `subtotal` | decimal(18,2) | sí |  |
| `total` | decimal(18,2) | sí |  |
| `created_at` | datetime | sí | `getdate()` |
| `comentario` | nvarchar(2000) | sí |  |
| `costo_modificado_manual` | bit | no | `0` |
| `total_modificado_manual` | bit | no | `0` |
| `comentario_modificado_manual` | bit | no | `0` |
| `updated_at` | datetime | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `bodega` | int | sí |  |
| `orden_linea` | int | no | `0` |
| `costo_margen` | decimal(18,4) | sí |  |
| `costo_unitario` | decimal(18,4) | sí |  |
| `cantidad_solicitada_original` | decimal(18,4) | sí |  |
| `creado_por` | nvarchar(450) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |
| `modificado_fecha` | datetime | sí |  |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`

### `pedido_detalle_modificacion_columna`

**Clave primaria:** `modificacion_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `modificacion_id` | uniqueidentifier | no | `newid()` |
| `pedido_detalle_id` | uniqueidentifier | no |  |
| `columna_key` | nvarchar(50) | no |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `fecha_modificacion` | datetime | sí | `getdate()` |
| `valor_anterior` | nvarchar(MAX) | sí |  |
| `valor_nuevo` | nvarchar(MAX) | sí |  |
| `rol_modificador` | nvarchar(30) | sí |  |

**Claves foráneas:** `pedido_detalle_id` → `pedido_detalle.pedido_detalle_id`

### `pedido_detalle_original`

**Clave primaria:** `pedido_detalle_original_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `pedido_detalle_original_id` | uniqueidentifier | no | `newid()` |
| `pedido_original_id` | uniqueidentifier | no |  |
| `pedido_detalle_id` | uniqueidentifier | no |  |
| `codigo_interno` | nvarchar(50) | sí |  |
| `descripcion_sap` | nvarchar(255) | sí |  |
| `marca` | nvarchar(50) | sí |  |
| `codigo_barras` | nvarchar(50) | sí |  |
| `pack` | nvarchar(50) | sí |  |
| `costo_doc_sin_iva` | decimal(18,4) | sí |  |
| `descuento_1` | decimal(5,2) | sí |  |
| `pvp` | decimal(18,4) | sí |  |
| `subtotal` | decimal(18,2) | sí |  |
| `total` | decimal(18,2) | sí |  |
| `comentario` | nvarchar(MAX) | sí |  |
| `copiado_en` | datetime | sí | `getdate()` |
| `orden_linea` | int | no | `0` |
| `costo_margen` | decimal(18,4) | sí |  |
| `costo_unitario` | decimal(18,4) | sí |  |

**Claves foráneas:** `pedido_original_id` → `pedido_original.pedido_original_id`

### `pedido_detalle_tienda`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | uniqueidentifier | no | `newid()` |
| `pedido_detalle_id` | uniqueidentifier | no |  |
| `tienda_id` | uniqueidentifier | no |  |
| `cantidad` | decimal(18,4) | no |  |
| `created_at` | datetime | sí | `getdate()` |
| `fila_origen` | int | sí |  |
| `es_bodega` | bit | no | `0` |
| `cantidad_solicitada_original` | decimal(18,4) | sí |  |
| `creado_por` | nvarchar(450) | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime2(7) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |

**Claves foráneas:** `pedido_detalle_id` → `pedido_detalle.pedido_detalle_id`; `tienda_id` → `tienda.tienda_id`

### `pedido_estado`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | int | no |  |
| `nombre` | nvarchar(100) | no |  |
| `orden` | int | no | `0` |
| `activo` | bit | no | `1` |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |

### `pedido_estado_historial`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `estado_anterior_id` | int | sí |  |
| `estado_nuevo_id` | int | no |  |
| `fecha_cambio` | datetime2(7) | no | `sysutcdatetime()` |
| `usuario_cambio` | nvarchar(450) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |
| `accion` | nvarchar(20) | sí | `'MANUAL'` |
| `comentario` | nvarchar(500) | sí |  |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`; `estado_anterior_id` → `pedido_estado.id`; `estado_nuevo_id` → `pedido_estado.id`

### `pedido_original`

**Clave primaria:** `pedido_original_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `pedido_original_id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `numero_pedido` | nvarchar(100) | no |  |
| `fecha_pedido` | date | sí |  |
| `fecha_entrega` | nvarchar(50) | sí |  |
| `forma_pago` | nvarchar(50) | sí |  |
| `mensaje` | nvarchar(500) | sí |  |
| `proveedor_nombre` | nvarchar(150) | sí |  |
| `comprador_nombre` | nvarchar(150) | sí |  |
| `comprador_codigo` | nvarchar(50) | sí |  |
| `origen_traslado` | nvarchar(50) | sí |  |
| `serie` | nvarchar(50) | sí |  |
| `archivo_nombre` | nvarchar(255) | sí |  |
| `copiado_por` | nvarchar(450) | sí |  |
| `copiado_en` | datetime | sí | `getdate()` |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`

### `pedido_respuesta_proveedor`

**Clave primaria:** `respuesta_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `respuesta_id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `version` | int | no | `1` |
| `estado` | nvarchar(50) | no | `'PENDIENTE_REVISION'` |
| `fecha_respuesta` | datetime | no | `getdate()` |
| `fecha_aprobacion` | datetime | sí |  |
| `creado_por` | nvarchar(450) | sí |  |
| `aprobado_por` | nvarchar(450) | sí |  |
| `observaciones_generales` | nvarchar(1000) | sí |  |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`

### `pedido_respuesta_proveedor_detalle`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | uniqueidentifier | no | `newid()` |
| `respuesta_id` | uniqueidentifier | no |  |
| `pedido_detalle_id` | uniqueidentifier | no |  |
| `cantidad_solicitada_total` | decimal(18,4) | no |  |
| `cantidad_confirmada_total` | decimal(18,4) | no |  |
| `costo_doc_sin_iva_original` | decimal(18,4) | sí |  |
| `costo_doc_sin_iva_ajustado` | decimal(18,4) | sí |  |
| `descuento_1_original` | decimal(5,2) | sí |  |
| `descuento_1_ajustado` | decimal(5,2) | sí |  |
| `observaciones` | nvarchar(500) | sí |  |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |

**Claves foráneas:** `respuesta_id` → `pedido_respuesta_proveedor.respuesta_id`; `pedido_detalle_id` → `pedido_detalle.pedido_detalle_id`

### `pedido_respuesta_proveedor_detalle_tienda`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | uniqueidentifier | no | `newid()` |
| `respuesta_detalle_id` | uniqueidentifier | no |  |
| `pedido_detalle_tienda_id` | uniqueidentifier | no |  |
| `cantidad_confirmada` | int | no |  |
| `observaciones` | nvarchar(500) | sí |  |
| `created_at` | datetime | sí | `getdate()` |

**Claves foráneas:** `respuesta_detalle_id` → `pedido_respuesta_proveedor_detalle.id`; `pedido_detalle_tienda_id` → `pedido_detalle_tienda.id`

### `pedido_sap_procesamiento_detalle`

**Clave primaria:** `procesamiento_detalle_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `procesamiento_detalle_id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `pedido_detalle_id` | uniqueidentifier | no |  |
| `descripcion_producto` | nvarchar(255) | sí |  |
| `item_code_sap` | nvarchar(50) | sí |  |
| `pack_sap` | nvarchar(10) | sí |  |
| `unidad_conversion` | decimal(18,4) | sí |  |
| `unidad_sap` | nvarchar(10) | sí |  |
| `cantidad_original` | decimal(18,4) | sí |  |
| `cantidad_sap` | decimal(18,4) | sí |  |
| `precio_unitario_original` | decimal(18,4) | sí |  |
| `precio_unitario_sap` | decimal(18,4) | sí |  |
| `total_linea_original` | decimal(18,4) | sí |  |
| `total_linea_sap` | decimal(18,4) | sí |  |
| `producto_homologado` | bit | sí | `1` |
| `tipo_problema` | nvarchar(50) | sí |  |
| `item_code_sap_encontrado` | nvarchar(50) | sí |  |
| `mensaje_error` | nvarchar(500) | sí |  |
| `fecha_procesamiento` | datetime | sí | `getdate()` |
| `procesado_por` | nvarchar(450) | sí |  |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`; `pedido_detalle_id` → `pedido_detalle.pedido_detalle_id`

### `producto_mba3_staging`

**Clave primaria:** `staging_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `staging_id` | uniqueidentifier | no | `newid()` |
| `product_id` | varchar(100) | no |  |
| `product_name` | nvarchar(255) | sí |  |
| `corp` | varchar(50) | sí |  |
| `grupo_prenda` | varchar(100) | sí |  |
| `talla` | varchar(50) | sí |  |
| `presentacion` | varchar(100) | sí |  |
| `descontinuado` | bit | no | `0` |
| `product_id_normalizado` | varchar(100) | no |  |
| `ultima_sincronizacion` | datetime | no |  |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |

### `producto_sap_cache`

**Clave primaria:** `cache_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `cache_id` | uniqueidentifier | no | `newid()` |
| `sku` | varchar(50) | no |  |
| `item_code` | varchar(50) | no |  |
| `item_name` | varchar(200) | sí |  |
| `pack_sap` | varchar(10) | sí |  |
| `unidad_conversion` | decimal(10,4) | sí |  |
| `pack_id` | varchar(10) | sí |  |
| `ultima_consulta` | datetime | sí |  |
| `activo` | bit | sí | `1` |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |
| `grupo_articulos` | varchar(100) | sí |  |
| `codigo_barras` | varchar(50) | sí |  |
| `pvp_sap` | decimal(19,6) | sí |  |
| `marca_sap` | nvarchar(50) | sí |  |

### `producto_sap_staging`

**Clave primaria:** `staging_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `staging_id` | uniqueidentifier | no | `newid()` |
| `item_code` | varchar(100) | no |  |
| `item_name` | nvarchar(255) | sí |  |
| `pack_sap` | varchar(10) | sí |  |
| `itms_grp_cod` | int | sí |  |
| `itms_grp_nam` | varchar(100) | sí |  |
| `valid_for` | char(1) | sí |  |
| `item_code_normalizado` | varchar(100) | no |  |
| `activo` | bit | no | `0` |
| `ultima_sincronizacion` | datetime | no |  |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |

### `productos_no_homologados_notificados`

**Clave primaria:** `notificacion_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `notificacion_id` | uniqueidentifier | no | `newid()` |
| `sku` | varchar(50) | no |  |
| `fecha_notificacion` | datetime | no | `getdate()` |
| `veces_notificado` | int | sí | `1` |
| `ultima_notificacion` | datetime | no | `getdate()` |
| `activo` | bit | sí | `1` |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |

### `redistribucion_borrador`

**Clave primaria:** `id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `numero_pedido` | nvarchar(100) | no |  |
| `ajustes_detalle` | nvarchar(MAX) | no |  |
| `creado_por` | nvarchar(450) | sí |  |
| `fecha_guardado` | datetime | sí | `getdate()` |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |

**Claves foráneas:** `pedido_id` → `pedido.pedido_id`

### `remision_cabecera`

**Clave primaria:** `remision_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `remision_id` | uniqueidentifier | no | `newid()` |
| `empresa` | varchar(50) | no |  |
| `codigo_cliente` | varchar(50) | no |  |
| `fecha_remision` | date | no |  |
| `codigo_factura` | varchar(100) | no |  |
| `anulada` | bit | sí | `0` |
| `numero_pedido_sistema` | int | sí |  |
| `numero_orden` | int | sí |  |
| `numero_factura` | int | no |  |
| `tipo_documento` | varchar(10) | no | `'REM'` |
| `orden_compra` | varchar(50) | sí |  |
| `orden_compra_cliente` | varchar(50) | sí |  |
| `remision_facturada` | bit | sí | `0` |
| `factura_impresa` | bit | sí | `0` |
| `confirmado` | bit | sí | `0` |
| `fecha_factura` | date | sí |  |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |
| `creado_por` | nvarchar(450) | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime2(7) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |

### `sap_integration_logs`

**Clave primaria:** `log_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `log_id` | uniqueidentifier | no | `newid()` |
| `proceso_id` | uniqueidentifier | sí |  |
| `timestamp_log` | datetime | no | `getdate()` |
| `nivel_log` | varchar(20) | no |  |
| `mensaje` | nvarchar(MAX) | no |  |
| `usuario` | varchar(100) | sí |  |
| `fuente` | varchar(50) | sí |  |
| `oc_id` | uniqueidentifier | sí |  |
| `referencia_despacho` | nvarchar(100) | sí |  |
| `proveedor` | varchar(100) | sí |  |
| `doc_entry` | int | sí |  |
| `doc_num` | int | sí |  |
| `error_code` | varchar(20) | sí |  |
| `error_source` | varchar(50) | sí |  |
| `success` | bit | sí |  |
| `detalles_adicionales` | nvarchar(MAX) | sí |  |
| `created_at` | datetime | sí | `getdate()` |

### `schema_migrations`

**Clave primaria:** `version`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `version` | varchar(50) | no |  |
| `name` | nvarchar(255) | no |  |
| `applied_at` | datetime | sí | `getdate()` |
| `execution_time_ms` | int | sí |  |
| `checksum` | varchar(64) | sí |  |
| `applied_by` | nvarchar(100) | sí |  |

### `sku_homologacion`

**Clave primaria:** `homologacion_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `homologacion_id` | uniqueidentifier | no | `newid()` |
| `sku_mba3` | varchar(100) | no |  |
| `nombre_producto_mba3` | nvarchar(255) | sí |  |
| `precio_unitario_mba3` | decimal(18,2) | sí |  |
| `cantidad_docena_mba3` | decimal(18,2) | sí |  |
| `total_linea_mba3` | decimal(18,2) | sí |  |
| `sku_sap` | varchar(100) | sí |  |
| `nombre_producto_sap` | nvarchar(255) | sí |  |
| `precio_unitario_sap` | decimal(18,2) | sí |  |
| `cantidad_pack_sap` | decimal(18,2) | sí |  |
| `unidad_sap` | varchar(20) | sí |  |
| `subtotal_sap` | decimal(18,2) | sí |  |
| `estado` | varchar(20) | no | `'PENDIENTE'` |
| `tiene_diferencias` | bit | no | `0` |
| `tiene_datos_sap` | bit | no | `0` |
| `detalle_id` | uniqueidentifier | sí |  |
| `despacho_id` | uniqueidentifier | sí |  |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |
| `ultima_modificacion` | datetime | sí |  |
| `modificado_por` | varchar(100) | sí |  |
| `creado_por` | nvarchar(450) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |

### `solicitud_transferencia`

**Clave primaria:** `solicitud_transferencia_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `solicitud_transferencia_id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | no |  |
| `oc_id` | uniqueidentifier | sí |  |
| `oc_doc_num` | int | sí |  |
| `bodega_origen` | nvarchar(20) | sí |  |
| `total_tiendas` | int | no | `0` |
| `transferencias_creadas` | int | no | `0` |
| `transferencias_errores` | int | no | `0` |
| `success` | bit | no | `0` |
| `resultado_json` | nvarchar(MAX) | sí |  |
| `payloads_sap_json` | nvarchar(MAX) | sí |  |
| `creado_fecha` | datetime2(7) | no | `getdate()` |

### `solicitud_transferencia_bodega`

**Clave primaria:** `solicitud_transferencia_bodega_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `solicitud_transferencia_bodega_id` | uniqueidentifier | no | `newid()` |
| `pedido_id` | uniqueidentifier | sí |  |
| `oc_id` | uniqueidentifier | sí |  |
| `oc_doc_num` | int | sí |  |
| `bodega_origen` | nvarchar(20) | sí |  |
| `total_bodegas` | int | no | `0` |
| `transferencias_creadas` | int | no | `0` |
| `transferencias_errores` | int | no | `0` |
| `success` | bit | no | `0` |
| `resultado_json` | nvarchar(MAX) | sí |  |
| `creado_fecha` | datetime2(7) | no | `getdate()` |

### `solicitud_transferencia_bodega_detalle`

**Clave primaria:** `solicitud_transferencia_bodega_detalle_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `solicitud_transferencia_bodega_detalle_id` | uniqueidentifier | no | `newid()` |
| `solicitud_transferencia_bodega_id` | uniqueidentifier | no |  |
| `bodega_codigo` | nvarchar(20) | no |  |
| `estado` | nvarchar(20) | no |  |
| `doc_num` | int | sí |  |
| `doc_entry` | int | sí |  |
| `error_mensaje` | nvarchar(500) | sí |  |
| `creado_fecha` | datetime2(7) | no | `getdate()` |

**Claves foráneas:** `solicitud_transferencia_bodega_id` → `solicitud_transferencia_bodega.solicitud_transferencia_bodega_id`

### `solicitud_transferencia_detalle`

**Clave primaria:** `solicitud_transferencia_detalle_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `solicitud_transferencia_detalle_id` | uniqueidentifier | no | `newid()` |
| `solicitud_transferencia_id` | uniqueidentifier | no |  |
| `tienda_codigo` | nvarchar(20) | no |  |
| `tienda_nombre` | nvarchar(255) | sí |  |
| `estado` | nvarchar(20) | no |  |
| `doc_num` | int | sí |  |
| `doc_entry` | int | sí |  |
| `error_mensaje` | nvarchar(500) | sí |  |
| `creado_fecha` | datetime2(7) | no | `getdate()` |
| `job_id` | nvarchar(64) | sí |  |

**Claves foráneas:** `solicitud_transferencia_id` → `solicitud_transferencia.solicitud_transferencia_id`

### `sync_control`

**Clave primaria:** `sync_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `sync_id` | uniqueidentifier | no | `newid()` |
| `entidad` | varchar(50) | no |  |
| `estado` | varchar(20) | no |  |
| `ultima_sync_exitosa` | datetime | sí |  |
| `registros_sincronizados` | int | sí | `0` |
| `registros_nuevos` | int | sí | `0` |
| `registros_actualizados` | int | sí | `0` |
| `registros_eliminados` | int | sí | `0` |
| `mensaje_error` | nvarchar(MAX) | sí |  |
| `stack_trace` | nvarchar(MAX) | sí |  |
| `duracion_segundos` | int | sí |  |
| `iniciado_por` | varchar(100) | sí |  |
| `created_at` | datetime | sí | `getdate()` |

### `tienda`

**Clave primaria:** `tienda_id`

| Columna | Tipo | Nulo | Por defecto |
|---|---|:--:|---|
| `tienda_id` | uniqueidentifier | no | `newid()` |
| `codigo` | nvarchar(100) | no |  |
| `nombre` | nvarchar(150) | sí |  |
| `activa` | bit | sí | `1` |
| `created_at` | datetime | sí | `getdate()` |
| `updated_at` | datetime | sí | `getdate()` |
| `marca` | nvarchar(20) | sí |  |
| `creado_por` | nvarchar(450) | sí |  |
| `modificado_por` | nvarchar(450) | sí |  |
| `modificado_fecha` | datetime2(7) | sí |  |
| `origen` | nvarchar(50) | sí |  |
| `ip_origen` | nvarchar(45) | sí |  |
