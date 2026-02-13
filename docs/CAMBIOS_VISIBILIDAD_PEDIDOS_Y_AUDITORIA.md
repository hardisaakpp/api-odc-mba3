# Cambios: Visibilidad de Pedidos y Campos de Auditoría Legibles

**Fecha:** 2026-02-13  
**Autor:** Sistema  
**Referencia:** Mejora de visibilidad compartida y legibilidad de auditoría

---

## 📋 Resumen de Cambios

Esta actualización incluye dos mejoras principales:

1. **Visibilidad compartida de pedidos** en la página cargar-plantilla
2. **Campos de auditoría legibles** (email/username en lugar de UUID)

---

## 1. Visibilidad Compartida de Pedidos

### ✅ Problema Resuelto

**Antes:** Los usuarios con permiso `mabel.view` solo veían los pedidos que ellos mismos creaban en la página `/mba3-consultas/cargar-plantilla`.

**Después:** Todos los usuarios con permiso `mabel.view` ven **todos los pedidos** (incluyendo BORRADOR), sin importar quién los creó.

### 📝 Cambios Implementados

#### 1.1. Endpoint `GET /api/plantillas/pedidos`

**Archivo:** `src/endpoints/plantillas.py` (línea 425)

```python
# ANTES
resultado = repo.get_pedidos_con_filtros(
    creado_por=user_id,  # Solo pedidos del usuario actual
    ...
)

# DESPUÉS
resultado = repo.get_pedidos_con_filtros(
    creado_por=None,  # Todos los pedidos, sin filtrar por usuario
    ...
)
```

#### 1.2. Endpoint `GET /api/plantillas/buscar`

**Archivo:** `src/endpoints/plantillas.py` (línea 696)

```python
# ANTES
resultado = repo.get_pedidos_con_filtros(
    creado_por=user_id,  # Solo pedidos del usuario actual
    ...
)

# DESPUÉS
resultado = repo.get_pedidos_con_filtros(
    creado_por=None,  # Todos los pedidos, sin filtrar por usuario
    ...
)
```

### 🎯 Impacto

- ✅ Usuarios AD pueden ver pedidos creados por admin
- ✅ Admin puede ver pedidos creados por usuarios AD
- ✅ Usuarios AD pueden ver pedidos de otros usuarios AD
- ✅ Visibilidad completa desde estado BORRADOR
- ✅ Facilita trabajo colaborativo en equipos

---

## 2. Campos de Auditoría Legibles

### ✅ Problema Resuelto

**Antes:** Los campos `creado_por` y `modificado_por` mostraban UUIDs ilegibles:
```
c4ba7535-1e65-4009-86d3-0a7b09c44bc6
```

**Después:** Muestran información legible (email o username):
```
juan.perez@empresa.com
admin
```

### 📝 Cambios Implementados

#### 2.1. Función `get_user_id()`

**Archivo:** `src/endpoints/pedidos/utils.py` (líneas 43-67)

```python
# ANTES (priorizaba UUID)
user_id = user.get('id') or user.get('username')

# DESPUÉS (prioriza legibilidad)
user_id = (
    user.get('email') or      # PRIMERO: Email (usuarios AD)
    user.get('username') or   # SEGUNDO: Username (usuarios no-AD)
    user.get('id')            # ÚLTIMO RECURSO: UUID
)
```

#### 2.2. Función `get_username_from_user()`

**Archivo:** `src/utils/audit_context.py` (líneas 159-181)

```python
# ANTES
username = (
    user.get("username") or
    user.get("name") or
    user.get("sub") or
    user.get("user_id") or
    user.get("id")  # Retornaba UUID
)

# DESPUÉS
username = (
    user.get("email") or      # PRIMERO: Email
    user.get("username") or   
    user.get("name") or       
    user.get("sub") or        
    user.get("user_id") or    
    user.get("id")            # Último recurso
)
```

### 🎯 Impacto

