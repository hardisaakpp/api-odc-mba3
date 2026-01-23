# Personalización y Preferencias de Usuario

Documentación sobre campos personalizables y preferencias del sistema.

---

## 1. Persistencia de Campos Modificados Manualmente

### 📋 Resumen

Permite registrar qué campos de `pedido_detalle` fueron modificados manualmente por el usuario, persisting esta información en la base de datos.

### 🎯 Objetivo

Permitir que el frontend sepa qué campos (`costo_doc_sin_iva`, `total`, `comentario`) fueron modificados manualmente, para resaltarlos visualmente.

### ✅ Ventajas de la solución Backend

- ✅ **Persiste entre navegadores/dispositivos:** Funciona en cualquier lugar donde inicie sesión
- ✅ **Auditoría completa:** Se rastrea qué campos fueron modificados y cuándo
- ✅ **Más robusto:** No se pierde al limpiar caché del navegador

### 🗄️ Diseño de Base de Datos

Se agregan tres campos booleanos en `pedido_detalle`:

```sql
ALTER TABLE pedido_detalle
ADD costo_modificado_manual BIT DEFAULT 0,
    total_modificado_manual BIT DEFAULT 0,
    comentario_modificado_manual BIT DEFAULT 0;
```

**Ventajas:**
- ✅ Simple y directo
- ✅ Fácil de consultar con índices
- ✅ Cada campo es independiente

### 🔄 Flujo de Funcionamiento

#### Al Modificar un Campo

1. Usuario modifica `costo_doc_sin_iva` en frontend
2. Frontend llama a `PATCH /api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/costo`
3. Backend actualiza:
   - `costo_doc_sin_iva` con el nuevo valor
   - `updated_at` con la fecha actual
   - `modificado_por` con el usuario
   - **`costo_modificado_manual = 1`** ⭐

#### Al Cargar un Pedido

1. Frontend llama a `GET /api/plantillas/{identificador}`
2. Backend incluye en cada `detalle`:
```json
{
  "pedido_detalle_id": "...",
  "costo_doc_sin_iva": 25.50,
  "total": 510.00,
  "comentario": "Producto con descuento",
  "costo_modificado_manual": true,      // ⭐
  "total_modificado_manual": true,      // ⭐
  "comentario_modificado_manual": false // ⭐
}
```
3. Frontend resalta celdas según estos flags

### 📊 Estructura de Respuesta Actualizada

```json
{
  "cabecera": {...},
  "detalle": [
    {
      "pedido_detalle_id": "uuid",
      "codigo_interno": "SKU-001",
      "costo_doc_sin_iva": 25.50,
      "total": 510.00,
      "comentario": "Nota especial",
      "costo_modificado_manual": true,
      "total_modificado_manual": true,
      "comentario_modificado_manual": false
    }
  ]
}
```

### 📝 Cambios Implementados

**Script SQL:**
- `scripts/add_campos_modificados_manual.sql`

**Repositorio:**
- `src/database/repositories/pedido_repository.py`
  - `update_costo_detalle()` - Marca `costo_modificado_manual = 1`
  - `update_total_detalle()` - Marca `total_modificado_manual = 1`
  - `update_comentario_detalle()` - Marca `comentario_modificado_manual = 1`
  - `get_pedido_completo()` - Incluye estos campos en respuesta

---

## 2. Sistema de Preferencias de Usuario

### 📋 Descripción

Sistema para que usuarios personalicen sus preferencias en el aplicativo (tablas visibles, layout, etc.).

### 🎯 Funcionalidades

- ✅ Guardar preferencias de tablas visibles
- ✅ Guardar preferencias de sidebar
- ✅ Persistir configuración por usuario
- ✅ Sincronización entre sesiones

### 🔌 Endpoints

**GET** `/api/user-preferences`
- Obtiene preferencias del usuario actual

**POST** `/api/user-preferences`
- Guarda/actualiza preferencias del usuario

**PATCH** `/api/user-preferences/{key}`
- Actualiza una preferencia específica

### 📊 Estructura

```json
{
  "user_id": "uuid-usuario",
  "preferencias": {
    "tabla_visible_pedidos": true,
    "tabla_visible_despachos": true,
    "sidebar_colapsado": false,
    "tema_oscuro": false,
    "items_por_pagina": 25
  }
}
```

### ✅ Estado

Sistema completamente implementado y funcional.

---

## ✅ Resumen

- **Campos Modificados:** Tracking de cambios manuales en pedidos
- **Preferencias:** Personalización de interfaz por usuario
