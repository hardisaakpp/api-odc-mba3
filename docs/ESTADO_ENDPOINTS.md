# Estado de los 4 Endpoints Requeridos

## 📋 Resumen de Endpoints

| # | Endpoint Requerido | Estado | Endpoint Actual | Método | Notas |
|---|-------------------|--------|-----------------|--------|-------|
| 1 | **CONSULTAR despachos** | ⚠️ **MEZCLADO** | `POST /consulta` | POST | Consulta + Guarda (no separado) |
| 2 | **MIGRAR información** | ⚠️ **MEZCLADO** | `GET /facturas`<br>`GET /consulta`<br>`POST /consulta` | GET/POST | Consulta + Guarda (no separado) |
| 3 | **PROCESAR** | ✅ **COMPLETO** | `GET /consulta/predefinida` | GET | Consulta + Guarda + Copia a ODC |
| 4 | **INTEGRAR con SAP** | ❌ **PENDIENTE** | - | - | Aún no desarrollado |

## 🔍 Análisis Detallado

### 1. CONSULTAR despachos (POST) - ⚠️ MEZCLADO

**Requerimiento:**
- Solo consulta, NO guarda
- Muestra resultados en swagger/postman
- Método POST

**Estado Actual:**
- `POST /consulta` existe pero **también guarda** en SQL Server
- No hay un endpoint POST que SOLO consulte sin guardar

**Recomendación:**
- Opción A: Crear `POST /despachos/consultar` que solo consulte
- Opción B: Agregar parámetro `save_to_db=false` a `POST /consulta`

### 2. MIGRAR información - ⚠️ MEZCLADO

**Requerimiento:**
- Guarda en `despacho_cabecera`/`despacho_detalle`
- NO copia a ODC

**Estado Actual:**
- `GET /facturas` con `save_to_db=True` - Consulta + Guarda
- `GET /consulta` - Consulta + Guarda
- `POST /consulta` - Consulta + Guarda

**Problema:**
- Estos endpoints hacen consulta Y guardado juntos
- No hay un endpoint que SOLO migre (asumiendo que los datos ya están consultados)

**Recomendación:**
- Documentar que estos endpoints hacen ambas cosas
- O crear `POST /despachos/migrar` que reciba datos y solo guarde

### 3. PROCESAR - ✅ COMPLETO

**Requerimiento:**
- Consulta + Guarda + Copia a ODC
- Método GET
- Query predefinida

**Estado Actual:**
- `GET /consulta/predefinida` ✅
  - ✅ Consulta datos desde MBA3
  - ✅ Guarda en `despacho_cabecera`/`despacho_detalle`
  - ✅ Copia a `orden_compra_cabecera`/`orden_compra_detalle`

**Implementación:**
```python
# Flujo del endpoint:
1. Ejecuta query predefinida → MBA3Service.execute_query()
2. Guarda en despacho → MBA3Service.save_to_database()
3. Copia a ODC → copy_despacho_to_orden_compra() para cada despacho
```

**Respuesta incluye:**
- `data`: Resultados de MBA3
- `metadata.save_status`: Estado del guardado
- `metadata.oc_status`: Estado de copia a ODC

### 4. INTEGRAR con SAP - ❌ PENDIENTE

**Requerimiento:**
- Integración con SAP para enviar órdenes de compra
- Aún no desarrollado

**Estado Actual:**
- Solo existen endpoints de prueba: `/sap/test` y `/sap/test/direct`
- No hay endpoint de integración completa

## 📝 Recomendaciones

### Separación de Responsabilidades

**Opción Recomendada: Mantener estructura actual pero documentar claramente**

1. **CONSULTAR**: Usar `POST /consulta` con `save_to_db=false` (si se implementa)
   - O crear `POST /despachos/consultar` que solo consulte

2. **MIGRAR**: Usar `GET /facturas` o `POST /consulta` con `save_to_db=true`
   - Documentar que estos endpoints hacen consulta + guardado

3. **PROCESAR**: `GET /consulta/predefinida` ✅ (ya implementado)

4. **INTEGRAR**: Pendiente de desarrollo

### Alternativa: Separar Completamente

Si se requiere separación total:

1. `POST /despachos/consultar` - Solo consulta
2. `POST /despachos/migrar` - Solo guarda (recibe datos)
3. `GET /consulta/predefinida` - Proceso completo ✅
4. `POST /despachos/integrar-sap` - Integración SAP (pendiente)

## ✅ Estado Final

- **Endpoint PROCESAR**: ✅ **COMPLETO Y FUNCIONAL**
- **Endpoints CONSULTAR y MIGRAR**: ⚠️ Mezclados pero funcionales
- **Endpoint INTEGRAR**: ❌ Pendiente

