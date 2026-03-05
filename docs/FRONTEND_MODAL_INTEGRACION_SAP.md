# Indicaciones Frontend: Modal de Integración SAP

## 📋 Resumen

Este documento describe la implementación en el backend y las indicaciones para implementar un modal informativo en el frontend que muestre los resultados de la integración con SAP cuando se envía una ODC.

### ⚠️ Requisito: Solicitudes de Transferencia en el modal

**Las Solicitudes de Transferencia (ITR) solo se muestran hoy en el correo electrónico.** Es obligatorio que el modal de la UI muestre la **misma información** que el correo: resumen (X de Y creadas), lista por tienda (código, nombre, estado, DocNum o error). Los datos ya vienen en la respuesta del backend en `metadata.detalles[].solicitudes_transferencia` (misma estructura que usa el email). El modal debe incluir siempre una sección visible para Solicitudes de Transferencia cuando haya `detalle` de integración, mostrando el contenido o un mensaje tipo "No hay información de Solicitudes de Transferencia" si no aplica.

## ✅ Cambios Implementados en el Backend

### 1. Campo `tienda_nombre` agregado

Se agregó el campo `tienda_nombre` en la respuesta de las Solicitudes de Transferencia (ITR) para incluir el nombre completo de cada tienda.

**Archivo modificado:** `src/database/services/stock_transfer_service.py`

**Cambios:**
- Se creó un mapeo `mapeo_nombre_tienda` que almacena el nombre de cada tienda obtenido de SAP durante la validación
- Se incluye `tienda_nombre` en cada resultado de ITR creado

## 📡 Estructura de Respuesta del Endpoint

### Endpoint: `POST /integrar-sap`

### Respuesta Exitosa

```json
{
  "status": "success",
  "message": "ODC enviada exitosamente a SAP (DocNum: 17098)",
  "metadata": {
    "enviadas": 1,
    "errores": 0,
    "total_procesadas": 1,
    "detalles": [
      {
        "oc_id": "DA876CC8-22D6-4EE3-9A71-B117EFE61155",
        "proveedor": "P1790389219001",
        "success": true,
        "doc_entry": 32230,
        "doc_num": 17098,
        "referencia_despacho": "P-12.19 - 12 - 2025",
        "solicitudes_transferencia": {
          "success": true,
          "transferencias_creadas": 5,
          "transferencias_errores": 0,
          "total_tiendas": 5,
          "resultados": [
            {
              "tienda_id": "uuid-tienda-1",
              "tienda_codigo": "TOUT-CEN",
              "tienda_nombre": "TRANSITORIA DESCUENTON CENTRO HISTORICO",
              "success": true,
              "doc_entry": 312432,
              "doc_num": 17537,
              "error": null
            },
            {
              "tienda_id": "uuid-tienda-2",
              "tienda_codigo": "TOUT-OTA",
              "tienda_nombre": "TRANSITORIA DESCUENTON OTAVALO",
              "success": true,
              "doc_entry": 312433,
              "doc_num": 17538,
              "error": null
            }
            // ... más tiendas
          ]
        }
      }
    ]
  }
}
```

### Respuesta con Errores Parciales

```json
{
  "status": "partial",
  "message": "Proceso completado: 3 enviada(s), 2 error(es) de 5 procesada(s)",
  "metadata": {
    "enviadas": 3,
    "errores": 2,
    "total_procesadas": 5,
    "detalles": [
      {
        "oc_id": "uuid-oc-1",
        "success": true,
        "doc_num": 17098,
        "solicitudes_transferencia": {
          "success": true,
          "transferencias_creadas": 5,
          "transferencias_errores": 0,
          "resultados": [...]
        }
      },
      {
        "oc_id": "uuid-oc-2",
        "success": false,
        "error": "Error al enviar ODC a SAP",
        "error_message": "Error al enviar ODC a SAP",
        "error_code": -4013,
        "error_source": "SAP"
      }
    ]
  }
}
```

## 🎨 Indicaciones para el Frontend

### 1. Estructura del Modal

El modal debe mostrar:

#### **Encabezado:**
- ✅ **Título:** "Integración con SAP Completada" (si todo fue exitoso)
- ⚠️ **Título:** "Integración con SAP - Resultados Parciales" (si hay errores)
- ❌ **Título:** "Error en Integración con SAP" (si todo falló)

#### **Sección 1: Orden de Compra (OC)**
- **Estado:** ✅ Exitoso / ❌ Error
- **Número de OC en SAP:** `doc_num` (ej: "OC #17098")
- **DocEntry:** `doc_entry` (ej: "32230") - opcional, puede ir en tooltip
- **Mensaje:** "Orden de Compra enviada exitosamente a SAP" o mensaje de error

