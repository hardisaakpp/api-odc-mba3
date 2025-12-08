# Autenticación JWT - Integración con SCNexus.Core

Este documento explica cómo usar la autenticación JWT para integrar el módulo backend con el Core de SCNexus.

## 📋 Configuración

### 1. Variables de Entorno

Agrega estas variables a tu archivo `.env`:

```env
# JWT Configuration (DEBE coincidir con appsettings.json del Core)
JWT_SECRET=clave_super_secreta_para_jwt_12345
JWT_ISSUER=SCNexus.Core
JWT_AUDIENCE=SCNexus.Users

# Habilitar autenticación JWT (opcional, por defecto false)
ENABLE_JWT_AUTH=false
```

⚠️ **IMPORTANTE**: Los valores de `JWT_SECRET`, `JWT_ISSUER` y `JWT_AUDIENCE` **DEBEN coincidir exactamente** con los configurados en `appsettings.json` del Core.

### 2. Instalar Dependencias

```bash
pip install -r requirements.txt
```

Esto instalará `PyJWT>=2.8.0` automáticamente.

## 🔐 Uso en Endpoints

### Endpoint Público (sin autenticación)

```python
@app.get("/health")
async def health_check():
    """Endpoint público, no requiere autenticación."""
    return {"status": "ok"}
```

### Endpoint con Autenticación JWT Requerida

```python
from security.jwt_auth import verify_jwt_token
from fastapi import Depends

@app.get("/facturas")
async def get_facturas(
    request: Request,
    user: dict = Depends(verify_jwt_token)  # ✅ Requiere JWT válido
):
    """
    Endpoint protegido que requiere token JWT válido.
    El usuario autenticado está disponible en el parámetro 'user'.
    """
    # Información del usuario disponible:
    # - user['id']: ID del usuario
    # - user['username']: Nombre de usuario
    # - user['email']: Email del usuario
    # - user['roles']: Lista de roles
    # - user['permissions']: Lista de permisos
    
    username = user.get('username')
    logger.info(f"Usuario autenticado: {username}")
    
    # Tu lógica aquí...
    return {"data": [...]}
```

### Endpoint con Autenticación JWT Opcional

```python
from security.jwt_auth import optional_jwt_auth

@app.get("/consultar")
async def consultar_despachos(
    request: Request,
    user: Optional[dict] = Depends(optional_jwt_auth)  # ✅ Opcional
):
    """
    Endpoint que funciona con o sin autenticación.
    Si hay token válido, 'user' contendrá la información del usuario.
    Si no hay token, 'user' será None.
    """
    if user:
        logger.info(f"Usuario autenticado: {user.get('username')}")
    else:
        logger.info("Acceso sin autenticación")
    
    # Tu lógica aquí...
    return {"data": [...]}
```

### Endpoint con Permiso Específico

```python
from security.jwt_auth import verify_jwt_token, require_permission
from fastapi import Depends

@app.get("/migrar")
async def migrar_despachos(
    request: Request,
    user: dict = Depends(verify_jwt_token),  # ✅ Requiere JWT válido
    _: None = Depends(require_permission('mba3_consultas.migrar'))  # ✅ Requiere permiso
):
    """
    Endpoint que requiere:
    1. Token JWT válido
    2. Permiso específico 'mba3_consultas.migrar'
    """
    # Tu lógica aquí...
    return {"status": "success"}
```

### Endpoint con Rol Específico

```python
from security.jwt_auth import verify_jwt_token, require_role
from fastapi import Depends

@app.get("/ordenes-compra")
async def get_ordenes_compra(
    request: Request,
    estado: Optional[str] = Query(None),
    user: dict = Depends(verify_jwt_token),  # ✅ Requiere JWT válido
    _: None = Depends(require_role('Admin'))  # ✅ Requiere rol Admin
):
    """
    Endpoint que requiere:
    1. Token JWT válido
    2. Rol 'Admin'
    """
    # Tu lógica aquí...
    return {"data": [...]}
```

