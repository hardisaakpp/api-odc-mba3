# Proceso de Copia: Despacho → Orden de Compra

Este documento describe el proceso que copia datos desde `despacho_cabecera`/`despacho_detalle` hacia `orden_compra_cabecera`/`orden_compra_detalle`.

**Nota:** Este proceso corresponde al **Paso 3** del flujo completo. Para ver el contexto completo del flujo, ver [FLUJO_COMPLETO.md](FLUJO_COMPLETO.md).

## 📋 Mapeo de Campos

### Cabecera: `despacho_cabecera` → `orden_compra_cabecera`

| Campo Origen | Campo Destino | Descripción |
|--------------|---------------|-------------|
| `despacho_id` | `despacho_id` | Asociación 1:1 (referencia interna) |
| `empresa` | `proveedor` | **OJO:** Si empresa ≠ CardCode SAP, se mapea desde tabla `cliente` |
| `fecha_despacho` o `fecha_factura` | `fecha_generacion` | La fecha base de la ODC |
| `numero_factura` | `referencia_despacho` | Para rastrear en SAP de qué documento viene |
| `codigo_bodega` | `codigo_bodega` | Opcional, a veces requerido en SAP como WarehouseCode |

### Detalle: `despacho_detalle` → `orden_compra_detalle`

| Campo Origen | Campo Destino | Descripción |
|--------------|---------------|-------------|
| `detalle_id` | `referencia_detalle` | Para rastrear la línea original |
| `despacho_id` | `oc_id` | FK indirecta (a través de cabecera) |
| `sku` | `sku_sap` | ItemCode de SAP (ya transformado) |
| `cantidad_pack_sap` | `cantidad_sap` | Cantidad en packs que SAP espera |
| `unidad_sap` | `unidad_sap` | UoM SAP (X3, X2, etc.) |
| `precio_unitario_sap` | `precio_unitario` | Precio que SAP usa por pack |
| `total_linea_mba3` o `subtotal_sap` | `total_linea` | Subtotal para validar con SAP |
| `cantidad_docena_mba3` | `cantidad_origen` | Para auditoría |
| `descuento` | `descuento` | Si aplica |
| `nombre_producto` | *(opcional)* | No se envía a SAP |
| `tipo_linea` | *(ignorar)* | No aplica a SAP |
| `impuesto` | *(no aplicar)* | SAP define TaxCode por línea |

## 🚀 Uso

### Ejemplo Básico

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
despacho_id = "uuid-del-despacho"
resultado = copy_despacho_to_orden_compra(
    despacho_repo=despacho_repo,
    oc_repo=oc_repo,
    despacho_id=despacho_id,
    skip_if_exists=True  # No copiar si ya existe
)

if resultado:
    print(f"✅ OC creada: {resultado['oc_id']}")
    print(f"   Proveedor: {resultado['proveedor']}")
    print(f"   Detalles: {resultado['detalles_insertados']}")
else:
    print("⚠️ No se pudo crear la OC o ya existe")
```

### Ejemplo con Múltiples Despachos

```python
from database.connection import get_sql_server_connection
from database.repositories.despacho_repository import DespachoRepository
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.services.orden_compra_service import copy_despacho_to_orden_compra

conn = get_sql_server_connection()
despacho_repo = DespachoRepository(conn)
oc_repo = OrdenCompraRepository(conn)

# Lista de despachos a procesar
despachos_ids = ["uuid-1", "uuid-2", "uuid-3"]

resultados = []
for despacho_id in despachos_ids:
    try:
        resultado = copy_despacho_to_orden_compra(
            despacho_repo=despacho_repo,
            oc_repo=oc_repo,
            despacho_id=despacho_id,
            skip_if_exists=True
        )
        if resultado:
            resultados.append(resultado)
    except Exception as e:
        print(f"❌ Error procesando despacho {despacho_id}: {e}")

print(f"✅ Procesados {len(resultados)} despachos exitosamente")
```

## 🔍 Mapeo Empresa → Proveedor

El sistema intenta mapear `empresa` a `proveedor` (CardCode SAP) desde la tabla `cliente`:

1. **Primero** busca en `cliente` donde `empresa = ?` o `CardCode = ?`
2. **Si no encuentra**, busca por `nombre`, `razon_social` o `CardName`
3. **Si no encuentra mapeo**, usa la `empresa` misma como `proveedor` (puede ser que ya sea el CardCode)

### Estructura Esperada de Tabla `cliente`

La tabla `cliente` puede tener diferentes estructuras. El sistema intenta:

- Campo `empresa` y `CardCode`
- Campo `nombre`/`razon_social`/`CardName` y `CardCode`

## 📝 Notas Importantes

1. **Validación de Detalles**: Solo se copian detalles que tengan `sku_sap` y `cantidad_sap` válidos
2. **Cálculo de Precio**: Si `precio_unitario_sap` no existe, se calcula como `total_linea / cantidad_sap`
3. **Fecha de Generación**: Se usa `fecha_factura` si existe, sino `fecha_despacho`
4. **Prevención de Duplicados**: Por defecto, no copia si ya existe una OC para el despacho (`skip_if_exists=True`)

## 🗂️ Archivos Relacionados

- **Repositorio**: `src/database/repositories/orden_compra_repository.py`
- **Mapper**: `src/database/mappers/orden_compra_mapper.py`
- **Servicio**: `src/database/services/orden_compra_service.py`
- **Repositorio Despacho**: `src/database/repositories/despacho_repository.py`

## ⚠️ Requisitos Previos

1. Las tablas `orden_compra_cabecera` y `orden_compra_detalle` deben existir en SQL Server
2. La tabla `cliente` debe existir si se requiere mapeo empresa → proveedor
3. Los despachos deben tener datos completos (cabecera y detalles)

## 🔧 Estructura de Tablas Esperada

### `orden_compra_cabecera`

```sql
CREATE TABLE orden_compra_cabecera (
    oc_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    despacho_id UNIQUEIDENTIFIER NOT NULL,
    proveedor VARCHAR(50) NOT NULL,
    fecha_generacion DATE NOT NULL,
    referencia_despacho VARCHAR(50) NULL,
    codigo_bodega VARCHAR(50) NULL,
    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME DEFAULT GETDATE()
);
```

### `orden_compra_detalle`

```sql
CREATE TABLE orden_compra_detalle (
    detalle_oc_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    oc_id UNIQUEIDENTIFIER NOT NULL,
    referencia_detalle UNIQUEIDENTIFIER NULL,
    sku_sap VARCHAR(50) NOT NULL,
    cantidad_sap DECIMAL(18, 4) NOT NULL,
    unidad_sap VARCHAR(10) NULL,
    precio_unitario DECIMAL(18, 4) NULL,
    total_linea DECIMAL(18, 4) NOT NULL,
    cantidad_origen DECIMAL(18, 4) NULL,
    descuento DECIMAL(18, 4) DEFAULT 0,
    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (oc_id) REFERENCES orden_compra_cabecera(oc_id)
);
```