#### **Sección 2: Solicitudes de Transferencia (ITR)** *(obligatoria en el modal — misma información que el correo)*
- Origen de datos: `detalle.solicitudes_transferencia` (misma estructura que se envía en el email).
- **Resumen:**
  - "X de Y Solicitudes de Transferencia creadas exitosamente"
  - Si hay errores: "X exitosas, Y con errores"
  
- **Lista de Tiendas:**
  Para cada tienda en `solicitudes_transferencia.resultados`:
  - ✅ **Si `success: true`:**
    - Código: `tienda_codigo` (ej: "TOUT-CEN")
    - Nombre: `tienda_nombre` (ej: "TRANSITORIA DESCUENTON CENTRO HISTORICO")
    - ITR #: `doc_num` (ej: "17537")
    - DocEntry: `doc_entry` (ej: "312432") - opcional, puede ir en tooltip
  
  - ❌ **Si `success: false`:**
    - Código: `tienda_codigo`
    - Nombre: `tienda_nombre` (si está disponible)
    - Error: `error` (mensaje de error)

#### **Pie del Modal:**
- Botón "Cerrar" o "Aceptar"
- Opcional: Botón "Ver Detalles" que expanda información adicional

### 2. Ejemplo de Diseño Sugerido

```
┌─────────────────────────────────────────────────────┐
│  ✅ Integración con SAP Completada              [X]  │
├─────────────────────────────────────────────────────┤
│                                                      │
│  📦 Orden de Compra                                  │
│  ──────────────────────                              │
│  ✅ OC #17098 enviada exitosamente                  │
│     DocEntry: 32230                                  │
│                                                      │
│  🚚 Solicitudes de Transferencia                    │
│  ──────────────────────                              │
│  ✅ 5 de 5 creadas exitosamente                      │
│                                                      │
│  📋 Detalle por Tienda:                              │
│                                                      │
│  ✅ TOUT-CEN - TRANSITORIA DESCUENTON CENTRO...      │
│     ITR #17537 (DocEntry: 312432)                    │
│                                                      │
│  ✅ TOUT-OTA - TRANSITORIA DESCUENTON OTAVALO        │
│     ITR #17538 (DocEntry: 312433)                    │
│                                                      │
│  ✅ TOUT-PSC - TRANSITORIA DESCUENTON PORTAL...      │
│     ITR #17539 (DocEntry: 312434)                    │
│                                                      │
│  ✅ TOUT-QSS - TRANSITORIA DESCUENTON QUICENTRO...   │
│     ITR #17540 (DocEntry: 312435)                    │
│                                                      │
│  ✅ TOUT-REC - TRANSITORIA DESCUENTON RECREO         │
│     ITR #17541 (DocEntry: 312436)                    │
│                                                      │
│                    [Cerrar]                          │
└─────────────────────────────────────────────────────┘
```

### 3. Manejo de Casos Especiales

#### **Caso 1: ODC exitosa, pero sin Solicitudes de Transferencia**
```json
{
  "solicitudes_transferencia": {
    "success": false,
    "transferencias_creadas": 0,
    "transferencias_errores": 0,
    "total_tiendas": 0,
    "error": "No se generó ningún Inventory Transfer Request (ej. origen = destinos)"
  }
}
```
**Mostrar:** Mensaje informativo: "OC enviada exitosamente, pero no se generaron Solicitudes de Transferencia (no aplicable para este pedido)"

#### **Caso 2: ODC exitosa, pero algunas ITR fallaron**
```json
{
  "solicitudes_transferencia": {
    "success": true,
    "transferencias_creadas": 3,
    "transferencias_errores": 2,
    "total_tiendas": 5,
    "resultados": [
      {"success": true, ...},
      {"success": false, "error": "Error message", ...}
    ]
  }
}
```
**Mostrar:** 
- Resumen: "3 de 5 Solicitudes de Transferencia creadas exitosamente"
- Lista con ✅ para exitosas y ❌ para fallidas con mensaje de error

#### **Caso 3: ODC falló**
```json
{
  "success": false,
  "error": "Error al enviar ODC a SAP",
  "error_code": -4013,
  "error_source": "SAP"
}
```
**Mostrar:** 
- Título: "Error en Integración con SAP"
- Mensaje de error principal
- Código de error si está disponible
- No mostrar sección de Solicitudes de Transferencia (no se intentaron crear)

#### **Caso 4: Mostrar siempre el bloque de Solicitudes de Transferencia**
- Cuando hay `detalle` de integración (OC procesada), la sección "Solicitudes de Transferencia" debe **mostrarse siempre** (mismo contenedor/estilo que la sección de OC).
- Si `solicitudes_transferencia` es `null` o no viene en la respuesta: mostrar dentro del mismo bloque el mensaje *"No hay información de Solicitudes de Transferencia para este resultado."*
- Así el usuario ve en la UI la misma información que recibe por correo, sin depender solo del email.

