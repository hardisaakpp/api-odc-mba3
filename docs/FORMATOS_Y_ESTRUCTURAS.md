# Formatos y Estructuras de Datos

Documentación de formatos, estructuras de requests y esquemas de datos.

---

## 1. Estructura de Request para Crear Pedido Manual

### POST /api/pedidos

#### ❌ Estructura Incorrecta (Frontend Actual)

```json
{
  "cabecera": {
    "numero_pedido": "P-12.56 - 12 - 2025",
    "codigo_producto": "R5000.911.AJCL"  // ❌ INCORRECTO
  },
  "articulos": [...]
}
```

**Errores:**
1. ❌ Campos de cabecera dentro de objeto `cabecera`
2. ❌ `codigo_producto` debe ser `codigo_interno`
3. ❌ `costo_unitario` debe ser `costo_doc_sin_iva`

#### ✅ Estructura Correcta

```json
{
  "numero_pedido": "P-12.56 - 12 - 2025",
  "fecha_pedido": "2025-12-25",
  "fecha_entrega": "INMEDIATO",
  "forma_pago": "120 DIAS",
  "odc": null,
  "proveedor_nombre": "TEXTILES EL RAYO S.A.",
  "comprador_nombre": "VACA ANDREA",
  "comprador_codigo": "801",
  "origen_traslado": "RL-CD",
  "serie": "10131",
  "articulos": [
    {
      "codigo_interno": "R5000.911.AJCL",
      "descripcion_sap": "DESCRIPCION DEL PRODUCTO",
      "marca": "MARCA",
      "codigo_barras": null,
      "pack": null,
      "costo_doc_sin_iva": 6.9,
      "descuento_1": null,
      "pvp": null,
      "subtotal": null,
      "total": null,
      "distribuciones": [
        {
          "tienda_codigo": "TOUT-COT",
          "tienda_nombre": null,
          "cantidad": 5
        }
      ]
    }
  ]
}
```

---

## 2. Formato Excel de Pedidos

**Template:** `Template_Pedido_Inicial_v1.0.xlsx`

### Formatos Soportados

#### Formato Nuevo v1.0 (con Bodegas Centrales) ⭐
- **Hojas:** `cabecera` y `detalle` (minúsculas)
- **Características:** Soporta bodegas centrales (RL-CD, OUT-CD, REG-CD) + tiendas individuales
- **Cálculo:** TOTAL = SUBTOTAL + RL-CD + OUT-CD + REG-CD

#### Formato Antiguo (Legacy)
- **Hojas:** `CABECERA_PEDIDO` y `DETALLE_ARTICULO` (mayúsculas)
- **Características:** Formato tabular simple

### Hoja: "cabecera"

Tabla clave-valor con datos generales del pedido:

| CAMPO | VALOR | DESCRIPCIÓN |
|-------|-------|-------------|
| CODIGO PEDIDO | P-12.55 - 12 - 2025 | Identificador único |
| FECHA DE PEDIDO | 2025-12-25 00:00:00 | Fecha y hora |
| FECHA DE ENTREGA | INMEDIATO | Tipo de entrega |
| FORMA DE PAGO | 120 DIAS | Condición de pago |
| ODC | (vacío) | Orden de Compra |
| NOMBRE PROVEEDOR | TEXTILES EL RAYO S.A. | Proveedor |
| COMPRADOR NOMBRE | VACA ANDREA | Comprador |
| COD COMPRADOR | 801 | Código comprador |
| ORIGEN TRASLADO | RL-CD | Centro distribución |
| SERIE | 10131 | Número de serie |

### Hoja: "detalle"

Contiene líneas de artículos con distribución por tiendas:

| COLUMNA | DESCRIPCIÓN |
|---------|-------------|
| A | Código Interno (producto en MBA3) |
| B | Descripción |
| C | Pack |
| D | Costo |
| E | Descuento 1 |
| F-I | Otros campos del producto |
| J-L | Bodegas (RL-CD, OUT-CD, RG-CD) |
| M+ | Tiendas |

> **Nota (2026-02-05):** La columna "Marca" fue eliminada de la plantilla.

**Ejemplo de Fila:**
```
R5000.911.AJCL | Artículo | 1 | 6.9 | - | ... | 5 | 3 | 2 | ... | 3 | 2 | 1
                               ^   ^        ^   ^   ^       ^   ^   ^
                             Pack Costo   RL-CD OUT-CD RG-CD Tiendas...
```

---

## 3. Proceso de Copia: Despacho → Orden de Compra

### Mapeo de Campos

#### Cabecera: `despacho_cabecera` → `orden_compra_cabecera`

| Campo Origen | Campo Destino | Descripción |
|--------------|---------------|-------------|
| `despacho_id` | `despacho_id` | Asociación 1:1 |
| `empresa` | `proveedor` | Si empresa ≠ CardCode SAP, mapear desde tabla `cliente` |
| `fecha_despacho` o `fecha_factura` | `fecha_generacion` | Base para ODC |
| `numero_factura` | `referencia_despacho` | Para rastrear en SAP |
| `codigo_bodega` | `codigo_bodega` | Opcional, WarehouseCode en SAP |

#### Detalle: `despacho_detalle` → `orden_compra_detalle`

| Campo Origen | Campo Destino | Descripción |
|--------------|---------------|-------------|
| `detalle_id` | `referencia_detalle` | Rastrear línea original |
| `despacho_id` | `oc_id` | FK indirecta |
| `sku` | `sku_sap` | ItemCode SAP |
| `cantidad_pack_sap` | `cantidad_sap` | Cantidad en packs |
| `unidad_sap` | `unidad_sap` | UoM SAP |
| `precio_unitario_sap` | `precio_unitario` | Precio por pack |
| `total_linea_mba3` | `total_linea` | Subtotal |
| `cantidad_docena_mba3` | `cantidad_origen` | Auditoría |
| `descuento` | `descuento` | Si aplica |

### Uso

```python
from database.connection import get_sql_server_connection
from database.repositories.despacho_repository import DespachoRepository
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.services.orden_compra_service import copy_despacho_to_orden_compra

# Obtener conexión
conn = get_sql_server_connection()

# Crear repositorios
despacho_repo = DespachoRepository(conn)
oc_repo = OrdenCompraRepository(conn)

# Copiar despacho a orden de compra
copy_despacho_to_orden_compra(conn, despacho_id)
```

---

## ✅ Resumen

- **Requests:** Estructura clara para crear pedidos manually
- **Excel:** Dos formatos soportados, nuevo v1.0 recomendado
- **Mapeo:** Procesos documentados para transformar datos
