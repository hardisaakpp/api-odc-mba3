# Catálogo de migraciones (generado)

> Generado el 2026-10-01 desde `scripts/migrations_manifest.yaml`: **113 migraciones**, la última es la **669** (`add_orden_compra_listado_indexes`). No editar a mano: ejecutar `python scripts/generar_catalogo_migraciones.py` al agregar una migración.
> Cómo se aplican, el orden y el manejo de errores: ver [DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md). La tabla va **en el orden de ejecución del manifest**, que no siempre coincide con el número de versión (por ejemplo, la 008 se ejecuta antes que la 007 porque esta depende de aquella).

## Resumen por categoría

- **Cambios de estructura (ALTER)** (`alter`): 47
- **Estructura base (tablas y objetos iniciales)** (`base`): 28
- **Configuración** (`config`): 9
- **Datos (inserts/updates de catálogos)** (`data`): 22
- **Estados del pedido** (`estado`): 2
- **Índices** (`index`): 3
- **Reversiones** (`rollback`): 2

## Migraciones en orden de ejecución

### Migración 000.5 — `bootstrap_tablas_sin_script`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/bootstrap_tablas_sin_script.sql`
- **Qué hace:** Crea si no existen despacho_cabecera/detalle, orden_compra_cabecera/detalle y pack_conversion (DECIMAL(19,9): la 002 la define DECIMAL(10,9) e inserta 12.0 -> overflow en BD vacía)

### Migración 001 — `create_despacho_tables`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_producto_staging_tables.sql`
- **Qué hace:** Crear tablas de staging para productos

### Migración 002 — `create_sap_tables`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_sap_tables.sql`
- **Qué hace:** Crear tablas para cache de productos SAP

### Migración 003 — `create_sku_homologacion`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_sku_homologacion_table.sql`
- **Qué hace:** Crear tabla de homologación de SKUs

### Migración 004 — `create_pedido_tables`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_pedido_tables.sql`
- **Qué hace:** Crear tablas principales de pedidos

### Migración 005 — `create_pedido_estado_table`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_pedido_estado_table.sql`
- **Qué hace:** Crear tabla maestra de estados de pedido
- **Notas:** depende de: `004`

### Migración 006 — `create_distribucion_confirmada`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_distribucion_confirmada_table.sql`
- **Qué hace:** Crear tabla para distribución confirmada

### Migración 008 — `create_respuesta_proveedor_tables`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/add_respuesta_proveedor_tables.sql`
- **Qué hace:** Crear tablas para respuesta de proveedor

### Migración 007 — `create_pedido_confirmacion_rayo`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_pedido_confirmacion_rayo_tables.sql`
- **Qué hace:** Crear tablas para confirmación El Rayo
- **Notas:** depende de: `008`

### Migración 009 — `create_pedido_sap_procesamiento`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_pedido_sap_procesamiento_table.sql`
- **Qué hace:** Crear tabla para procesamiento SAP

### Migración 010 — `create_remision_cabecera`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_remision_cabecera_table.sql`
- **Qué hace:** Crear tabla para remisiones

### Migración 011 — `create_sap_integration_logs`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_sap_integration_logs_table.sql`
- **Qué hace:** Crear tabla de logs de integración SAP

### Migración 012 — `create_user_preferences`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_user_preferences_table.sql`
- **Qué hace:** Crear tabla de preferencias de usuario

### Migración 013 — `create_bodega_sap_cache`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/add_bodega_sap_cache_table.sql`
- **Qué hace:** Crear tabla de cache de bodegas SAP

### Migración 014 — `create_homologacion_notificados`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_homologacion_notificados_table.sql`
- **Qué hace:** Crear tabla para notificaciones de homologación

### Migración 015 — `create_pedido_detalle_modificacion_columna`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_pedido_detalle_modificacion_columna_table.sql`
- **Qué hace:** Crear tabla para modificaciones de columnas en detalle

### Migración 016 — `create_notificacion_destinatarios`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_notificacion_destinatarios.sql`
- **Qué hace:** Crear tabla notificacion_destinatarios (configuración de destinatarios de email por tipo de notificación, sustituye listas fijas en .env); faltaba registrada en el manifest aunque ya se usa en código

### Migración 101 — `add_precio_unitario_sap`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_precio_unitario_sap_column.sql`
- **Qué hace:** Agregar columna precio_unitario_sap
- **Notas:** depende de: `004`

### Migración 102 — `add_unidad_sap`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_unidad_sap_column.sql`
- **Qué hace:** Agregar columna unidad_sap

### Migración 103 — `add_grupo_articulos`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_grupo_articulos_column.sql`
- **Qué hace:** Agregar columna grupo_articulos

### Migración 104 — `add_codigo_bodega_orden_compra_cabecera`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_codigo_bodega_orden_compra.sql`
- **Qué hace:** Agregar codigo_bodega a orden_compra_cabecera

### Migración 105 — `add_codigo_bodega_orden_compra_detalle`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_codigo_bodega_orden_compra_detalle.sql`
- **Qué hace:** Agregar codigo_bodega a orden_compra_detalle

### Migración 106 — `add_doc_entry_and_pedido_id`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_doc_entry_and_pedido_id.sql`
- **Qué hace:** Agregar doc_entry y pedido_id a orden_compra_cabecera

### Migración 107 — `add_respuesta_sap_fields`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_respuesta_sap_fields.sql`
- **Qué hace:** Agregar campos de respuesta SAP a orden_compra_cabecera

### Migración 108 — `add_comentario_column`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_comentario_column.sql`
- **Qué hace:** Agregar columna comentario

