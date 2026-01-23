# Permisos y Capabilities - Arquitectura y Transición

## 📋 Resumen

Este documento describe la arquitectura de permisos y capabilities del sistema, incluyendo la estrategia de transición de permisos legacy a permisos específicos por intención de negocio.

---

## 🎯 Principio de Diseño

### Regla Mental Única

> **La UI no depende del usuario ni del modo, depende de capacidades.**
>
> **Si una capacidad no existe, el botón no existe.**

No se deshabilita, no se oculta por CSS, no se valida por nombre de empresa.
**No se renderiza.**

### Principio de Capabilities

**Una capability = una intención de negocio específica.**

Cada capability mapea a un permiso específico, no a permisos genéricos. Esto permite:
- ✅ Expresar casos de uso complejos (ej: puede subir Excel pero no operar pedidos)
- ✅ Escalar sin hacks cuando aparezcan nuevos actores
- ✅ Mantener semántica clara en el código

---

## 🔐 Modelo de Permisos

### Permisos Específicos (Recomendado)

Los permisos deben ser específicos por intención de negocio:

| Permiso | Intención | Endpoints Relacionados |
|---------|-----------|------------------------|
| `mba3-consultas.plantillas.upload` | Subir plantillas Excel | `POST /api/plantillas/upload` |
| `mba3-consultas.plantillas.view` | Ver plantillas y pedidos | `GET /api/plantillas/ultimo`, `GET /api/plantillas/{identificador}` |
| `mba3-consultas.pedidos.operate` | Operar pedidos (redistribuir, confirmar, exportar) | `POST /api/pedidos/{id}/redistribuir`, `POST /api/pedidos/{id}/confirmar` |

### Permisos Legacy (En Transición)

Durante la transición, se mantiene compatibilidad con permisos legacy:

| Permiso Legacy | Permiso Específico Equivalente | Estado |
|----------------|-------------------------------|--------|
| `mba3-consultas.proceso.execute` | `mba3-consultas.plantillas.upload`<br>`mba3-consultas.pedidos.operate` | ⚠️ Deprecado, usar específicos |
| `mba3-consultas.facturas.view` | `mba3-consultas.plantillas.view` | ⚠️ Deprecado, usar específicos |

---

## 🎨 Capabilities

Las capabilities son booleanos simples que el frontend usa para decidir qué UI mostrar.

### Capabilities Definidas

| Capability | Permiso Específico | Descripción |
|------------|-------------------|-------------|
| `can_upload_templates` | `mba3-consultas.plantillas.upload` | Puede subir plantillas Excel |
| `can_view_templates` | `mba3-consultas.plantillas.view` | Puede ver plantillas y pedidos |
| `can_operate_pedidos` | `mba3-consultas.pedidos.operate` | Puede operar pedidos (redistribuir, confirmar, exportar) |

### Mapeo de Permisos a Capabilities

El mapeo se realiza en `src/endpoints/auth.py` en la función `_map_permissions_to_capabilities()`.

**Lógica:**
1. Si el usuario es `Admin` → todas las capabilities son `true`
2. Si tiene el permiso específico → capability es `true`
3. Si no tiene el específico pero tiene el legacy (backward compatibility) → capability es `true` (con warning en logs)

---

## 🔄 Estrategia de Transición

### Fase 1: Backward Compatibility (Actual)

**Estado:** ✅ Implementado

- Los endpoints aceptan tanto permisos específicos como legacy
- Las capabilities mapean a permisos específicos, con fallback a legacy
- Se emiten warnings en logs cuando se usa permiso legacy

**Ejemplo de uso en endpoints:**
```python
@app.post("/api/plantillas/upload")
async def upload_plantilla(
    user: Dict = Depends(verify_jwt_token),
    _: None = Depends(require_permission(
        'mba3-consultas.plantillas.upload',  # Permiso específico
        legacy_permission='mba3-consultas.proceso.execute'  # Backward compat
    ))
):
    ...
```

### Fase 2: Migración en el Core (Pendiente)

**Acción requerida:** Actualizar permisos en SCNexus.Core

- Asignar `mba3-consultas.plantillas.upload` a usuarios MABEL TRADING
- Asignar `mba3-consultas.pedidos.operate` a usuarios EL RAYO
- Asignar `mba3-consultas.plantillas.view` a ambos

