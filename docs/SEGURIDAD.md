# Configuración de Seguridad

Este documento explica cómo activar las funcionalidades de seguridad de la aplicación.

## 🔒 Funcionalidades de Seguridad

Todas las funcionalidades de seguridad están **DESHABILITADAS por defecto** para mantener compatibilidad con el código existente. Puedes activarlas gradualmente según tus necesidades.

### Funcionalidades Disponibles

1. **Autenticación JWT** - Integración con SCNexus.Core mediante tokens JWT
2. **Rate Limiting** - Limita el número de requests por tiempo
3. **CORS Restrictivo** - Limita orígenes permitidos
4. **Ocultar Swagger en Producción** - Oculta documentación en producción

---

## 📋 Configuración

### Variables de Entorno

Agrega estas variables a tu archivo `.env`:

```env
# ============================================================================
# CONFIGURACIÓN DE SEGURIDAD (Opcional)
# ============================================================================

# Autenticación JWT (integración con SCNexus.Core)
JWT_SECRET=clave_super_secreta_para_jwt_12345  # DEBE coincidir con Core
JWT_ISSUER=SCNexus.Core                        # DEBE coincidir con Core
JWT_AUDIENCE=SCNexus.Users                     # DEBE coincidir con Core
ENABLE_JWT_AUTH=false                          # true para habilitar JWT

# Rate Limiting
ENABLE_RATE_LIMITING=false           # true para habilitar rate limiting
RATE_LIMIT_DEFAULT=100/minute         # Límite por defecto (ej: "10/minute", "100/hour")

# CORS Restrictivo
ENABLE_CORS_RESTRICTION=false        # true para habilitar CORS restrictivo
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://tu-dominio.com  # Orígenes permitidos (separados por comas)

# Ambiente y Swagger
ENVIRONMENT=development               # development, staging, production
HIDE_SWAGGER_IN_PROD=true            # true para ocultar /docs en producción
```

---

## 🔐 Autenticación JWT (Integración con SCNexus.Core)

La autenticación JWT permite integrar el módulo backend con el Core de SCNexus usando tokens JWT estándar.

### Configuración

1. **Variables de Entorno:**
```env
# JWT Configuration (DEBE coincidir con appsettings.json del Core)
JWT_SECRET=clave_super_secreta_para_jwt_12345
JWT_ISSUER=SCNexus.Core
JWT_AUDIENCE=SCNexus.Users

# Habilitar autenticación JWT (opcional, por defecto false)
ENABLE_JWT_AUTH=false
```

⚠️ **IMPORTANTE**: Los valores de `JWT_SECRET`, `JWT_ISSUER` y `JWT_AUDIENCE` **DEBEN coincidir exactamente** con los configurados en `appsettings.json` del Core.

2. **Instalar Dependencias:**
```bash
pip install -r requirements.txt
```

Esto instalará `PyJWT>=2.8.0` automáticamente.

### Uso en Endpoints

#### Endpoint con Autenticación JWT Requerida

```python
from security.jwt_auth import verify_jwt_token
from fastapi import Depends

@app.get("/despachos/count")
async def get_despachos_count(
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
    
    return {"data": [...]}
```

#### Endpoint con Permiso Específico

```python
from security.jwt_auth import verify_jwt_token, require_permission

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
    return {"status": "success"}
```

### Flujo Completo

1. **Frontend/Cliente** → `POST /api/auth/login` al Core
2. **Core** → Retorna JWT con roles y permisos
3. **Frontend/Cliente** → `GET /api/despachos/count` a tu módulo Python con `Authorization: Bearer <token>`
4. **Tu módulo** → Valida el token con la misma clave JWT
5. **Tu módulo** → Verifica permisos y ejecuta lógica

### Estructura del Token JWT

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

### Funciones Disponibles

- **`verify_jwt_token`**: Valida y decodifica un token JWT. Lanza `HTTPException` si el token es inválido o falta.
  - Uso: `user: dict = Depends(verify_jwt_token)`

- **`require_permission(permission_key: str)`**: Valida que el usuario tenga un permiso específico. Los usuarios con rol 'Admin' tienen acceso automáticamente.
  - Uso: `_: None = Depends(require_permission('mba3_consultas.migrar'))`

### Registro de Permisos en el Core

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

### Pruebas

#### Probar con curl

```bash
# 1. Obtener token del Core
TOKEN=$(curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user","password":"pass"}' \
  | jq -r '.token')

# 2. Usar token en tu módulo
curl -X GET http://localhost:8000/despachos/count \
  -H "Authorization: Bearer $TOKEN"
```

#### Probar con Postman

1. Obtén un token JWT del Core (`POST /api/auth/login`)
2. En tu módulo, agrega header: `Authorization: Bearer <token>`
3. Realiza la petición al endpoint protegido

### Errores Comunes JWT

- **Token inválido (401)**: Verifica que `JWT_SECRET`, `JWT_ISSUER` y `JWT_AUDIENCE` coincidan con el Core
- **Permiso denegado (403)**: Verifica que el permiso esté registrado y asignado al rol del usuario
- **Token faltante (401)**: Verifica que el header `Authorization: Bearer <token>` esté presente

### Lo que NO necesitas

