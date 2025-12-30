# Propuesta de Refactorización: PedidoService

## Problema Actual
- `pedido_service.py` tiene ~1,800 líneas
- Anti-patrón "God Service": demasiadas responsabilidades en una sola clase
- Dificulta mantenimiento y testing

## Solución Propuesta: Separación por Responsabilidades

### 1. **pedido_parser.py** - Parsing de Excel
**Responsabilidad**: Extraer datos crudos del Excel sin lógica de negocio

**Métodos a mover**:
- `parsear_excel_pedido()` - Parsing formato dos hojas
- `_extraer_cabecera()` - Extracción de cabecera desde DataFrame
- `_extraer_detalle_con_tiendas()` - Extracción detalle formato complejo
- `_extraer_detalle_formato_simple()` - Extracción formato simple
- `_obtener_valor_celda()` - Utilidad para celdas
- `_get_cell_value()` - Utilidad para valores de celda
- `_get_numeric_value()` - Utilidad para valores numéricos
- `_extraer_distribuciones_tienda()` - Extracción distribuciones

**Salida**: Datos crudos sin normalizar ni consolidar

### 2. **pedido_consolidator.py** - Normalización y Consolidación
**Responsabilidad**: Normalizar datos y consolidar duplicados

**Métodos a mover**:
- `_normalizar_cabecera_para_bd()` - Normalización de cabecera
- Lógica de consolidación de duplicados (actualmente en `parsear_excel_pedido`)
- Agrupación de productos por código (en `_extraer_detalle_formato_simple`)

**Salida**: Datos normalizados y consolidados listos para BD

### 3. **pedido_service.py** - Orquestación y Persistencia
**Responsabilidad**: Coordinar parsing, consolidación, validación y persistencia

**Métodos a mantener**:
- `validar_y_procesar_archivo_excel()` - Método principal (orquestador)
- `procesar_archivo_excel()` - Procesamiento y persistencia
- Integración con `PedidoRepository` y `PedidoValidator`

**Dependencias**:
- Usa `PedidoParser` para parsing
- Usa `PedidoConsolidator` para normalización
- Usa `PedidoValidator` para validación
- Usa `PedidoRepository` para persistencia

## Estructura Propuesta

```
src/database/services/
├── pedido_parser.py          # Parsing de Excel (nuevo)
├── pedido_consolidator.py    # Normalización y consolidación (nuevo)
├── pedido_service.py          # Orquestación (refactorizado, más delgado)
├── pedido_validator.py        # Validación (ya existe)
└── pedido_repository.py      # Persistencia (ya existe)
```

## Beneficios

1. **Separación de responsabilidades**: Cada módulo tiene una responsabilidad clara
2. **Testabilidad**: Más fácil testear cada componente por separado
3. **Mantenibilidad**: Cambios en parsing no afectan consolidación y viceversa
4. **Reutilización**: Parser puede usarse en otros contextos
5. **Escalabilidad**: Fácil agregar nuevos formatos de Excel sin tocar otros módulos

## Compatibilidad

- `PedidoService` mantendrá la misma interfaz pública
- Los métodos públicos existentes seguirán funcionando
- Cambios internos transparentes para el código cliente

## Fase 2 - Preparación ERP

En el futuro, se puede agregar:
- `pedido_erp_preparator.py` - Preparación de datos para ERP
- Transformaciones específicas para SAP, etc.