### Fase 3: Remover Backward Compatibility (Futuro)

**⚠️ FECHA DE MUERTE DEL LEGACY: Q2 2026 (30 de junio de 2026)**

Una vez que todos los usuarios tengan permisos específicos:

1. Remover parámetro `legacy_permission` de `require_permission()`
2. Remover lógica de fallback en `_map_permissions_to_capabilities()`
3. Actualizar documentación
4. Remover warnings de backward compatibility

**Criterio de eliminación:**
- ✅ Todos los usuarios tienen permisos específicos asignados en el Core
- ✅ No se detectan usos de permisos legacy en logs durante 30 días
- ✅ Métricas muestran 0% de uso de permisos legacy

**Acción requerida antes de la fecha:**
- Migrar todos los usuarios a permisos específicos en SCNexus.Core
- Verificar que tokens JWT incluyan solo permisos específicos
- Monitorear logs para confirmar ausencia de uso legacy

---

## 📊 Casos de Uso por Usuario

### MABEL TRADING

| Capability | Valor | Permiso Requerido |
|------------|-------|-------------------|
| `can_upload_templates` | ✅ `true` | `mba3-consultas.plantillas.upload` |
| `can_view_templates` | ✅ `true` | `mba3-consultas.plantillas.view` |
| `can_operate_pedidos` | ❌ `false` | `mba3-consultas.pedidos.operate` |

### EL RAYO

| Capability | Valor | Permiso Requerido |
|------------|-------|-------------------|
| `can_upload_templates` | ❌ `false` | `mba3-consultas.plantillas.upload` |
| `can_view_templates` | ✅ `true` | `mba3-consultas.plantillas.view` |
| `can_operate_pedidos` | ✅ `true` | `mba3-consultas.pedidos.operate` |

### Admin

| Capability | Valor | Permiso Requerido |
|------------|-------|-------------------|
| Todas | ✅ `true` | N/A (override por rol) |

---

## 🔌 Endpoint `/api/auth/me`

### Descripción

Endpoint único que retorna información del usuario autenticado, incluyendo capabilities.

**Ruta:** `GET /api/auth/me`

**Headers requeridos:**
- `Authorization: Bearer {token}`

**Respuesta (200):**
```json
{
  "user": {
    "id": "123",
    "username": "juan.perez",
    "email": "juan@example.com"
  },
  "roles": ["EL_RAYO_OPERADOR"],
  "permissions": [
    "mba3-consultas.plantillas.view",
    "mba3-consultas.pedidos.operate"
  ],
  "capabilities": {
    "can_upload_templates": false,
    "can_view_templates": true,
    "can_operate_pedidos": true
  }
}
```

### Uso en Frontend

El frontend debe:
1. Llamar a `/api/auth/me` al iniciar la app
2. Guardar `capabilities` en el contexto de autenticación
3. Usar capabilities para renderizar botones condicionalmente

**Ejemplo (React/TypeScript):**
```tsx
const { capabilities } = useAuth();

// ✅ CORRECTO: Renderizar condicionalmente
{capabilities.can_upload_templates && (
  <Button onClick={handleUploadExcel}>
    Cargar Plantillas Excel
  </Button>
)}

// ❌ INCORRECTO: No hacer esto
{modo === 'el-rayo' && <Button disabled={true}>...</Button>}
```

---

## 🛡️ Validación en Endpoints

### Función `require_permission()`

**Ubicación:** `src/security/jwt_auth.py`

**Uso:**
```python
@app.post("/api/plantillas/upload")
async def upload_plantilla(
    user: Dict = Depends(verify_jwt_token),
    _: None = Depends(require_permission(
        'mba3-consultas.plantillas.upload',
        legacy_permission='mba3-consultas.proceso.execute'
    ))
):
    ...
```

**Comportamiento:**
1. Verifica si el usuario es `Admin` → acceso permitido
2. Verifica permiso específico → acceso permitido si existe
3. Si no tiene específico pero tiene legacy → acceso permitido (con warning)
4. Si no tiene ninguno → acceso denegado (403)

---

## 📝 Checklist de Migración

### Backend (✅ Completado)

- [x] Endpoint `/api/auth/me` implementado
- [x] Función `_map_permissions_to_capabilities()` con permisos específicos
- [x] Backward compatibility en `require_permission()`
- [x] Endpoints de plantillas actualizados
- [x] Documentación creada