### Migración 109 — `add_campos_modificados_manual`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_campos_modificados_manual.sql`
- **Qué hace:** Agregar campos para modificaciones manuales

### Migración 110 — `add_fila_origen_pedido`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_fila_origen_pedido.sql`
- **Qué hace:** Agregar fila_origen a pedido_detalle

### Migración 111 — `add_audit_fields_pedido_detalle`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_audit_fields_pedido_detalle.sql`
- **Qué hace:** Agregar campos de auditoría a pedido_detalle

### Migración 112 — `add_bodega_column`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_bodega_column.sql`
- **Qué hace:** Agregar columna bodega

### Migración 113 — `add_es_bodega_column`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/add_es_bodega_column.sql`
- **Qué hace:** Agregar columna es_bodega

### Migración 201 — `add_index_pedido_usuario_fecha`

- **Categoría:** Índices
- **Archivo:** `scripts/add_index_pedido_usuario_fecha.sql`
- **Qué hace:** Agregar índice en pedido por usuario y fecha
- **Notas:** depende de: `004`

### Migración 301 — `migrate_pedido_estado_id`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrate_pedido_estado_id.sql`
- **Qué hace:** Migrar columna estado a estado_id
- **Notas:** depende de: `004`, `005`

### Migración 302 — `migrate_sku_homologacion_full`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrate_sku_homologacion_full.sql`
- **Qué hace:** Migración completa de homologación de SKUs
- **Notas:** depende de: `003`

### Migración 303 — `fix_unidad_conversion_precision`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/fix_unidad_conversion_precision.sql`
- **Qué hace:** Corregir precisión en conversión de unidades

### Migración 401 — `add_estado_pedido`

- **Categoría:** Configuración
- **Archivo:** `scripts/add_estado_pedido.sql`
- **Qué hace:** Agregar nuevos estados de pedido
- **Notas:** depende de: `005`

### Migración 402 — `add_estado_respuesta_pedido`

- **Categoría:** Configuración
- **Archivo:** `scripts/add_estado_respuesta_pedido.sql`
- **Qué hace:** Agregar estados de respuesta de pedido
- **Notas:** depende de: `005`

### Migración 403 — `add_estado_nuevo_pedido`

- **Categoría:** Configuración
- **Archivo:** `scripts/add_estado_nuevo_pedido.sql`
- **Qué hace:** Agregar estado NUEVO_PEDIDO
- **Notas:** depende de: `005`

### Migración 404 — `add_estado_confirmado_enviado`

- **Categoría:** Configuración
- **Archivo:** `scripts/add_estado_confirmado_enviado.sql`
- **Qué hace:** Agregar estado CONFIRMADO_ENVIADO
- **Notas:** depende de: `005`

### Migración 405 — `add_estado_despachar_y_facturar`

- **Categoría:** Configuración
- **Archivo:** `scripts/add_estado_despachar_y_facturar.sql`
- **Qué hace:** Agregar estado DESPACHAR_Y_FACTURAR
- **Notas:** depende de: `005`

### Migración 406 — `add_estado_finalizado`

- **Categoría:** Configuración
- **Archivo:** `scripts/add_estado_finalizado.sql`
- **Qué hace:** Agregar estado FINALIZADO
- **Notas:** depende de: `005`

### Migración 407 — `renombrar_estado_4_a_confirmado`

- **Categoría:** Configuración
- **Archivo:** `scripts/renombrar_estado_4_a_confirmado.sql`
- **Qué hace:** Renombrar estado 4 a CONFIRMADO
- **Notas:** depende de: `005`

### Migración 408 — `renombrar_estado_10_a_confirmado_redistribucion`

- **Categoría:** Configuración
- **Archivo:** `scripts/renombrar_estado_10_a_confirmado_redistribucion.sql`
- **Qué hace:** Renombrar estado 10 a CONFIRMADO_REDISTRIBUCION
- **Notas:** depende de: `005`

### Migración 601 — `remove_bodega_column`

- **Categoría:** Reversiones
- **Archivo:** `scripts/remove_bodega_column.sql`
- **Qué hace:** Remover columna bodega (rollback). skip_by_default retirado 2026-08-28 tras confirmar en dev que la columna está huérfana: 0/1346 filas de pedido_detalle con valor no nulo, sin objetos de BD ni código que la referencien
- **Notas:** **se ejecuta manualmente**, no en la corrida automática

### Migración 602 — `alter_tienda_codigo_size`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/alter_tienda_codigo_size.sql`
- **Qué hace:** Aumentar tamaño de columna tienda.codigo

### Migración 603 — `add_estado_cancelado`

- **Categoría:** Estados del pedido
- **Archivo:** `scripts/migrations/add_estado_cancelado.sql`
- **Qué hace:** Agregar estado CANCELADO (id=19) a pedido_estado
- **Notas:** depende de: `005`

### Migración 604 — `add_estado_cancelado_por_el_rayo`

- **Categoría:** Estados del pedido
- **Archivo:** `scripts/migrations/add_estado_cancelado_por_el_rayo.sql`
- **Qué hace:** Agregar estado CANCELADO POR EL RAYO (id=20) a pedido_estado
- **Notas:** depende de: `603`

### Migración 605 — `create_pedido_original_tables`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_pedido_original_tables.sql`
- **Qué hace:** Crear tablas pedido_original y pedido_detalle_original para snapshot inmutable del pedido al momento del envío
- **Notas:** depende de: `004`

