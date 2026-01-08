# Checklist de Validación Fase 4 - Ajuste y Redistribución

## 📋 Resumen

Este checklist cubre todos los casos críticos que deben validarse antes de deploy a producción.

---

## 🧪 Tests Automatizados

### ✅ Ejecutar pytest
```bash
pytest tests/test_services/test_pedido_ajuste_service.py -v --cov
```

### ✅ Verificar cobertura
- [ ] Cobertura > 85%
- [ ] Todos los casos críticos cubiertos
- [ ] Tests de rollback pasando

---

## 📝 Casos de Prueba Manuales

### ✅ Caso 1: Confirmación Exacta
**Objetivo:** Verificar que cuando se confirma exactamente lo solicitado, no hay cambios.

**Pasos:**
1. [ ] Crear pedido con 100 unidades (50/50 en 2 tiendas)
2. [ ] Cargar respuesta confirmando 100 unidades
3. [ ] Procesar confirmación vía endpoint
4. [ ] Verificar estado del pedido = `CONFIRMADO_PROVEEDOR`
5. [ ] Verificar diferencias en reporte = 0
6. [ ] Verificar cantidades por tienda sin cambios (50/50)
7. [ ] Verificar porcentaje de confirmación = 100%

**Resultado esperado:**
- Estado actualizado correctamente
- No hay diferencias
- Cantidades por tienda intactas

---

### ✅ Caso 2: Confirmación Parcial con Redistribución
**Objetivo:** Verificar redistribución proporcional cuando se confirma menos.

**Pasos:**
1. [ ] Crear pedido con 100 unidades (50/50 en 2 tiendas)
2. [ ] Cargar respuesta confirmando 70 unidades
3. [ ] Procesar confirmación
4. [ ] Verificar suma exacta = 70 (no 69, no 71)
5. [ ] Verificar última tienda absorbe residuo correctamente
6. [ ] Verificar no hay cantidades negativas
7. [ ] Verificar distribución proporcional (35/35 o similar)

**Resultado esperado:**
- Suma exacta = 70
- Última tienda tiene el residuo
- No hay números negativos
- Distribución proporcional correcta

---

### ✅ Caso 3: Distribución Específica del Proveedor
**Objetivo:** Verificar que se respeta la distribución específica cuando el proveedor la proporciona.

**Pasos:**
1. [ ] Crear pedido con 100 unidades (50/50 en 2 tiendas)
2. [ ] Cargar respuesta con distribución específica por tienda (ej: 40/30 = 70 total)
3. [ ] Procesar confirmación
4. [ ] Verificar se respeta distribución específica (40/30)
5. [ ] Verificar NO entra a redistribución proporcional
6. [ ] Verificar método usado = "distribucion_especifica"

**Resultado esperado:**
- Distribución específica respetada
- No se redistribuye proporcionalmente
- Método correcto en respuesta

---

### ✅ Caso 4: Idempotencia
**Objetivo:** Verificar que no se puede procesar dos veces la misma confirmación.

**Pasos:**
1. [ ] Procesar confirmación primera vez → debe ser exitosa
2. [ ] Verificar estado respuesta = `APROBADA`
3. [ ] Procesar confirmación segunda vez → debe fallar
4. [ ] Verificar HTTP status = 409 Conflict
5. [ ] Verificar mensaje indica "ya fue procesada"
6. [ ] Verificar BD sin cambios en segunda llamada
7. [ ] Verificar NO se hizo commit en segunda llamada

**Resultado esperado:**
- Primera llamada exitosa
- Segunda llamada retorna 409
- Sin cambios en BD en segunda llamada

---

### ✅ Caso 5: Cambio de Precio
**Objetivo:** Verificar recálculo de costos cuando hay cambios de precio.

**Pasos:**
1. [ ] Crear pedido con costo 100, descuento 10%, cantidad 100
2. [ ] Cargar respuesta con costo ajustado 120, descuento 15%
3. [ ] Procesar confirmación
4. [ ] Verificar subtotal recalculado = 120 * 100 = 12000
5. [ ] Verificar total con descuento = 12000 * 0.85 = 10200
6. [ ] Verificar persistencia en `pedido_detalle`
7. [ ] Verificar reporte muestra `cambio_precio = true`

**Resultado esperado:**
- Subtotal recalculado correctamente
- Total con descuento correcto
- Persistencia en BD correcta
- Reporte indica cambio de precio

---

### ✅ Caso 6: Rollback Transaccional
**Objetivo:** Verificar que ante un error, no se dejan datos parciales.

**Pasos:**
1. [ ] Preparar pedido con respuesta válida
2. [ ] Simular error a mitad del flujo (ej: error en BD)
3. [ ] Intentar procesar confirmación
4. [ ] Verificar excepción propagada
5. [ ] Verificar NO cambia estado del pedido
6. [ ] Verificar NO se aprueba la respuesta
7. [ ] Verificar NO hay cantidades parciales guardadas
8. [ ] Verificar NO se hizo commit

**Resultado esperado:**
- Excepción propagada
- Estado del pedido sin cambios
- Respuesta sin aprobar
- Sin commits parciales
- Rollback ejecutado (context manager)

---

## 🔍 Validaciones Adicionales

### ✅ Validación de Redondeo
- [ ] Probar con cantidades que generen decimales (ej: 73 de 100, 2 tiendas)
- [ ] Verificar suma exacta siempre
- [ ] Verificar última tienda absorbe residuo

### ✅ Validación de Estados
- [ ] Verificar transición de estados correcta
- [ ] Verificar estados intermedios no quedan "colgados"
- [ ] Verificar logs de auditoría

### ✅ Validación de Reporte
- [ ] Verificar reporte muestra cantidades actualizadas (post-commit)
- [ ] Verificar distribución por tienda en reporte
- [ ] Verificar diferencias calculadas correctamente

---

## 🚀 Pre-Deploy Checklist

Antes de hacer deploy a producción:

- [ ] Todos los tests automatizados pasando
- [ ] Todos los casos manuales validados
- [ ] Rollback probado y funcionando
- [ ] Logs revisados (sin errores críticos)
- [ ] Documentación actualizada
- [ ] Código revisado por otro dev (si aplica)
- [ ] Backup de BD realizado (si aplica)

---

## 📊 Métricas de Éxito

- ✅ Cobertura de tests > 85%
- ✅ Todos los casos críticos pasando
- ✅ Tiempo de respuesta < 2 segundos (para pedidos normales)
- ✅ Sin errores en logs durante pruebas
- ✅ Rollback funcionando correctamente

---

## 🐛 Casos Límite a Considerar

- [ ] Pedido con 0 unidades confirmadas
- [ ] Pedido con 1 sola tienda
- [ ] Pedido con muchas tiendas (10+)
- [ ] Confirmación mayor a solicitado (debe fallar en validación)
- [ ] Cambio de precio a 0 (debe validarse)
- [ ] Descuento > 100% (debe validarse)

---

## 📝 Notas

- Los tests automatizados cubren la mayoría de casos
- Los casos manuales son para validación de negocio
- El rollback es crítico: debe probarse siempre antes de producción
- El reporte debe mostrar datos actualizados (post-commit reload)

---

**Última actualización:** 2025-01-21
**Versión:** 1.0

