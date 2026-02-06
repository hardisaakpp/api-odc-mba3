# Convenciones de Nomenclatura - Backend MBA3

## Resumen

Este documento define las convenciones de nomenclatura para la API REST del backend MBA3-Consultas.

## Convención Adoptada

| Contexto | Convención | Ejemplo |
|----------|------------|---------|
| **URLs/Endpoints** | kebab-case, plural | `/api/pedidos`, `/ordenes-compra` |
| **Query Parameters** | snake_case + camelCase alias | `page_size`, `pageSize` |
| **Request Body (JSON)** | camelCase | `{ "columnOrder": [], "pageSize": 10 }` |
| **Response Body (JSON)** | camelCase para paginación | `{ "pageSize": 10, "totalPages": 5 }` |
| **Response Body (datos)** | snake_case para datos de negocio | `{ "numero_pedido": "P-001" }` |
| **Código Python** | snake_case | `page_size`, `numero_pedido` |

## Justificación

### Por qué mezcla de estilos

1. **Frontend (JavaScript)**: Usa camelCase nativamente
2. **Backend (Python)**: Usa snake_case como convención PEP8
3. **Datos de negocio**: Mantienen snake_case para consistencia con la base de datos
4. **Paginación/Metadata**: Usa camelCase para facilitar integración con frontend

### Compatibilidad

Los query parameters aceptan ambos estilos para máxima compatibilidad:
- `page_size=10` (Python style)
- `pageSize=10` (JavaScript style)

## Detalle por Contexto

### 1. URLs y Endpoints

**Convención**: kebab-case, sustantivos en plural

```
✅ Correcto:
GET  /api/pedidos
GET  /api/pedidos/{id}
POST /api/pedidos
GET  /ordenes-compra
GET  /ordenes-compra/logs

❌ Incorrecto:
GET  /api/pedido          (singular)
GET  /api/getPedidos      (verbo)
GET  /ordenesCompra       (camelCase)
```

### 2. Query Parameters

**Convención**: Aceptar ambos estilos (snake_case y camelCase)

```python
@app.get("/api/pedidos")
async def listar_pedidos(
    # Parámetro principal en snake_case
    page_size: Optional[int] = Query(50, description="Tamaño de página"),
    # Alias en camelCase para frontend
    pageSize: Optional[int] = Query(None, description="Alias de page_size"),
):
    # Priorizar camelCase si se envía
    size = pageSize if pageSize is not None else page_size
```

**Uso desde frontend:**
```javascript
// Ambos funcionan:
fetch('/api/pedidos?pageSize=10')
fetch('/api/pedidos?page_size=10')
```

### 3. Request Body (JSON)

**Convención**: camelCase para campos del frontend

```json
// ✅ Correcto (lo que envía el frontend)
{
    "visibleColumns": ["codigo", "nombre"],
    "columnOrder": ["codigo", "nombre", "estado"],
    "pageSize": 10,
    "filters": {}
}
```

**Modelo Pydantic:**
```python
class TablePreferencesDto(BaseModel):
    visibleColumns: list[str]
    columnOrder: list[str]
    pageSize: Optional[int]
    filters: Optional[Dict[str, Any]]
```

### 4. Response Body - Paginación

**Convención**: camelCase para metadatos de paginación

```json
{
    "status": "success",
    "data": [...],
    "metadata": {
        "total": 150,
        "page": 1,
        "pageSize": 50,
        "totalPages": 3,
        "hasMore": true
    }
}
```

### 5. Response Body - Datos de Negocio

**Convención**: snake_case para datos de entidades de negocio

```json
{
    "status": "success",
    "data": {
        "pedido_id": "123e4567-e89b-12d3-a456-426614174000",
        "numero_pedido": "P-12.48 - 12 - 2025",
        "fecha_pedido": "2025-01-21",
        "proveedor_nombre": "TEXTILES EL RAYO S.A.",
        "estado": "PENDIENTE_CONFIRMACION_PROVEEDOR",
        "creado_por": "usuario@example.com",
        "creado_en": "2025-01-21T10:30:00"
    }
}
```

**Justificación**: Los campos de negocio reflejan los nombres de columnas en la base de datos SQL Server, que usa snake_case.

## Implementación

### Helper para Respuestas Paginadas

```python
def paginated_response(
    data: List[Any],
    total: int,
    page: int,
    page_size: int
) -> Dict[str, Any]:
    """Genera respuesta paginada con nomenclatura estándar."""
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "status": "success",
        "data": data,
        "metadata": {
            "total": total,
            "page": page,
            "pageSize": page_size,      # camelCase para frontend
            "totalPages": total_pages,   # camelCase para frontend
            "hasMore": page < total_pages
        }
    }
```

### Modelos Pydantic con Alias

Para mantener snake_case interno pero exponer camelCase:

```python
from pydantic import BaseModel, Field

class PaginationMetadata(BaseModel):
    total: int
    page: int
    page_size: int = Field(..., alias="pageSize")
    total_pages: int = Field(..., alias="totalPages")
    has_more: bool = Field(..., alias="hasMore")
    
    class Config:
        populate_by_name = True  # Permite usar tanto el nombre como el alias
```

## Casos Especiales

### Headers HTTP

**Convención**: Title-Case con guiones (estándar HTTP)

```http
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440000
X-Cache: HIT
X-Source: FRONTEND
X-Total-Count: 150
```

### Códigos de Error

**Convención**: SCREAMING_SNAKE_CASE

```json
{
    "error": "No se puede procesar",
    "error_code": "SAP_VALIDATION_REQUIRED",
    "type": "business_exception"
}
```

## Tabla de Referencia Rápida

| Campo | En Request | En Response | En Python |
|-------|------------|-------------|-----------|
| Tamaño de página | `pageSize` | `pageSize` | `page_size` |
| Página actual | `page` | `page` | `page` |
| Total de páginas | - | `totalPages` | `total_pages` |
| Tiene más | - | `hasMore` | `has_more` |
| Orden de columnas | `columnOrder` | `columnOrder` | `column_order` |
| Columnas visibles | `visibleColumns` | `visibleColumns` | `visible_columns` |
| Número de pedido | - | `numero_pedido` | `numero_pedido` |
| Fecha de pedido | - | `fecha_pedido` | `fecha_pedido` |

## Archivos Relevantes

- `src/models.py` - Modelos Pydantic principales
- `src/utils/response_helpers.py` - Helpers para respuestas
- `src/endpoints/*/` - Endpoints de la API
- `docs/API_STANDARDS.md` - Estándares generales de API

## Migración y Compatibilidad

Para mantener retrocompatibilidad:

1. **Query parameters**: Aceptar ambos estilos (`pageSize` y `page_size`)
2. **No cambiar respuestas existentes** que ya usa el frontend
3. **Nuevos endpoints**: Seguir la convención documentada
4. **Documentar en Swagger**: Indicar el estilo preferido