### Migración 605.5 — `create_redistribucion_borrador`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/create_redistribucion_borrador.sql`
- **Qué hace:** Tabla redistribucion_borrador (borradores de ajustes de redistribución por pedido)
- **Notas:** depende de: `004`

### Migración 606 — `audit_completa_pedidos`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/audit_completa_pedidos.sql`
- **Qué hace:** Auditoría completa: valor_anterior/valor_nuevo en modificaciones, campos audit en redistribucion_borrador, tabla pedido_audit_log
- **Notas:** depende de: `004`, `015`

### Migración 607 — `add_orden_linea_pedido_detalle_original`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_orden_linea_pedido_detalle_original.sql`
- **Qué hace:** Agregar orden_linea a pedido_detalle_original para conservar orden de la plantilla en Descargar Pedido Original
- **Notas:** depende de: `605`

### Migración 608 — `alter_distribucion_confirmada_cantidad_decimal`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/alter_distribucion_confirmada_cantidad_decimal.sql`
- **Qué hace:** Cambiar cantidad_solicitada, cantidad_confirmada, cantidad_asignada en distribucion_confirmada e historial de INT a DECIMAL(18,4) para soportar decimales (ej. 0.5) al enviar ODC a SAP
- **Notas:** depende de: `006`

### Migración 609 — `add_orden_linea_pedido_detalle`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_orden_linea_pedido_detalle.sql`
- **Qué hace:** Agregar orden_linea a pedido_detalle para conservar orden de la plantilla en interfaces y Excel
- **Notas:** depende de: `004`

### Migración 610 — `alter_orden_compra_detalle_decimal_4`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/alter_orden_compra_detalle_decimal_4.sql`
- **Qué hace:** orden_compra_detalle: total_linea y precio_unitario a DECIMAL(18,4) (4 decimales)

### Migración 611 — `alter_pedido_sap_procesamiento_detalle_decimal_4`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/alter_pedido_sap_procesamiento_detalle_decimal_4.sql`
- **Qué hace:** pedido_sap_procesamiento_detalle: total_linea_original y total_linea_sap a DECIMAL(18,4) (4 decimales)

### Migración 611.5 — `create_solicitud_transferencia`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_solicitud_transferencia.sql`
- **Qué hace:** Tabla solicitud_transferencia: batch de solicitudes de transferencia (ITR) enviadas a SAP por pedido/OC

### Migración 612 — `create_solicitud_transferencia_detalle`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_solicitud_transferencia_detalle.sql`
- **Qué hace:** Tabla solicitud_transferencia_detalle: Tienda, Nombre, Estado, DocNum por cada solicitud de transferencia (info que se envía por correo)

### Migración 613 — `create_envio_odc_sap`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_envio_odc_sap.sql`
- **Qué hace:** Tabla envio_odc_sap: snapshot de cada Enviar ODC a SAP (OC + solicitudes de transferencia + fecha)

### Migración 614 — `add_estado_error_envio_sap_reintento`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_estado_error_envio_sap_reintento.sql`
- **Qué hace:** pedido_estado id 21: ERROR ENVIO SAP REINTENTO (fallo recuperable al enviar ODC a SAP)
- **Notas:** depende de: `005`

### Migración 615 — `add_job_id_solicitud_transferencia_detalle`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_job_id_solicitud_transferencia_detalle.sql`
- **Qué hace:** solicitud_transferencia_detalle.job_id: permite consultar GET /api/v1/jobs/{jobId} antes de reintentar una ITR encolada (HTTP 202), evita duplicados
- **Notas:** depende de: `612`

### Migración 616 — `add_codigo_barras_producto_sap_cache`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_codigo_barras_producto_sap_cache.sql`
- **Qué hace:** producto_sap_cache.codigo_barras: cachea CodeBars de SAP (OITM) para mostrarlo como dato de referencia en la carga de Excel de pedido (SAP es la fuente de verdad, no se valida contra el Excel)
- **Notas:** depende de: `002`

### Migración 617 — `add_pvp_sap_producto_sap_cache`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_pvp_sap_producto_sap_cache.sql`
- **Qué hace:** producto_sap_cache.pvp_sap: cachea el Price de ITM1 (PriceList=1, Precio Minorista) para validar obligatoriamente el PVP del Excel contra SAP (RN-02)
- **Notas:** depende de: `002`

### Migración 618 — `add_costo_margen_pedido_detalle`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_costo_margen_pedido_detalle.sql`
- **Qué hace:** pedido_detalle/pedido_detalle_original.costo_margen: columna 'Costo' de la plantilla Excel (req. 1.4), únicamente informativa para el cálculo del Margen de Rentabilidad (req. 1.5); distinta de costo_doc_sin_iva (RN-05)
- **Notas:** depende de: `004`, `605`

### Migración 619 — `add_costo_unitario_pedido_detalle`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_costo_unitario_pedido_detalle.sql`
- **Qué hace:** pedido_detalle/pedido_detalle_original.costo_unitario: costo_doc_sin_iva / unidad_conversion (pack_conversion, por el pack ya resuelto SAP/Excel); reemplaza a costo_margen como insumo del Margen de Rentabilidad (req. 1.5)
- **Notas:** depende de: `004`, `605`, `618`

### Migración 620 — `add_estado_produccion_pospuesta`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_estado_produccion_pospuesta.sql`
- **Qué hace:** pedido_estado id 22: PRODUCCION POSPUESTA (el proveedor pospone la producción de las diferencias para decidir con Mabel)
- **Notas:** depende de: `005`

