# Política de Caché - Backend MBA3

## Resumen

Este documento describe la estrategia de caché implementada en el backend de MBA3-Consultas para optimizar el rendimiento.

## Tipos de Caché

### 1. Caché de Catálogos SAP (Base de Datos)

**Tablas de caché:**
- `producto_sap_cache` - Productos consultados en SAP
- `bodega_sap_cache` - Bodegas/tiendas consultadas en SAP

**Configuración:**
```python
# En src/config.py
SAP_CACHE_DAYS = int(os.getenv("SAP_CACHE_DAYS", "30"))
```

**Comportamiento:**
- Los productos/bodegas consultados en SAP se almacenan en caché por 30 días (configurable)
- Antes de consultar SAP, se verifica si el dato existe en caché y no está expirado
- Si el caché es válido, se usa el dato local sin consultar SAP
- Si el caché está expirado o no existe, se consulta SAP y se actualiza el caché

**Implementación:**
```python
# src/database/services/sap_service.py
cache_valid = repository.is_cache_valid(sku, cache_days=SAP_CACHE_DAYS)
if cache_valid:
    # Usar dato de caché
    producto = repository.find_by_sku(sku)
else:
    # Consultar SAP y guardar en caché
    producto = sap_client.get_item(sku)
    repository.upsert(producto)
```

**Forzar actualización:**
```python
# Pasar force_refresh=True para ignorar caché
producto = sap_service.validar_sku(sku, force_refresh=True)
```

### 2. Caché de Endpoints (Memoria)

**Endpoints con caché en memoria:**

| Endpoint | TTL | Implementación |
|----------|-----|----------------|
| `/ordenes-compra` | 30 seg | `_ordenes_compra_cache` |
| `/despachos/count` | 30 seg | `_despachos_cache` |

**Configuración:**
```python
# src/endpoints/ordenes_compra.py
_oc_cache_ttl_seconds = 30  # 30 segundos de caché

# src/endpoints/despachos_info.py
_cache_ttl_seconds = 30  # 30 segundos de caché
```

**Comportamiento:**
- Los resultados de listados se almacenan en memoria por 30 segundos
- Headers de respuesta indican estado del caché: `X-Cache: HIT` o `X-Cache: MISS`
- El caché se invalida automáticamente al modificar datos relacionados

**Funciones de gestión:**
```python
# Obtener del caché (retorna None si expirado)
cached_result = get_cached_ordenes_compra(estado=estado)

# Guardar en caché
set_cached_ordenes_compra(response_data, estado=estado)

# Invalidar caché (al modificar datos)
invalidate_ordenes_compra_cache()
```

### 3. Caché de Verificación de Esquema (Instancia)

**Uso:** Verificación de columnas en tablas (evita consultas repetidas a `sys.columns`)

**Implementación:**
```python
# src/database/repositories/pedido/pedido_utils.py
class PedidoUtils:
    def __init__(self, conn):
        self._tiene_estado_cache: Optional[bool] = None
        self._tiene_estado_id_cache: Optional[bool] = None
        self._tiene_es_bodega_cache: Optional[bool] = None
    
    def tiene_estado_id(self) -> bool:
        if self._tiene_estado_id_cache is not None:
            return self._tiene_estado_id_cache
        # Consultar y cachear
        resultado = self._verificar_columna('estado_id')
        self._tiene_estado_id_cache = resultado
        return resultado
```

**Nota:** Este caché es por instancia del repositorio, no global.

## Thread Safety

Todos los cachés en memoria usan locks para garantizar thread safety:

```python
import threading

_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {}

def get_cached(key: str) -> Optional[Any]:
    with _cache_lock:
        if key in _cache:
            cached_data = _cache[key]
            # Verificar TTL...
```

## Invalidación de Caché

### Automática

El caché se invalida automáticamente cuando:
- Se modifica, crea o elimina una orden de compra
- Se procesa un despacho
- Se ejecutan tareas de Celery que modifican datos

