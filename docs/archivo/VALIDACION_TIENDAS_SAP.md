# RESUMEN DE IMPLEMENTACIÓN: Validación de Tiendas contra SAP

## 🎯 Objetivo

Validar códigos de tienda (ID TIENDA) contra SAP directamente al cargar el Excel. Si alguna tienda no existe en SAP, se rechaza la carga.

## ✅ Cambios Implementados

### 1️⃣ Nuevo Método en PedidoValidator

**Archivo:** `src/database/services/pedido_validator.py` (línea 1181+)

```python
def validar_tiendas_existen_en_sap(
    self,
    codigos_tiendas: List[str],
    sap_obligatorio: bool = True
) -> Dict[str, Any]
```

**Lo que hace:**

- Obtiene todas las tiendas de SAP OWHS
- Valida cada código de tienda contra el catálogo SAP
- Retorna: tiendas válidas, no encontradas, errores, etc.

---

### 2️⃣ Integración en Formato v1.0

**Archivo:** `src/database/services/pedido_service.py` (línea 1337+)

**Ubicación:** En `_procesar_formato_v1_0()` después de procesar Movimiento

**Flujo:**

```
1. Leer hoja Movimiento
2. Extraer códigos únicos de tiendas
3. ← NUEVO: Validar contra SAP
4. Si hay tiendas inválidas → RECHAZAR
5. Si todo OK → continuar con validaciones
```

---

### 3️� Integración en Formato DOS HOJAS

**Archivo:** `src/database/services/pedido_service.py` (línea 672+)

**Ubicación:** En `validar_y_procesar_archivo_excel()` después de consolidar detalles

**Flujo idéntico** al formato v1.0

---

## 📊 Flujo de Validación Completo

```
┌─────────────────────────────────────┐
│  Usuario sube Excel                │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  1️⃣ Validar Archivo (tamaño, etc.)  │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  2️⃣ Parsear Excel (leer hojas)      │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  3️⃣ Validar Productos contra SAP    │
│     (hoja Detalle Articulos)        │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  4️⃣ ← NUEVO:                        │
│     Validar TIENDAS contra SAP      │
│     (hoja Movimiento)               │
│                                     │
│     ❌ Si hay tiendas no válidas:   │
│     RECHAZAR la carga               │
└─────────────────────────────────────┘
           ↓ (Si OK)
┌─────────────────────────────────────┐
│  5️⃣ Validar Coherencia (Artículos)  │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  6️⃣ Validar General                 │
│     (cabecera, fechas, etc.)        │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  7️⃣ Guardar en BD (si todo OK)      │
└─────────────────────────────────────┘
```

---

## 🔧 Cómo Funciona

### Paso 1: Extrae tiendas del Excel

```python
# De la hoja "Movimiento" o "Detalle Articulo"
# Identifica todos los códigos únicos de tienda
# Ejemplo: ["ROL01", "ROL02", "ROL03"]
```

### Paso 2: Consulta SAP

```python
# GET todas las tiendas de SAP OWHS
sap_client.get_todas_bodegas()
# Retorna: [
#   {"WhsCode": "ROL01", "WhsName": "ROLAND QUICENTRO", ...},
#   {"WhsCode": "ROL02", "WhsName": "ROLAND BOSQUE", ...},
#   ...
# ]
```

### Paso 3: Valida cada código

```python
# Para cada tienda en el Excel:
# ✅ Si existe en SAP → VÁLIDA
# ❌ Si NO existe en SAP → NO ENCONTRADA

# Si hay NO ENCONTRADAS y sap_obligatorio=true:
# → RECHAZAR la carga con error
```

---

## 📋 Ejemplo: Respuesta de Error

### Cuando hay tiendas inválidas:

```json
{
  "status": "validation_error",
  "message": "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP. Tiendas no encontradas en SAP OWHS: ROL99, ROL98",
  "pedido_id": null,
  "validacion_tiendas_sap": {
    "total_codigos": 5,
    "validas": 3, // ROL01, ROL02, ROL03
    "no_encontradas": 2, // ROL99, ROL98
    "errores": 0,
    "warnings": 0,
    "todas_validas": false
  },
  "errores": [
    "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP..."
  ]
}
```

### Cuando todas las tiendas son válidas:

```json
{
  "status": "success",
  "message": "Plantilla procesada y guardada exitosamente",
  "pedido_id": "PED-2025-01-07-123456",
  "validacion_tiendas_sap": {
    "total_codigos": 3,
    "validas": 3,
    "no_encontradas": 0,
    "errores": 0,
    "warnings": 0,
    "todas_validas": true
  }
}
```

---

## 🎮 Cómo Probar

### Test 1: Excel con tiendas válidas ✅

```
1. Crear Excel con: ROL01, ROL02 (tiendas que existen en SAP)
2. Subir: POST /api/plantillas/upload?sap_obligatorio=true
3. Resultado: 200 OK - Pedido creado
```

### Test 2: Excel con tiendas inválidas ❌

```
1. Crear Excel con: ROL99, ROL98 (tiendas que NO existen en SAP)
2. Subir: POST /api/plantillas/upload?sap_obligatorio=true
3. Resultado: 400 Bad Request
   - status: "validation_error"
   - no_encontradas: ["ROL99", "ROL98"]
```

### Test 3: Desactivar validación obligatoria ⚠️

```
1. Crear Excel con tiendas inválidas
2. Subir: POST /api/plantillas/upload?sap_obligatorio=false
3. Resultado: 200 OK
   - Incluye warnings sobre tiendas inválidas
   - Pedido se crea igualmente
```

---

## 🔑 Parámetros de Control

### En el endpoint `/api/plantillas/upload`

```python
sap_obligatorio: bool = True  # Query parameter

# True (default)
# - Tiendas no válidas en SAP → BLOQUEAN la carga
# - Requiere que TODAS las tiendas existan en SAP

# False
# - Tiendas no válidas → generan WARNING
# - La carga continúa aunque haya tiendas inválidas
# - Útil para desarrollo/testing
```

---

## 📁 Archivos Modificados

```
src/database/services/
├── pedido_validator.py        ← Nuevo método validar_tiendas_existen_en_sap()
└── pedido_service.py          ← Integración en dos lugares

VALIDACION_TIENDAS_SAP.md      ← Documentación detallada (nuevo archivo)
```

---

## 🚀 Beneficios

✅ **Seguridad:** Garantiza que solo tiendas válidas en SAP se usen  
✅ **Prevención:** Evita errores downstream (rechaza tiendas antes de procesar)  
✅ **Claridad:** Mensajes específicos sobre qué tiendas son problemáticas  
✅ **Flexibilidad:** Puede desactivarse si es necesario (`sap_obligatorio=false`)  
✅ **Trazabilidad:** Información detallada para debugging/auditoría

---

## 📝 Notas

- La validación se aplica a **TODOS** los formatos de Excel soportados
- Los códigos de tienda se normalizan a mayúsculas para consistencia
- El catálogo de SAP se obtiene en tiempo real (en cada validación)
- Los errores incluyen máximo 5 tiendas en el mensaje (resto resumido)

---

## ✨ Resumen Ejecutivo

**Antes:** Las tiendas se validaban solo contra el catálogo en el Excel (hoja Tiendas)

**Ahora:** Las tiendas se validan **directamente contra SAP OWHS**

- Si la tienda no existe en SAP → Rechaza el Excel
- Mayor seguridad y consistencia
- El usuario ve exactamente qué tiendas son problemáticas