### Migración 621 — `add_estado_confirmado_por_produccion`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_estado_confirmado_por_produccion.sql`
- **Qué hace:** pedido_estado id 23: CONFIRMADO POR PRODUCCION (req. 1.8 - nuevo perfil Producción El Rayo); entre GESTIONAR PEDIDO (3) y CONFIRMADO POR EL RAYO (4)
- **Notas:** depende de: `005`

### Migración 622 — `add_codigo_evento_notificacion_destinatarios`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_codigo_evento_notificacion_destinatarios.sql`
- **Qué hace:** notificacion_destinatarios.codigo_evento: permite excluir un email de un evento puntual (ej. solo 'Redistribución Confirmada') sin sacarlo del resto de notificaciones de su mismo tipo_notificacion
- **Notas:** depende de: `016`

### Migración 623 — `add_exclusion_nvelasquez_redistribucion_confirmada`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/add_exclusion_nvelasquez_redistribucion_confirmada.sql`
- **Qué hace:** Excluye a nvelasquez@elrayo.com.ec del correo REDISTRIBUCION_CONFIRMADA (solicitud de Nicole Velasquez, El Rayo); se mantiene en el resto de notificaciones OPERACIONES
- **Notas:** depende de: `622`

### Migración 624 — `create_notificacion_tipo_correo`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_notificacion_tipo_correo.sql`
- **Qué hace:** Tabla notificacion_tipo_correo: catálogo administrable de correos (asuntos) y su tipo_notificacion; reemplaza el array hardcodeado del frontend. tipo_notificacion ya no depende del tuple TIPOS_NOTIFICACION para la interfaz de administración: se deriva de esta tabla

### Migración 625 — `create_notificacion_persona_correo`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_notificacion_persona_correo.sql`
- **Qué hace:** Tabla notificacion_persona_correo: organización persona-céntrica (nombre+email -> correos de notificacion_tipo_correo). Es la fuente real de destinatarios del envío de correos (ver migración 626 para el traslado de datos desde notificacion_destinatarios)
- **Notas:** depende de: `624`

### Migración 626 — `seed_notificacion_persona_correo_desde_destinatarios`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/seed_notificacion_persona_correo_desde_destinatarios.sql`
- **Qué hace:** Traslada los destinatarios base activos de notificacion_destinatarios (por tipo_notificacion) a notificacion_persona_correo (por correo específico del catálogo), respetando la exclusión de nvelasquez@elrayo.com.ec en Redistribución Confirmada. A partir de esta migración, notificacion_destinatarios queda como tabla histórica: ya no determina el envío real
- **Notas:** depende de: `625`

### Migración 627 — `add_fecha_facturacion_pedido`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_fecha_facturacion_pedido.sql`
- **Qué hace:** Columna fecha_facturacion (DATE NULL) en pedido: nuevo campo en Información del Pedido (req. 1.8), en blanco por defecto, editable solo por produccion-elrayo.view en estado GESTIONAR PEDIDO
- **Nota de revisión:** La descripción dice que `fecha_facturacion` es editable solo por `produccion-elrayo.view` en Gestionar Pedido. Hoy es **exclusiva de `odcsap.view` (EL RAYO)** y solo se edita con el pedido en **Confirmado y Enviado**; habilita el botón "Despachar y Facturar" (verificado en `PedidoDetalleView.vue`, `puedeEditarFechaFacturacion`).

### Migración 628 — `add_correo_pedido_confirmado_produccion`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/add_correo_pedido_confirmado_produccion.sql`
- **Qué hace:** Correo 'Pedido Confirmado por Producción' (OPERACIONES) en el catálogo, req. 1.8: se envía a Administración El Rayo cuando Producción confirma un pedido (botón 'Confirmar Producción'); renumera orden_flujo >= 5 en +1
- **Notas:** depende de: `624`

### Migración 629 — `add_correos_legacy_pedido_a_catalogo`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/add_correos_legacy_pedido_a_catalogo.sql`
- **Qué hace:** Agrega al catálogo los 3 correos de email_notifier_pedido.py (Pedido Confirmado por El Rayo, Pedido Despachar y Facturar, Pedido Finalizado) que quedaron con import roto (get_destinatarios_por_tipo) desde que el envío real pasó a notificacion_persona_correo; corrige el código para usar get_destinatarios_por_correo
- **Notas:** depende de: `624`

### Migración 630 — `drop_notificacion_destinatarios`

- **Categoría:** Reversiones
- **Archivo:** `scripts/migrations/drop_notificacion_destinatarios.sql`
- **Qué hace:** Elimina la tabla notificacion_destinatarios (histórica desde la migración 626); se retira junto con la interfaz de administración 'Destinatarios por Tipo (histórico)' y sus endpoints/repositorio, ya superados por notificacion_persona_correo ('Personas y Correos')
- **Notas:** depende de: `629`

### Migración 631 — `fix_descripcion_correo_pedido_descartado`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/fix_descripcion_correo_pedido_descartado.sql`
- **Qué hace:** Corrige la descripción del correo 'Pedido Descartado' en el catálogo: se acota al único flujo real (descartar en Nuevo Pedido, desde Cargar Plantilla); se retira la mención a 'cancelar desde Redistribución' porque ese flujo usa el correo distinto 'Pedido Cancelado' y no invoca este endpoint desde el frontend. Solo texto, sin cambio de lógica
- **Notas:** depende de: `624`

