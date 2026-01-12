# Implementación: Procesamiento SAP de Pedidos

**Fecha:** 2026-01-21  
**Estado:** ✅ Completado

## 📋 Resumen

Se implementó la funcionalidad para procesar pedidos con SAP cuando MT (MABEL TRADING) confirma la redistribución. Esta funcionalidad es similar a MIGRAR pero para pedidos (sin vínculo con MBA3).

## 🎯 Objetivo

Cuando MT hace clic en "Confirmar Redistribución", el sistema debe:
1. ✅ Consultar información SAP para cada producto (ItemCode, Pack, conversiones)
2. ✅ Calcular cantidades y precios en unidades SAP
3. ✅ Detectar productos no homologados
4. ✅ Guardar información procesada en base de datos
5. ✅ Notificar productos no homologados por email

## 📁 Archivos Creados

### 1. Script SQL
- **`scripts/create_pedido_sap_procesamiento_table.sql`**
  - Crea tabla `pedido_sap_procesamiento_detalle` para almacenar información SAP procesada
  - **NOTA:** La cabecera se reutiliza de la tabla `pedido` (no se modifica)
  - Campos: item_code_sap, pack_sap, unidad_conversion, cantidades convertidas, precios convertidos, estado de homologación

### 2. Repositorio
- **`src/database/repositories/pedido_sap_procesamiento_repository.py`**
  - Operaciones CRUD para `pedido_sap_procesamiento_detalle`
  - Métodos: `insert_procesamiento`, `update_procesamiento`, `upsert_procesamiento`, `get_procesamientos_por_pedido`, `get_productos_no_homologados_por_pedido`

### 3. Servicio
- **`src/database/services/pedido_sap_service.py`**
  - Función principal: `procesar_pedido_con_sap()`
  - Similar a `factura_service.py` pero para pedidos
  - Obtiene productos desde `pedido_detalle`
  - Suma cantidades desde `distribucion_confirmada`
  - Consulta SAP usando `SAPService`
  - Calcula conversiones de cantidades y precios
  - Detecta productos no homologados usando `HomologacionService`
  - Guarda en `pedido_sap_procesamiento_detalle`
  - **NOTA:** La cabecera se reutiliza de `pedido` (no se crea tabla separada)

## 🔧 Archivos Modificados

### 1. Endpoint
- **`src/endpoints/plantillas.py`**
  - Modificado: `confirmar_redistribucion()`
  - Después de confirmar la redistribución, ejecuta `procesar_pedido_con_sap()`
  - Notifica productos no homologados por email (similar a `despachos_migrar.py`)

## 🗄️ Estructura de Base de Datos

### Cabecera: Reutiliza `pedido`

La cabecera del pedido se reutiliza de la tabla `pedido` existente. **No se crea tabla separada** porque la información de cabecera no se modifica durante el procesamiento SAP.

### Tabla: `pedido_sap_procesamiento_detalle`

```sql
CREATE TABLE pedido_sap_procesamiento_detalle (
    procesamiento_detalle_id UNIQUEIDENTIFIER PRIMARY KEY,
    pedido_id UNIQUEIDENTIFIER NOT NULL,
    pedido_detalle_id UNIQUEIDENTIFIER NOT NULL,
    
    -- Información SAP
    item_code_sap NVARCHAR(50) NULL,
    pack_sap NVARCHAR(10) NULL,
    unidad_conversion DECIMAL(18, 4) NULL,
    unidad_sap NVARCHAR(10) NULL,
    
    -- Cantidades convertidas
    cantidad_original DECIMAL(18, 4) NULL,
    cantidad_sap DECIMAL(18, 4) NULL,
    
    -- Precios convertidos
    precio_unitario_original DECIMAL(18, 4) NULL,
    precio_unitario_sap DECIMAL(18, 4) NULL,
    total_linea_original DECIMAL(18, 2) NULL,
    total_linea_sap DECIMAL(18, 2) NULL,
    
    -- Estado de homologación
    producto_homologado BIT DEFAULT 1,
    tipo_problema NVARCHAR(50) NULL,
    item_code_sap_encontrado NVARCHAR(50) NULL,
    mensaje_error NVARCHAR(500) NULL,
    
    -- Auditoría
    fecha_procesamiento DATETIME DEFAULT GETDATE(),
    procesado_por NVARCHAR(450) NULL,
    
    FOREIGN KEY (pedido_id) REFERENCES pedido(pedido_id),
    FOREIGN KEY (pedido_detalle_id) REFERENCES pedido_detalle(pedido_detalle_id),
    UNIQUE (pedido_detalle_id)
);
```

