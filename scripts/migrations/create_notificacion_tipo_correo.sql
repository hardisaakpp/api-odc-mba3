-- ============================================================================
-- Migración: Crear tabla notificacion_tipo_correo
-- ============================================================================
-- Descripción: Catálogo administrable de los correos (asuntos) que envía el
--              sistema y a qué tipo_notificacion pertenece cada uno. Antes
--              vivía hardcodeado en el frontend (array estático) y de forma
--              implícita en el código de cada función send_*() en
--              src/utils/email_notifier.py.
--
--              tipo_notificacion aquí NO es una FK a una tabla de tipos: el
--              conjunto de tipos válidos para la interfaz de administración
--              se deriva dinámicamente de los valores distintos presentes en
--              esta misma tabla (activo=1), en vez de un tuple hardcodeado en
--              Python. Esto permite agregar/quitar/renombrar tipos sin
--              deploy, insertando o desactivando filas.
--
--              orden_flujo (NULL por defecto): posición del correo dentro del
--              flujo de pedido "Plantilla Excel -> ODC a SAP" (1..9). Los
--              correos que pertenecen a un proceso distinto (migración
--              automática de despachos/facturas SAP->MBA3, ajena al flujo de
--              pedido) se dejan en NULL: no tienen un lugar lógico en esa
--              secuencia y se listan aparte, sin numerar.
--
--              Esta tabla es solo catálogo/documentación: no determina el
--              envío real de correos (eso sigue en email_notifier.py); sí
--              determina qué tipos puede elegir un admin al agregar un
--              destinatario en notificacion_destinatarios (que no cambia).
-- Fecha: 2026-08-13
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'notificacion_tipo_correo')
BEGIN
    CREATE TABLE notificacion_tipo_correo (
        id INT IDENTITY(1,1) PRIMARY KEY,
        tipo_notificacion NVARCHAR(50) NOT NULL,
        tipo_correo NVARCHAR(200) NOT NULL,
        descripcion NVARCHAR(500) NULL,
        orden_flujo INT NULL,
        activo BIT NOT NULL DEFAULT 1,
        creado_fecha DATETIME2 NOT NULL DEFAULT GETDATE(),
        modificado_fecha DATETIME2 NULL,
        creado_por NVARCHAR(255) NULL,
        modificado_por NVARCHAR(255) NULL
    );

    CREATE INDEX IX_notificacion_tipo_correo_tipo_activo
        ON notificacion_tipo_correo(tipo_notificacion, activo);

    PRINT 'Tabla notificacion_tipo_correo creada correctamente.';
END
ELSE
BEGIN
    PRINT 'Tabla notificacion_tipo_correo ya existe.';
END
GO

-- Compatibilidad: si la tabla ya existía de una corrida previa de esta misma
-- migración (antes de agregar orden_flujo), añade la columna faltante.
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('notificacion_tipo_correo') AND name = 'orden_flujo'
)
BEGIN
    ALTER TABLE notificacion_tipo_correo ADD orden_flujo INT NULL;
    PRINT 'Columna orden_flujo agregada a notificacion_tipo_correo.';
END
GO

-- Compatibilidad: la columna se llamaba "nota"; se renombró a "descripcion"
-- para que el nombre coincida con lo que se muestra en la interfaz.
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('notificacion_tipo_correo') AND name = 'nota'
) AND NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('notificacion_tipo_correo') AND name = 'descripcion'
)
BEGIN
    EXEC sp_rename 'notificacion_tipo_correo.nota', 'descripcion', 'COLUMN';
    PRINT 'Columna nota renombrada a descripcion en notificacion_tipo_correo.';
END
GO

-- Seed: catálogo real extraído de src/utils/email_notifier.py (2026-08-13)
-- orden_flujo 1-9: secuencia real "Plantilla Excel -> ODC a SAP" (ver pedido_estados.py
-- y los call sites de cada send_*() en email_notifier.py). Sin orden_flujo (NULL):
-- correos de la migración automática de despachos/facturas SAP->MBA3, que es un
-- proceso aparte (Celery), no parte del flujo de pedido.
IF NOT EXISTS (SELECT 1 FROM notificacion_tipo_correo)
BEGIN
    INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, orden_flujo, creado_por) VALUES
        ('PRODUCCION_ELRAYO', N'Plantilla Excel Procesada (Pedido Enviado)', N'Se envía a Producción El Rayo cuando MABEL TRADING envía un pedido (clic en Enviar o subida de plantilla)', 1, 'seed_catalogo_2026-08-13'),
        ('OPERACIONES', N'Pedido Descartado', N'Se envía a El Rayo al descartar/eliminar un pedido en Borrador o Nuevo Pedido', 2, 'seed_catalogo_2026-08-13'),
        ('MABEL_TRADING', N'Pedido Eliminado', N'Se envía a MABEL TRADING al eliminar un pedido desde Detalle del Pedido', 3, 'seed_catalogo_2026-08-13'),
        ('OPERACIONES', N'Pedido Cancelado', N'Se envía a El Rayo al cancelar un pedido desde Redistribución, antes de la confirmación final', 4, 'seed_catalogo_2026-08-13'),
        ('OPERACIONES', N'Redistribución Confirmada por MABEL TRADING', N'MABEL TRADING confirma la redistribución final; dispara el envío de la ODC a SAP. Admite exclusión puntual por evento (ej. Nicole)', 5, 'seed_catalogo_2026-08-13'),
        ('OPERACIONES', N'Orden de Compra Generada', N'La ODC ya generada en SAP se envía en PDF al proveedor; cae a OPERACIONES solo si falta su email', 6, 'seed_catalogo_2026-08-13'),
        ('OPERACIONES', N'OC y Solicitudes de Transferencia - Listo para Despacho', N'También llega a MABEL_TRADING', 7, 'seed_catalogo_2026-08-13'),
        ('MABEL_TRADING', N'OC y Solicitudes de Transferencia - Listo para Despacho', N'También llega a OPERACIONES', 8, 'seed_catalogo_2026-08-13'),
        ('TECNICOS', N'Error en OC y Solicitudes de Transferencia', N'Se envía cuando falla el envío de la ODC o solicitud de transferencia a SAP (contraparte de falla del paso 7-8)', 9, 'seed_catalogo_2026-08-13'),
        ('OPERACIONES', N'Nuevos Registros Migrados', N'Se envía tras cada migración automática de despachos/facturas nuevas desde SAP', NULL, 'seed_catalogo_2026-08-13'),
        ('HOMOLOGACIONES', N'Productos NO Homologados Detectados', N'Se envía cuando el cruce de productos detecta SKUs sin homologar', NULL, 'seed_catalogo_2026-08-13'),
        ('TECNICOS', N'Error en Migración Automática', N'Se envía cuando falla la migración automática de despachos/facturas desde SAP', NULL, 'seed_catalogo_2026-08-13'),
        ('TECNICOS', N'Advertencia de Capacidad', N'Se envía por límite de tiempo, alto volumen o alta tasa de fallos en el procesamiento', NULL, 'seed_catalogo_2026-08-13');

    PRINT 'Catálogo de correos inicial insertado (13 filas).';