### Migración 632 — `drop_correo_pedido_eliminado`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/drop_correo_pedido_eliminado.sql`
- **Qué hace:** Retira del catálogo el correo 'Pedido Eliminado' (MABEL_TRADING): correspondía al endpoint DELETE /api/pedidos/{pedido_id}/eliminar, reemplazado desde el commit 'cancelar pedido' (2026-02-12) por POST /api/pedidos/{pedido_id}/cancelar-por-el-rayo (ya no borra, cambia estado y notifica solo en tiempo real, sin correo). Se retira también send_pedido_eliminado_mabel_notification y su vista previa en el código, ya sin ningún endpoint que los invocara
- **Notas:** depende de: `624`

### Migración 633 — `reconciliar_schema_migrations_catalogo_correos`

- **Categoría:** Configuración
- **Archivo:** `scripts/migrations/reconciliar_schema_migrations_catalogo_correos.sql`
- **Qué hace:** Registra en schema_migrations las versiones 624/625/627/628/632 (familia del catálogo de correos) que se aplicaron manualmente sin pasar por migration_runner.py, verificando en cada caso la evidencia real (tabla/columna/fila) antes de marcarlas; no toca datos de negocio. No reconcilia 626/629/630/631: verificado 2026-08-14 que siguen genuinamente pendientes (629 en particular: sin sus filas de catálogo, los 3 correos legacy de pedido no tienen destinatarios y no se están enviando). Sin dependencies a propósito: su función es justamente registrar 624 cuando el bookkeeping todavía no lo tiene, así que no puede depender de que 624 ya esté registrada

### Migración 634 — `add_correo_pedido_cancelado_por_el_rayo`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/add_correo_pedido_cancelado_por_el_rayo.sql`
- **Qué hace:** Correo 'Pedido Cancelado por El Rayo' (MABEL_TRADING) al catálogo, req. 1.8 segunda fase: se envía a MABEL TRADING cuando Administración El Rayo (odcsap.view) cancela un pedido desde Detalle del Pedido (botón 'Cancelar Pedido'), disponible solo en estado Confirmado por Producción (23). Reutiliza el orden_flujo=3 que dejó libre la migración 632 al retirar 'Pedido Eliminado', sin renumerar el resto del catálogo
- **Notas:** depende de: `624`

### Migración 635 — `reordenar_flujo_confirmado_produccion`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/reordenar_flujo_confirmado_produccion.sql`
- **Qué hace:** Reordena orden_flujo para reflejar la secuencia real al llegar a CONFIRMADO POR PRODUCCION (23): Pedido Confirmado por Producción pasa de 5 a 3 (se notifica primero a Administración El Rayo), Pedido Cancelado por El Rayo de 3 a 4 (solo si El Rayo decide cancelar después), Pedido Cancelado (Redistribución) de 4 a 5. orden_flujo >= 6 sin cambios. Solo reordena, sin cambiar descripciones ni lógica de envío
- **Notas:** depende de: `624`, `628`, `634`

### Migración 636 — `insertar_flujo_pedido_confirmado_por_el_rayo`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/insertar_flujo_pedido_confirmado_por_el_rayo.sql`
- **Qué hace:** Inserta 'Pedido Confirmado por El Rayo' (MABEL_TRADING, agregado sin orden_flujo en la migración 629) en orden_flujo=5: es la contraparte de éxito de 'Pedido Cancelado por El Rayo' (4) al llegar a Confirmado por Producción (23) — El Rayo cancela o confirma. Recorre +1 los correos desde Pedido Cancelado (Redistribución) en adelante. Guardado con IF NOT EXISTS para ser seguro de repetir
- **Notas:** depende de: `624`, `629`, `635`

### Migración 637 — `add_produccion_elrayo_a_correo_cancelado_por_el_rayo`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/add_produccion_elrayo_a_correo_cancelado_por_el_rayo.sql`
- **Qué hace:** 'Pedido Cancelado por El Rayo' también notifica a Producción El Rayo (fue quien confirmó el pedido originalmente), no solo a MABEL_TRADING: agrega fila PRODUCCION_ELRAYO en orden_flujo=5 (mismo patrón de doble audiencia que 'OC y ST Despacho'), actualiza la descripción de la fila MABEL_TRADING con la referencia cruzada, y recorre +1 el resto de la secuencia desde 5 en adelante. El código ahora usa _build_unique_recipients(['MABEL_TRADING','PRODUCCION_ELRAYO'], ...) para el envío real
- **Notas:** depende de: `624`, `634`, `636`

### Migración 638 — `consolidar_correo_cancelado_por_el_rayo`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/consolidar_correo_cancelado_por_el_rayo.sql`
- **Qué hace:** Retira la fila PRODUCCION_ELRAYO agregada en la migración 637 para 'Pedido Cancelado por El Rayo': con 'Personas y Correos' (notificacion_persona_correo) ya no hace falta una fila de catálogo por audiencia, cualquier persona se vincula directamente sin importar su equipo. Re-vincula sus destinatarios a la fila MABEL_TRADING (evitando duplicar vínculos) y actualiza su descripción. orden_flujo=5 queda vacante (no se renumera, mismo criterio que 632/634). El código ahora usa un solo get_destinatarios_por_correo('MABEL_TRADING', ...) en vez de _build_unique_recipients de 2 tipos. No aplica a 'OC y ST Despacho' (mismo patrón de 2 filas): queda pendiente de revisión aparte porque su contenido podría diferir por audiencia
- **Notas:** depende de: `637`