| Tipo de Usuario | Email | Username | Valor en `creado_por` |
|----------------|-------|----------|----------------------|
| Usuario AD | ✅ `juan.perez@empresa.com` | ✅ Sí | `juan.perez@empresa.com` |
| Usuario admin | ❌ No | ✅ `admin` | `admin` |
| Usuario con ambos | ✅ `admin@empresa.com` | ✅ `admin` | `admin@empresa.com` |

### ⚠️ Compatibilidad con Datos Existentes

- Los registros existentes **conservan** sus valores actuales (UUIDs)
- Solo los **nuevos registros** y **modificaciones futuras** usarán email/username
- No se requieren migraciones de datos

---

## 📚 Documentación Actualizada

Se actualizaron los siguientes archivos de documentación:

### 1. `docs/FRONTEND.md`

**Cambios:**
- Actualizada tabla de diferencias entre `/api/pedidos` y `/api/plantillas/pedidos`
- Corregida descripción de filtrado por usuario (ahora ambos NO filtran)
- Agregada nota sobre visibilidad compartida para trabajo colaborativo
- Actualizado comportamiento del endpoint `/api/plantillas/buscar`

### 2. `docs/BUENAS_PRACTICAS_SQL.md`

**Cambios:**
- Actualizado comentario de campos `creado_por` y `modificado_por` en template
- Agregada sección explicativa sobre formato de campos de auditoría
- Documentado orden de prioridad (email → username → UUID)
- Incluidos ejemplos de valores almacenados

### 3. `src/utils/audit_context.py`

**Cambios:**
- Actualizado docstring del módulo
- Agregada nota sobre priorización de información legible
- Documentado comportamiento para usuarios AD vs locales

---

## 🧪 Pruebas Recomendadas

### Visibilidad de Pedidos

1. **Usuario admin carga plantilla** → Verificar que usuarios AD lo vean en la lista
2. **Usuario AD carga plantilla** → Verificar que admin y otros usuarios AD lo vean
3. **Búsqueda por número** → Verificar que encuentre pedidos de cualquier usuario
4. **Estado BORRADOR** → Verificar que sea visible para todos los usuarios con `mabel.view`

### Campos de Auditoría

1. **Crear pedido con usuario AD** → Verificar que `creado_por` muestre email
2. **Modificar pedido con usuario admin** → Verificar que `modificado_por` muestre "admin"
3. **Ver pedidos existentes** → Verificar que UUIDs antiguos se conserven

---

## 📌 Notas Importantes

### Servidor

- ✅ El servidor recarga automáticamente con uvicorn --reload
- ✅ No requiere reinicio manual
- ✅ Los cambios están activos inmediatamente

### Frontend

- ⚠️ Si no se ven los cambios, limpiar caché del navegador (Ctrl+F5)
- ⚠️ Verificar que las llamadas al API no tengan caché activo
- ✅ Abrir DevTools → Network → "Disable cache" para desarrollo

### Base de Datos

- ✅ No requiere migraciones
- ✅ Esquema existente es compatible
- ✅ Datos existentes se conservan sin cambios

---

## 🔍 Archivos Modificados

```
src/endpoints/plantillas.py              (2 cambios: líneas 425, 696)
src/endpoints/pedidos/utils.py           (1 cambio: función get_user_id)
src/utils/audit_context.py               (2 cambios: docstring + get_username_from_user)
docs/FRONTEND.md                         (2 secciones actualizadas)
docs/BUENAS_PRACTICAS_SQL.md             (2 secciones actualizadas)
docs/CAMBIOS_VISIBILIDAD_PEDIDOS_Y_AUDITORIA.md  (nuevo archivo)
```

---

## 📞 Soporte

Para preguntas o problemas relacionados con estos cambios, contactar al equipo de desarrollo.

---

**Estado:** ✅ Completado  
**Versión:** 1.0  
**Última actualización:** 2026-02-13
