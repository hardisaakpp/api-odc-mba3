# 🔧 Migración a SAP Service Layer :50001

**Fecha:** 22 de enero de 2026  
**Objetivo:** Actualizar backend para usar Service Layer en `:50001` con endpoints correctos

---

## ✅ CAMBIOS IMPLEMENTADOS

### 1️⃣ Configuración Base (.env)

**Archivo:** `.env`

```env
# ⚠️ URL base corregida (sin /Login)
SAP_SERVICE_LAYER_URL=http://10.128.240.4:50001/b1s/v1
SAP_SERVICE_LAYER_USERNAME=MZ-SIS-05
SAP_SERVICE_LAYER_PASSWORD=***REMOVED***
SAP_SERVICE_LAYER_DATABASE=TEST_MABEL
ENABLE_SAP_SERVICE_LAYER=true
```

**Cambio crítico:** Eliminado `/Login` del URL base (se agrega automáticamente en el cliente)

---

### 2️⃣ Cliente SAP Service Layer

**Archivo:** `src/database/clients/sap_service_layer_client.py`

#### Cambio Principal: Endpoint de Transferencias

**❌ ANTES (incorrecto):**
```python
url = f"{self.base_url}/StockTransfers"
```

**✅ AHORA (correcto):**
```python
url = f"{self.base_url}/InventoryTransferRequests"
```

**Razón:** SAP Service Layer usa `InventoryTransferRequests` para solicitudes de traslado, no `StockTransfers`.

#### Logging Mejorado

- Mensajes de log actualizados para reflejar "Inventory Transfer Request"
- Errores detallados con código SAP y mensaje completo

---

### 3️⃣ Mapper de Órdenes de Compra

**Archivo:** `src/database/mappers/sap_oc_mapper.py`

#### Cambio Principal: WarehouseCode por Línea

**❌ ANTES (incorrecto):**
```python
# Solo usaba warehouse_code de parámetro (cabecera)
if warehouse_code:
    line["WarehouseCode"] = warehouse_code
```

**✅ AHORA (correcto):**
```python
# Prioridad 1: warehouse_code del detalle
# Prioridad 2: warehouse_code de parámetro (fallback)
detalle_warehouse = detalle.get("codigo_bodega") or detalle.get("warehouse_code")
warehouse_final = detalle_warehouse or warehouse_code

if warehouse_final:
    line["WarehouseCode"] = warehouse_final
    logger.debug(f"   Línea {idx}: ItemCode={line['ItemCode']}, WarehouseCode={warehouse_final}")
else:
    logger.warning(f"⚠️ Línea {idx} sin código de bodega: ItemCode={line.get('ItemCode')}")
```

**Razón:** SAP requiere que cada línea tenga su propio `WarehouseCode`. Una OC puede tener líneas para diferentes bodegas.

---

### 4️⃣ Mapper de Stock Transfer

**Archivo:** `src/database/mappers/sap_stock_transfer_mapper.py`

#### Cambios Principales

1. **Agregado `DueDate`** (requerido por `InventoryTransferRequests`):
```python
stock_transfer = {
    "DocDate": fecha,
    "DueDate": fecha,  # Fecha de vencimiento
    "FromWarehouse": bodega_origen_upper,
    "ToWarehouse": tienda_destino,
    "Comments": comentario_base,
    "StockTransferLines": stock_transfer_lines
}
```

2. **Eliminado `LineNum`** (no requerido):
```python
# ⚠️ ANTES:
line = {
    "LineNum": idx,  # ❌ No necesario
    "ItemCode": item_code,
    "Quantity": float(cantidad)
}

# ✅ AHORA:
line = {
    "ItemCode": item_code,
    "Quantity": float(cantidad)
}
```

---

## 📋 ESTRUCTURA DE DATOS SAP

### Purchase Order (OC)