### Migración 639 — `add_rol_modificador_pedido_detalle_modificacion_columna`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_rol_modificador_pedido_detalle_modificacion_columna.sql`
- **Qué hace:** Agrega columna rol_modificador (NVARCHAR(30) NULL) a pedido_detalle_modificacion_columna para que el resaltado de celdas TOTAL/COMENTARIO editadas en Detalle del Pedido persista el color según quién hizo la última edición (PRODUCCION_ELRAYO = morado, ODCSAP = ámbar) en vez de según quién esté viendo la pantalla. Se deriva del estado del pedido al guardar (GESTIONAR_PEDIDO / CONFIRMADO_POR_PRODUCCION), no del permiso JWT. Filas existentes quedan en NULL, sin backfill: no se puede reconstruir el estado en que se hizo cada edición histórica
- **Notas:** depende de: `638`
- **Nota de revisión:** La descripción invierte los colores. En el Detalle del Pedido, lo que editó **EL RAYO (`odcsap.view`, rol ODCSAP) se resalta en púrpura** y lo que editó **Producción El Rayo (rol PRODUCCION_ELRAYO) en naranja** (verificado en `PedidoDetalleView.vue`, `claseResaltadoModificado`).

### Migración 640 — `consolidar_correo_oc_listo_despacho`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/consolidar_correo_oc_listo_despacho.sql`
- **Qué hace:** Retira la fila MABEL_TRADING de 'OC y Solicitudes de Transferencia - Listo para Despacho' (mismo patrón de 2 filas que la migración 638 dejó pendiente de revisión): se verificó que el envío real es un solo correo con el mismo asunto y cuerpo para ambas audiencias, sin bifurcar por tipo_notificacion. Re-vincula sus destinatarios a la fila OPERACIONES (evitando duplicar vínculos) y actualiza su descripción. orden_flujo=11 queda vacante (no se renumera). El código ahora usa un solo get_destinatarios_por_correo('OPERACIONES', ...) en vez de _build_unique_recipients de 2 tipos
- **Notas:** depende de: `624`

### Migración 641 — `add_cantidad_solicitada_original_pedido_detalle`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_cantidad_solicitada_original_pedido_detalle.sql`
- **Qué hace:** Req. 1.2 (pedidos parciales): agrega cantidad_solicitada_original (DECIMAL(18,4) NULL) a pedido_detalle, escrita una sola vez en el INSERT (carga de Excel) y nunca tocada por los PATCH de 'Total' de produccion-elrayo.view/odcsap.view. Permite calcular la diferencia entre lo solicitado originalmente y el total vigente sin importar cuántas veces se haya editado. Filas existentes quedan en NULL, sin backfill
- **Notas:** depende de: `004`

### Migración 642 — `add_cantidad_solicitada_original_pedido_detalle_tienda`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_cantidad_solicitada_original_pedido_detalle_tienda.sql`
- **Qué hace:** Req. 1.2 (pedidos parciales): mismo campo que la migración 641 pero a nivel de pedido_detalle_tienda, protegiendo a futuro la cantidad original por tienda de la sobreescritura que sufre 'cantidad' al redistribuir/ajustar por confirmación de proveedor. No es consumida por la detección de diferencia de 1.2 (que opera a nivel agregado de pedido_detalle)
- **Notas:** depende de: `004`

### Migración 643 — `add_pedido_padre_id`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_pedido_padre_id.sql`
- **Qué hace:** Req. 1.2 (pedidos parciales): agrega pedido_padre_id (UNIQUEIDENTIFIER NULL, FK a pedido.pedido_id) a pedido para enlazar el pedido 'hijo' generado con la diferencia (numero_pedido = '<original>.NN') con el pedido original. Se infiere es_parcial con pedido_padre_id IS NOT NULL, sin columna booleana aparte
- **Notas:** depende de: `004`

### Migración 644 — `add_correo_diferencia_pedido`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/add_correo_diferencia_pedido.sql`
- **Qué hace:** Req. 1.2 (pedidos parciales): correo 'Diferencia en Pedido' (MABEL_TRADING) al catálogo, enviado desde POST /api/pedidos/{pedido_id}/confirmar-con-diferencia cuando Administración El Rayo confirma un pedido por debajo de lo solicitado y genera el pedido hijo con la diferencia. orden_flujo=12 (siguiente puesto libre tras el 11 que dejó vacante la migración 640)
- **Notas:** depende de: `624`

### Migración 645 — `add_marca_sap_producto_sap_cache`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_marca_sap_producto_sap_cache.sql`
- **Qué hace:** producto_sap_cache.marca_sap: cachea U_MARCA de SAP (OITM) para usarla como fuente de la columna 'Marca' del detalle de pedido, reemplazando la derivación anterior por bodega/origen_traslado
- **Notas:** depende de: `002`

### Migración 646 — `add_estado_rechazado`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_estado_rechazado.sql`
- **Qué hace:** pedido_estado id 24: RECHAZADO. Botón 'Rechazar' (ex 'Cancelar Pedido Pospuesto') sobre un pedido hijo en PRODUCCION POSPUESTA (22): Mabel Trading rechaza la diferencia pospuesta en vez de esperar a que El Rayo la retome. Terminal, igual que CANCELADO (19)
- **Notas:** depende de: `005`

### Migración 647 — `add_estado_listo_para_redistribucion`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_estado_listo_para_redistribucion.sql`
- **Qué hace:** pedido_estado id 25: LISTO PARA REDISTRIBUCION. Botón 'Aceptar' sobre un pedido hijo en PRODUCCION POSPUESTA (22): Mabel Trading acepta la diferencia pospuesta y la envía directo a la cola de redistribución sin pasar por 'Confirmado por El Rayo' (4). Visible únicamente en el listado de Redistribución
- **Notas:** depende de: `005`