### 4. Código de Ejemplo (Pseudocódigo)

```javascript
function mostrarModalIntegracionSAP(respuesta) {
  const detalle = respuesta.metadata.detalles[0];
  
  // Determinar estado general
  const estadoGeneral = respuesta.status; // "success", "partial", "error"
  const ocExitoso = detalle.success;
  const st = detalle.solicitudes_transferencia;
  
  // Configurar título del modal
  let titulo = "";
  if (estadoGeneral === "success" && ocExitoso) {
    titulo = "✅ Integración con SAP Completada";
  } else if (estadoGeneral === "partial") {
    titulo = "⚠️ Integración con SAP - Resultados Parciales";
  } else {
    titulo = "❌ Error en Integración con SAP";
  }
  
  // Construir contenido del modal
  const contenido = {
    oc: {
      exitoso: ocExitoso,
      docNum: detalle.doc_num,
      docEntry: detalle.doc_entry,
      error: detalle.error
    },
    solicitudesTransferencia: st ? {
      total: st.total_tiendas,
      creadas: st.transferencias_creadas,
      errores: st.transferencias_errores,
      resultados: st.resultados.map(r => ({
        codigo: r.tienda_codigo,
        nombre: r.tienda_nombre, // ⭐ NUEVO: Nombre de la tienda
        exitoso: r.success,
        docNum: r.doc_num,
        docEntry: r.doc_entry,
        error: r.error
      }))
    } : null
  };
  
  // Mostrar modal con contenido
  mostrarModal(titulo, contenido);
}
```

### 5. Campos Disponibles en la Respuesta

#### **Nivel OC (Orden de Compra):**
- `oc_id`: UUID de la OC
- `proveedor`: Código del proveedor
- `success`: Boolean - Si la OC se envió exitosamente
- `doc_entry`: Número DocEntry en SAP
- `doc_num`: Número de OC en SAP (DocNum)
- `referencia_despacho`: Referencia del despacho
- `error`: Mensaje de error (si aplica)
- `error_code`: Código de error de SAP (si aplica)
- `error_source`: Origen del error ("SAP", "BACKEND", etc.)

#### **Nivel ST (Solicitudes de Transferencia):**
- `success`: Boolean - Si al menos una ST se creó exitosamente
- `transferencias_creadas`: Cantidad de ST creadas exitosamente
- `transferencias_errores`: Cantidad de ST con errores
- `total_tiendas`: Total de tiendas procesadas
- `resultados`: Array con detalles por tienda:
  - `tienda_id`: UUID de la tienda
  - `tienda_codigo`: Código de la tienda (ej: "TOUT-CEN")
  - `tienda_nombre`: **⭐ NUEVO** - Nombre completo de la tienda (ej: "TRANSITORIA DESCUENTON CENTRO HISTORICO")
  - `success`: Boolean - Si la ST se creó exitosamente
  - `doc_entry`: DocEntry del ITR en SAP
  - `doc_num`: Número del ITR en SAP (DocNum)
  - `error`: Mensaje de error (si aplica)

## 📝 Notas Importantes

1. **El campo `tienda_nombre` puede ser `null`** si no se pudo obtener de SAP, en ese caso mostrar solo el código.

2. **El campo `solicitudes_transferencia` puede ser `null`** si no se intentó crear ST (por ejemplo, si la OC falló antes).

3. **Múltiples OCs:** Si se procesan múltiples OCs, el array `detalles` tendrá un elemento por cada OC. Para el modal, generalmente se muestra solo la primera (o se puede hacer un modal por cada una).

4. **Headers de respuesta:** El endpoint también incluye headers útiles:
   - `X-OC-Status`: "success", "partial", o "error"
   - `X-Enviadas`: Cantidad de OCs enviadas
   - `X-Errores`: Cantidad de errores

## 🧪 Testing

Para probar el modal, puedes usar estos escenarios:

1. **Caso exitoso completo:** Enviar una ODC con distribución a múltiples tiendas
2. **Caso con errores parciales:** Simular error en alguna tienda (si es posible)
3. **Caso sin ST:** Enviar una ODC que no genere ST (origen = destino)
4. **Caso con error en OC:** Simular error al enviar la OC a SAP

## 📚 Referencias

- Endpoint: `POST /integrar-sap`
- Documentación de endpoints: `docs/ENDPOINTS.md`
- Flujo completo: `docs/FLUJO_COMPLETO.md`