```json
{
  "CardCode": "P123456",
  "DocDate": "2026-01-22",
  "DocDueDate": "2026-01-22",
  "TaxDate": "2026-01-22",
  "Comments": "Ref: P-12.48",
  "U_ORIGEN": "C",
  "U_USUARIO": "user123",
  "U_FECHA": "2026-01-22",
  "U_LOTE": "pedido-uuid",
  "DocumentLines": [
    {
      "ItemCode": "R5082-15.1012",
      "Quantity": 120.0,
      "UnitPrice": 1.50,
      "LineTotal": 180.0,
      "WarehouseCode": "OUT-CON"  // ⚠️ Por línea, no en cabecera
    }
  ]
}
```

### Inventory Transfer Request (ST)

```json
{
  "DocDate": "2026-01-22",
  "DueDate": "2026-01-22",  // ⚠️ Requerido
  "FromWarehouse": "OUT-CON",
  "ToWarehouse": "RG-CD",
  "Comments": "Transferencia desde OC 12345 - Pedido P-12.48",
  "StockTransferLines": [
    {
      "ItemCode": "R5082-15.1012",
      "Quantity": 10.0
      // ⚠️ Sin LineNum
    }
  ]
}
```

---

## 🧪 VALIDACIÓN

### Checklist de Pruebas

✅ Puerto `50001` en URL base  
✅ Endpoint `InventoryTransferRequests` (no `StockTransfers`)  
✅ `WarehouseCode` por línea en OC (no en cabecera)  
✅ `DueDate` incluido en ST  
✅ `LineNum` eliminado de ST  
✅ SessionId reutilizado correctamente  
✅ Logs detallados de request/response  

---

## 🔥 ERRORES COMUNES SAP

### Error -10: Warehouse not defined
**Causa:** `WarehouseCode` inválido o no existe en SAP  
**Solución:** Verificar que el código de bodega existe en SAP y está activo

### Error -4013: Invalid ItemCode
**Causa:** `ItemCode` no existe o está inactivo en SAP  
**Solución:** Verificar homologación SKU → ItemCode SAP

### Error -5002: Invalid Warehouse
**Causa:** Bodega origen/destino no válida para el artículo  
**Solución:** Verificar que el artículo esté habilitado en ambas bodegas

---

## 🎯 FLUJO CORRECTO

```
Pedido Confirmado
   ↓
Distribución Confirmada (tienda/bodega)
   ↓
Crear OC (WarehouseCode por línea)
   ↓
Enviar OC a SAP → DocEntry/DocNum
   ↓
Agrupar por bodega destino
   ↓
Crear ST Requests (1 por bodega)
   ↓
Enviar ST a SAP → DocEntry/DocNum
```

---

## 📊 IMPACTO EN BASE DE DATOS

**No requiere cambios de schema**, solo ajustes en lógica de mapeo.

Las tablas existentes ya soportan:
- `orden_compra_detalle.codigo_bodega` (para WarehouseCode por línea)
- `orden_compra_cabecera.doc_entry` / `doc_num` (para respuestas SAP)
- `pedido_sap_procesamiento_detalle.codigo_bodega` (para distribución)

---

## ⚡ PRÓXIMOS PASOS

1. **Reiniciar servicio** para aplicar cambios en `.env`
2. **Probar creación de OC** desde pedido confirmado
3. **Validar generación de ST** por bodega
4. **Monitorear logs** para detectar errores SAP
5. **Ajustar homologaciones** si hay errores de ItemCode

---

## 📝 NOTAS TÉCNICAS

- **URL Base:** Sin `/Login` (se agrega en método específico)
- **Sesión:** Reutilizada automáticamente (5 min de buffer)
- **TLS Fallback:** Automático si falla TLS 1.2+ (soporta TLS 1.0/1.1)
- **Timeouts:** 30 segundos por defecto (configurable)
- **SSL Verification:** Deshabilitada (desarrollo), activar en producción

---

## 🔗 REFERENCIAS

- [SAP Service Layer API Reference](https://help.sap.com/doc/0d2533ad95ba4ad7a702e83570a21c32/10.0/en-US/SAPB1_ServiceLayer.html)
- Postman Collection: Validado con `http://10.128.240.4:50001`
- Logs: Revisar `logger.info` para flujo completo

---

**Estado:** ✅ Implementado y listo para pruebas  
**Validado con:** Postman (endpoints funcionando correctamente)  
**Pendiente:** Pruebas end-to-end en ambiente de desarrollo