### Migración 648 — `add_marca_tienda`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_marca_tienda.sql`
- **Qué hace:** tienda.marca (ROLAND/REGIONS/DESCUENTON), sincronizada desde sc_maestros.dbo.almacenes_local (u_marca por whs_code=tienda.codigo). Base para resolver a qué bodega (RL-CD/RG-CD/OUT-CD) pertenece cada tienda sin depender solo del prefijo del código. Requerimiento PYTD002 (2 ODC para pedidos que mezclan tiendas ROLAND y REGIONS)
- **Notas:** depende de: `004`

### Migración 649 — `remove_correo_diferencia_pedido`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/remove_correo_diferencia_pedido.sql`
- **Qué hace:** Retira del catálogo el correo 'Diferencia en Pedido' (MABEL_TRADING, migración 644): se simplificó el flujo de confirmación para que los tres casos (Confirmar sin diferencia, Diferencia no será entregada, Confirmar y generar N pedidos con la diferencia) reutilicen un solo correo, 'Pedido Confirmado por El Rayo', enviado una vez para el pedido padre, en vez de un correo distinto por cada hijo generado. Se retira también send_diferencia_pedido_notification, _build_diferencia_pedido_email y su vista previa en el código, ya sin ningún endpoint que los invocara. orden_flujo=12 queda vacante
- **Notas:** depende de: `644`

### Migración 650 — `add_job_id_orden_compra_cabecera`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_job_id_orden_compra_cabecera.sql`
- **Qué hace:** orden_compra_cabecera.job_id: permite consultar GET /api/v1/jobs/{jobId} antes de reintentar una ODC encolada (HTTP 202 al crear la Purchase Order), evita duplicados -- mismo patrón que job_id en solicitud_transferencia_detalle (migración 615), replicado tras el incidente de ODC 24711/24712 duplicadas

### Migración 651 — `add_correo_odc_creacion_error_tecnicos`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/add_correo_odc_creacion_error_tecnicos.sql`
- **Qué hace:** Correo 'Error al crear ODC en SAP (reconciliación automática)' al catálogo (TECNICOS): se envía cuando la reconciliación automática de una ODC ENCOLADA reintenta el envío y SAP lo rechaza con un error real. orden_flujo=NULL (no es parte de la secuencia de un pedido)
- **Notas:** depende de: `624`

### Migración 652 — `create_solicitud_transferencia_bodega`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_solicitud_transferencia_bodega.sql`
- **Qué hace:** Tablas solicitud_transferencia_bodega / _detalle: persiste el resultado de las Inventory Transfer Requests entre bodegas (OCSAPService._enviar_itrs_por_bodega), antes solo devuelto en la respuesta HTTP y nunca guardado en base de datos. Tablas separadas de solicitud_transferencia / _detalle a propósito, para no interferir con la lógica de 'último batch' que usa el reintento automático de tiendas (F4.5)

### Migración 653 — `add_fecha_envio_iniciado_orden_compra_cabecera`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_fecha_envio_iniciado_orden_compra_cabecera.sql`
- **Qué hace:** orden_compra_cabecera.fecha_envio_iniciado: timestamp de inicio del intento de envío a SAP en curso/más reciente, escrito al entrar al nuevo estado ENVIANDO. Defensa en profundidad de UX -- el lock Redis redis_lock_envio_odc ya impide un doble envío real; esto permite a la reconciliación periódica detectar una ENVIANDO estancada (proceso caído a mitad de un envío, sin job_id ni forma segura de verificar contra SAP) y escalarla a ERROR para revisión manual en vez de dejarla colgada indefinidamente. A diferencia de job_id, no se limpia al salir de ENVIANDO

### Migración 654 — `deactivate_estados_obsoletos`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/deactivate_estados_obsoletos.sql`
- **Qué hace:** Marca activo=0 en pedido_estado para 6 estados sembrados desde create_pedido_estado_table.sql sin ningún camino de código vivo que los alcance: 6 CONFIRMADO_PROVEEDOR (único setter, PedidoAjusteService.procesar_confirmacion_proveedor, sin caller), y 7 RECHAZADO_PROVEEDOR/8 EN_AJUSTE_MABEL/11 PROCESADO_SAP/15 EN_PROCESO/16 COMPLETADO (sin constante Python ni referencia de código alguna). No borra filas -- solo desactiva, respetado por el único consumidor del catálogo (get_estados, siempre solo_activos=True). Verifica por id que no haya pedidos reales en ese estado antes de desactivarlo; dev confirmó 0 pedidos en los 6 el 2026-09-03
- **Notas:** depende de: `005`

### Migración 655 — `deactivate_estados_redistribuido_error_datos_maestros`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/deactivate_estados_redistribuido_error_datos_maestros.sql`
- **Qué hace:** Marca activo=0 en pedido_estado para 2 estados con setter real pero código huérfano: 9 REDISTRIBUIDO (solo lo asigna endpoints_core.py, expuesto en rutas que el frontend ya no llama -- usa redistribucion/confirmar y proceso-completo-sap, que van directo a CONFIRMADO REDISTRIBUCION/10), y 14 ERROR_DATOS_MAESTROS (la única clasificación que produce error_type='datos_maestros', stock_transfer_service._validate_stock_before_st, está marcada DEPRECADO PARA ITR y sin caller -- el flujo real usa _validate_itr_minimal). Verificado contra pedido_estado_historial en producción (SCOdcsap, 2026-09-04): 0 transiciones históricas a estos ids en 7717 registros / 6+ meses. Misma mecánica que la migración 654 (no borra filas, verifica 0 pedidos reales por id antes de desactivar)
- **Notas:** depende de: `005`