## 🔑 Flujo Completo

1. **Frontend/Cliente** → `POST /api/auth/login` al Core
2. **Core** → Retorna JWT con roles y permisos
3. **Frontend/Cliente** → `GET /api/facturas` a tu módulo Python con `Authorization: Bearer <token>`
4. **Tu módulo** → Valida el token con la misma clave JWT
5. **Tu módulo** → Verifica permisos y ejecuta lógica

## 📝 Estructura del Token JWT

El token JWT contiene claims estándar de .NET Identity:

```json
{
  "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier": "user-id",
  "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": "username",
  "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": "user@example.com",
  "iss": "SCNexus.Core",
  "aud": "SCNexus.Users",
  "permission": ["mba3_consultas.view", "mba3_consultas.migrar"],
  "...": "otros claims"
}
```

## ✅ Funciones Disponibles

### `verify_jwt_token`
Valida y decodifica un token JWT. Lanza `HTTPException` si el token es inválido o falta.

**Uso**: `user: dict = Depends(verify_jwt_token)`

### `optional_jwt_auth`
Similar a `verify_jwt_token` pero retorna `None` si no hay token (no lanza excepción).

**Uso**: `user: Optional[dict] = Depends(optional_jwt_auth)`

### `require_permission(permission_key: str)`
Valida que el usuario tenga un permiso específico.

**Uso**: `_: None = Depends(require_permission('mba3_consultas.migrar'))`

### `require_role(role_name: str)`
Valida que el usuario tenga un rol específico.

**Uso**: `_: None = Depends(require_role('Admin'))`

## 🚫 Lo que NO necesitas

Tu módulo Python **NO necesita**:
- ❌ Base de datos de usuarios
- ❌ Endpoints de login/registro
- ❌ Gestión de permisos

Solo necesita:
- ✅ Validar el token JWT
- ✅ Leer roles/permisos del token
- ✅ Proteger endpoints

## 🔧 Registro de Permisos en el Core

Antes de usar permisos, debes registrarlos en el Core:

```bash
# Ejemplo: Registrar permiso para ver facturas
POST http://localhost:5000/api/permissions
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "key": "mba3_consultas.view",
  "description": "Ver facturas MBA3",
  "module": "mba3_consultas"
}

# Ejemplo: Registrar permiso para migrar
POST http://localhost:5000/api/permissions
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "key": "mba3_consultas.migrar",
  "description": "Migrar despachos a base de datos",
  "module": "mba3_consultas"
}
```

Luego, asigna permisos a roles:

```bash
POST http://localhost:5000/api/permissions/assign
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "roleName": "Ventas",
  "permissionId": 10
}
```

## 🧪 Pruebas

### Probar con curl

```bash
# 1. Obtener token del Core
TOKEN=$(curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user","password":"pass"}' \
  | jq -r '.token')

# 2. Usar token en tu módulo
curl -X GET http://localhost:8000/facturas \
  -H "Authorization: Bearer $TOKEN"
```

### Probar con Postman

1. Obtén un token JWT del Core (`POST /api/auth/login`)
2. En tu módulo, agrega header: `Authorization: Bearer <token>`
3. Realiza la petición al endpoint protegido

## ⚠️ Errores Comunes

### Token inválido (401)
- Verifica que `JWT_SECRET`, `JWT_ISSUER` y `JWT_AUDIENCE` coincidan con el Core
- Verifica que el token no haya expirado
- Verifica el formato del header: `Authorization: Bearer <token>`

### Permiso denegado (403)
- Verifica que el permiso esté registrado en el Core
- Verifica que el rol del usuario tenga el permiso asignado
- Verifica que el permiso esté incluido en el token JWT

### Token faltante (401)
- Verifica que el header `Authorization` esté presente
- Verifica el formato: `Bearer <token>` (con espacio entre "Bearer" y el token)











