# Guía de Uso - Módulos Refactorizados

## Visión General

`pedido_service.py` ha sido refactorizado en múltiples módulos especializados. Esta guía explica cómo usar cada uno.

## 1. PedidoTypeConverter

Convierte valores entre tipos de datos.

### Instalación

```python
from src.database.services.pedido_type_converter import PedidoTypeConverter
```

### Métodos Disponibles

#### convertir_a_decimal()

Convierte strings a float. Tolera múltiples formatos.

```python
# Formatos soportados
PedidoTypeConverter.convertir_a_decimal("1.5")      # → 1.5
PedidoTypeConverter.convertir_a_decimal("1,5")      # → 1.5 (europeo)
PedidoTypeConverter.convertir_a_decimal(1)          # → 1.0
PedidoTypeConverter.convertir_a_decimal("abc")      # → None
PedidoTypeConverter.convertir_a_decimal(None)       # → None
```

#### convertir_a_entero()

Convierte strings a int. Redondea si es necesario.

```python
PedidoTypeConverter.convertir_a_entero("10")        # → 10
PedidoTypeConverter.convertir_a_entero("10.5")      # → 10 (redondea)
PedidoTypeConverter.convertir_a_entero("10.7")      # → 11 (redondea)
PedidoTypeConverter.convertir_a_entero(None)        # → None
```

#### parsear_fecha_texto()

Parsea fechas en múltiples formatos. Retorna date o valor original.

```python
# Formatos soportados
PedidoTypeConverter.parsear_fecha_texto("01/01/2024")  # → date(2024, 1, 1)
PedidoTypeConverter.parsear_fecha_texto("2024-01-01")  # → date(2024, 1, 1)
PedidoTypeConverter.parsear_fecha_texto("01-01-2024")  # → date(2024, 1, 1)
PedidoTypeConverter.parsear_fecha_texto("INMEDIATO")   # → "INMEDIATO" (valor original)
PedidoTypeConverter.parsear_fecha_texto(None)          # → None
```

#### normalizar_codigo_producto()

Normaliza códigos de producto para SAP.

```python
PedidoTypeConverter.normalizar_codigo_producto(" abc123 ")  # → "ABC123"
PedidoTypeConverter.normalizar_codigo_producto(None)         # → None
```

#### normalizar_codigo_tienda()

Normaliza códigos de tienda.

```python
PedidoTypeConverter.normalizar_codigo_tienda(" tienda 01 ")  # → "TIENDA01"
```

#### booleano_desde_texto()

Convierte strings a booleano.

```python
PedidoTypeConverter.booleano_desde_texto("sí")      # → True
PedidoTypeConverter.booleano_desde_texto("no")      # → False
PedidoTypeConverter.booleano_desde_texto("1")       # → True
PedidoTypeConverter.booleano_desde_texto("0")       # → False
PedidoTypeConverter.booleano_desde_texto("activo")  # → True
```

## 2. PedidoFormatHandler

Detecta formatos de Excel y lee hojas.

### Instalación

```python
from src.database.services.pedido_format_handler import PedidoFormatHandler
```

### Métodos Disponibles

#### detectar_hojas_excel()

Encuentra las hojas del Excel.

```python
hojas = PedidoFormatHandler.detectar_hojas_excel(file_content)
# Retorna:
# {
#     'cabecera': 'Cabecera Pedido' o None,
#     'detalle': 'Detalle Articulos' o None,
#     'movimiento': 'Movimiento' o None,
#     'tiendas': 'Tiendas' o None
# }
```

#### detectar_formato_excel()

Determina el formato basado en hojas encontradas.

```python
hojas = PedidoFormatHandler.detectar_hojas_excel(file_content)
formato = PedidoFormatHandler.detectar_formato_excel(hojas)
# Retorna: 'cuatro_hojas_v1_0', 'dos_hojas', o 'simple'

if formato == 'cuatro_hojas_v1_0':
    print("Formato v1.0 con 4 hojas")
elif formato == 'dos_hojas':
    print("Formato de 2 hojas")
else:
    print("Formato simple")
```

#### detectar_formato_detalle()

Identifica si el detalle es simple o complejo.

```python
es_simple, columnas_tiendas = PedidoFormatHandler.detectar_formato_detalle(
    excel_file,
    sheet_name='Detalle Articulos'
)

if es_simple:
    print("Formato simple: CodigoProducto, IdTienda, Cantidad")
else:
    print(f"Formato complejo con tiendas: {columnas_tiendas}")
```

#### leer_hoja_segura()

Lee una hoja con fallback robusto.

```python
df = PedidoFormatHandler.leer_hoja_segura(
    excel_file,
    sheet_name='Detalle',
    header=0
)
# Intenta con header primero, luego sin header
# Retorna DataFrame vacío si falla
```

## 3. PedidoSAPHandler

Valida contra SAP y construye mensajes de error.

### Instalación

```python
from src.database.services.pedido_sap_handler import PedidoSAPHandler
from src.database.services.pedido_validator import PedidoValidator

validator = PedidoValidator()
sap_handler = PedidoSAPHandler(validator)
```

### Métodos Disponibles

#### validar_tiendas_contra_sap()

Valida que los códigos de tienda existan en SAP OWHS.

```python
resultado = sap_handler.validar_tiendas_contra_sap(
    codigos_tiendas=['01', '02', '03'],
    sap_obligatorio=True
)

# Resultado:
# {
#     'todas_validas': True/False,
#     'validas': ['01', '02'],
#     'no_encontradas': ['03'],
#     'errores': [],
#     'warnings': []
# }
```

