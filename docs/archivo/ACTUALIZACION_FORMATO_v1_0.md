# Actualización del Sistema de Procesamiento de Plantillas - v1.0

**Fecha:** 6 de Enero de 2026  
**Versión:** 1.0  
**Estado:** ✅ Completado

---

## 📋 Resumen de Cambios

El sistema ha sido actualizado para soportar un nuevo formato mejorado de plantilla Excel de pedidos: **Template_Pedido_Inicial_v1.0.xlsx** con 4 hojas especializadas.

### ¿Qué cambió?

**Formato Anterior (2 hojas):**

```
CABECERA_PEDIDO + DETALLE_ARTICULO
```

**Nuevo Formato v1.0 (4 hojas):**

```
Cabecera Pedido + Detalle Articulos + Movimiento + Tiendas
```

---

## 🎯 Nuevo Formato v1.0 - Descripción de las 4 Hojas

### 1️⃣ **Cabecera Pedido** (Metadatos)

Información general del pedido:

- Código de pedido (identificador único)
- Fechas (pedido y entrega)
- Información del proveedor
- Información del comprador
- Términos de pago
- Bodega origen

### 2️⃣ **Detalle Articulos** (Catálogo de Productos)

Maestro de productos:

- Código de producto (SKU)
- Marca
- Descripción SAP
- Código de barras
- Pack/Empaque
- Costo sin IVA
- Descuento
- Precio de venta (PVP)
- Cantidad en bodega (informativa)

### 3️⃣ **Movimiento** (Distribución a Tiendas) ⭐ **CRÍTICA**

Asignación de cantidades por tienda:

- CODIGO PRODUCTO (SKU a distribuir)
- TIENDAS (código o nombre de tienda)
- CANTIDAD (unidades a enviar)

**Características:**

- Un producto puede distribuirse a múltiples tiendas
- Soporta códigos cortos (`TRL-QSN`) o nombres completos
- Validación automática contra catálogo de tiendas

### 4️⃣ **Tiendas** (Maestro de Tiendas)

Catálogo de puntos de venta:

- ID TIENDA (código único)
- NOMBRE_TIENDA (descripción)
- ACTIVO (SI/NO)
- ID_TIENDA_ACTIVA (validación)

**Segmentación:**

- Tiendas ROLAND (`TRL-*`)
- Tiendas DESCUENTON (`TOUT-*`)
- Tiendas REGIONS (`RG-*`)
- Bodegas (`*-CD`)

---

## 🔧 Cambios Técnicos

### 1. **pedido_parser.py** - Nuevos Métodos

#### Método: `leer_hoja_movimiento()`

```python
def leer_hoja_movimiento(
    self,
    file_content: bytes,
    catalogo_tiendas: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, Any]
```

**Funcionalidad:**

- Lee la hoja "Movimiento"
- Procesa distribuciones de productos a tiendas
- Valida códigos de tienda contra catálogo
- Retorna distribuciones estructuradas con validaciones

**Validaciones incluidas:**

- ✅ Códigos de producto no vacíos
- ✅ Tiendas existentes en catálogo
- ✅ Cantidades válidas (enteros > 0)
- ✅ Tiendas activas

#### Método: `leer_hoja_tiendas()` - Mejorado

```python
def leer_hoja_tiendas(self, file_content: bytes) -> Dict[str, Dict[str, Any]]
```

**Mejoras:**

- Ahora retorna más información (nombre, estado activo, ID de validación)
- Mejor detección de columnas (flexible)
- Logging detallado de tiendas cargadas

---

### 2. **pedido_service.py** - Nuevo Flujo

#### Detección Automática de Formato

En `validar_y_procesar_archivo_excel()`:

```python
# Detecta si tiene 4 hojas y usa el nuevo flujo
if tiene_cabecera_pedido and tiene_detalle_articulo and tiene_movimiento and tiene_tiendas:
    return self._procesar_formato_v1_0(...)
```

#### Nuevo Método: `_procesar_formato_v1_0()`

