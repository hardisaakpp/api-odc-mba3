# Estándares de API - Backend MBA3

## Resumen

Este documento describe los estándares implementados en la API del backend MBA3-Consultas según las buenas prácticas de desarrollo.

## Formato de Respuestas

### Respuesta Exitosa

Todas las respuestas exitosas siguen el formato:

```json
{
    "status": "success",
    "message": "Descripción de la operación realizada",
    "data": { ... },
    "metadata": {
        "total": 100,
        "page": 1,
        "pageSize": 10,
        "totalPages": 10,
        "hasMore": false
    }
}
```

> **Nota**: Los campos de paginación usan camelCase para compatibilidad con el frontend.
> Ver [NAMING_CONVENTIONS.md](./NAMING_CONVENTIONS.md) para la convención completa.

**Campos:**
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `status` | string | `"success"` para operaciones exitosas |
| `message` | string | Descripción legible de la operación |
| `data` | object/array | Datos de respuesta |
| `metadata` | object | Metadatos (paginación, conteos, etc.) |

### Respuesta de Error

```json
{
    "error": "Mensaje de error legible",
    "type": "tipo_de_error",
    "error_code": "CODIGO_ERROR",
    "status_code": 400,
    "details": { ... }
}
```

**Campos:**
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `error` | string | Mensaje de error legible para el usuario |
| `type` | string | Tipo de error para clasificación |
| `error_code` | string | Código único para identificación programática |
| `status_code` | int | Código HTTP del error |
| `details` | object | Detalles adicionales del error |

## Códigos HTTP

### Exitosos (2xx)

| Código | Uso |
|--------|-----|
| `200 OK` | Operación exitosa (GET, PUT, DELETE) |
| `201 Created` | Recurso creado exitosamente (POST) |
| `204 No Content` | Operación exitosa sin contenido de respuesta |

### Errores del Cliente (4xx)

| Código | Tipo | Uso |
|--------|------|-----|
| `400 Bad Request` | `validation_error`, `business_exception` | Datos inválidos o error de negocio |
| `401 Unauthorized` | `authentication_error` | Token JWT faltante o inválido |
| `403 Forbidden` | `authorization_error` | Sin permisos para la operación |
| `404 Not Found` | `not_found` | Recurso no encontrado |
| `422 Unprocessable Entity` | `validation_error` | Error de validación de Pydantic |
| `429 Too Many Requests` | `rate_limit_exceeded` | Límite de requests excedido |

### Errores del Servidor (5xx)

| Código | Tipo | Uso |
|--------|------|-----|
| `500 Internal Server Error` | `internal_server_error` | Error inesperado del servidor |
| `503 Service Unavailable` | `mba3_connection_error` | Servicio externo no disponible |

## Tipos de Error

### `validation_error`
Error de validación de datos de entrada.

```json
{
    "error": "Error de validación del request",
    "type": "validation_error",
    "details": [
        {
            "loc": ["body", "campo"],
            "msg": "field required",
            "type": "value_error.missing"
        }
    ]
}
```

### `business_exception`
Error de lógica de negocio.

```json
{
    "error": "No se puede procesar el pedido sin validación SAP",
    "type": "business_exception",
    "error_code": "SAP_VALIDATION_REQUIRED",
    "status_code": 400,
    "data": {
        "pedido_id": "123",
        "items_sin_validar": 5
    }
}
```

### `authentication_error`
Error de autenticación JWT.

```json
{
    "error": "Token JWT inválido o expirado",
    "type": "http_exception",
    "status_code": 401
}
```

### `authorization_error`
Error de permisos.

```json
{
    "error": "No tienes permisos para esta operación",
    "type": "http_exception",
    "status_code": 403,
    "required_permission": "pedidos.create"
}
```

## Códigos de Error de Negocio

| Código | Descripción | HTTP |
|--------|-------------|------|
| `BUSINESS_ERROR` | Error genérico de negocio | 400 |
| `SAP_VALIDATION_REQUIRED` | Requiere validación SAP previa | 400 |
| `SAP_DATA_MASTER_ERROR` | Error de datos maestros en SAP | 400 |
| `PEDIDO_NOT_FOUND` | Pedido no encontrado | 404 |
| `OC_NOT_FOUND` | Orden de compra no encontrada | 404 |
| `INVALID_STATE` | Estado inválido para la operación | 400 |

## Validaciones

### Validación de Entrada (Pydantic)

Todos los endpoints usan modelos Pydantic para validación:

```python
from pydantic import BaseModel, field_validator

class CrearPedidoRequest(BaseModel):
    numero_pedido: str
    items: List[ItemPedido]
    
    @field_validator('numero_pedido')
    @classmethod
    def validar_numero(cls, v):
        if not v or len(v) < 3:
            raise ValueError('Número de pedido debe tener al menos 3 caracteres')
        return v.strip()
```

### Prevención de SQL Injection

Todas las queries usan parámetros (`?`):

```python
# ✅ Correcto - Parámetros
cursor.execute("SELECT * FROM pedido WHERE id = ?", (pedido_id,))

# ❌ Incorrecto - String interpolation
cursor.execute(f"SELECT * FROM pedido WHERE id = '{pedido_id}'")
```

