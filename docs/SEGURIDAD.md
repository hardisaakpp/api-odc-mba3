# Configuración de Seguridad

Este documento explica cómo activar las funcionalidades de seguridad de la aplicación.

## 🔒 Funcionalidades de Seguridad

Todas las funcionalidades de seguridad están **DESHABILITADAS por defecto** para mantener compatibilidad con el código existente. Puedes activarlas gradualmente según tus necesidades.

### Funcionalidades Disponibles

1. **Autenticación mediante API Keys** - Protege endpoints con API Keys
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

# Autenticación mediante API Keys
ENABLE_AUTH=false                    # true para habilitar autenticación
API_KEY=tu-api-key-secreta-aqui      # Requerida si ENABLE_AUTH=true

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

## 🔑 Autenticación (API Keys)

### Activar Autenticación

1. **Configurar en `.env`:**
```env
ENABLE_AUTH=true
API_KEY=mi-api-key-super-secreta-12345
```

2. **Usar en requests:**
```bash
# Con curl
curl -H "X-API-Key: mi-api-key-super-secreta-12345" \
     http://localhost:8000/consultar

# Con Postman
# Agregar header: X-API-Key = mi-api-key-super-secreta-12345
```

### Endpoints Protegidos

Cuando `ENABLE_AUTH=true`, estos endpoints requieren API Key:
- ✅ `GET /consultar`
- ✅ `GET /migrar`
- ✅ `GET /procesar-oc`
- ✅ `POST /integrar-sap`
- ✅ `GET /pruebas`

### Endpoints Públicos (sin autenticación)

Estos endpoints siempre son públicos:
- ✅ `GET /health` - Health check
- ✅ `GET /docs` - Swagger UI (si está habilitado)

### Comportamiento

- **Si `ENABLE_AUTH=false`**: Todos los endpoints funcionan sin autenticación (comportamiento actual)
- **Si `ENABLE_AUTH=true`**: Endpoints protegidos requieren `X-API-Key` header

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

### Fase 1: Desarrollo (Sin Seguridad)
```env
ENABLE_AUTH=false
ENABLE_RATE_LIMITING=false
ENABLE_CORS_RESTRICTION=false
ENVIRONMENT=development
```
✅ **Estado actual** - Todo funciona sin cambios

### Fase 2: Testing (Activar CORS)
```env
ENABLE_AUTH=false
ENABLE_RATE_LIMITING=false
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=http://localhost:5173
ENVIRONMENT=development
```
✅ **Protege contra CSRF** sin afectar funcionalidad

### Fase 3: Staging (Activar Rate Limiting)
```env
ENABLE_AUTH=false
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT=50/minute
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=https://staging.tu-dominio.com
ENVIRONMENT=staging
```
✅ **Protege contra abuso** sin requerir autenticación

### Fase 4: Producción (Todo Activado)
```env
ENABLE_AUTH=true
API_KEY=generar-api-key-segura-aqui
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT=100/minute
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=https://app.tu-dominio.com
ENVIRONMENT=production
HIDE_SWAGGER_IN_PROD=true
```
✅ **Máxima seguridad** - Listo para producción

---

## 🔧 Generar API Key Segura

### Opción 1: Python
```python
import secrets
api_key = secrets.token_urlsafe(32)
print(f"API_KEY={api_key}")
```

### Opción 2: OpenSSL
```bash
openssl rand -hex 32
```

### Opción 3: Online
Usa un generador de tokens seguros (ej: https://randomkeygen.com/)

---

## ⚠️ Notas Importantes

1. **Por Defecto Todo Está Deshabilitado**: La aplicación funciona igual que antes
2. **Activa Gradualmente**: No necesitas activar todo de una vez
3. **Prueba en Desarrollo**: Siempre prueba en desarrollo antes de producción
4. **Guarda API Keys Seguras**: Nunca subas API Keys al repositorio
5. **Health Check Siempre Público**: `/health` nunca requiere autenticación

---

## 🐛 Troubleshooting

### Error: "API Key requerida"
- Verifica que `ENABLE_AUTH=true` en `.env`
- Verifica que estás enviando el header `X-API-Key`
- Verifica que la API Key coincide con `API_KEY` en `.env`

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
ENABLE_AUTH=false
ENABLE_RATE_LIMITING=false
ENABLE_CORS_RESTRICTION=false
ENVIRONMENT=development
```
✅ Todo funciona sin autenticación

### Ejemplo 2: Testing con Frontend
```env
ENABLE_AUTH=false
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=http://localhost:5173
ENVIRONMENT=development
```
✅ Frontend puede conectarse, sin autenticación

### Ejemplo 3: Producción
```env
ENABLE_AUTH=true
API_KEY=sk_live_abc123xyz789...
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT=100/minute
ENABLE_CORS_RESTRICTION=true
CORS_ALLOWED_ORIGINS=https://app.tu-dominio.com
ENVIRONMENT=production
HIDE_SWAGGER_IN_PROD=true
```
✅ Máxima seguridad