```python
def _procesar_formato_v1_0(
    self,
    file_content: bytes,
    filename: str,
    usuario_id: Optional[str] = None,
    hoja_cabecera: str = "Cabecera Pedido",
    hoja_detalle: str = "Detalle Articulos",
    hoja_movimiento: str = "Movimiento",
    hoja_tiendas: str = "Tiendas",
    ...
) -> Dict[str, Any]
```

**Pasos del procesamiento:**

1. **PASO 1:** Leer hoja "Tiendas"

   - Cargar catálogo de tiendas válidas
   - Validar estados (ACTIVO/INACTIVO)

2. **PASO 2:** Leer hoja "Cabecera Pedido"

   - Extraer metadatos
   - Normalizar campos
   - Generar Pedido ID

3. **PASO 3:** Leer hoja "Detalle Articulos"

   - Cargar catálogo de SKUs
   - Obtener costos y precios
   - Crear diccionario de referencia

4. **PASO 4:** Leer hoja "Movimiento"

   - Procesar distribuciones
   - Validar productos y tiendas
   - Validar cantidades

5. **PASO 5:** Consolidar por producto

   - Agrupar distribuciones
   - Consolidar cantidades

6. **PASO 6:** Validación pre-negocio

   - Ejecutar validaciones completas
   - Generar reportes de errores

7. **PASO 7:** Persistencia en BD
   - Crear cabecera
   - Crear detalles
   - Crear distribuciones por tienda

---

## 📊 Respuesta del Sistema

### Formato v1.0 Exitoso

```json
{
  "status": "success",
  "formato_detectado": "cuatro_hojas_v1_0",
  "pedido_id": "uuid-aqui",
  "articulos_cargados": 3,
  "distribuciones_cargados": 12,
  "resumen": {
    "hojas_procesadas": [
      "Tiendas",
      "Cabecera Pedido",
      "Detalle Articulos",
      "Movimiento"
    ],
    "tiendas_validadas": 15,
    "productos_cargados": 3,
    "distribuciones_totales": 12
  },
  "warnings": []
}
```

---

## 🚀 Uso

### Mediante API REST

```bash
POST /pedidos/importar-excel

Content-Type: multipart/form-data
Body:
  file: [archivo Excel]
  hoja_cabecera: "Cabecera Pedido"
  hoja_detalle: "Detalle Articulos"
  validar_sap: true
  sap_obligatorio: false
```

### Mediante Script CLI

```bash
# Procesamiento básico
python scripts/procesar_plantilla_pedido.py Template_Pedido_Inicial_v1.0.xlsx

# Con validación SAP
python scripts/procesar_plantilla_pedido.py pedido.xlsx --validar-sap

# Verbose y guardar resultado
python scripts/procesar_plantilla_pedido.py pedido.xlsx --verbose --output-json resultado.json
```

---

## 📚 Documentación

**Archivo Principal:** [docs/PLANTILLA_PEDIDO_INICIAL_v1_0.md](../docs/PLANTILLA_PEDIDO_INICIAL_v1_0.md)

Contiene:

- ✅ Descripción detallada de cada hoja
- ✅ Estructura exacta de columnas
- ✅ Ejemplos de datos reales
- ✅ Validaciones implementadas
- ✅ Casos de uso
- ✅ Troubleshooting

---

## ✅ Validaciones Implementadas

### Validaciones de Estructura

| Validación                | Nivel | Descripción                               |
| ------------------------- | ----- | ----------------------------------------- |
| Hojas obligatorias        | ERROR | Todas las 4 hojas deben existir           |
| CODIGO PEDIDO obligatorio | ERROR | Cabecera debe tener número                |
| CODIGO PRODUCTO no vacío  | ERROR | Cada fila de Movimiento debe tener SKU    |
| TIENDA no vacía           | ERROR | Cada fila de Movimiento debe tener tienda |
| CANTIDAD válida           | ERROR | Debe ser entero > 0                       |

### Validaciones de Referencia

