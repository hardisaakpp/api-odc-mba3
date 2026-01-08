# Mapeo de Campos: CABECERA_PEDIDO → Base de Datos

## 📋 Campos Reales de la Cabecera

Según el encabezado real de la hoja `CABECERA_PEDIDO`:

1. **CODIGO PEDIDO**
2. **FECHA PEDIDO**
3. **FECHA ENTREGA**
4. **FORMA PAGO**
5. **ODC**
6. **NOMBRE PROVEEDOR**
7. **COMPRADOR NOMBRE**
8. **COD COMPRADOR**
9. **ORIGEN TRASLADO**
10. **SERIE**

---

## 🔄 Mapeo Excel → Base de Datos

### Tabla: `pedido`

| Campo Excel | Campo BD | Tipo | Notas |
|-------------|----------|------|-------|
| **CODIGO PEDIDO** | `numero_pedido` | NVARCHAR(50) | UNIQUE, obligatorio |
| **FECHA PEDIDO** | `fecha_pedido` | DATE | Convertido de string |
| **FECHA ENTREGA** | `fecha_entrega` | NVARCHAR(50) | Puede ser "INMEDIATO" o fecha |
| **FORMA PAGO** | `forma_pago` | NVARCHAR(50) | |
| **ODC** | `odc` | NVARCHAR(50) | |
| **NOMBRE PROVEEDOR** | `proveedor_nombre` | NVARCHAR(150) | |
| **COMPRADOR NOMBRE** | `comprador_nombre` | NVARCHAR(150) | |
| **COD COMPRADOR** | `comprador_codigo` | NVARCHAR(50) | |
| **ORIGEN TRASLADO** | `origen_traslado` | NVARCHAR(50) | |
| **SERIE** | `serie` | NVARCHAR(50) | |
| (generado) | `archivo_nombre` | NVARCHAR(255) | Nombre del Excel subido |
| (generado) | `creado_por` | NVARCHAR(450) | User ID del JWT |
| (generado) | `creado_en` | DATETIME | Timestamp automático |

---

## 📝 Ejemplo de Parsing

### Excel Input (CABECERA_PEDIDO)

| Campo | Valor |
|-------|-------|
| CODIGO PEDIDO | P-12.48 |
| FECHA PEDIDO | 21/01/2025 |
| FECHA ENTREGA | INMEDIATO |
| FORMA PAGO | Contado |
| ODC | ODC-001 |
| NOMBRE PROVEEDOR | Proveedor XYZ |
| COMPRADOR NOMBRE | Juan Pérez |
| COD COMPRADOR | COMP001 |
| ORIGEN TRASLADO | Almacén Central |
| SERIE | A |

### Resultado del Parsing

```json
{
  "cabecera": {
    "CODIGO PEDIDO": "P-12.48",
    "numero_pedido": "P-12.48",
    "FECHA PEDIDO": "21/01/2025",
    "fecha_pedido": "21/01/2025",
    "FECHA ENTREGA": "INMEDIATO",
    "fecha_entrega": "INMEDIATO",
    ...
  }
}
```

**Nota:** Se guardan tanto el nombre original como el normalizado para compatibilidad.

### Después de Normalización (para BD)

```python
{
  "numero_pedido": "P-12.48",
  "fecha_pedido": date(2025, 1, 21),  # Convertido a DATE
  "fecha_entrega": "INMEDIATO",
  "forma_pago": "Contado",
  "odc": "ODC-001",
  "proveedor_nombre": "Proveedor XYZ",
  "comprador_nombre": "Juan Pérez",
  "comprador_codigo": "COMP001",
  "origen_traslado": "Almacén Central",
  "serie": "A",
  "archivo_nombre": "Template_Pedido_Inicial_v1.0.xlsx",
  "creado_por": "user123"
}
```

---

## 🗄️ Resultado en Base de Datos

### Registro en `pedido`

```sql
pedido_id: 'abc-123-def-456...'
numero_pedido: 'P-12.48'
fecha_pedido: '2025-01-21'
fecha_entrega: 'INMEDIATO'
forma_pago: 'Contado'
odc: 'ODC-001'
proveedor_nombre: 'Proveedor XYZ'
comprador_nombre: 'Juan Pérez'
comprador_codigo: 'COMP001'
origen_traslado: 'Almacén Central'
serie: 'A'
archivo_nombre: 'Template_Pedido_Inicial_v1.0.xlsx'
creado_por: 'user123'
creado_en: '2025-01-21 12:00:00'
```

---

## ✅ Implementación

### Mapeo en Código

El método `_normalizar_cabecera_para_bd()` realiza el mapeo:

```python
mapeo_campos_cabecera = {
    "CODIGO PEDIDO": "numero_pedido",
    "FECHA PEDIDO": "fecha_pedido",
    "FECHA ENTREGA": "fecha_entrega",
    "FORMA PAGO": "forma_pago",
    "ODC": "odc",
    "NOMBRE PROVEEDOR": "proveedor_nombre",
    "COMPRADOR NOMBRE": "comprador_nombre",
    "COD COMPRADOR": "comprador_codigo",
    "ORIGEN TRASLADO": "origen_traslado",
    "SERIE": "serie"
}
```

### Conversión de Tipos

- **Fechas**: Se convierten de string (DD/MM/YYYY) a `date`
- **Strings**: Se mantienen como están (con trim)
- **NULLs**: Se preservan si el campo está vacío en el Excel

---

## 🔍 Validaciones

### Campos Obligatorios (validación pre-negocio)

- `numero_pedido` (CODIGO PEDIDO) - **Obligatorio**
- Otros campos son opcionales según reglas de negocio

### Conversión de Fechas

- Formato aceptado: `DD/MM/YYYY` o `YYYY-MM-DD`
- Si falla la conversión, se guarda como NULL y se registra warning

---

## 📊 Resumen

✅ **Mapeo implementado** - Todos los campos de la cabecera se mapean correctamente
✅ **Conversión de tipos** - Fechas se convierten automáticamente
✅ **Case-insensitive** - Funciona con variaciones de mayúsculas/minúsculas
✅ **Retrocompatible** - Mantiene nombres originales además de normalizados

