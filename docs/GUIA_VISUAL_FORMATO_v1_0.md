# Guía Visual - Estructura del Excel v1.0

**Documento de Referencia Rápida**  
**Última Actualización:** 6 de Enero de 2026

---

## 🗂️ Vista General del Archivo Excel

```
┌─────────────────────────────────────────────┐
│ Template_Pedido_Inicial_v1.0.xlsx          │
├─────────────────────────────────────────────┤
│ 📄 Hoja 1: Cabecera Pedido                 │
│ 📊 Hoja 2: Detalle Articulos               │
│ 🚚 Hoja 3: Movimiento                      │
│ 🏪 Hoja 4: Tiendas                         │
└─────────────────────────────────────────────┘
```

---

## 📄 Hoja 1: Cabecera Pedido

**Vista en Excel (Formato Vertical):**

```
┌──────────────────────────┬──────────────────────────────┬──────────────────────────┐
│ Campo                    │ Valor                        │ Ejemplo                  │
├──────────────────────────┼──────────────────────────────┼──────────────────────────┤
│ CODIGO PEDIDO            │ P-12.48 - 12 - 2025         │ Identificador único      │
│ FECHA DE PEDIDO          │ 2025-12-22                  │ Fecha YYYY-MM-DD         │
│ FECHA DE ENTREGA         │ INMEDIATO                   │ Plazo o instrucción      │
│ FORMA DE PAGO            │ 120 DIAS                    │ Término de crédito       │
│ ODC                      │ (vacío)                     │ Orden de Compra (opt)    │
│ NOMBRE PROVEEDOR         │ TEXTILES EL RAYO S.A.       │ Nombre de proveedor      │
│ COMPRADOR NOMBRE         │ VACA ANDREA                 │ Persona responsable      │
│ COD COMPRADOR            │ 801                         │ ID interno comprador     │
│ ORIGEN TRASLADO          │ RL-CD                       │ Bodega origen            │
│ SERIE                    │ 10131                       │ Número de serie          │
└──────────────────────────┴──────────────────────────────┴──────────────────────────┘
```

**Nota:** Los datos pueden estar en orden diferente. El sistema busca por nombre de campo.

---

## 📊 Hoja 2: Detalle Articulos

**Vista en Excel (Formato Tabular):**

```
┌─────────────────┬────────┬────────────────────────┬────────────────┬──────┬───────────┬───────────┬───────┬────────┐
│ CODIGO PRODUCTO │ MARCA  │ DESCRIPCION SAP        │ CODIGO BARRAS  │ PACK │ COSTO ... │ DESCUENTO │  PVP  │ BODEGA │
├─────────────────┼────────┼────────────────────────┼────────────────┼──────┼───────────┼───────────┼───────┼────────┤
│ MTF123.9        │ ROLAND │ VALETAS C. TALONERA    │ 7861224113401  │ X1   │   5.65    │    0.2    │  9.99 │  150   │
│ MTF124.5        │ ROLAND │ MEDIA TOBILLERA        │ 7861224113402  │ X1   │   6.75    │    0.2    │ 10.99 │  200   │
│ MTF125.2        │ ROLAND │ MEDIA CASUAL PACK      │ 7861224113403  │ X3   │   4.25    │    0.2    │  8.49 │  180   │
│ R5000.1012-2    │ ROLAND │ VALETA NYLON           │ 7861224113404  │ X1   │   5.80    │    0.2    │  9.99 │   99   │
│ R5000.1012-3    │ ROLAND │ CALCETÍN ELASTICADO    │ 7861224113405  │ X1   │   6.25    │    0.2    │ 10.99 │  175   │
└─────────────────┴────────┴────────────────────────┴────────────────┴──────┴───────────┴───────────┴───────┴────────┘
```

**Columnas Importantes:**
- ✅ **CODIGO PRODUCTO** - SKU único (obligatorio, debe coincidir con Movimiento)
- ✅ **MARCA** - Fabricante
- ✅ **DESCRIPCION SAP** - Nombre técnico del producto
- ✅ **COSTO SIN IVA** - Valor de compra
- ✅ **PVP** - Precio de venta
- ℹ️ **BODEGA** - Información (no se usa en distribución)

---

## 🚚 Hoja 3: Movimiento (LA MÁS IMPORTANTE)

**Vista en Excel (Distribución por Tienda):**

