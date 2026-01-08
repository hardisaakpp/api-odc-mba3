# Resumen: Base de Datos con Cambios Implementados

## 📊 Estado Actual de la Base de Datos

### Estructura Existente (Sin Cambios)

La estructura actual de tablas **ya es suficiente** para soportar el nuevo flujo:

```
tienda
  ├── tienda_id (PK)
  ├── codigo (UNIQUE)
  └── nombre

pedido
  ├── pedido_id (PK)
  ├── numero_pedido (UNIQUE)
  ├── archivo_nombre
  └── creado_por

pedido_detalle
  ├── pedido_detalle_id (PK)
  ├── pedido_id (FK)
  └── codigo_interno

pedido_detalle_tienda
  ├── id (PK)
  ├── pedido_detalle_id (FK)
  ├── tienda_id (FK)
  ├── cantidad
  └── fila_origen (NUEVO - opcional)
```

---

## 🆕 Cambio Requerido: Campo `fila_origen`

### ¿Por qué se necesita?

El nuevo método `parsear_excel_pedido()` retorna `filaOrigen` para cada registro, permitiendo:
- **Auditoría**: Saber exactamente de qué fila del Excel vino cada dato
- **Debugging**: Rastrear problemas a la fila específica del Excel
- **Trazabilidad**: Validar que los datos guardados corresponden al Excel original

### Script de Migración

**Archivo:** `scripts/add_fila_origen_pedido.sql`

```sql
ALTER TABLE pedido_detalle_tienda
ADD fila_origen INT NULL;

CREATE INDEX idx_pedido_detalle_tienda_fila_origen 
ON pedido_detalle_tienda(fila_origen);
```

**Características:**
- Campo **opcional (NULL)** para mantener compatibilidad con datos existentes
- Índice para búsquedas rápidas por fila origen

---

## 🔄 Flujo Completo: Excel → Base de Datos

### Paso 1: Parsing Técnico (Fase 1 - Tarea 2)

**Endpoint:** `POST /pedidos/importar-excel`

**Método:** `parsear_excel_pedido()`

**Resultado:**
```json
{
  "resumen": { "filasLeidas": 120, "filasValidas": 115, "filasInvalidas": 5 },
  "errores": [...],
  "data": [
    { "codigoProducto": "R225.1012.BCO", "idTienda": "T001", "cantidad": 10, "filaOrigen": 2 }
  ]
}
```

**⚠️ NO se guarda en BD** - Solo parsing técnico.

---

### Paso 2: Validación y Guardado (Fase 1 - Tarea 3)

**Endpoint:** `POST /api/plantillas/upload`

**Método:** `validar_y_procesar_archivo_excel()`

**Proceso:**

1. **Parsea el Excel** (puede usar `parsear_excel_pedido()` internamente)
2. **Valida datos** (catálogo, tiendas, unidades, fechas)
3. **Si pasa validación → Guarda en BD:**

   ```
   pedido (cabecera)
     └── pedido_detalle (productos)
          └── pedido_detalle_tienda (distribuciones con fila_origen)
   ```

---

## 📝 Mapeo de Datos

### Del Parsing a la BD

**Input (del parsing):**
```json
{
  "codigoProducto": "R225.1012.BCO",
  "idTienda": "T001",
  "cantidad": 10,
  "filaOrigen": 2
}
```

**Output (en BD):**

**pedido:**
- `numero_pedido`: "AUTO-20250121-120000"
- `archivo_nombre`: "pedido.xlsx"

**pedido_detalle:**
- `codigo_interno`: "R225.1012.BCO"

**pedido_detalle_tienda:**
- `tienda_id`: (UUID de tienda con codigo="T001")
- `cantidad`: 10
- `fila_origen`: 2 ✅

---

## 🔍 Consultas Útiles

### Ver pedido completo con filas origen

```sql
SELECT 
    p.numero_pedido,
    p.archivo_nombre,
    pd.codigo_interno,
    t.codigo AS tienda_codigo,
    pdt.cantidad,
    pdt.fila_origen
FROM pedido p
INNER JOIN pedido_detalle pd ON p.pedido_id = pd.pedido_id
INNER JOIN pedido_detalle_tienda pdt ON pd.pedido_detalle_id = pdt.pedido_detalle_id
INNER JOIN tienda t ON pdt.tienda_id = t.tienda_id
WHERE p.pedido_id = @pedido_id
ORDER BY pdt.fila_origen;
```

### Buscar registros de una fila específica del Excel

```sql
SELECT 
    p.numero_pedido,
    pd.codigo_interno,
    t.codigo,
    pdt.cantidad
FROM pedido_detalle_tienda pdt
INNER JOIN pedido_detalle pd ON pdt.pedido_detalle_id = pd.pedido_detalle_id
INNER JOIN pedido p ON pd.pedido_id = p.pedido_id
INNER JOIN tienda t ON pdt.tienda_id = t.tienda_id
WHERE pdt.fila_origen = 18;
```

---

## ✅ Resumen de Cambios Necesarios

### 1. Ejecutar Script de Migración

```bash
# Ejecutar en SQL Server
sqlcmd -S servidor -d base_datos -i scripts/add_fila_origen_pedido.sql
```

### 2. Código Actualizado

✅ **Repositorio** (`pedido_repository.py`):
- Método `insert_detalle_tiendas()` actualizado para aceptar `fila_origen`
- Compatible con BD sin el campo (verifica existencia)

✅ **Servicio** (`pedido_service.py`):
- Método `parsear_excel_pedido()` retorna `filaOrigen`
- Método `validar_y_procesar_archivo_excel()` puede pasar `fila_origen` al guardar

### 3. Compatibilidad

- ✅ **Datos existentes**: No se afectan (campo es NULL)
- ✅ **BD sin campo**: El código detecta y funciona sin `fila_origen`
- ✅ **BD con campo**: El código guarda `fila_origen` automáticamente

---

## 🎯 Estado Final

### Tablas Existentes (Sin Cambios)
- ✅ `tienda` - Sin cambios
- ✅ `pedido` - Sin cambios  
- ✅ `pedido_detalle` - Sin cambios

### Tabla Modificada
- ✅ `pedido_detalle_tienda` - **Agregado campo `fila_origen`** (opcional)

### Nuevos Endpoints
- ✅ `POST /pedidos/importar-excel` - Solo parsing (no guarda)
- ✅ `POST /api/plantillas/upload` - Parsing + validación + guardado

---

## 📋 Checklist de Implementación

- [x] Script SQL para agregar `fila_origen`
- [x] Repositorio actualizado para aceptar `fila_origen`
- [x] Servicio de parsing retorna `filaOrigen`
- [x] Documentación de estructura de BD
- [ ] **Ejecutar script de migración en BD de producción**
- [ ] **Probar guardado con `fila_origen`**

---

## ⚠️ Nota Importante

El campo `fila_origen` es **opcional** y **retrocompatible**. Si no se ejecuta el script de migración, el sistema seguirá funcionando normalmente, simplemente no guardará la información de fila origen.