#### validar_productos_contra_sap()

Valida que los códigos de producto existan en SAP ITEMS.

```python
resultado = sap_handler.validar_productos_contra_sap(
    codigos_productos=['PROD001', 'PROD002'],
    validar_sap=True,
    usar_cache=True,
    sap_obligatorio=True
)

if resultado is None:
    print("Validación deshabilitada")
else:
    print(f"Productos válidos: {len(resultado.get('validos', []))}")
```

#### construir_mensaje_error_tiendas_invalidas()

Construye mensaje legible para tiendas inválidas.

```python
validacion = sap_handler.validar_tiendas_contra_sap(['01', '02'])
if not validacion['todas_validas']:
    mensaje = sap_handler.construir_mensaje_error_tiendas_invalidas(validacion)
    print(mensaje)
    # Output: "No se puede procesar la plantilla: existen tiendas (ID TIENDA)
    #         no válidas en SAP. Tiendas no encontradas: 01, 02"
```

#### construir_mensaje_error_productos_invalidos()

Construye mensaje legible para productos inválidos.

```python
validacion = sap_handler.validar_productos_contra_sap(['PROD001'])
if not validacion['todos_validos']:
    mensaje = sap_handler.construir_mensaje_error_productos_invalidos(validacion)
    print(mensaje)
```

#### construir_datos_validacion_error()

Construye estructura de respuesta para API.

```python
datos = sap_handler.construir_datos_validacion_error(
    error_type='tiendas',
    validacion_sap=validacion,
    total_codigos=10
)

# Estructura para retornar al frontend
# {
#     "validacion": {...},
#     "validacion_sap": {...}
# }
```

## 4. Usando PedidoService con los nuevos módulos

`PedidoService` ahora usa los nuevos módulos internamente:

```python
from src.database.services.pedido_service import PedidoService

service = PedidoService()

# Los métodos públicos funcionan igual
resultado = service.validar_y_procesar_archivo_excel(
    file_content=excel_bytes,
    filename="pedido.xlsx",
    usuario_id="user123"
)

# Internamente usa:
# - service.type_converter para conversiones
# - service.format_handler para detectar formatos
# - service.sap_handler para validación SAP
```

## 5. Ejemplos Completos

### Validar Tiendas en SAP

```python
from src.database.services.pedido_sap_handler import PedidoSAPHandler
from src.database.services.pedido_validator import PedidoValidator

validator = PedidoValidator()
sap_handler = PedidoSAPHandler(validator)

# Validar tiendas
tiendas = ['01', '02', '03']
validacion = sap_handler.validar_tiendas_contra_sap(tiendas)

if validacion['todas_validas']:
    print("Todas las tiendas son válidas")
else:
    print(f"Tiendas no encontradas: {validacion['no_encontradas']}")
    mensaje = sap_handler.construir_mensaje_error_tiendas_invalidas(validacion)
    print(mensaje)
```

### Detectar Formato y Procesar

```python
from src.database.services.pedido_format_handler import PedidoFormatHandler
import pandas as pd

# Detectar formato
hojas = PedidoFormatHandler.detectar_hojas_excel(file_content)
formato = PedidoFormatHandler.detectar_formato_excel(hojas)

print(f"Formato detectado: {formato}")

if formato == 'cuatro_hojas_v1_0':
    # Procesar v1.0
    excel_file = pd.ExcelFile(io.BytesIO(file_content))
    es_simple, cols_tiendas = PedidoFormatHandler.detectar_formato_detalle(
        excel_file,
        hojas['detalle']
    )
    print(f"Detalle simple: {es_simple}, Tiendas: {cols_tiendas}")
```

### Convertir Múltiples Valores

```python
from src.database.services.pedido_type_converter import PedidoTypeConverter

converter = PedidoTypeConverter()

# Procesar fila de Excel
fila_datos = {
    'cantidad': "10.5",
    'precio': "99,99",
    'fecha': "01/01/2024",
    'activo': "sí"
}

cantidad = converter.convertir_a_entero(fila_datos['cantidad'])  # → 10
precio = converter.convertir_a_decimal(fila_datos['precio'])     # → 99.99
fecha = converter.parsear_fecha_texto(fila_datos['fecha'])       # → date(2024,1,1)
activo = converter.booleano_desde_texto(fila_datos['activo'])    # → True
```

## 6. Preguntas Frecuentes

### ¿Puedo seguir usando PedidoService como antes?

**Sí.** La interfaz pública no ha cambiado. El código cliente funciona igual.

### ¿Qué pasa si necesito usar PedidoTypeConverter en otro lugar?

**Perfecto.** Es reutilizable. Puedes importarlo en cualquier servicio.

### ¿Los nuevos módulos tienen dependencias externas?

**No.** Solo usan librerías estándar (pandas, datetime, re) que ya están en requirements.

### ¿Cómo testeo los nuevos módulos?

```python
# Test unitario de PedidoTypeConverter
def test_convertir_a_decimal():
    assert PedidoTypeConverter.convertir_a_decimal("1,5") == 1.5
    assert PedidoTypeConverter.convertir_a_decimal(None) is None
```

## 7. Notas de Rendimiento

- **PedidoTypeConverter**: Operaciones muy rápidas (microsegundos)
- **PedidoFormatHandler**: Depende del tamaño del Excel (milisegundos)
- **PedidoSAPHandler**: Depende de latencia SAP (segundos)

No hay cambios en rendimiento respecto a antes.

---

**Para más detalles, ver `REFACTORIZACION_PEDIDO_SERVICE.md`**
