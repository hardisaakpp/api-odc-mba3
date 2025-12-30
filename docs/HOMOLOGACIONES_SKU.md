# Homologaciones SKU - Documentación Técnica

## 📋 Índice

1. [Introducción](#introducción)
2. [Arquitectura](#arquitectura)
3. [Base de Datos](#base-de-datos)
4. [API Endpoints](#api-endpoints)
5. [Modelos de Datos](#modelos-de-datos)
6. [Lógica de Negocio](#lógica-de-negocio)
7. [Instalación y Configuración](#instalación-y-configuración)
8. [Ejemplos de Uso](#ejemplos-de-uso)

---

## Introducción

El módulo de **Homologaciones SKU** permite gestionar las correspondencias entre los códigos de productos (SKUs) de MBA3 y SAP, facilitando:

- **Detección automática** de diferencias entre sistemas
- **Gestión manual** de homologaciones
- **Sincronización** desde despachos
- **Seguimiento** del estado de cada homologación

### Casos de Uso

1. **Detección de diferencias**: Identificar productos que tienen códigos diferentes entre MBA3 y SAP
2. **Homologación manual**: Registrar correspondencias manualmente
3. **Actualización masiva**: Actualizar múltiples homologaciones simultáneamente
4. **Sincronización**: Sincronizar automáticamente desde los despachos existentes

---

## Arquitectura

### Stack Tecnológico

- **Backend**: FastAPI (Python 3.11+)
- **Base de Datos**: SQL Server
- **ORM**: PyODBC (acceso directo)
- **Validación**: Pydantic
- **Autenticación**: JWT

### Estructura de Capas

```
┌─────────────────────────────────────────┐
│          API Layer (FastAPI)            │
│    src/endpoints/homologaciones_sku.py  │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         Service Layer                   │
│  src/database/services/                 │
│    homologacion_service.py              │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│       Repository Layer                  │
│  src/database/repositories/             │
│    homologacion_repository.py           │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         Database Layer                  │
│    SQL Server - sku_homologacion        │
└─────────────────────────────────────────┘
```

---

## Base de Datos

### Tabla: `sku_homologacion`

```sql
CREATE TABLE [dbo].[sku_homologacion] (
    -- Primary Key
    homologacion_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    
    -- Datos de MBA3 (requeridos)
    sku_mba3 VARCHAR(100) NOT NULL,
    nombre_producto_mba3 NVARCHAR(255) NULL,
    precio_unitario_mba3 DECIMAL(18, 2) NULL,
    cantidad_docena_mba3 DECIMAL(18, 2) NULL,
    total_linea_mba3 DECIMAL(18, 2) NULL,
    
    -- Datos de SAP (opcionales)
    sku_sap VARCHAR(100) NULL,
    nombre_producto_sap NVARCHAR(255) NULL,
    precio_unitario_sap DECIMAL(18, 2) NULL,
    cantidad_pack_sap DECIMAL(18, 2) NULL,
    unidad_sap VARCHAR(20) NULL,
    subtotal_sap DECIMAL(18, 2) NULL,
    
    -- Estado y flags
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    tiene_diferencias BIT NOT NULL DEFAULT 0,
    tiene_datos_sap BIT NOT NULL DEFAULT 0,
    
    -- Relaciones
    detalle_id UNIQUEIDENTIFIER NULL,
    despacho_id UNIQUEIDENTIFIER NULL,
    
    -- Metadata
    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME DEFAULT GETDATE(),
    ultima_modificacion DATETIME NULL,
    modificado_por VARCHAR(100) NULL,
    
    CONSTRAINT CK_sku_homologacion_estado CHECK (estado IN ('PENDIENTE', 'HOMOLOGADO', 'ERROR'))
);
```

### Índices

- `idx_sku_homologacion_sku_mba3` - Búsqueda por SKU MBA3
- `idx_sku_homologacion_sku_sap` - Búsqueda por SKU SAP
- `idx_sku_homologacion_estado` - Filtro por estado
- `idx_sku_homologacion_tiene_diferencias` - Filtro por diferencias
- `idx_sku_homologacion_tiene_datos_sap` - Filtro por datos SAP
- `idx_sku_homologacion_created_at` - Ordenamiento por fecha

### Script de Instalación

```bash
# Ejecutar el script SQL para crear la tabla
sqlcmd -S tu_servidor -d mba3_consultas -i scripts/create_sku_homologacion_table.sql
```

---

## API Endpoints

### 1. GET `/api/homologaciones-sku`

Obtiene lista paginada de homologaciones con filtros.

**Query Parameters:**
- `page` (int, default: 1) - Número de página
- `pageSize` (int, default: 10) - Tamaño de página
- `estado` (string, optional) - PENDIENTE | HOMOLOGADO | ERROR
- `tiene_diferencias` (boolean, optional) - Filtrar por diferencias
- `tiene_datos_sap` (boolean, optional) - Filtrar por datos SAP
- `sku` (string, optional) - Búsqueda por SKU (MBA3 o SAP)

**Response:**
```json
{
  "status": "success",
  "data": [...],
  "metadata": {
    "count": 150,
    "total_pendientes": 50,
    "total_homologados": 80,
    "total_errores": 20
  },
  "total": 150,
  "page": 1,
  "pageSize": 10,
  "totalPages": 15
}
```

### 2. PUT `/api/homologaciones-sku/{homologacion_id}`

Actualiza una homologación específica.

**Path Parameters:**
- `homologacion_id` (string) - UUID de la homologación

**Request Body:**
```json
{
  "sku_sap": "SKU001-SAP",
  "nombre_producto_sap": "Producto SAP",
  "precio_unitario_sap": 105.00,
  "cantidad_pack_sap": 12,
  "unidad_sap": "UN",
  "subtotal_sap": 1260.00,
  "estado": "HOMOLOGADO"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {...},
  "message": "Homologación actualizada correctamente"
}
```

### 3. POST `/api/homologaciones-sku/bulk-update`

Actualiza múltiples homologaciones en lote.

**Request Body:**
```json
{
  "updates": [
    {
      "homologacion_id": "uuid-123",
      "data": {
        "sku_sap": "SKU001-SAP",
        "estado": "HOMOLOGADO"
      }
    },
    {
      "homologacion_id": "uuid-456",
      "data": {
        "sku_sap": "SKU002-SAP",
        "estado": "HOMOLOGADO"
      }
    }
  ]
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "actualizadas": 2,
    "errores": 0,
    "detalles": [...]
  }
}
```

### 4. POST `/api/homologaciones-sku/sincronizar`

Sincroniza homologaciones desde los despachos.

**Request Body:** vacío

**Response:**
```json
{
  "status": "success",
  "data": {
    "homologaciones_encontradas": 25,
    "homologaciones_nuevas": 10,
    "homologaciones_actualizadas": 15,
    "mensaje": "Sincronización completada"
  }
}
```

---

## Modelos de Datos

### SkuHomologacion

```python
class SkuHomologacion(BaseModel):
    homologacion_id: str
    
    # Datos MBA3
    sku_mba3: str
    nombre_producto_mba3: Optional[str]
    precio_unitario_mba3: Optional[float]
    cantidad_docena_mba3: Optional[float]
    total_linea_mba3: Optional[float]
    
    # Datos SAP
    sku_sap: Optional[str]
    nombre_producto_sap: Optional[str]
    precio_unitario_sap: Optional[float]
    cantidad_pack_sap: Optional[float]
    unidad_sap: Optional[str]
    subtotal_sap: Optional[float]
    
    # Estado y flags
    estado: str  # PENDIENTE | HOMOLOGADO | ERROR
    tiene_diferencias: bool
    tiene_datos_sap: bool
    
    # Relaciones
    detalle_id: Optional[str]
    despacho_id: Optional[str]
    
    # Metadata
    created_at: Optional[str]
    updated_at: Optional[str]
    ultima_modificacion: Optional[str]
    modificado_por: Optional[str]
```

### HomologacionSkuUpdateRequest

```python
class HomologacionSkuUpdateRequest(BaseModel):
    sku_sap: Optional[str]
    nombre_producto_sap: Optional[str]
    precio_unitario_sap: Optional[float]  # >= 0
    cantidad_pack_sap: Optional[float]    # >= 0
    unidad_sap: Optional[str]
    subtotal_sap: Optional[float]
    estado: Optional[str]  # PENDIENTE | HOMOLOGADO | ERROR
```

---

## Lógica de Negocio

### Cálculo de Flags

#### `tiene_datos_sap`

Se marca como `true` si al menos uno de estos campos tiene valor:
- `sku_sap`
- `nombre_producto_sap`
- `precio_unitario_sap`
- `cantidad_pack_sap`
- `unidad_sap`
- `subtotal_sap`

#### `tiene_diferencias`

Se marca como `true` si hay diferencias entre MBA3 y SAP en:
- SKU diferente
- Precio unitario diferente (tolerancia: 0.01)
- Cantidad diferente
- Total diferente

### Estados

- **PENDIENTE**: Nueva homologación o con diferencias detectadas
- **HOMOLOGADO**: Validada y sin diferencias
- **ERROR**: Error durante sincronización o validación

### Proceso de Sincronización

1. Lee todos los productos de `despacho_detalle`
2. Busca información SAP en `producto_sap_cache`
3. Compara datos MBA3 vs SAP
4. Detecta diferencias
5. Crea nuevas homologaciones o actualiza existentes
6. Calcula flags automáticamente
7. Asigna estado apropiado

---

## Instalación y Configuración

### 1. Crear la Tabla

```bash
# Ejecutar script SQL
sqlcmd -S localhost -d mba3_consultas -i scripts/create_sku_homologacion_table.sql
```

### 2. Verificar Instalación

```sql
-- Verificar que la tabla existe
SELECT * FROM sku_homologacion;

-- Verificar índices
EXEC sp_helpindex 'sku_homologacion';
```

### 3. Configurar Permisos

```sql
-- Otorgar permisos al usuario de la aplicación
GRANT SELECT, INSERT, UPDATE ON sku_homologacion TO [usuario_app];
```

### 4. Reiniciar Servidor

```bash
# Reiniciar el servidor FastAPI para cargar los nuevos endpoints
python src/main.py
```

---

## Ejemplos de Uso

### Ejemplo 1: Listar Homologaciones Pendientes

```bash
curl -X GET "http://localhost:8000/api/homologaciones-sku?estado=PENDIENTE&page=1&pageSize=20" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Ejemplo 2: Actualizar Homologación

```bash
curl -X PUT "http://localhost:8000/api/homologaciones-sku/uuid-123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sku_sap": "SKU001-SAP",
    "precio_unitario_sap": 105.00,
    "estado": "HOMOLOGADO"
  }'
```

### Ejemplo 3: Sincronizar Homologaciones

```bash
curl -X POST "http://localhost:8000/api/homologaciones-sku/sincronizar" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Ejemplo 4: Actualización Masiva

```bash
curl -X POST "http://localhost:8000/api/homologaciones-sku/bulk-update" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "updates": [
      {
        "homologacion_id": "uuid-123",
        "data": {"estado": "HOMOLOGADO"}
      },
      {
        "homologacion_id": "uuid-456",
        "data": {"estado": "HOMOLOGADO"}
      }
    ]
  }'
```

### Ejemplo 5: Buscar por SKU

```bash
curl -X GET "http://localhost:8000/api/homologaciones-sku?sku=SKU001&page=1" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Manejo de Errores

### Códigos HTTP

- `200` - Éxito
- `400` - Error de validación
- `401` - No autenticado
- `403` - Sin permisos
- `404` - Homologación no encontrada
- `500` - Error interno del servidor

### Formato de Error

```json
{
  "status": "error",
  "message": "Descripción del error",
  "error_code": "ERROR_CODE_OPCIONAL",
  "details": {}
}
```

---

## Testing

### Pruebas Unitarias

```bash
# Ejecutar tests
pytest tests/test_repositories/test_homologacion_repository.py
pytest tests/test_services/test_homologacion_service.py
pytest tests/test_endpoints/test_homologaciones_sku.py
```

### Pruebas de Integración

```bash
# Ejecutar prueba completa de sincronización
curl -X POST "http://localhost:8000/api/homologaciones-sku/sincronizar" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Verificar resultados
curl -X GET "http://localhost:8000/api/homologaciones-sku?page=1&pageSize=10" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Mejoras Futuras

1. **Historial de cambios**: Tabla de auditoría para cambios en homologaciones
2. **Notificaciones**: Alertas cuando se detectan nuevas diferencias
3. **Validación automática**: Reglas de validación configurables
4. **Exportación**: Exportar homologaciones a Excel/CSV
5. **Dashboard**: Visualización de estadísticas y métricas
6. **API de búsqueda avanzada**: Búsquedas más complejas con filtros combinados

---

## Soporte

Para reportar bugs o solicitar features:
- **Email**: soporte@empresa.com
- **Documentación**: `/docs/HOMOLOGACIONES_SKU.md`
- **API Docs**: `http://localhost:8000/docs` (Swagger UI)

---

**Última actualización**: Diciembre 2024
**Versión**: 1.0.0


