```
┌─────────────────┬──────────────────────────────┬──────────┐
│ CODIGO PRODUCTO │ TIENDAS                      │ CANTIDAD │
├─────────────────┼──────────────────────────────┼──────────┤
│ MTF123.9        │ TRL-QSN                      │    10    │
│ MTF123.9        │ TRL-SMA                      │     5    │
│ MTF123.9        │ ROLAND MALL DEL SOL          │     8    │
│ MTF123.9        │ TOUT-BOMB                    │     3    │
│ MTF124.5        │ TRL-QSN                      │     7    │
│ MTF124.5        │ TRL-REGIONAL-QUITO           │     4    │
│ MTF125.2        │ TOUT-BOMB                    │     2    │
│ MTF125.2        │ RG-INT                       │     1    │
│ R5000.1012-2    │ TRL-SMA                      │     6    │
│ R5000.1012-3    │ TRL-QSN                      │     5    │
└─────────────────┴──────────────────────────────┴──────────┘

RESUMEN:
- Filas leídas: 10
- Productos únicos: 5
- Tiendas destino: 8
- Distribuciones totales: 10
```

**Características:**

| Característica | Ejemplo | Notas |
|---|---|---|
| **Un producto a varias tiendas** | MTF123.9 → 4 tiendas | Distribución normal |
| **Mismo producto a mismo código de tienda** | ❌ No permitido | Error: Duplicado |
| **Código corto de tienda** | TRL-QSN | Soportado ✅ |
| **Nombre completo de tienda** | ROLAND MALL DEL SOL | Soportado ✅ |
| **Cantidad decimal** | 5.5 | ❌ Error: Debe ser entero |
| **Cantidad cero** | 0 | ❌ Error: Debe ser > 0 |
| **Cantidad negativa** | -5 | ❌ Error: Debe ser > 0 |

---

## 🏪 Hoja 4: Tiendas (Catálogo de Referencia)

**Vista en Excel (Maestro de Tiendas):**

```
┌──────────────┬──────────────────────────────────┬────────┬─────────────────┐
│ ID TIENDA    │ NOMBRE_TIENDA                    │ ACTIVO │ ID_TIENDA_ACTIVA│
├──────────────┼──────────────────────────────────┼────────┼─────────────────┤
│ TRL-QSN      │ ROLAND QUICENTRO NORTE           │   SI   │    TRL-QSN      │
│ TRL-SMA      │ ROLAND SAN MARINO                │   SI   │    TRL-SMA      │
│ TRL-BOSQUE   │ ROLAND CC EL BOSQUE              │   SI   │  TRL-BOSQUE     │
│ TRL-CEIBOS   │ ROLAND CC CEIBOS                 │   SI   │   TRL-CEIBOS    │
│ TOUT-BOMB    │ DESCUENTON BOMBOLÍ               │   SI   │   TOUT-BOMB     │
│ TOUT-MAP     │ DESCUENTON MAPASINGUE            │   SI   │   TOUT-MAP      │
│ RG-QSN       │ ROLAND REGIONS QUITO (INT)       │   SI   │    RG-QSN       │
│ RG-NAC       │ ROLAND REGIONS QUITO (NAC)       │   SI   │    RG-NAC       │
│ RG-GYE       │ ROLAND REGIONS GUAYAQUIL         │   SI   │    RG-GYE       │
│ RG-CUENCA    │ ROLAND REGIONS CUENCA            │   SI   │  RG-CUENCA      │
│ RL-CD        │ BODEGA ROLAND CD                 │   SI   │    RL-CD        │
│ OUT-CD       │ BODEGA OUTLET CD                 │   SI   │    OUT-CD       │
│ RG-CD        │ BODEGA REGIONS CD                │   SI   │    RG-CD        │
│ CERRADA      │ TIENDA EN REPARACION             │   NO   │   CERRADA       │
└──────────────┴──────────────────────────────────┴────────┴─────────────────┘
```

**Segmentación de Tiendas:**

```
┌─────────────────────────────────────────────────────┐
│ TIENDAS PRINCIPALES (TRL-*)                        │
├─────────────────────────────────────────────────────┤
│ • TRL-QSN    → ROLAND QUICENTRO NORTE              │
│ • TRL-SMA    → ROLAND SAN MARINO                   │
│ • TRL-BOSQUE → ROLAND CC EL BOSQUE                │
│ • TRL-CEIBOS → ROLAND CC CEIBOS                   │
│ • TRL-REGIONAL-QUITO                              │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ TIENDAS DESCUENTON (TOUT-*)                        │
├─────────────────────────────────────────────────────┤
│ • TOUT-BOMB  → DESCUENTON BOMBOLÍ                  │
│ • TOUT-MAP   → DESCUENTON MAPASINGUE               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ TIENDAS REGIONS (RG-*)                             │
├─────────────────────────────────────────────────────┤
│ • RG-QSN     → ROLAND REGIONS QUITO (INT)         │
│ • RG-NAC     → ROLAND REGIONS QUITO (NAC)         │
│ • RG-GYE     → ROLAND REGIONS GUAYAQUIL           │
│ • RG-CUENCA  → ROLAND REGIONS CUENCA              │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ BODEGAS (*-CD)                                     │
├─────────────────────────────────────────────────────┤
│ • RL-CD      → BODEGA ROLAND CD                   │
│ • OUT-CD     → BODEGA OUTLET CD                   │
│ • RG-CD      → BODEGA REGIONS CD                  │
└─────────────────────────────────────────────────────┘
```

