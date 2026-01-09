# Implementación de Preferencias de Usuario - Backend

## ✅ Estado: Implementado

Se ha implementado el sistema completo de preferencias de usuario en el backend de Python/FastAPI.

---

## 📋 Archivos Creados/Modificados

### 1. Modelos Pydantic
**Archivo:** `src/models.py`
- ✅ Agregados modelos: `TablePreferencesDto`, `SavePreferencesRequest`, `PreferencesResponse`, `AllPreferencesResponse`

### 2. Repositorio
**Archivo:** `src/database/repositories/user_preferences_repository.py`
- ✅ Implementado `UserPreferencesRepository` con métodos:
  - `get_table_preferences()` - Obtener preferencias de una tabla
  - `save_table_preferences()` - Guardar/actualizar preferencias
  - `get_all_preferences()` - Obtener todas las preferencias del usuario
  - `delete_table_preferences()` - Eliminar preferencias

### 3. Endpoints
**Archivo:** `src/endpoints/user_preferences.py`
- ✅ Implementados 4 endpoints:
  - `GET /api/users/preferences/{table_id}` - Obtener preferencias
  - `POST /api/users/preferences/{table_id}` - Guardar preferencias
  - `GET /api/users/preferences` - Obtener todas las preferencias
  - `DELETE /api/users/preferences/{table_id}` - Eliminar preferencias

### 4. Registro de Endpoints
**Archivo:** `src/endpoints/__init__.py`
- ✅ Agregado registro de `register_user_preferences_endpoints()`

### 5. Script SQL
**Archivo:** `scripts/create_user_preferences_table.sql`
- ✅ Script para crear la tabla `UserPreferences` en SQL Server

---

## 🚀 Pasos para Completar la Implementación

### Paso 1: Crear la Tabla en SQL Server

Ejecutar el script SQL:

```bash
# Opción 1: Desde SQL Server Management Studio
# Abrir scripts/create_user_preferences_table.sql y ejecutar

# Opción 2: Desde línea de comandos (sqlcmd)
sqlcmd -S tu_servidor -d tu_base_de_datos -i scripts/create_user_preferences_table.sql
```

El script creará:
- Tabla `UserPreferences` con todos los campos necesarios
- Índices para mejorar rendimiento
- Constraint único `(UserId, TableId)`

### Paso 2: Verificar Configuración JWT

Asegurar que en `.env` estén configurados los valores correctos:

```env
JWT_SECRET=clave_super_secreta_para_jwt_12345  # DEBE coincidir con Core
JWT_ISSUER=SCNexus.Core                         # DEBE coincidir con Core
JWT_AUDIENCE=SCNexus.Users                      # DEBE coincidir con Core
ENABLE_JWT_AUTH=true                            # Habilitar autenticación JWT
```

### Paso 3: Reiniciar el Servidor

```bash
# Detener el servidor actual (Ctrl+C)
# Reiniciar
python src/api_server.py
```

### Paso 4: Probar los Endpoints

#### 4.1 Obtener Preferencias (sin preferencias existentes)

```bash
curl -X GET "http://localhost:8000/api/users/preferences/despachos" \
  -H "Authorization: Bearer {tu_token_jwt}" \
  -H "Content-Type: application/json"
```

**Respuesta esperada:**
```json
{
  "preferences": null
}
```

#### 4.2 Guardar Preferencias

```bash
curl -X POST "http://localhost:8000/api/users/preferences/despachos" \
  -H "Authorization: Bearer {tu_token_jwt}" \
  -H "Content-Type: application/json" \
  -d '{
    "preferences": {
      "visibleColumns": ["codigo_factura", "numero_factura", "empresa"],
      "columnOrder": ["codigo_factura", "empresa", "numero_factura"],
      "filters": {},
      "pageSize": 10
    }
  }'
```

**Respuesta esperada:**
```json
{
  "success": true,
  "message": "Preferencias guardadas correctamente"
}
```

#### 4.3 Obtener Preferencias (con preferencias existentes)

```bash
curl -X GET "http://localhost:8000/api/users/preferences/despachos" \
  -H "Authorization: Bearer {tu_token_jwt}" \
  -H "Content-Type: application/json"
```

**Respuesta esperada:**
```json
{
  "preferences": {
    "visibleColumns": ["codigo_factura", "numero_factura", "empresa"],
    "columnOrder": ["codigo_factura", "empresa", "numero_factura"],
    "filters": {},
    "pageSize": 10
  }
}
```

#### 4.4 Obtener Todas las Preferencias