### Core (⏳ Pendiente)

- [ ] Definir permisos específicos en SCNexus.Core
- [ ] Asignar `mba3-consultas.plantillas.upload` a MABEL TRADING
- [ ] Asignar `mba3-consultas.pedidos.operate` a EL RAYO
- [ ] Asignar `mba3-consultas.plantillas.view` a ambos
- [ ] Verificar que tokens JWT incluyan permisos específicos

### Frontend (⏳ Pendiente)

- [ ] Implementar llamada a `/api/auth/me` al iniciar app
- [ ] Guardar capabilities en contexto de autenticación
- [ ] Actualizar componentes para usar capabilities (no modo/identidad)
- [ ] Remover lógica basada en `modo === 'el-rayo'` o nombre de empresa

### Limpieza Futura (⏳ Pendiente)

- [ ] Remover backward compatibility una vez migrados todos los usuarios
- [ ] Actualizar todos los endpoints para usar solo permisos específicos
- [ ] Remover permisos legacy del código

---

## 🚨 Advertencias Importantes

1. **No usar permisos genéricos para capabilities específicas**
   - ❌ `can_upload_templates` → `proceso.execute`
   - ✅ `can_upload_templates` → `plantillas.upload`

2. **No validar por identidad o modo en el frontend**
   - ❌ `if (modo === 'el-rayo') { ... }`
   - ✅ `if (capabilities.can_operate_pedidos) { ... }`

3. **No deshabilitar botones, no renderizarlos**
   - ❌ `<Button disabled={!canUpload}>`
   - ✅ `{canUpload && <Button>}`

---

## 📚 Referencias

- **Endpoint de auth:** `src/endpoints/auth.py`
- **Validación de permisos:** `src/security/jwt_auth.py`
- **Endpoints de plantillas:** `src/endpoints/plantillas.py`
- **Documentación de seguridad:** `docs/SEGURIDAD.md`

---

---

## 📊 Métricas y Monitoreo

### Métricas Recomendadas

Para monitorear la transición de permisos legacy a específicos:

1. **Porcentaje de uso de permisos legacy:**
   - Contar requests que usan `legacy_permission` en `require_permission()`
   - Objetivo: 0% antes de Q2 2026

2. **Usuarios con permisos específicos:**
   - Contar usuarios que tienen permisos específicos en tokens JWT
   - Objetivo: 100% antes de Q2 2026

3. **Warnings de backward compatibility:**
   - Monitorear logs con `[BACKWARD COMPAT]`
   - Objetivo: 0 warnings antes de remover legacy

### Logs de Ejemplo

```
⚠️ [BACKWARD COMPAT] Usuario juan.perez tiene permiso legacy 'mba3-consultas.proceso.execute' 
   pero no tiene 'mba3-consultas.plantillas.upload'. Considerar migrar permisos en el Core.
```

---

## ✅ Checklist de Producción

### Arquitectura (✅ Completado)

- [x] Endpoint `/api/auth/me` implementado
- [x] Capabilities mapean a permisos específicos (no genéricos)
- [x] Backward compatibility con fecha de muerte definida
- [x] Documentación completa
- [x] Validación de múltiples capabilities simultáneas
- [x] Separación clara AD/Core/API/Frontend

### Frontend (⏳ Pendiente - Validar)

- [ ] Frontend usa SOLO `capabilities` (no `permissions` ni `roles`)
- [ ] No hay lógica basada en `modo === 'el-rayo'`
- [ ] No hay validación por nombre de usuario o empresa
- [ ] Cada botón depende de UNA capability independiente
- [ ] UI soporta usuarios con múltiples capabilities

### Core (⏳ Pendiente)

- [ ] Permisos específicos definidos en SCNexus.Core
- [ ] Usuarios migrados a permisos específicos
- [ ] Tokens JWT incluyen solo permisos específicos

### Limpieza (⏳ Pendiente - Q2 2026)

- [ ] Remover backward compatibility
- [ ] Remover parámetro `legacy_permission`
- [ ] Actualizar todos los endpoints
- [ ] Remover permisos legacy del código

---

**Última actualización:** 2026-01-23
**Estado:** Fase 1 (Backward Compatibility) - ✅ Implementado
**Fecha de muerte legacy:** Q2 2026 (30 de junio de 2026)
