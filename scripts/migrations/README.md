# Migraciones de base de datos

Ejecutar en orden si aplica a tu instalación.

## alter_pedido_detalle_tienda_cantidad_decimal.sql

**Cuándo:** Si la tabla `pedido_detalle_tienda` fue creada con la columna `cantidad` como **INT**.

**Qué hace:** Cambia `cantidad` a **DECIMAL(18,4)** para permitir valores como 0.5, 1.25, etc.

**Por qué:** Sin esta migración, las cantidades decimales del Excel (p. ej. 0.5 en columnas de tiendas) se truncan a entero al insertar y se pierden. Tras aplicarla, la aplicación guarda y muestra correctamente cantidades decimales por tienda.

**Cómo ejecutar:** En SQL Server Management Studio o con `sqlcmd`, ejecutar el script sobre la base de datos del proyecto.
