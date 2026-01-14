# Endpoint: Obtener Último Pedido por Usuario

## 📋 Resumen

Nuevo endpoint que permite obtener automáticamente el último pedido cargado por el usuario autenticado. Diseñado para mostrar automáticamente el último Excel subido en la página de "cargar plantillas".

## 🎯 Objetivo

Permitir que la página `/mba3-consultas/cargar-plantillas` y el formulario de "Crear Pedido Manual" muestren automáticamente el último pedido cargado por el usuario (ya sea creado manualmente o cargado desde Excel), sin necesidad de buscar manualmente por número de pedido.

## 🔌 Endpoint

### `GET /api/plantillas/ultimo`

**Autenticación:** Requerida (JWT)  
**Permisos:** `mba3-consultas.facturas.view`

### Query Parameters

- `incluir_respuesta` (bool, opcional, default: `false`): Si `true`, incluye la respuesta del proveedor si existe

### Respuesta Exitosa (200)

**Formato:** Mismo formato exacto que `GET /api/plantillas/{identificador}` (directo, sin envolver):

```json
{
    "cabecera": {
        "pedido_id": "uuid-del-pedido",
        "numero_pedido": "P-12.48 - 12 - 2025",
        "fecha_pedido": "2025-01-21",
        "archivo_nombre": "pedido.xlsx",  // o "CREACION_MANUAL" para pedidos manuales
        "creado_por": "user123",
        "creado_en": "2025-01-21T10:30:00",
        ...
    },
    "detalles": [
        {
            "pedido_detalle_id": "...",
            "codigo_interno": "...",
            "tiendas": [...]
        }
    ],
    "respuesta_proveedor": {...}  // Solo si incluir_respuesta=true
}
```

**Nota importante:** La respuesta es **directa** (`{cabecera, detalles}`), NO está envuelta en `{status, data, mensaje}`. Esto permite que el frontend use el mismo código para procesar ambos endpoints.

### Respuesta Sin Pedidos (404)

HTTP Status: `404 Not Found`

```json
{
    "detail": "No hay pedidos cargados para este usuario"
}
```

## 🔒 Seguridad

- ✅ **Filtrado por usuario**: Cada usuario solo ve sus propios pedidos
- ✅ **Autenticación requerida**: JWT obligatorio
- ✅ **Permisos validados**: Requiere permiso de visualización
- ✅ **User ID normalizado**: Usa función helper `get_user_id()` para consistencia

## 🏗️ Implementación

### Backend

1. **Nuevo método en repositorio**: `PedidoRepository.get_ultimo_pedido(usuario_id)`
   - Filtra por `creado_por = usuario_id`
   - Ordena por `creado_en DESC`
   - Retorna el más reciente o `None`
   - **Funciona tanto para pedidos creados manualmente como para pedidos cargados desde Excel**
   - Ambos tipos se almacenan en la misma tabla `pedido` y se identifican por el campo `archivo_nombre`:
     - Pedidos manuales: `archivo_nombre = "CREACION_MANUAL"`
     - Pedidos Excel: `archivo_nombre = nombre_del_archivo.xlsx`

2. **Nuevo endpoint**: `GET /api/plantillas/ultimo`
   - Usa el mismo formato de respuesta que `GET /api/plantillas/{identificador}`
   - Reutiliza `get_pedido_completo()` para consistencia

3. **Función helper**: `get_user_id(user)`
   - Normaliza la obtención del ID del usuario
   - Valida que el usuario tenga ID válido
   - Evita bugs silenciosos con usuarios inválidos

### Base de Datos

**Índice optimizado**: `idx_pedido_usuario_fecha`
- Columna clave: `(creado_por, creado_en DESC)`
- Include: `pedido_id`
- Optimiza consultas de último pedido por usuario

**Script**: `scripts/add_index_pedido_usuario_fecha.sql`

## 📱 Uso en Frontend

### Ejemplo de implementación

```javascript
// Al montar el componente de cargar-plantillas
onMounted(async () => {
  if (!pedidoInicialCargado.value) {
    await cargarUltimoPedido();
  }
});

async function cargarUltimoPedido() {
  try {
    const response = await fetch('/api/plantillas/ultimo', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    
    if (response.status === 404) {
      // No hay pedidos, mostrar mensaje informativo
      mostrarMensaje('No hay pedidos cargados. Sube un Excel para comenzar.');
      pedidoInicialCargado.value = true;
      return;
    }
    
    if (response.ok) {
      const pedido = await response.json();
      // Usar el MISMO método que cuando se carga manualmente
      setPedidoData(pedido);
      pedidoInicialCargado.value = true;
      
      // Mostrar badge informativo (UX)
      mostrarBadge(`Mostrando último pedido: ${pedido.cabecera.numero_pedido}`);
    }
  } catch (error) {
    console.error('Error al cargar último pedido:', error);
    pedidoInicialCargado.value = true;
  }
}
```

### Consideraciones UX

1. **No sobreescribir búsquedas manuales**: Usar flag `pedidoInicialCargado` para evitar recargas automáticas después de búsquedas manuales
2. **Badge informativo**: Mostrar claramente que se está mostrando el último pedido
3. **Botón "Cargar nuevo Excel"**: Permitir al usuario cargar un nuevo archivo fácilmente

## ✅ Checklist de Pruebas

### Backend
- [ ] Usuario A sube Excel → `/ultimo` devuelve el suyo
- [ ] Usuario B entra → **NO ve** el de A
- [ ] Usuario sin pedidos → 404 limpio
- [ ] Usuario con 5 pedidos → devuelve el más reciente
- [ ] `incluir_respuesta=true` → incluye respuesta si existe

### Frontend
- [ ] Entro a la pantalla → veo último pedido
- [ ] Busco manualmente otro → no se sobrescribe
- [ ] Refresco la página → vuelve a cargar último
- [ ] Subo nuevo Excel → se muestra ese
- [ ] Creo pedido manual → al recargar se muestra ese
- [ ] Último pedido puede ser manual o Excel → funciona en ambos casos

## 🔄 Cambios Relacionados

### Archivos Modificados

1. `src/database/repositories/pedido_repository.py`
   - Agregado método `get_ultimo_pedido(usuario_id)`

2. `src/endpoints/plantillas.py`
   - Agregada función helper `get_user_id(user)`
   - Agregado endpoint `GET /api/plantillas/ultimo`
   - Normalizado uso de `user_id` en otros endpoints

3. `scripts/add_index_pedido_usuario_fecha.sql`
   - Nuevo script para crear índice optimizado

## 📚 Referencias

- Endpoint relacionado: `GET /api/plantillas/{identificador}`
- Repositorio: `PedidoRepository`
- Documentación de estructura: `docs/ESTRUCTURA_BD_PEDIDOS.md`

## 🎯 Próximos Pasos (Opcional)

- [ ] Endpoint para "últimos N pedidos" si se requiere historial
- [ ] Cache del último pedido por usuario (si el volumen crece)
- [ ] Métricas de uso del endpoint
