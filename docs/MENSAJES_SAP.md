# Mensajes de SAP y Origen de Errores

Este documento explica el origen de los mensajes de error y éxito que se generan durante el proceso de integración con SAP, y cómo estructurarlos para mostrarlos en el frontend.

## Origen de los Mensajes

### 1. Mensajes que vienen de SAP Service Layer

Estos mensajes son generados por SAP cuando hay un problema al crear la Purchase Order:

**Ejemplo:**
```
❌ Posting period locked; specify an alternative date (Código: -4013)
```

**Estructura de respuesta de SAP:**
```json
{
  "error": {
    "code": "-4013",
    "message": {
      "value": "Posting period locked; specify an alternative date"
    }
  }
}
```

**Cómo se extraen:**
- El código de error se extrae de `error.code`
- El mensaje se extrae de `error.message.value`
- Estos se incluyen en la respuesta del endpoint `/integrar-sap`

### 2. Mensajes generados por el Backend

Estos mensajes son generados por el backend cuando hay problemas antes de enviar a SAP:

**Ejemplos:**
- `"No se encontraron detalles para la ODC: {oc_id}"` - La ODC no tiene detalles en la base de datos
- `"No se encontró orden de compra con ID: {oc_id}"` - La ODC no existe
- `"La ODC no está en estado PENDIENTE (estado actual: {estado})"` - La ODC no está en estado correcto
- `"Error al construir JSON de SAP: {mensaje}"` - Error al convertir datos a formato SAP
- `"No se recibió respuesta de SAP Service Layer"` - Problema de conexión con SAP

## Estructura de Respuesta del Endpoint `/integrar-sap`

### Respuesta Exitosa

```json
{
  "status": "success",
  "message": "ODC enviada exitosamente a SAP (DocNum: 16947)",
  "metadata": {
    "enviadas": 1,
    "errores": 0,
    "total_procesadas": 1,
    "detalles": [
      {
        "oc_id": "4AC5623D-1ABA-4701-A56D-E34F72FC6E54",
        "proveedor": "PROVEEDOR001",
        "success": true,
        "doc_entry": 31868,
        "doc_num": 16947,
        "error": null,
        "error_code": null,
        "error_source": null,
        "sap_response": {
          "DocEntry": 31868,
          "DocNum": 16947,
          ...
        },
        "sap_error_details": null
      }
    ]
  }
}
```

### Respuesta con Error de SAP

```json
{
  "status": "error",
  "message": "Error al enviar ODC a SAP: Posting period locked; specify an alternative date (Código SAP: -4013)",
  "metadata": {
    "enviadas": 0,
    "errores": 1,
    "total_procesadas": 1,
    "detalles": [
      {
        "oc_id": "53B43021-E0F2-4BE7-8F2D-B5EFEEA0230F",
        "proveedor": "PROVEEDOR002",
        "success": false,
        "doc_entry": null,
        "doc_num": null,
        "error": "Posting period locked; specify an alternative date (Código SAP: -4013)",
        "error_code": "-4013",
        "error_source": "SAP",
        "sap_response": null,
        "sap_error_details": {
          "error": {
            "code": "-4013",
            "message": {
              "value": "Posting period locked; specify an alternative date"
            }
          }
        }
      }
    ]
  }
}
```

### Respuesta con Error del Backend

```json
{
  "status": "error",
  "message": "Error al enviar ODC a SAP: No se encontraron detalles para la ODC: 195A2FB5-6677-488F-A225-DEDEDC04D61B",
  "metadata": {
    "enviadas": 0,
    "errores": 1,
    "total_procesadas": 1,
    "detalles": [
      {
        "oc_id": "195A2FB5-6677-488F-A225-DEDEDC04D61B",
        "proveedor": "PROVEEDOR003",
        "success": false,
        "doc_entry": null,
        "doc_num": null,
        "error": "No se encontraron detalles para la ODC: 195A2FB5-6677-488F-A225-DEDEDC04D61B",
        "error_code": null,
        "error_source": "BACKEND",
        "sap_response": null,
        "sap_error_details": null
      }
    ]
  }
}
```

## Campos de la Respuesta