---

## 🔄 Flujo de Validación Visual

```
ARCHIVO EXCEL CARGADO
        ↓
┌──────────────────────────────┐
│ ¿Tiene 4 hojas?             │
└──────┬───────────────────┬───┘
       NO                  SI
       │                   ↓
    [Usar]        ┌─────────────────────────────┐
    [flujo        │ LEER HOJA TIENDAS           │
    [antiguo]     │ ✅ Cargar catálogo         │
    [2 hojas]     └──────────┬──────────────────┘
                             ↓
                   ┌─────────────────────────────┐
                   │ LEER CABECERA PEDIDO        │
                   │ ✅ Extraer metadatos       │
                   │ ✅ Validar CODIGO PEDIDO   │
                   └──────────┬──────────────────┘
                             ↓
                   ┌─────────────────────────────┐
                   │ LEER DETALLE ARTICULOS      │
                   │ ✅ Cargar catálogo SKUs    │
                   │ ✅ Crear referencia        │
                   └──────────┬──────────────────┘
                             ↓
                   ┌─────────────────────────────┐
                   │ LEER MOVIMIENTO             │
                   │ ✅ Procesar distribuciones │
                   │ ✅ Validar refs            │
                   │ ✅ Validar cantidades      │
                   └──────────┬──────────────────┘
                             ↓
                   ┌─────────────────────────────┐
                   │ CONSOLIDAR POR PRODUCTO     │
                   │ ✅ Agrupar datos           │
                   └──────────┬──────────────────┘
                             ↓
                   ┌─────────────────────────────┐
                   │ VALIDAR PEDIDO COMPLETO     │
                   │ ✅ Reglas de negocio       │
                   └────┬──────────────────────┬─┘
                        │ ERRORES              │ OK
                        ↓                      ↓
                   [RECHAZAR]        ┌──────────────────┐
                                     │ GUARDAR EN BD    │
                                     │ ✅ Persistencia  │
                                     └────────┬─────────┘
                                             ↓
                                     [PEDIDO CARGADO ✅]
```

---

## 📊 Ejemplo Completo: De Excel a Base de Datos

### Entrada: Archivo Excel

```
Hoja: Cabecera Pedido
┌────────────────┬──────────────────────────┐
│ CODIGO PEDIDO  │ P-2025-001-QUITO        │
│ FECHA PEDIDO   │ 2025-01-06              │
│ PROVEEDOR      │ TEXTILES EL RAYO        │
│ FORMA PAGO     │ 30 DIAS                 │
└────────────────┴──────────────────────────┘

Hoja: Detalle Articulos
┌─────────┬────────┬───────┐
│ CODIGO  │ MARCA  │  PVP  │
├─────────┼────────┼───────┤
│ MTF123  │ ROLAND │  9.99 │
│ MTF124  │ ROLAND │ 10.99 │
└─────────┴────────┴───────┘

Hoja: Movimiento
┌────────┬──────────┬────────┐
│ CODIGO │ TIENDAS  │ CANTIDAD
├────────┼──────────┼────────┤
│ MTF123 │ TRL-QSN  │   10   │
│ MTF123 │ TRL-SMA  │    5   │
│ MTF124 │ TRL-QSN  │    7   │
└────────┴──────────┴────────┘

Hoja: Tiendas
┌────────┬──────────────────────────┐
│ ID     │ NOMBRE                   │
├────────┼──────────────────────────┤
│TRL-QSN │ ROLAND QUICENTRO NORTE  │
│TRL-SMA │ ROLAND SAN MARINO       │
└────────┴──────────────────────────┘
```

### Procesamiento Interno

