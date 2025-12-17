# 🚀 Quick Start - Homologaciones SKU

## ⚡ Instalación en 3 Pasos

### Paso 1: Crear la Tabla en SQL Server

```bash
# Opción A: Con sqlcmd
sqlcmd -S localhost -d mba3_consultas -i scripts/create_sku_homologacion_table.sql

# Opción B: SQL Server Management Studio
# Abrir y ejecutar: scripts/create_sku_homologacion_table.sql
```

**Verificar instalación:**
```sql
SELECT COUNT(*) FROM sku_homologacion;
-- Debe retornar 0 (tabla vacía pero existente)
```

---

### Paso 2: Reiniciar el Servidor

```bash
# Detener el servidor si está corriendo (Ctrl+C)

# Iniciar nuevamente
python src/main.py

# Debería ver en los logs:
# ✅ Registrando endpoints de homologaciones SKU
```

---

### Paso 3: Primera Sincronización

```bash
# Obtener un JWT token (si no lo tienes)
# Ver: docs/JWT_AUTHENTICATION.md

# Ejecutar sincronización inicial
curl -X POST "http://localhost:8000/api/homologaciones-sku/sincronizar" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Respuesta esperada:
# {
#   "status": "success",
#   "data": {
#     "homologaciones_encontradas": 25,
#     "homologaciones_nuevas": 10,
#     "homologaciones_actualizadas": 15,
#     "mensaje": "Sincronización completada"
#   }
# }
```

---

## 🎯 Endpoints Disponibles

### 1. Listar Homologaciones
```bash
GET /api/homologaciones-sku?page=1&pageSize=10&estado=PENDIENTE
```

### 2. Actualizar Individual
```bash
PUT /api/homologaciones-sku/{homologacion_id}
```

### 3. Actualización Masiva
```bash
POST /api/homologaciones-sku/bulk-update
```

### 4. Sincronizar
```bash
POST /api/homologaciones-sku/sincronizar
```

---

## 📖 Documentación Completa

- **API Swagger**: http://localhost:8000/docs
- **Documentación técnica**: [docs/HOMOLOGACIONES_SKU.md](docs/HOMOLOGACIONES_SKU.md)
- **Endpoints**: [docs/ENDPOINTS.md](docs/ENDPOINTS.md)
- **Resumen de implementación**: [IMPLEMENTACION_HOMOLOGACIONES_SKU.md](IMPLEMENTACION_HOMOLOGACIONES_SKU.md)

---

## 🧪 Test Rápido (PowerShell)

```powershell
# Variables
$BASE_URL = "http://localhost:8000"
$TOKEN = "YOUR_JWT_TOKEN"

# Headers
$headers = @{
    "Authorization" = "Bearer $TOKEN"
    "Content-Type" = "application/json"
}

# 1. Sincronizar
Invoke-RestMethod -Uri "$BASE_URL/api/homologaciones-sku/sincronizar" -Method POST -Headers $headers

# 2. Listar
Invoke-RestMethod -Uri "$BASE_URL/api/homologaciones-sku?page=1&pageSize=5" -Method GET -Headers $headers

# 3. Listar solo pendientes
Invoke-RestMethod -Uri "$BASE_URL/api/homologaciones-sku?estado=PENDIENTE" -Method GET -Headers $headers
```

---

## ✅ Checklist de Verificación

- [ ] Tabla `sku_homologacion` creada en SQL Server
- [ ] Servidor reiniciado y corriendo
- [ ] Endpoints visibles en Swagger UI (http://localhost:8000/docs)
- [ ] Primera sincronización ejecutada exitosamente
- [ ] Al menos una homologación visible en GET lista

---

## 🆘 Troubleshooting

### Error: "Tabla no existe"
```bash
# Verificar que el script SQL se ejecutó correctamente
sqlcmd -S localhost -d mba3_consultas -Q "SELECT * FROM sys.tables WHERE name = 'sku_homologacion'"
```

### Error: "401 Unauthorized"
```bash
# Verificar que el JWT token es válido
# El token debe estar en formato: Bearer eyJ...
```

### Error: "No se encontraron endpoints"
```bash
# Verificar que el servidor se reinició después de agregar los archivos
# Revisar logs de startup del servidor
```

### No aparecen homologaciones después de sincronizar
```bash
# Verificar que existen despachos en la base de datos
sqlcmd -S localhost -d mba3_consultas -Q "SELECT COUNT(*) FROM despacho_detalle"

# Si el resultado es 0, primero ejecutar migración de despachos:
curl -X GET "http://localhost:8000/migrar" -H "Authorization: Bearer $TOKEN"
```

---

## 💡 Tips

1. **Primera vez**: Ejecuta sincronización después de tener despachos migrados
2. **Performance**: La sincronización puede tardar con muchos despachos (es normal)
3. **Filtros**: Usa `tiene_diferencias=true` para ver solo productos con problemas
4. **Búsqueda**: Usa parámetro `sku` para buscar por código de producto

---

## 📊 Ejemplo de Respuesta

```json
{
  "status": "success",
  "data": [
    {
      "homologacion_id": "550e8400-e29b-41d4-a716-446655440000",
      "sku_mba3": "5-0012.9",
      "nombre_producto_mba3": "Producto Ejemplo",
      "precio_unitario_mba3": 100.50,
      "sku_sap": "5-0012.9-SAP",
      "nombre_producto_sap": "Producto SAP",
      "precio_unitario_sap": 100.00,
      "estado": "PENDIENTE",
      "tiene_diferencias": true,
      "tiene_datos_sap": true,
      "created_at": "2024-12-17T10:30:00Z"
    }
  ],
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

---

**¡Listo para usar! 🎉**

Si necesitas ayuda, consulta la [documentación completa](docs/HOMOLOGACIONES_SKU.md).