END
ELSE
BEGIN
    PRINT 'notificacion_tipo_correo ya tiene datos; se omite el seed.';
END
GO

-- Backfill: si esta migración ya se ejecutó antes de agregar las descripciones/orden_flujo
-- de arriba, completa únicamente lo que quedó vacío (idempotente).
UPDATE notificacion_tipo_correo SET descripcion = N'Se envía tras cada migración automática de despachos/facturas nuevas desde SAP', modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Nuevos Registros Migrados' AND descripcion IS NULL;
UPDATE notificacion_tipo_correo SET descripcion = N'Se envía a El Rayo al cancelar un pedido desde Redistribución, antes de la confirmación final', modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Pedido Cancelado' AND descripcion IS NULL;
UPDATE notificacion_tipo_correo SET descripcion = N'Se envía a El Rayo al descartar/eliminar un pedido en Borrador o Nuevo Pedido', modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Pedido Descartado' AND descripcion IS NULL;
UPDATE notificacion_tipo_correo SET descripcion = N'Se envía a MABEL TRADING al eliminar un pedido desde Detalle del Pedido', modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Eliminado' AND descripcion IS NULL;
UPDATE notificacion_tipo_correo SET descripcion = N'Se envía cuando el cruce de productos detecta SKUs sin homologar', modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'HOMOLOGACIONES' AND tipo_correo = N'Productos NO Homologados Detectados' AND descripcion IS NULL;
UPDATE notificacion_tipo_correo SET descripcion = N'Se envía cuando falla la migración automática de despachos/facturas desde SAP', modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'TECNICOS' AND tipo_correo = N'Error en Migración Automática' AND descripcion IS NULL;
UPDATE notificacion_tipo_correo SET descripcion = N'Se envía por límite de tiempo, alto volumen o alta tasa de fallos en el procesamiento', modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'TECNICOS' AND tipo_correo = N'Advertencia de Capacidad' AND descripcion IS NULL;
UPDATE notificacion_tipo_correo SET descripcion = N'Se envía cuando falla el envío de la ODC o solicitud de transferencia a SAP (contraparte de falla del paso 7-8)', modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'TECNICOS' AND tipo_correo = N'Error en OC y Solicitudes de Transferencia' AND descripcion IS NULL;
UPDATE notificacion_tipo_correo SET descripcion = N'Se envía a Producción El Rayo cuando MABEL TRADING envía un pedido (clic en Enviar o subida de plantilla)', modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'PRODUCCION_ELRAYO' AND tipo_correo = N'Plantilla Excel Procesada (Pedido Enviado)' AND descripcion IS NULL;

UPDATE notificacion_tipo_correo SET orden_flujo = 1, modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'PRODUCCION_ELRAYO' AND tipo_correo = N'Plantilla Excel Procesada (Pedido Enviado)' AND orden_flujo IS NULL;
UPDATE notificacion_tipo_correo SET orden_flujo = 2, modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Pedido Descartado' AND orden_flujo IS NULL;
UPDATE notificacion_tipo_correo SET orden_flujo = 3, modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Eliminado' AND orden_flujo IS NULL;
UPDATE notificacion_tipo_correo SET orden_flujo = 4, modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Pedido Cancelado' AND orden_flujo IS NULL;
UPDATE notificacion_tipo_correo SET orden_flujo = 5, modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Redistribución Confirmada por MABEL TRADING' AND orden_flujo IS NULL;
UPDATE notificacion_tipo_correo SET orden_flujo = 6, modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Orden de Compra Generada' AND orden_flujo IS NULL;
UPDATE notificacion_tipo_correo SET orden_flujo = 7, modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'OC y Solicitudes de Transferencia - Listo para Despacho' AND orden_flujo IS NULL;
UPDATE notificacion_tipo_correo SET orden_flujo = 8, modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'OC y Solicitudes de Transferencia - Listo para Despacho' AND orden_flujo IS NULL;
UPDATE notificacion_tipo_correo SET orden_flujo = 9, modificado_por = 'seed_catalogo_2026-08-13', modificado_fecha = GETDATE()
    WHERE tipo_notificacion = 'TECNICOS' AND tipo_correo = N'Error en OC y Solicitudes de Transferencia' AND orden_flujo IS NULL;
GO