```bash
curl -X GET "http://localhost:8000/api/users/preferences" \
  -H "Authorization: Bearer {tu_token_jwt}" \
  -H "Content-Type: application/json"
```

#### 4.5 Eliminar Preferencias

```bash
curl -X DELETE "http://localhost:8000/api/users/preferences/despachos" \
  -H "Authorization: Bearer {tu_token_jwt}"
```

---

## 📝 Endpoints Disponibles

### GET `/api/users/preferences/{table_id}`
Obtiene las preferencias de una tabla específica.

**Parámetros:**
- `table_id`: `despachos`, `ordenes-compra`, o `historial-ordenes`

**Headers:**
- `Authorization: Bearer {token}` (requerido)

**Respuesta:**
- `200 OK`: `{"preferences": {...}}` o `{"preferences": null}`

---

### POST `/api/users/preferences/{table_id}`
Guarda o actualiza las preferencias de una tabla.

**Parámetros:**
- `table_id`: `despachos`, `ordenes-compra`, o `historial-ordenes`

**Headers:**
- `Authorization: Bearer {token}` (requerido)
- `Content-Type: application/json` (requerido)

**Body:**
```json
{
  "preferences": {
    "visibleColumns": ["col1", "col2"],
    "columnOrder": ["col1", "col2"],
    "filters": {},
    "pageSize": 10
  }
}
```

**Respuesta:**
- `200 OK`: `{"success": true, "message": "Preferencias guardadas correctamente"}`

---

### GET `/api/users/preferences`
Obtiene todas las preferencias del usuario.

**Headers:**
- `Authorization: Bearer {token}` (requerido)

**Respuesta:**
- `200 OK`: `{"preferences": {"table_id": {...}, ...}}`

---

### DELETE `/api/users/preferences/{table_id}`
Elimina las preferencias de una tabla.

**Parámetros:**
- `table_id`: `despachos`, `ordenes-compra`, o `historial-ordenes`

**Headers:**
- `Authorization: Bearer {token}` (requerido)

**Respuesta:**
- `200 OK`: `{"success": true, "message": "Preferencias eliminadas correctamente"}`
- `404 Not Found`: Si no existen preferencias

---

## 🔒 Seguridad

- ✅ Todos los endpoints requieren autenticación JWT
- ✅ El `UserId` se extrae del token JWT automáticamente
- ✅ Solo el usuario puede acceder a sus propias preferencias
- ✅ Validación de `table_id` (solo valores permitidos)

---

## ✅ Valores de tableId Permitidos

- `despachos` - Tabla de despachos disponibles
- `ordenes-compra` - Tabla de órdenes de compra generadas
- `historial-ordenes` - Tabla de historial/logs de órdenes
- `remisiones` - Tabla de documentos de remisión
- `productos-pedido` - Tabla de productos del pedido (detalle de pedidos)

---

## 🐛 Troubleshooting

### Error: "No se pudo obtener el ID del usuario del token"
- Verificar que el token JWT sea válido
- Verificar que `JWT_SECRET`, `JWT_ISSUER`, `JWT_AUDIENCE` coincidan con el Core
- Verificar que el claim `nameidentifier` esté presente en el token

### Error: "tableId inválido"
- Verificar que el `table_id` sea uno de: `despachos`, `ordenes-compra`, `historial-ordenes`, `remisiones`, `productos-pedido`

### Error: "Error al guardar preferencias"
- Verificar que la tabla `UserPreferences` exista en SQL Server
- Verificar conexión a SQL Server
- Revisar logs del servidor para más detalles

### Error: CORS
- Verificar que `ENABLE_CORS_RESTRICTION=false` en desarrollo
- O configurar `CORS_ALLOWED_ORIGINS` con el origen del frontend

---

## 📚 Documentación Adicional

- Ver `docs/JWT_AUTHENTICATION.md` para detalles de autenticación
- Ver `docs/CONFIGURACION.md` para configuración general
- Ver `docs/ENDPOINTS.md` para documentación de otros endpoints

---

## ✨ Próximos Pasos

1. ✅ Backend implementado
2. ⏳ Ejecutar script SQL para crear tabla
3. ⏳ Probar endpoints con Postman/Thunder Client
4. ⏳ Frontend ya está preparado y funcionará automáticamente cuando los endpoints estén disponibles

---

## 📝 Notas

- El prefijo `/api/users/preferences` está configurado en los endpoints
- Los datos se almacenan como JSON en SQL Server (campos `NVARCHAR(MAX)`)
- El formato de respuesta coincide exactamente con lo esperado por el frontend
- El sistema funciona de forma híbrida: localStorage en el frontend + sincronización con backend