### Migración 656 — `deactivate_estado_respuesta_proveedor_cargada`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/deactivate_estado_respuesta_proveedor_cargada.sql`
- **Qué hace:** Marca activo=0 en pedido_estado para el id 5 RESPUESTA_PROVEEDOR_CARGADA (mostrado como 'EN_REVISION' en algunos ambientes -- nombre editable): el único setter real (pedido_proveedor_service.importar_respuesta_proveedor) esta wireado a un endpoint backend valido (POST /api/pedidos/{pedido_id}/cargar-respuesta-proveedor), pero ningun componente/vista de scnexus-front llama al servicio correspondiente -- huerfano a nivel de UI, no de ruta. Mismo flujo muerto que 6 CONFIRMADO_PROVEEDOR (654): 'proveedor responde por Excel' fue reemplazado por Redistribucion sin retirar el endpoint. 0 transiciones historicas a este id en produccion (SCOdcsap, 7717 registros / 6+ meses)
- **Notas:** depende de: `005`

### Migración 657 — `reordenar_flujo_pedido_estado`

- **Categoría:** Datos (inserts/updates de catálogos)
- **Archivo:** `scripts/migrations/reordenar_flujo_pedido_estado.sql`
- **Qué hace:** Reasigna pedido_estado.orden (1..16) para los 16 estados activos siguiendo la secuencia real del flujo de negocio en vez del orden de creacion (orden = id historicamente): rama principal (Borrador -> Nuevo Pedido -> Gestionar Pedido -> Confirmado por Produccion -> Confirmado por El Rayo -> Confirmado Redistribucion -> Confirmado Enviado -> Despachar y Facturar -> Finalizado) con las ramas de cancelacion/excepcion (Cancelado por El Rayo, Produccion Pospuesta/Listo para Redistribucion/Rechazado, Cancelado, Error Envio SAP Reintento, Pendiente Logistica) ubicadas junto al punto del flujo donde ocurren. No toca estados inactivos (654/655/656), invisibles en cualquier dropdown
- **Notas:** depende de: `005`, `654`, `655`, `656`

### Migración 658 — `add_agregada_manualmente_distribucion_confirmada`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_agregada_manualmente_distribucion_confirmada.sql`
- **Qué hace:** distribucion_confirmada.agregada_manualmente: marca las filas de tiendas agregadas manualmente en la Vista Excel de Redistribucion (pedidos hijo, fuera del Excel original), para que el frontend pueda resaltar esas columnas de forma permanente (sobrevive recargar la pagina y confirmar la redistribucion)

### Migración 659 — `add_archivo_plantilla`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/add_archivo_plantilla.sql`
- **Qué hace:** Tabla archivo_plantilla (archivos Excel originales de plantillas de pedido)

### Migración 660 — `create_fn_normalizar_codigo`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_fn_normalizar_codigo.sql`
- **Qué hace:** Función dbo.fn_normalizar_codigo (quita . - / _ y espacios, mayúsculas) para comparar códigos de producto

### Migración 661 — `add_audit_fields_complete`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_audit_fields_complete.sql`
- **Qué hace:** Campos de auditoría (creado_por, modificado_por, modificado_fecha, origen, ip_origen) en pedidos, despachos y órdenes de compra

### Migración 662 — `add_audit_fields_origen`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/add_audit_fields_origen.sql`
- **Qué hace:** Campos origen/ip_origen en tablas que no los tenían

### Migración 663 — `add_missing_indexes`

- **Categoría:** Índices
- **Archivo:** `scripts/migrations/add_missing_indexes.sql`
- **Qué hace:** Índices faltantes de consultas frecuentes

### Migración 664 — `create_pedido_estado_historial`

- **Categoría:** Estructura base (tablas y objetos iniciales)
- **Archivo:** `scripts/migrations/create_pedido_estado_historial.sql`
- **Qué hace:** Tabla pedido_estado_historial (bitácora de transiciones de estado de pedidos)
- **Notas:** depende de: `004`, `005`

### Migración 665 — `alter_numero_pedido_mensaje_100`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/alter_numero_pedido_mensaje_100.sql`
- **Qué hace:** Amplía numero_pedido/mensaje/referencia_despacho a NVARCHAR(100) (solo amplía, nunca reduce)

### Migración 666 — `alter_pedido_detalle_tienda_cantidad_decimal`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/alter_pedido_detalle_tienda_cantidad_decimal.sql`
- **Qué hace:** pedido_detalle_tienda.cantidad a DECIMAL(18,4)

### Migración 667 — `alter_pedido_respuesta_detalle_cantidad_decimal`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/alter_pedido_respuesta_detalle_cantidad_decimal.sql`
- **Qué hace:** pedido_respuesta_proveedor_detalle.cantidad_solicitada_total/cantidad_confirmada_total a DECIMAL(18,4)

### Migración 668 — `alter_pedido_mensaje_nvarchar_500`

- **Categoría:** Cambios de estructura (ALTER)
- **Archivo:** `scripts/migrations/alter_pedido_mensaje_nvarchar_500.sql`
- **Qué hace:** pedido.mensaje y pedido_original.mensaje a NVARCHAR(500)

### Migración 669 — `add_orden_compra_listado_indexes`

- **Categoría:** Índices
- **Archivo:** `scripts/migrations/add_orden_compra_listado_indexes.sql`
- **Qué hace:** Índices para el listado de órdenes de compra