### Campos en `detalles[]`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `oc_id` | string | UUID de la orden de compra |
| `proveedor` | string | Código del proveedor |
| `success` | boolean | `true` si se envió exitosamente, `false` si hubo error |
| `doc_entry` | number\|null | DocEntry de SAP (solo si éxito) |
| `doc_num` | number\|null | DocNum de SAP (solo si éxito) |
| `error` | string\|null | Mensaje de error completo (solo si error) |
| `error_message` | string\|null | **Alias de `error`** - Mensaje de error completo (solo si error). Usar este campo para compatibilidad con frontend. |
| `error_code` | string\|null | Código de error de SAP (ej: "-4013") - solo si error viene de SAP |
| `error_source` | string\|null | Origen del error: `"SAP"`, `"BACKEND"`, `"SAP_CONNECTION"`, o `null` si éxito |
| `sap_response` | object\|null | Respuesta completa de SAP cuando es exitoso |
| `sap_error_details` | object\|null | Detalles completos del error de SAP (solo si error viene de SAP) |

## Códigos de Error Comunes de SAP

| Código | Mensaje | Descripción |
|--------|---------|-------------|
| `-4013` | Posting period locked; specify an alternative date | Período contable bloqueado |
| `-5002` | Invalid object reference | Referencia de objeto inválida |
| `-5004` | Invalid field value | Valor de campo inválido |
| `-5005` | Missing required field | Campo requerido faltante |
| `-5006` | Duplicate key | Clave duplicada |

## Recomendaciones para el Frontend

### 1. Identificar el Origen del Error

Usar el campo `error_source` para determinar cómo mostrar el error:

```javascript
if (detalle.error_source === "SAP") {
  // Error de SAP - mostrar código y mensaje
  mostrarErrorSAP(detalle.error, detalle.error_code);
} else if (detalle.error_source === "BACKEND") {
  // Error del backend - mostrar mensaje simple
  mostrarErrorBackend(detalle.error);
} else if (detalle.error_source === "SAP_CONNECTION") {
  // Error de conexión - mostrar mensaje de conexión
  mostrarErrorConexion(detalle.error);
}
```

### 2. Mostrar Información de Éxito

Cuando `success === true`:
- Mostrar `doc_num` como número de orden de compra creada en SAP
- Opcionalmente mostrar `doc_entry` para referencia técnica

### 3. Manejar Códigos de Error Específicos

Para códigos conocidos de SAP, mostrar mensajes más amigables:

```javascript
const mensajesSAP = {
  "-4013": "El período contable está bloqueado. Contacte al administrador de SAP para desbloquear el período o especificar una fecha alternativa.",
  "-5002": "Referencia inválida. Verifique que el proveedor y los productos existan en SAP.",
  // ... más códigos
};

function obtenerMensajeAmigable(errorCode, errorMessage) {
  return mensajesSAP[errorCode] || errorMessage;
}
```

### 4. Estructura de Componente de Error (Ejemplo React)

```jsx
function ErrorODC({ detalle }) {
  // Buscar error_message o error (ambos están disponibles)
  const errorMsg = detalle.error_message || detalle.error;
  if (!errorMsg) return null;
  
  const esErrorSAP = detalle.error_source === "SAP";
  const esErrorBackend = detalle.error_source === "BACKEND";
  
  return (
    <div className={`error ${detalle.error_source?.toLowerCase()}`}>
      {esErrorSAP && (
        <>
          {detalle.error_code && (
            <div className="error-code">Código SAP: {detalle.error_code}</div>
          )}
          <div className="error-message">{errorMsg}</div>
          {detalle.sap_error_details && (
            <details>
              <summary>Detalles técnicos</summary>
              <pre>{JSON.stringify(detalle.sap_error_details, null, 2)}</pre>
            </details>
          )}
        </>
      )}
      {esErrorBackend && (
        <div className="error-message">{errorMsg}</div>
      )}
    </div>
  );
}
```

## Flujo de Procesamiento

1. **Backend valida ODC** → Si falla, `error_source: "BACKEND"`
2. **Backend construye JSON** → Si falla, `error_source: "BACKEND"`
3. **Backend envía a SAP** → Si falla conexión, `error_source: "SAP_CONNECTION"`
4. **SAP procesa request** → Si falla, `error_source: "SAP"` con `error_code` y `sap_error_details`
5. **SAP responde éxito** → `success: true` con `doc_entry`, `doc_num` y `sap_response`

## Logs Relacionados

Los logs del backend muestran:
- `❌ {mensaje} (Código: {código})` - Errores de SAP con código
- `❌ {mensaje}` - Errores del backend sin código
- `✅ Purchase Order creada exitosamente en SAP: DocEntry={doc_entry}, DocNum={doc_num}` - Éxito

Estos logs ayudan a identificar el origen del problema durante el desarrollo y debugging.