| Validación      | Nivel   | Descripción                                     |
| --------------- | ------- | ----------------------------------------------- |
| Producto existe | ERROR   | CODIGO PRODUCTO debe estar en Detalle Articulos |
| Tienda existe   | ERROR   | TIENDA debe estar en hoja Tiendas               |
| Tienda activa   | WARNING | Si tienda está INACTIVO                         |

---

## 🔄 Compatibilidad

El sistema **mantiene compatibilidad hacia atrás** con el formato anterior de 2 hojas:

```
✅ Formato antiguo (2 hojas) → Sigue funcionando
✅ Nuevo formato v1.0 (4 hojas) → Automáticamente detectado y procesado
```

**Detección automática:**

- Si archivo tiene 4 hojas → Usa flujo v1.0
- Si archivo tiene 2 hojas → Usa flujo antiguo

---

## 🐛 Errores Comunes y Soluciones

### Error: "Tienda no encontrada"

**Causa:** Tienda en Movimiento no existe en Tiendas o está inactiva
**Solución:** Verificar código exacto en hoja Tiendas

### Error: "Producto no encontrado"

**Causa:** CODIGO PRODUCTO en Movimiento no existe en Detalle Articulos
**Solución:** Verificar que SKU esté en Detalle Articulos

### Error: "Hoja no encontrada"

**Causa:** Falta alguna de las 4 hojas requeridas
**Solución:** Verificar que existan las hojas exactas:

- `Cabecera Pedido` (o similar)
- `Detalle Articulos` (o similar)
- `Movimiento`
- `Tiendas`

---

## 📝 Archivos Modificados

### Código Fuente

- ✅ `src/database/services/pedido_parser.py` - Nuevos métodos para leer hojas
- ✅ `src/database/services/pedido_service.py` - Nuevo flujo v1.0 + detección automática

### Scripts

- ✅ `scripts/procesar_plantilla_pedido.py` - Nuevo script CLI para procesamiento

### Documentación

- ✅ `docs/PLANTILLA_PEDIDO_INICIAL_v1_0.md` - Documentación completa del nuevo formato

---

## 🎓 Ejemplos de Uso

### Ejemplo 1: Importación Inicial Completa

1. Crear Excel con 4 hojas
2. Llenar metadatos en Cabecera Pedido
3. Listar SKUs en Detalle Articulos
4. Definir distribución en Movimiento
5. Definir tiendas en Tiendas
6. Subir archivo
7. Sistema genera pedido completo

**Resultado:** Pedido con distribución a múltiples tiendas ✅

### Ejemplo 2: Reabastecimiento a Tienda Específica

1. Excel con 1 pedido
2. 5 SKUs en Detalle Articulos
3. Movimiento solo para 1 tienda
4. Catálogo de tiendas (puede copiar de anterior)
5. Subir archivo

**Resultado:** Pedido pequeño de reabastecimiento ✅

---

## 📞 Soporte

Para preguntas o problemas:

1. Revisar documentación en `docs/PLANTILLA_PEDIDO_INICIAL_v1_0.md`
2. Revisar logs del sistema (con `--verbose`)
3. Verificar que Excel cumpla con estructura
4. Contactar al equipo de desarrollo

---

## ✨ Beneficios del Nuevo Formato

| Aspecto            | Anterior | Nuevo v1.0                                 |
| ------------------ | -------- | ------------------------------------------ |
| **Claridad**       | Confuso  | Muy clara (4 hojas especializadas)         |
| **Mantenibilidad** | Difícil  | Fácil (cada hoja con un propósito)         |
| **Escalabilidad**  | Limitada | Excelente (soporta muchas tiendas)         |
| **Validaciones**   | Básicas  | Completas (tiendas, productos, cantidades) |
| **Trazabilidad**   | Limitada | Completa (fila de origen, auditoría)       |
| **Debugging**      | Difícil  | Fácil (errores detallados por hoja)        |

---

**Documento actualizado:** 6 de Enero de 2026  
**Estado:** Listo para Producción ✅