```
┌────────────────────────────────────────────────────┐
│ ETAPA 1: PARSING                                   │
├────────────────────────────────────────────────────┤
│ Cabecera:                                          │
│ {                                                  │
│   numero_pedido: "P-2025-001-QUITO",             │
│   fecha_pedido: 2025-01-06,                      │
│   forma_pago: "30 DIAS",                         │
│   proveedor_nombre: "TEXTILES EL RAYO"           │
│ }                                                 │
│                                                   │
│ Movimiento (procesado):                          │
│ [                                                 │
│   {                                               │
│     codigo_producto: "MTF123",                   │
│     tienda_codigo: "TRL-QSN",                    │
│     cantidad: 10,                                │
│     validacion: { valida: true }                 │
│   },                                             │
│   {                                               │
│     codigo_producto: "MTF123",                   │
│     tienda_codigo: "TRL-SMA",                    │
│     cantidad: 5,                                 │
│     validacion: { valida: true }                 │
│   },                                             │
│   {                                               │
│     codigo_producto: "MTF124",                   │
│     tienda_codigo: "TRL-QSN",                    │
│     cantidad: 7,                                 │
│     validacion: { valida: true }                 │
│   }                                              │
│ ]                                                │
│                                                   │
│ Consolidado por producto:                        │
│ {                                                 │
│   "MTF123": {                                     │
│     distribuciones: [                            │
│       { tienda: TRL-QSN, cantidad: 10 },        │
│       { tienda: TRL-SMA, cantidad: 5 }          │
│     ]                                            │
│   },                                             │
│   "MTF124": {                                     │
│     distribuciones: [                            │
│       { tienda: TRL-QSN, cantidad: 7 }          │
│     ]                                            │
│   }                                              │
│ }                                                │
└────────────────────────────────────────────────────┘
```

### Salida: Base de Datos

```
Tabla: pedido
┌──────────────────────────────────────────┐
│ pedido_id: a1b2c3d4-... (UUID)           │
│ numero_pedido: P-2025-001-QUITO          │
│ fecha_pedido: 2025-01-06                 │
│ forma_pago: 30 DIAS                      │
│ proveedor_nombre: TEXTILES EL RAYO       │
└──────────────────────────────────────────┘

Tabla: pedido_detalle (2 filas)
┌──────────────────────────────────────────┐
│ pedido_detalle_id: uuid1                 │
│ pedido_id: a1b2c3d4-...                  │
│ codigo_interno: MTF123                   │
│ marca: ROLAND                            │
│ pvp: 9.99                                │
├──────────────────────────────────────────┤
│ pedido_detalle_id: uuid2                 │
│ pedido_id: a1b2c3d4-...                  │
│ codigo_interno: MTF124                   │
│ marca: ROLAND                            │
│ pvp: 10.99                               │
└──────────────────────────────────────────┘

Tabla: pedido_detalle_tienda (3 filas)
┌──────────────────────────────────────────┐
│ id: uuid1                                │
│ pedido_detalle_id: uuid1 (MTF123)        │
│ tienda_id: uuid_TRL_QSN                  │
│ cantidad: 10                             │
├──────────────────────────────────────────┤
│ id: uuid2                                │
│ pedido_detalle_id: uuid1 (MTF123)        │
│ tienda_id: uuid_TRL_SMA                  │
│ cantidad: 5                              │
├──────────────────────────────────────────┤
│ id: uuid3                                │
│ pedido_detalle_id: uuid2 (MTF124)        │
│ tienda_id: uuid_TRL_QSN                  │
│ cantidad: 7                              │
└──────────────────────────────────────────┘
```

---

## ✨ Resumen Visual

```
╔════════════════════════════════════════════════════╗
║        TEMPLATE PEDIDO INICIAL v1.0                ║
╠════════════════════════════════════════════════════╣
║  4 HOJAS ESPECIALIZADAS                           ║
╠════════════════════════════════════════════════════╣
║                                                    ║
║  1️⃣  CABECERA PEDIDO                              ║
║     → Metadatos del pedido                        ║
║     → 10 campos clave                             ║
║                                                    ║
║  2️⃣  DETALLE ARTICULOS                            ║
║     → Catálogo de productos                       ║
║     → Costos y precios                            ║
║                                                    ║
║  3️⃣  MOVIMIENTO ⭐                                ║
║     → Distribución a tiendas                      ║
║     → La hoja más importante                      ║
║                                                    ║
║  4️⃣  TIENDAS                                      ║
║     → Maestro de ubicaciones                      ║
║     → Validación de códigos                       ║
║                                                    ║
╠════════════════════════════════════════════════════╣
║  RESULTADO: Pedido completo con distribuciones   ║
║            listo para envío a SAP                 ║
╚════════════════════════════════════════════════════╝
```

---

**Documento de Referencia Rápida**  
**Imprime o guarda como referencia mientras completas el Excel**
