# Estados del pedido: tabla maestra y migración

## Resumen

Los estados del pedido se identifican por **`estado_id`** (número). El **nombre** es solo presentación y puede ser editado por el usuario sin afectar lógica ni históricos.

- **Verdad absoluta:** `estado_id` (1, 2, 3, …).
- **Presentación:** `estado_nombre` (editable en tabla `pedido_estado`).
- **Estado inicial** al subir Excel o crear pedido: **siempre `estado_id = 1`** (BORRADOR).

---

## Tabla maestra `pedido_estado`

| id | nombre (editable) | orden | Uso típico |
|----|-------------------|-------|------------|
| 1  | BORRADOR | 1  | Estado inicial (ex PENDIENTE_CONFIRMACION_PROVEEDOR) |
| 2  | NUEVO PEDIDO | 2  | Enviado a EL RAYO (notificación enviada) |
| 3  | GESTIONAR PEDIDO | 3  | Al hacer clic en Ver Detalle desde tabla Pedidos |
| 4  | CONFIRMADO | 4  | Redistribución (tras confirmar respuesta EL RAYO) |
| 5  | RESPUESTA_PROVEEDOR_CARGADA | 5  | Respuesta del proveedor cargada |
| 6  | CONFIRMADO_PROVEEDOR | 6  | Aprobado por proveedor |
| 7  | RECHAZADO_PROVEEDOR | 7  | Rechazado por proveedor |
| 8  | EN_AJUSTE_MABEL | 8  | En ajuste MABEL (redistribución) |
| 9  | REDISTRIBUIDO | 9  | Redistribución aplicada |
| 10 | CONFIRMADO REDISTRIBUCION | 10 | Pedido confirmado (redistribución confirmada) |
| 11 | PROCESADO_SAP | 11 | Procesado en SAP |
| 12 | CONFIRMADO_ENVIADO | 12 | Todas las ODC enviadas a SAP |
| 13 | PENDIENTE_LOGISTICA | 13 | OC OK, ST pendiente/error |
| 14 | ERROR_DATOS_MAESTROS | 14 | Error en datos maestros |
| 15 | EN_PROCESO | 15 | En proceso |
| 16 | COMPLETADO | 16 | Completado |
| 17 | DESPACHAR Y FACTURAR | 17 | Manual: desde Confirmado y Enviado (ODC enviada a SAP) |
| 18 | FINALIZADO | 18 | Estado final del flujo; solo desde Despachar y Facturar |
| 19 | CANCELADO | 19 | Pedido cancelado por MABEL TRADING desde Redistribución |

El **id es semántico** (no depende del orden en BD). El **orden** es solo para visualización (listas, filtros).

---

## Mapping: string legacy → estado_id

Para migración y compatibilidad temporal:

| String legacy (columna `estado`) | estado_id |
|----------------------------------|-----------|
| PENDIENTE_CONFIRMACION_PROVEEDOR | 1 (BORRADOR) |
| BORRADOR                         | 1 |
| NUEVO_PEDIDO                    | 2 |
| GESTIONAR_PEDIDO                | 3 |
| EN_REVISION                     | 4 (REDISTRIBUCION) |
| REDISTRIBUCION                  | 4 |
| CONFIRMADO                      | 4 |
| RESPUESTA_PROVEEDOR_CARGADA     | 5 |
| CONFIRMADO_PROVEEDOR            | 6 |
| RECHAZADO_PROVEEDOR             | 7 |
| EN_AJUSTE_MABEL                 | 8 |
| REDISTRIBUIDO                   | 9 |
| PEDIDO_CONFIRMADO               | 10 |
| CONFIRMADO REDISTRIBUCION       | 10 |
| PROCESADO_SAP                   | 11 |
| CONFIRMADO_ENVIADO              | 12 |
| PENDIENTE_LOGISTICA             | 13 |
| ERROR_DATOS_MAESTROS            | 14 |
| EN_PROCESO                      | 15 |
| COMPLETADO                      | 16 |
| DESPACHAR Y FACTURAR            | 17 |
| DESPACHAR_Y_FACTURAR            | 17 |
| FINALIZADO                      | 18 |
| CANCELADO                       | 19 |
| *(cualquier otro o NULL)*       | 1 (BORRADOR) |

---

## API: respuesta recomendada

Devolver siempre **id + nombre** para que el front no invente etiquetas:

```json
{
  "estado_id": 1,
  "estado_nombre": "BORRADOR"
}
```

El nombre debe venir de la tabla `pedido_estado` (JOIN o caché) para reflejar cambios del usuario.

---

## Plan de migración (sin downtime)

### Prerrequisitos

1. Ejecutar **`create_pedido_estado_table.sql`** (crea tabla y datos iniciales).
2. Asegurar que no quede ningún valor de `pedido.estado` sin mapear (ver mapping arriba).

### Fase 1: agregar estado_id sin romper nada

1. Ejecutar **`migrate_pedido_estado_id.sql`**:
   - Agrega columna `pedido.estado_id` (INT NULL).
   - Pobla `estado_id` desde `estado` (string) con el mapping explícito.
   - Asigna default `estado_id = 1` para nuevas filas.
   - Crea FK a `pedido_estado(id)` e índice en `estado_id`.
2. **No eliminar** la columna `estado` todavía: permite rollback y reportes antiguos.

### Fase 2: adaptar backend

1. Usar constantes de **`src/database/pedido_estados.py`** en toda la lógica:
   - Asignar estado inicial: `estado_id = ESTADO_BORRADOR` (1).
   - Actualizar estado: `update_estado(pedido_id, estado_id)`.
   - Validaciones: comparar por `estado_id` (p. ej. `estado_id in ESTADOS_VALIDOS_PARA_ODC`).
2. En lecturas: JOIN con `pedido_estado` y devolver `estado_id` + `estado_nombre` en la cabecera del pedido.
3. Filtros por estado: usar `estado_id` en lugar de string.

### Fase 3 (opcional): retirar columna estado

1. Cuando todo el código y reportes usen solo `estado_id`:
   - Eliminar columna `pedido.estado`.
   - Actualizar scripts/documentación que la referencien.

### Verificación post-migración

- No debe haber filas en `pedido` con `estado_id` NULL.
- El script de migración incluye un chequeo final; si aparece advertencia, revisar valores de `estado` no mapeados.

---

## Constantes en backend (Python)

Referencia única en **`src/database/pedido_estados.py`**:

- `ESTADO_BORRADOR = 1`, `ESTADO_RESPUESTA_PROVEEDOR_CARGADA = 2`, …
- `ESTADO_INICIAL = ESTADO_BORRADOR`
- Conjuntos: `ESTADOS_PERMITEN_REDISTRIBUCION`, `ESTADOS_VALIDOS_PARA_ODC`, `ESTADOS_BLOQUEADOS_PROVEEDOR`
- `estado_id_desde_legacy(estado_string)` para compatibilidad durante la transición.

No usar strings hardcodeados en lógica; usar siempre `estado_id` y estas constantes.