## Autenticación y Autorización

### JWT Token

Todos los endpoints protegidos requieren token JWT:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Verificación de Permisos

```python
from src.security.jwt_auth import verify_jwt_token, require_permission

@app.get("/pedidos")
async def get_pedidos(user: dict = Depends(verify_jwt_token)):
    # user contiene datos del token JWT
    pass

@app.post("/pedidos")
async def crear_pedido(
    user: dict = Depends(verify_jwt_token),
    _: None = Depends(require_permission('pedidos.create'))
):
    pass
```

## Headers de Respuesta

### Headers Estándar

| Header | Descripción |
|--------|-------------|
| `X-Source` | Origen de la petición (CURL, FRONTEND, etc.) |
| `X-Endpoint` | Nombre del endpoint |
| `X-Cache` | Estado del caché (HIT/MISS) |
| `X-Correlation-ID` | ID único de la petición para trazabilidad |

### Ejemplo

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Source: FRONTEND
X-Endpoint: PEDIDOS-LISTAR
X-Cache: MISS
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440000
```

## Rate Limiting

### Configuración

```env
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT=100/minute
```

### Respuesta de Límite Excedido

```json
{
    "error": "Rate limit exceeded",
    "type": "rate_limit_exceeded",
    "retry_after": 60
}
```

**Headers:**
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1612137600
```

## CORS

### Configuración

```env
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com
```

### Métodos Permitidos

- `GET` - Consultas
- `POST` - Crear recursos
- `PUT` - Actualizar recursos
- `DELETE` - Eliminar recursos

## Documentación OpenAPI

### Acceso

- **Swagger UI**: `GET /docs`
- **ReDoc**: `GET /redoc`
- **OpenAPI JSON**: `GET /openapi.json`

### Tags de Endpoints

| Tag | Descripción |
|-----|-------------|
| Sistema | Health check y estado |
| Consultas MBA3 | Consultar/migrar datos de MBA3 |
| Procesamiento | Procesar despachos y OCs |
| Integración SAP | Integración con SAP |
| Órdenes de Compra | Gestión de OCs |
| Pedidos | Gestión de pedidos |
| Historial | Consulta de logs |
| Autenticación | Auth y autorización |

## Exception Handlers

### Implementación Centralizada

Los exception handlers están en `src/middleware/exception_handlers.py`:

```python
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "error": "Error de validación",
            "type": "validation_error",
            "details": exc.errors()
        }
    )

@app.exception_handler(BusinessException)
async def business_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={
            "error": exc.message,
            "type": "business_exception",
            "error_code": exc.error_code,
            "data": exc.data
        }
    )
```

### Excepciones Personalizadas

| Excepción | Uso | HTTP |
|-----------|-----|------|
| `QueryValidationError` | Error de validación de SQL | 400 |
| `MBA3ConnectionError` | Error de conexión a MBA3 | 503 |
| `MBA3QueryError` | Error al ejecutar query en MBA3 | 500 |
| `BusinessException` | Error de lógica de negocio | 400 |
| `SAPDataMasterError` | Error de datos maestros SAP | 400 |

## Paginación

### Request

Los query parameters aceptan ambos estilos para compatibilidad:

```http
# Estilo snake_case (backend)
GET /pedidos?page=1&page_size=10

# Estilo camelCase (frontend) - preferido
GET /pedidos?page=1&pageSize=10

# También soportado offset/limit
GET /pedidos?limit=10&offset=0
```

### Response

La respuesta usa **camelCase** para metadatos de paginación (compatibilidad frontend):

```json
{
    "status": "success",
    "data": [...],
    "metadata": {
        "total": 150,
        "page": 1,
        "pageSize": 10,
        "totalPages": 15,
        "hasMore": true
    }
}
```

### Nomenclatura

Referencia completa: [NAMING_CONVENTIONS.md](./NAMING_CONVENTIONS.md)

| Campo | En Request | En Response |
|-------|------------|-------------|
| Tamaño de página | `pageSize` o `page_size` | `pageSize` |
| Página actual | `page` | `page` |
| Total de registros | - | `total` |
| Total de páginas | - | `totalPages` |
| Tiene más páginas | - | `hasMore` |

## Versionado

La API actual es v2.0.0. El versionado se indica en:

1. **Metadata de FastAPI**: `version="2.0.0"`
2. **Header de respuesta** (opcional): `X-API-Version: 2.0.0`

## Archivos Relevantes

- `src/api_server.py` - Configuración principal de FastAPI
- `src/middleware/exception_handlers.py` - Exception handlers
- `src/exceptions.py` - Excepciones personalizadas
- `src/security/jwt_auth.py` - Autenticación JWT
- `src/security/rate_limit.py` - Rate limiting
- `src/models.py` - Modelos Pydantic
- `src/schemas/api_responses.py` - Modelos de respuesta para OpenAPI
- `src/utils/response_helpers.py` - Helpers para respuestas estandarizadas
- `docs/ENDPOINTS.md` - Documentación de endpoints
- `docs/NAMING_CONVENTIONS.md` - Convenciones de nomenclatura

## Referencias

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [HTTP Status Codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status)
- [JSON API Specification](https://jsonapi.org/)