Tu módulo Python **NO necesita**:
- ❌ Base de datos de usuarios
- ❌ Endpoints de login/registro
- ❌ Gestión de permisos

Solo necesita:
- ✅ Validar el token JWT
- ✅ Leer roles/permisos del token
- ✅ Proteger endpoints

---

## ⏱️ Rate Limiting

### Activar Rate Limiting

1. **Instalar dependencia:**
```bash
pip install slowapi
```

2. **Configurar en `.env`:**
```env
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT=100/minute
```

### Formatos de Límite

- `100/minute` - 100 requests por minuto
- `10/second` - 10 requests por segundo
- `1000/hour` - 1000 requests por hora

### Respuesta cuando se excede el límite

```json
{
  "error": "Rate limit exceeded: 100 per 1 minute"
}
```

Status Code: `429 Too Many Requests`

---

## 🌐 CORS Restrictivo

### Activar CORS Restrictivo

1. **Configurar en `.env`:**
```env
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://tu-dominio.com
```

### Comportamiento

- **Si `ENABLE_CORS_RESTRICTION=false`**: Permite cualquier origen (desarrollo)
- **Si `ENABLE_CORS_RESTRICTION=true`**: Solo permite orígenes en `CORS_ALLOWED_ORIGINS`

### Ejemplo de Configuración

```env
# Desarrollo
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# Producción
CORS_ALLOWED_ORIGINS=https://app.tu-dominio.com,https://admin.tu-dominio.com
```

---

## 📚 Ocultar Swagger en Producción

### Configuración

```env
ENVIRONMENT=production
HIDE_SWAGGER_IN_PROD=true
```

### Comportamiento

- **Si `ENVIRONMENT=production` y `HIDE_SWAGGER_IN_PROD=true`**: 
  - `/docs` y `/redoc` retornan 404
- **En otros casos**: Swagger está disponible normalmente

---

## 🚀 Activación Gradual Recomendada

### Fase 1: Desarrollo (Sin Seguridad Adicional)
```env
ENABLE_JWT_AUTH=false
ENABLE_RATE_LIMITING=false
ENABLE_CORS_RESTRICTION=false
ENVIRONMENT=development
```
✅ **Estado actual** - Endpoints disponibles sin autenticación

### Fase 2: Testing (Activar CORS)
```env
ENABLE_JWT_AUTH=false
ENABLE_RATE_LIMITING=false
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=http://localhost:5173
ENVIRONMENT=development
```
✅ **Protege contra CSRF** sin afectar funcionalidad

### Fase 3: Staging (Activar Rate Limiting)
```env
ENABLE_JWT_AUTH=false
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT=50/minute
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=https://staging.tu-dominio.com
ENVIRONMENT=staging
```
✅ **Protege contra abuso** sin requerir autenticación

### Fase 4: Producción (JWT + Rate Limiting + CORS)
```env
ENABLE_JWT_AUTH=true
JWT_SECRET=clave_super_secreta_para_jwt_12345
JWT_ISSUER=SCNexus.Core
JWT_AUDIENCE=SCNexus.Users
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT=100/minute
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=https://app.tu-dominio.com
ENVIRONMENT=production
HIDE_SWAGGER_IN_PROD=true
```
✅ **Máxima seguridad** - JWT + Rate Limiting + CORS restrictivo

---

## ⚠️ Notas Importantes

1. **JWT es la forma de autenticación**: Solo JWT, no API Keys
2. **Activa Gradualmente**: No necesitas activar todo de una vez
3. **Prueba en Desarrollo**: Siempre prueba en desarrollo antes de producción
4. **Guarda Secretos Seguros**: Nunca subas JWT_SECRET al repositorio
5. **Health Check Siempre Público**: `/health` nunca requiere autenticación

---

## 🐛 Troubleshooting

### Error: "Rate limit exceeded"
- Aumenta `RATE_LIMIT_DEFAULT` en `.env`
- O deshabilita temporalmente: `ENABLE_RATE_LIMITING=false`

### CORS bloqueado
- Verifica que el origen está en `CORS_ALLOWED_ORIGINS`
- O deshabilita temporalmente: `ENABLE_CORS_RESTRICTION=false`

### Swagger no aparece
- Verifica que `ENVIRONMENT != "production"` o `HIDE_SWAGGER_IN_PROD=false`

---

## 📖 Ejemplos de Uso

### Ejemplo 1: Desarrollo Local
```env
# .env para desarrollo
ENABLE_JWT_AUTH=false
ENABLE_RATE_LIMITING=false
ENABLE_CORS_RESTRICTION=false
ENVIRONMENT=development
```
✅ Todo funciona sin autenticación JWT

### Ejemplo 2: Testing con Frontend
```env
ENABLE_JWT_AUTH=false
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=http://localhost:5173
ENVIRONMENT=development
```
✅ Frontend puede conectarse, sin autenticación JWT

### Ejemplo 3: Producción con SCNexus.Core
```env
ENABLE_JWT_AUTH=true
JWT_SECRET=clave_super_secreta_para_jwt_12345
JWT_ISSUER=SCNexus.Core
JWT_AUDIENCE=SCNexus.Users
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT=100/minute
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=https://app.tu-dominio.com
ENVIRONMENT=production
HIDE_SWAGGER_IN_PROD=true
```
✅ Máxima seguridad con integración JWT