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

## Verificación automática (stack Docker)

```powershell
.\scripts\docker-app-up.ps1 -Build
.\scripts\docker-verify.ps1
```

Comprueba contenedores, `/health`, Redis/MinIO/SQL desde `mba3-api`, tareas Celery registradas y beat.

---

## Checklist E2E manual (con JWT)

**Automatizado (ítems 1 y 6, poll mock):** en `scnexus-front`, `npm run test:e2e:mba3`. OpenAPI: `npm run sync:openapi` (API en `:8000`).  
**Live smoke:** `.env.test` + `E2E_LIVE=1` → `npm run test:e2e:mba3:live`.

Requisitos: perfil `app` arriba, front `npm run dev`, proxy a `http://localhost:8000`, usuario con permiso `mabel.view`.

| # | Flujo | Pasos | Éxito | Timeout / edge |
|---|--------|-------|-------|----------------|
| 1 | Plantilla | Subir Excel en cargar-plantilla | Modal progreso → pedido creado / redirect | Toast amarillo; refrescar; no ERROR local |
| 2 | Proceso SAP | Redistribución → Enviar ODC a SAP | Modal + doc SAP o partial con flags | Reanudar con banner si hay `process_id` en sessionStorage |
| 3 | Integrar ODC | Proceso completo → enviar una ODC | `ENVIADA` en tabla | Toast amarillo + refresh lista |
| 4 | Reintento ST | OC `ENVIADA` con ST pendiente | Botón reintentar → refresh flags | Transient 120s → warning |
| 5 | Cruce | Homologaciones → Cruce MBA3/SAP | Modal progreso → lista actualizada | Sin fallback sync en timeout de poll |
| 6 | Celery off | Parar `mba3-celery-worker`, plantilla | Fallback sync o error claro (`storage_required` si MinIO off) | Documentar en incidente |

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
