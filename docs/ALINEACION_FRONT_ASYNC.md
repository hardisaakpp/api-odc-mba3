# Alineación front ↔ backend (jobs async)

Documentación **canónica del contrato compartido** entre `mba3-consultas` (API + Celery) y `scnexus-front` (módulo `mba3-consultas`).

La copia detallada con rutas de archivos del front vive en el repo del frontend:

`scnexus-front/docs/ALINEACION_FRONT_ASYNC.md`

---

## Patrón general

```
POST async (o upload) → accepted + process_id  [o 200 sync sin poll]
        ↓
GET .../stream/{process_id}  (opcional, SSE)
        ↓ si falla
GET .../resultado/{process_id}  cada 2 s
        ↓
Estado terminal → persistencia en BD → front refresca GET pedido / OCs / homologaciones
```

**Reglas que el backend debe cumplir:**

| Regla | Backend |
|--------|---------|
| Progreso | En Redis: `status: processing`, `step`, `progress`, `message` |
| Terminal plantilla | `status: completed` en Redis; `GET resultado` devuelve cuerpo de upload síncrono |
| Terminal proceso SAP | `status: completed` en Redis; `GET resultado` devuelve cuerpo de negocio + `process_status: completed`, `progress: 100` |
| Terminal cruce | `GET resultado` con `{ status: success, data: ... }` o `status: processing` + `estado: { ... }` |
| Fallback sin Celery | `fallback: sync`, `process_id: null`, `async: false` (plantilla, proceso SAP) |
| Cruce inicio async | `200` + `status: success` + `process_id` (no `202 accepted`) |
| Sin worker | Plantilla/SAP: fallback sync si no hay workers; cruce: poll hasta timeout |

---

## Endpoints async

| Flujo | Inicio | Progreso | Terminal |
|-------|--------|----------|----------|
| Plantilla | `POST /api/plantillas/upload-async` | `GET .../resultado/{id}`, `GET .../stream/{id}` | Cuerpo upload en `completed` |
| Proceso SAP | `POST .../proceso-completo-sap-async` | `GET .../proceso-sap/resultado/{id}`, `GET .../stream/{id}` | `ProcesoCompletoSAPResponse` |
| Cruce | `POST /cruce-productos/iniciar` | `GET .../resultado/{id}`, `GET .../stream/{id}` | `{ status: success, data }` |

Prefijos `process_id`: `plantilla-`, `proceso-sap-`, `cruce-`.

---

## Validación de plantilla: código + Pack/PVP en una sola pasada

`POST /api/plantillas/upload-async` valida código, Pack y PVP contra SAP **juntos**
y lanza una única excepción combinada cuando alguno falla — ya no es secuencial
(código bloqueando, Pack/PVP en un reintento aparte). El `error_code` indica solo
cuál se detectó *primero*, no cuáles vienen en el payload:

| `error_code` | Significa | Pero el payload puede traer |
|---|---|---|
| `PRODUCTOS_NO_VALIDOS_SAP` | hay código(s) inválido(s) | `validacion_sap` **y**, si también hay Pack/PVP, `validacion_pack_pvp` |
| `PACK_PVP_INVALIDOS_SAP` | todos los códigos son válidos, falló Pack/PVP | solo `validacion_pack_pvp` |

**El frontend debe detectar cada bloque por presencia de su clave
(`validacion_sap` / `validacion_pack_pvp`), no por `error_code` ni parseando
`message`** — con ambos fallando, `error_code` es `PRODUCTOS_NO_VALIDOS_SAP` pero
`validacion_pack_pvp` viene igual en el payload.

Cada entrada de `validacion_sap.detalle_validacion[codigo]` para un código
**todavía inválido** ahora también trae `pack_excel` y `pvp_excel` — el Pack/PVP
tal como venían en esa fila del Excel (`null` si no venían). Junto con
`pack_sap`/`pvp_sap` del endpoint de abajo, permite detectar el mismatch de
Pack/PVP automáticamente apenas el usuario elige una sugerencia, sin esperar al
reintento. Misma convención que el resto de la validación de Pack/PVP: si el
código aparece en varias filas del Excel, se toma el primer valor no nulo, sin
comparar entre filas.

Los dos mapas de corrección usan claves distintas a propósito:

- `correcciones_codigos`: código **tal como viene en el Excel** → código SAP elegido.
- `correcciones_pack_pvp`: código **ya corregido/resuelto en SAP** → `{ pack?, pvp? }`.

El reintento es **stateless**: cada llamada reevalúa desde cero contra lo que llega
en esa petición (siempre el Excel original, nunca uno modificado). El cliente debe
acumular y reenviar la unión de las correcciones de todas las rondas anteriores, o
las de una ronda se pierden en la siguiente.