**Nota importante:** 
- La cabecera se reutiliza de `pedido` (no se modifica)
- Solo se crea esta tabla de detalle para almacenar información SAP procesada

## 🔄 Flujo de Ejecución

```
Usuario MT hace clic en "Confirmar Redistribución"
    ↓
[Endpoint: confirmar_redistribucion]
    ├─→ Confirma redistribución (código existente)
    ├─→ Actualiza estado del pedido a 'REDISTRIBUIDO'
    └─→ NUEVO: procesar_pedido_con_sap()
        ├─→ Obtiene productos de pedido_detalle
        ├─→ Para cada producto:
        │   ├─→ Suma cantidades de distribucion_confirmada (todas las tiendas)
        │   ├─→ Consulta SAP (SAPService.get_or_fetch_producto_info)
        │   ├─→ Calcula conversiones (cantidades, precios)
        │   ├─→ Detecta no homologados (HomologacionService)
        │   └─→ Guarda en pedido_sap_procesamiento_detalle (UPSERT)
        │       (La cabecera se reutiliza de pedido, no se modifica)
        └─→ Notifica productos no homologados (email)
    ↓
Respuesta con confirmación exitosa
```

## 📊 Características

### ✅ Ventajas de la Implementación

1. **Separación de responsabilidades**: No modifica tablas existentes (`pedido_detalle` mantiene datos del Excel)
2. **Reprocesable**: Se puede volver a procesar sin afectar datos originales
3. **Trazabilidad**: Fecha y usuario del procesamiento
4. **Consistente**: Misma lógica que MIGRAR pero para pedidos
5. **No afecta flujo legacy**: MBA3/despachos sigue igual

### 🔍 Detección de Productos No Homologados

El sistema detecta tres tipos de problemas:
- **`no_existe`**: Producto no encontrado en SAP
- **`mismatch`**: SKU de pedido no coincide con ItemCode de SAP
- **`error`**: Error al consultar SAP

### 📧 Notificaciones

- Se envían emails solo para productos **nuevos** no homologados
- Filtra productos ya notificados anteriormente
- Usa la misma lógica que `despachos_migrar.py`

## 🚀 Pasos para Usar

### 1. Ejecutar Script SQL

```sql
-- Ejecutar en SQL Server
EXEC scripts/create_pedido_sap_procesamiento_table.sql
```

### 2. Flujo Normal

1. MABEL TRADING sube Excel → se guarda en `pedido` y `pedido_detalle`
2. EL RAYO modifica costos/comentarios → se guarda en `pedido_confirmacion_rayo`
3. MT hace redistribución → se guarda en `distribucion_confirmada`
4. MT hace clic en "Confirmar Redistribución" → **se ejecuta procesamiento SAP automáticamente**

### 3. Consultar Resultados

```sql
-- Ver procesamientos SAP de un pedido
SELECT * FROM pedido_sap_procesamiento_detalle
WHERE pedido_id = '...'
ORDER BY fecha_procesamiento DESC;

-- Ver productos no homologados
SELECT * FROM pedido_sap_procesamiento_detalle
WHERE pedido_id = '...' AND producto_homologado = 0;
```

## 🔗 Dependencias

- **SAPService**: Consulta información de productos en SAP
- **HomologacionService**: Detecta productos no homologados
- **DistribucionConfirmadaRepository**: Obtiene cantidades redistribuidas
- **PedidoRepository**: Obtiene información del pedido

## ⚠️ Notas Importantes

1. **No modifica tablas originales**: `pedido` y `pedido_detalle` mantienen datos del Excel intactos
2. **Cabecera reutilizada**: La cabecera se reutiliza de `pedido` (no se crea tabla separada)
3. **UPSERT**: Si se reprocesa, actualiza el registro existente en `pedido_sap_procesamiento_detalle` (no duplica)
4. **Manejo de errores**: Si falla el procesamiento SAP, la redistribución sigue confirmada (solo se loguea el error)
5. **Cantidades**: Se suman desde `distribucion_confirmada` (cantidad_asignada_total)
6. **Precios**: Se obtienen desde `pedido_detalle` (costo_doc_sin_iva)

## 📚 Documentación Relacionada

- [Flujo Completo de Despachos](FLUJO_COMPLETO.md) - Referencia para lógica similar
- [Estructura BD Pedidos](ESTRUCTURA_BD_PEDIDOS.md) - Estructura de tablas de pedidos
- [Integración SAP](INTEGRACION_SAP.md) - Configuración e integración con SAP
