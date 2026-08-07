# Configuración del Botón "Exportar a Excel" — Solicitudes de Traslado

> Implementa el requerimiento **1.9** de `docs/requeriments/PYTD002_ODC-MABEL-RAYO.md`.

## Resumen

Se ha implementado un endpoint nuevo, independiente del de "Descargar Redistribución",
para exportar las **Solicitudes de Traslado** del pedido: una fila por cada combinación
(producto, tienda destino), con el número de traslado, la tienda, el código de barras y
las cantidades solicitada/confirmada/asignada. El botón está en la misma pantalla de
Redistribución, visible para **ambos roles** (MABEL TRADING y EL RAYO).

## ⚠️ Limitaciones de los datos — leer antes de interpretar el archivo

> **1. El Nº de traslado es por TIENDA, no por producto.**
> El sistema no registra qué producto viajó en qué Solicitud de Transferencia (ITR); el
> número se repite en todas las líneas de la misma tienda. Es una inferencia correcta a
> nivel tienda, no una trazabilidad línea a línea.
>
> **2. Las bodegas centrales (RL-CD, RG-CD, OUT-CD) no tienen Nº de traslado registrado.**
> Su flujo de envío (`OCSAPService._enviar_itrs_por_bodega`) no persiste el `doc_num` en
> base de datos, solo lo devuelve en la respuesta HTTP del momento del envío. Aparecen en
> el archivo (para que los totales cuadren con la redistribución real) con el texto
> `"No aplica"`.
>
> **3. "Cantidad Confirmada" es la que registra EL RAYO por tienda; "Cantidad Asignada
> (ITR)" es la que efectivamente viaja a SAP.** En la práctica, salvo ajuste manual, ambas
> suelen coincidir por tienda porque la confirmación se hace sobre la distribución ya
> redistribuida. El **confirmado real del proveedor a nivel producto** (antes de
> redistribuir) se muestra aparte en la columna "Confirmado Total Producto", para no
> perder ese dato.

## Endpoint

### `/api/pedidos/{pedido_id}/traslados/exportar-excel`

- **Método:** GET
- **Formato:** Excel (.xlsx)
- **Estado requerido:** Debe existir una distribución confirmada (igual que el export de
  Redistribución; **no** se gatea por `estado_id` de la ODC)
- **Autenticación:** JWT Token requerido
- **Permisos:** `odcsap.view` o `mabel.view` (ambos roles)
- **Fuente del Nº de traslado:** **Base de datos** (`solicitud_transferencia_detalle`).
  A diferencia del endpoint de Redistribución, **no** llama a SAP en vivo, por lo que el
  archivo no depende de que el middleware `.NET` esté disponible
  ([sap_middleware_connection_refused_pattern]).

## Query Parameters

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `version` | int | No | Versión específica de la redistribución. Si no se especifica, exporta la última versión. |

## Estructura del Archivo Excel

El archivo generado contiene **3 hojas**:

### Hoja 1: "Información del Pedido"

Cabecera del pedido más el detalle de cobertura del Nº de traslado (tiendas con/sin
número, bodegas incluidas) y las notas de alcance de la sección de limitaciones.

### Hoja 2: "Matriz por Tienda" — hoja principal, tiendas en columnas

Replica el layout de la tabla dinámica que hoy se arma manualmente fuera del sistema
(y de la vista "Vista Excel - Redistribución" ya existente en pantalla): una fila por
producto, y **cada tienda ocupa una sola columna (Solicitada)**. Lo Confirmado real
del proveedor solo se muestra en el bloque final "Total General" — no tiene sentido
mostrarlo por tienda porque es una distribución proporcional del confirmado real, no
un dato propio de la tienda.

- **Fila de encabezado 1 (por columna de tienda):** Número de Traslado (DocNum), o
  `Pendiente`/`No aplica`.
- **Filas de encabezado 2-3 (fusionadas, por columna de tienda):** Nombre de la tienda
  (texto vertical). No se repite `Sol.` por tienda (una sola columna ya lo es
  implícitamente); ese subencabezado solo aparece en el bloque "Total General", que sí
  tiene `Sol.` / `Conf.` como columnas separadas.
- **Columnas fijas** (congeladas al desplazar horizontalmente): Código Artículo,
  Código de Barras.
- **Bloque final "Total General"**: `Sol.` = suma de lo solicitado en todas las
  tiendas; `Conf.` = **confirmado real del proveedor** (`cantidad_confirmada_total`),
  la misma fuente que usa "Descargar Redistribución" en su hoja "Resumen de
  Productos" — no una suma de valores distribuidos por tienda (evita arrastrar el
  ruido de redondeo de la distribución proporcional).
- **Fila TOTALES**: `Sol.` por tienda y `Sol.`/`Conf.` de Total General (`Conf.` es la
  suma del confirmado real de cada producto).
- **Sin resaltado de color** en la celda "Conf." de Total General: se muestra el
  valor tal cual, sin marcar la diferencia con lo solicitado.
- **Encabezado (3 filas) y columnas fijas congelados** (`freeze_panes`) al desplazar,
  igual criterio de usabilidad que el punto 1.1.1 del requerimiento.

### Hoja 3: "Traslados (Detalle)" — formato largo, una fila por (producto, tienda)

Complementa a la matriz para quien prefiera filtrar/ordenar en Excel en vez de leer el
pivote. Mismas columnas que en la matriz, en formato plano:

| Columna | Descripción | Origen |
|---|---|---|
| Número de Traslado | DocNum de la ITR de la tienda, o `Pendiente`/`No aplica` | `solicitud_transferencia_detalle.doc_num` |
| Código Tienda | Código de la tienda destino | `tienda.codigo` |
| Nombre de la Tienda | Nombre de la tienda destino | `tienda.nombre` |
| Código Artículo | Código interno del producto | `pedido_detalle.codigo_interno` |
| Descripción | Descripción SAP del producto | `pedido_detalle.descripcion_sap` |
| Código de Barras | Código de barras del producto | `pedido_detalle.codigo_barras` |
| Cantidad Solicitada | Cantidad solicitada a esa tienda | `distribucion_confirmada.cantidad_solicitada` |
| Cantidad Confirmada | Cantidad confirmada por EL RAYO para esa tienda | `distribucion_confirmada.cantidad_confirmada` |
| Cantidad Asignada (ITR) | Cantidad que viaja en la Solicitud de Transferencia | `distribucion_confirmada.cantidad_asignada` |
| Confirmado Total Producto | Confirmado real del proveedor a nivel producto (ver limitación 3) | `pedido_respuesta_proveedor_detalle` vía `cantidad_confirmada_total` |

Las cinco columnas del requerimiento (número mínimo pedido en el punto 1.9) son: Número de
Traslado, Nombre de la Tienda, Código de Barras, Cantidad Solicitada y Cantidad Confirmada.
El resto se añade para que el formato largo no sea ambiguo y para no perder el confirmado
real del proveedor.

## Origen de Datos

```sql
-- Nº de traslado por tienda (última ITR creada, desempatando por fecha, no por MIN)
WITH itr AS (
    SELECT
        UPPER(LTRIM(RTRIM(d.tienda_codigo))) AS tienda_norm,
        d.doc_num,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(LTRIM(RTRIM(d.tienda_codigo)))
            ORDER BY st.creado_fecha DESC, d.creado_fecha DESC
        ) AS rn
    FROM solicitud_transferencia st
    INNER JOIN solicitud_transferencia_detalle d
        ON d.solicitud_transferencia_id = st.solicitud_transferencia_id
    WHERE st.pedido_id = ?
      AND d.estado = 'Creada'
      AND d.doc_num IS NOT NULL
)
SELECT tienda_norm, doc_num FROM itr WHERE rn = 1
```

Las cantidades y el código de barras reutilizan exactamente la misma consulta que ya usa
el endpoint de Redistribución (`DistribucionConfirmadaRepository.get_distribucion_completa`
+ `enriquecer_productos_con_pedido`).

## Validaciones

Idénticas a `/api/pedidos/{pedido_id}/distribucion/descargar-excel`: 404 si el pedido no
existe o si no hay distribución confirmada, con el mismo formato de error.

## Nombre del Archivo

Formato: `traslados_{numero_pedido}_v{version}_{fecha_hora}.xlsx`

## Permisos Requeridos

El usuario debe tener uno de los siguientes permisos:
- `odcsap.view` (Usuario EL RAYO)
- `mabel.view` (Usuario MABEL TRADING)

A diferencia del botón "Descargar Redistribución" (que hasta esta implementación solo era
visible en modo `soloLectura`), **este botón y el existente ahora se muestran para ambos
roles** en `MabelTradingRedistribucionView.vue`.

## Diferencias con "Descargar Redistribución"

| Característica | Descargar Redistribución | Exportar a Excel (Traslados) |
|---|---|---|
| Endpoint | `/api/pedidos/{id}/distribucion/descargar-excel` | `/api/pedidos/{id}/traslados/exportar-excel` |
| Nº de traslado | Consulta en vivo a SAP (`SAPServiceLayerClient`), con fallback silencioso si falla | Solo base de datos, sin llamada a SAP |
| Unidad de fila | Producto (con sub-filas por tienda en la hoja de detalle) | Producto **+** tienda (una fila por combinación) |
| Costo unitario | Sí (hoja "Distribución por Tienda") | No — fuera de alcance del requerimiento 1.9 |
| Bodegas | Incluidas, sin distinción visual | Incluidas, marcadas explícitamente como sin Nº de traslado |

## Soporte y Mantenimiento

Para cualquier modificación:
1. Generador: `src/endpoints/pedidos/redistribucion/_excel_traslados.py`
2. Handler y ruta: `src/endpoints/pedidos/redistribucion/endpoints_frontend.py`
   (`_exportar_traslados_excel_handler`, `exportar_traslados_excel`)
3. Origen del Nº de traslado: `SolicitudTransferenciaRepository.get_doc_num_itr_por_pedido_id`
   en `src/database/repositories/solicitud_transferencia_repository.py`
4. Tests: `tests/test_traslados_export_excel.py`
5. Frontend: `src/modules/mba3-consultas/views/MabelTradingRedistribucionView.vue`
   (botón + `handleExportarTrasladosExcel`), método de service en
   `src/modules/mba3-consultas/services/domains/pedidos.ts`
   (`exportarTrasladosExcel`)

Ver también: [CONFIGURACION_DESCARGA_DISTRIBUCION_EXCEL.md](CONFIGURACION_DESCARGA_DISTRIBUCION_EXCEL.md)
para el export "hermano" de Redistribución del que este endpoint reutiliza el patrón de
descarga y los estilos (`_crear_estilos` en `_excel_generators.py`), pero **no** su libro:
son dos endpoints y dos archivos `.xlsx` distintos.

## Pendiente de decisión del negocio (no bloqueante para esta entrega)

- Persistir el resultado de `OCSAPService._enviar_itrs_por_bodega` para que las bodegas
  también tengan Nº de traslado (limitación 2). Estimado: +1 día, no incluido en el
  cronograma original del requerimiento.

---

**Fecha de implementación:** 2026-08-05
**Estado:** Completado (mínimo contractual del requerimiento 1.9)