Por qué siguen siendo mínimo 2 rondas si el frontend no consulta SAP antes de
reintentar: el Pack/PVP de un código no se puede evaluar hasta saber a qué ítem de
SAP mapea, y eso solo se sabe después de que el usuario elige una sugerencia para
un código inválido. Cada sugerencia en `validacion_sap.detalle_validacion[codigo]
.sugerencias_sap[]` ya trae `pack` (comparable de inmediato contra el Pack del
Excel, sin llamada extra), pero no trae `pvp`.

### `GET /api/plantillas/sap-info-productos?codigos=A,B,C` — para resolver en 1 sola ronda

Devuelve Pack, PVP (Precio Minorista) y código de barras de SAP para hasta 100
códigos, en una sola consulta batch (con cache — mismo camino que
`get_or_fetch_productos_batch`). Pensado para que el modal, al momento en que el
usuario elige una sugerencia para un código inválido, consulte de una vez si esa
elección también implica una discrepancia de PVP — y la resuelva en la misma
ronda en la que resuelve el código, en vez de descubrirla en el reintento
siguiente.

```json
GET /api/plantillas/sap-info-productos?codigos=R311.AMAZ-4-1012,CODIGO-INEXISTENTE

{
  "productos": {
    "R311.AMAZ-4-1012": {
      "encontrado": true,
      "motivo": null,
      "pack_sap": "X1",
      "pvp_sap": 6.99,
      "codigo_barras": "7861215678025",
      "item_name": "COLORS C. CASUAL LISA  TUCAN SURTIDO X1"
    },
    "CODIGO-INEXISTENTE": {
      "encontrado": false,
      "motivo": "no_existe",
      "pack_sap": null,
      "pvp_sap": null,
      "codigo_barras": null,
      "item_name": null
    }
  }
}
```

`motivo` cuando `encontrado: false`: `no_existe` | `inactivo` | `mismatch` | `null`
(no resuelto, ej. SAP deshabilitado). Nunca tumba la consulta completa por un
código problemático — cada código responde de forma independiente.

---

## Verificación automática (stack Docker)

```powershell
.\scripts\docker-app-up.ps1
.\scripts\docker-verify.ps1
```

Comprueba contenedores, `/health`, Redis/MinIO/SQL desde `mba3-api`, tareas Celery registradas y beat.

---

## Checklist E2E manual (con JWT)

**Automatizado (ítems 1 y 5, poll mock):** en `scnexus-front`, `npm run test:e2e:mba3` (`mba3-plantilla-async.spec.ts`, `mba3-async.spec.ts`). OpenAPI: `npm run sync:openapi` (API en `:8000`).  
**Live smoke:** `.env.test` + `E2E_LIVE=1` → `npm run test:e2e:mba3:live`.

Requisitos: perfil `app` arriba, front `npm run dev`, proxy a `http://localhost:8000`, usuario con permiso `mabel.view`.

| # | Flujo | Pasos | Éxito | Timeout / edge |
|---|--------|-------|-------|----------------|
| 1 | Plantilla | Subir Excel en cargar-plantilla | Modal progreso → pedido creado / redirect | Toast amarillo; refrescar; no ERROR local |
| 2 | Proceso SAP | Redistribución → Enviar ODC a SAP | Modal + doc SAP o partial con flags | Reanudar con banner si hay `process_id` en sessionStorage |
| 3 | Integrar ODC | Proceso completo → enviar una ODC | `ENVIADA` en tabla | Toast amarillo + refresh lista |
| 4 | Reintento ST | OC `ENVIADA` con ST pendiente | Botón reintentar → refresh flags | Transient 120s → warning |
| 5 | Cruce | Homologaciones → Cruce MBA3/SAP | Modal progreso → lista actualizada | Sin fallback sync en timeout de poll |
| 6 | Celery off | Parar `mba3-celery-worker`, plantilla | Fallback sync o error claro (`storage_required` si MinIO off) | Documentar en incidente; **no** automatizado |
| 7 | Migrar / ODC | Proceso completo → migrar o generar ODC | Lista/despachos actualizados | Transient → warning + refresh (ver matriz front) |

Marcar cada fila en PR o release notes cuando se valide en DESA.

---

## Síncronos (sin poll de job)

- `POST /integrar-sap` — timeout largo en front; estado en BD.
- `GET /migrar`, `GET /procesar-oc` — `metadata.oc_status`; `processing` en OC **no usado hoy** en backend.
- `POST /api/homologaciones-sku/sincronizar` — POST síncrono.

---

## Referencias

- [DOCKER_COMPOSE.md](DOCKER_COMPOSE.md) — stack de desarrollo
- [CELERY_QUICKSTART.md](CELERY_QUICKSTART.md) — Redis y workers
- Front: `scnexus-front/docs/ALINEACION_FRONT_ASYNC.md`
