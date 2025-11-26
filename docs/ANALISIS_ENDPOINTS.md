# Análisis de Endpoints - Mapeo a los 4 Requeridos

## 📋 Endpoints Requeridos

1. **CONSULTAR despachos** (POST) - Solo consulta, muestra en swagger/postman, NO guarda
2. **MIGRAR información** - Guarda en `despacho_cabecera`/`despacho_detalle`
3. **PROCESAR** (GET /consulta/predefinida) - Consulta + Guarda + Copia a ODC
4. **INTEGRAR con SAP** - Aún no desarrollado

## 🔍 Endpoints Actuales y su Mapeo

### Endpoints Existentes:

| Endpoint | Método | Función Actual | Mapeo a Requeridos |
|----------|--------|----------------|-------------------|
| `/health` | GET | Health check | - |
| `/test` | POST | Prueba comunicación | - |
| `/query` | POST | Valida query (no ejecuta) | - |
| `/query/forward` | POST | Placeholder | - |
| `/facturas` | GET | Consulta + Guarda (save_to_db=True) | **Parcialmente MIGRAR** |
| `/consulta` | GET | Consulta dinámica + Guarda | **Parcialmente MIGRAR** |
| `/consulta/predefinida` | GET | Consulta predefinida + Guarda | **PROCESAR (falta copiar a ODC)** |
| `/consulta` | POST | Consulta dinámica + Guarda | **Parcialmente MIGRAR** |
| `/sap/test` | GET | Prueba SAP | - |
| `/sap/test/direct` | GET | Prueba SAP directa | - |

## ⚠️ Problemas Identificados

### 1. CONSULTAR (POST) - ❌ NO EXISTE CLARAMENTE
- **Problema**: No hay un endpoint POST que SOLO consulte sin guardar
- **Solución**: Crear `POST /despachos/consultar` que solo ejecute la query y retorne resultados

### 2. MIGRAR - ⚠️ MEZCLADO CON CONSULTAR
- **Problema**: Los endpoints actuales (`/facturas`, `/consulta`) hacen consulta Y guardado juntos
- **Solución**: Separar responsabilidades o documentar claramente que estos endpoints hacen ambas cosas

### 3. PROCESAR - ✅ EXISTE PERO INCOMPLETO
- **Endpoint**: `GET /consulta/predefinida`
- **Hace**: Consulta + Guarda en despacho
- **Falta**: Copiar a `orden_compra_cabecera`/`orden_compra_detalle`
- **Solución**: Agregar lógica de copia a ODC después del guardado

### 4. INTEGRAR con SAP - ❌ NO DESARROLLADO
- **Estado**: Pendiente

## ✅ Recomendaciones

### Opción A: Mantener endpoints actuales y agregar funcionalidad
- Modificar `GET /consulta/predefinida` para agregar copia a ODC
- Documentar claramente qué hace cada endpoint

### Opción B: Separar responsabilidades completamente
- Crear `POST /despachos/consultar` - Solo consulta
- Crear `POST /despachos/migrar` - Solo guarda en despacho
- Modificar `GET /consulta/predefinida` - Consulta + Guarda + Copia a ODC

## 🎯 Decisión Actual

**Modificar `GET /consulta/predefinida`** para agregar la funcionalidad de copiar a ODC, manteniendo la estructura actual pero agregando el paso final.

