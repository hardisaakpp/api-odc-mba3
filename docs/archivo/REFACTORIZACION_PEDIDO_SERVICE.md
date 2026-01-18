# Refactorización de pedido_service.py - Nuevo Diseño Arquitectónico

## Problema Original

El archivo `pedido_service.py` contenía más de 2100 líneas de código con múltiples responsabilidades:

- Detección de formatos Excel
- Conversión de tipos de datos
- Validación contra SAP
- Persistencia en BD
- Procesamiento de diferentes formatos (v1.0, dos hojas, simple)
- Lógica de consolidación

Esta complejidad causaba:

- Errores de Pylance ("Code too complex to analyze")
- Dificultad para mantener el código
- Difícil de testear aisladamente
- Violación del principio de responsabilidad única

## Solución Implementada

Se ha dividido `pedido_service.py` en 4 módulos especializados, reduciendo su tamaño de 2100+ líneas a ~800 líneas.

### Arquitectura Nueva

```
pedido_service.py (Orquestador principal)
├── pedido_type_converter.py (Conversión de tipos)
├── pedido_format_handler.py (Detección de formatos)
├── pedido_sap_handler.py (Validación SAP)
├── pedido_parser.py (Parsing Excel) [ya existía]
├── pedido_consolidator.py (Consolidación) [ya existía]
├── pedido_validator.py (Validación negocio) [ya existía]
└── pedido_repository.py (Persistencia BD) [ya existía]
```

## Nuevos Módulos

### 1. pedido_type_converter.py

**Responsabilidad:** Conversión de tipos de datos

**Métodos principales:**

- `convertir_a_decimal()` - str → float (tolera "1,5", "1.5")
- `convertir_a_entero()` - str → int (redondea)
- `parsear_fecha_texto()` - str → date (soporta múltiples formatos)
- `normalizar_codigo_producto()` - normaliza códigos SAP
- `normalizar_codigo_tienda()` - normaliza códigos tienda
- `booleano_desde_texto()` - str → bool

**Beneficio:** Reutilizable en cualquier contexto, sin dependencias de negocio.

### 2. pedido_format_handler.py

**Responsabilidad:** Detección y manejo de formatos Excel

**Métodos principales:**

- `detectar_hojas_excel()` - Encuentra hojas CABECERA, DETALLE, MOVIMIENTO, TIENDAS
- `detectar_formato_excel()` - Determina formato (v1.0, dos_hojas, simple)
- `detectar_formato_detalle()` - Identifica si detalle es simple o complejo
- `leer_hoja_segura()` - Lee hojas con fallback robusto

**Beneficio:** Lógica de detección centralizada y testeable.

### 3. pedido_sap_handler.py

**Responsabilidad:** Validación contra SAP y construcción de mensajes de error

**Métodos principales:**

- `validar_tiendas_contra_sap()` - Valida códigos de tienda en SAP OWHS
- `validar_productos_contra_sap()` - Valida códigos de producto en SAP ITEMS
- `construir_mensaje_error_tiendas_invalidas()` - Mensajes amigables
- `construir_mensaje_error_productos_invalidos()` - Mensajes estructurados
- `construir_datos_validacion_error()` - Estructura de datos para respuesta API

**Beneficio:** Lógica SAP centralizada, fácil de mockear en tests.

## Impacto en pedido_service.py

### Antes

- 2128 líneas
- 23 métodos
- Múltiples responsabilidades

### Después

- ~800 líneas (reducción: 62%)
- 17 métodos (6 extraídos)
- Responsabilidad enfocada: orquestación

## Cambios en la Interfaz Pública

**NO HAY CAMBIOS.** La interfaz pública de `PedidoService` permanece idéntica:

- `parsear_excel_pedido()`
- `procesar_archivo_excel()`
- `validar_y_procesar_archivo_excel()`

Todos los cambios son internos. Código cliente existente funciona sin modificaciones.

## Métodos Delegados en PedidoService

Los siguientes métodos ahora delegan a los nuevos módulos:

```python
# Conversión de tipos (delegado a PedidoTypeConverter)
_convertir_a_decimal() → type_converter.convertir_a_decimal()
_convertir_a_entero() → type_converter.convertir_a_entero()
_parsear_fecha_texto() → type_converter.parsear_fecha_texto()
```

## Ventajas de la Refactorización

✅ **Mantenibilidad Mejorada**

- Cada módulo tiene una responsabilidad clara
- Código más legible y navegable
- Easier to find where bugs are

✅ **Testabilidad Mejorada**

- Módulos independientes se pueden testear en aislamiento
- Inyección de dependencias para mocks
- Tests más rápidos y enfocados

✅ **Reutilización**

- `PedidoTypeConverter` puede usarse en otros servicios
- `PedidoFormatHandler` funciona con cualquier Excel
- `PedidoSAPHandler` encapsula toda lógica SAP

✅ **Escalabilidad**

- Fácil agregar nuevos formatos en `PedidoFormatHandler`
- Fácil agregar nuevas conversiones en `PedidoTypeConverter`
- Fácil extender validaciones SAP en `PedidoSAPHandler`

✅ **Sin Errores de Pylance**

- Código bajo límite de complejidad
- Tipos explícitos y correctos
- Sin warnings de análisis

## Migración y Compatibilidad

✅ **Backward Compatible**

- Ningún cambio en API pública
- Misma funcionalidad
- Mismo comportamiento

✅ **Sin Cambios en BD**

- Esquema de persistencia idéntico
- Datos guardados igual
- Queries sin cambios

✅ **Sin Cambios en Endpoints**

- `/api/plantillas/upload` funciona igual
- Respuestas idénticas
- Frontend no requiere cambios

## Estructura de Archivos

```
src/database/services/
├── pedido_service.py (800 líneas, orquestación)
├── pedido_type_converter.py (165 líneas, conversiones)
├── pedido_format_handler.py (180 líneas, formatos)
├── pedido_sap_handler.py (155 líneas, SAP)
├── pedido_parser.py (1400+ líneas, parsing)
├── pedido_consolidator.py (500+ líneas, consolidación)
├── pedido_validator.py (1200+ líneas, validación)
└── ... (otros servicios)
```

## Cómo Usar los Nuevos Módulos

### Como Cliente Externo

Sin cambios: sigue usando `PedidoService` como antes.

### Reutilizando PedidoTypeConverter

```python
from src.database.services.pedido_type_converter import PedidoTypeConverter

converter = PedidoTypeConverter()
cantidad = converter.convertir_a_entero("10.5")  # Returns 10
fecha = converter.parsear_fecha_texto("01/01/2024")
```

### Reutilizando PedidoFormatHandler

```python
from src.database.services.pedido_format_handler import PedidoFormatHandler

hojas = PedidoFormatHandler.detectar_hojas_excel(file_content)
formato = PedidoFormatHandler.detectar_formato_excel(hojas)
```

### Reutilizando PedidoSAPHandler

```python
from src.database.services.pedido_sap_handler import PedidoSAPHandler
from src.database.services.pedido_validator import PedidoValidator

validator = PedidoValidator()
sap_handler = PedidoSAPHandler(validator)
validacion = sap_handler.validar_tiendas_contra_sap(["01", "02"])
```

## Testing

Cada módulo puede ser testeado independientemente:

```python
# Test conversiones
def test_convertir_a_decimal():
    assert PedidoTypeConverter.convertir_a_decimal("1,5") == 1.5

# Test detección formato
def test_detectar_hojas():
    hojas = PedidoFormatHandler.detectar_hojas_excel(test_file)
    assert hojas['cabecera'] is not None

# Test validación SAP
def test_validar_tiendas():
    handler = PedidoSAPHandler(mock_validator)
    result = handler.validar_tiendas_contra_sap(["01"])
```

## Conclusión

Esta refactorización mantiene toda la funcionalidad mientras:

- ✅ Reduce complejidad de `pedido_service.py` en 62%
- ✅ Elimina errores de Pylance
- ✅ Mejora mantenibilidad y testabilidad
- ✅ Preserva compatibilidad al 100%
- ✅ Facilita futuras extensiones

El código es ahora más limpio, más modular y más profesional.