### Manual

```python
# Invalidar caché de órdenes de compra
from src.endpoints.ordenes_compra import invalidate_ordenes_compra_cache
invalidate_ordenes_compra_cache()

# Invalidar caché de despachos
from src.endpoints.despachos_info import invalidate_despachos_cache
invalidate_despachos_cache()
```

## Configuración por Entorno

### Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `SAP_CACHE_DAYS` | Días de validez del caché de SAP | 30 |

### Recomendaciones por Entorno

**Desarrollo:**
- Usar TTL cortos para ver cambios rápidamente
- Considerar `SAP_CACHE_DAYS=1` para pruebas

**Producción:**
- `SAP_CACHE_DAYS=30` (productos no cambian frecuentemente)
- TTL de 30 segundos para endpoints de listado

## Monitoreo

### Headers de Respuesta

Los endpoints con caché incluyen headers informativos:

```http
X-Cache: HIT       # Dato servido desde caché
X-Cache: MISS      # Dato consultado de la base de datos
```

### Logs

El sistema registra eventos de caché en modo DEBUG:

```
📦 Cache HIT para /ordenes-compra (estado=PENDIENTE)
📭 Cache MISS para /ordenes-compra (estado=PENDIENTE)
💾 Cache SAVED para /ordenes-compra (estado=PENDIENTE)
🗑️ Cache invalidado para /ordenes-compra
```

## Consideraciones de Rendimiento

### Cuándo usar caché

✅ **Usar caché para:**
- Catálogos que cambian poco (productos SAP, bodegas)
- Listados con filtros comunes
- Datos de solo lectura

❌ **No usar caché para:**
- Datos que cambian frecuentemente
- Operaciones de escritura
- Datos sensibles o específicos por usuario

### Memoria

El caché en memoria tiene límites implícitos:
- Solo se cachean claves específicas (estado, limit)
- Los datos expiran automáticamente
- La invalidación limpia todas las entradas

## Archivos Relevantes

- `src/config.py` - Configuración `SAP_CACHE_DAYS`
- `src/endpoints/ordenes_compra.py` - Caché de órdenes
- `src/endpoints/despachos_info.py` - Caché de despachos
- `src/database/services/sap_service.py` - Caché de productos SAP
- `src/database/services/bodega_sap_service.py` - Caché de bodegas SAP
- `src/database/repositories/producto_sap_repository.py` - Tabla `producto_sap_cache`
- `src/database/repositories/bodega_sap_repository.py` - Tabla `bodega_sap_cache`

## Índices de Rendimiento

Para optimizar consultas, se han creado índices en las tablas principales. Ver `scripts/migrations/add_missing_indexes.sql`:

| Tabla | Índice | Columnas |
|-------|--------|----------|
| `pedido` | `idx_pedido_estado_id` | `estado_id` |
| `pedido` | `idx_pedido_creado_por_fecha` | `creado_por`, `creado_en` |
| `pedido_detalle` | `idx_pedido_detalle_marca` | `marca` |
| `distribucion_confirmada` | `idx_distribucion_confirmada_version` | `version` |
| `distribucion_confirmada` | `idx_distribucion_confirmada_pedido_version` | `pedido_id`, `version` |
| `orden_compra_cabecera` | `idx_orden_compra_estado` | `estado` |
| `orden_compra_cabecera` | `idx_orden_compra_pedido_id` | `pedido_id` |
| `orden_compra_cabecera` | `idx_orden_compra_doc_entry` | `doc_entry` |
| `sap_integration_logs` | `idx_sap_logs_timestamp` | `timestamp_log` |
| `sap_integration_logs` | `idx_sap_logs_nivel` | `nivel_log` |
| `sap_integration_logs` | `idx_sap_logs_oc_id` | `oc_id` |
| `pedido_respuesta_proveedor` | `idx_respuesta_proveedor_pedido_id` | `pedido_id` |
