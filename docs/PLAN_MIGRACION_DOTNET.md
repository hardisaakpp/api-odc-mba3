# Migración de api-odc-mba3 a .NET: arquitectura y plan

Propuesta para reescribir `api-odc-mba3` (FastAPI + Celery) en .NET sin cortar el servicio y sin que el frontend (`web-scnexus`) tenga que cambiar.

- **Estado:** propuesta, pendiente de aprobación.
- **Fecha:** 2026-09-24.
- **Alcance:** todo el backend (`src/`, tareas Celery, runner de migraciones SQL). No incluye cambios de esquema de BD ni de frontend.

---

## 1. Decisiones principales

| Tema | Decisión | Motivo |
|---|---|---|
| Plataforma | **.NET 10 LTS** | .NET 8 (el de Core y del middleware) pierde soporte el 10-nov-2026. Conviene planificar también la subida de esos dos proyectos. |
| Estilo de arquitectura | Capas **Api / Application / Domain / Infrastructure**, organizadas por módulo de negocio | Es la misma estructura que `api-middleware-sap`, así el equipo trabaja con un solo patrón. |
| Acceso a datos | **Dapper + Microsoft.Data.SqlClient**, con las **mismas consultas SQL** | Hay unas 490 consultas escritas a mano que ya funcionan. Pasarlas a Entity Framework obligaría a rehacer y volver a validar todas. |
| Tareas en segundo plano | **Hangfire** con almacenamiento en SQL Server, en un proceso Worker aparte | Reemplaza a Celery, Celery Beat y Flower (Hangfire trae su propio panel). |
| Redis | **Se mantiene mientras conviven Python y .NET.** Al final se decide si retirarlo. | Python usa Redis para bloqueos distribuidos (envío de ODC, reintento de ST), para guardar el progreso de procesos y para pasar notificaciones del worker a la API. Mientras convivan, los dos lados tienen que usar **los mismos** bloqueos o se podrían duplicar envíos a SAP. |
| Convivencia | **Migración por módulos**, con un proxy inverso (YARP) delante | El frontend sigue llamando a una sola URL. Cada módulo se pasa a .NET cuando cumple su criterio de salida. |
| Contrato HTTP | **Idéntico al actual**: rutas, JSON en snake_case, códigos HTTP, formato de errores, eventos SSE | Es lo que hace posible migrar sin tocar el frontend. |

---

## 2. Inventario de lo que hay que migrar

Medido sobre el código actual:

| Capa | Tamaño | Contenido |
|---|---|---|
| `endpoints/` | ~17.600 líneas | ~140 rutas HTTP en 15 grupos |
| `database/repositories/` | ~17.000 líneas | 40 repositorios con SQL a mano |
| `database/services/` | ~19.000 líneas | Lógica de negocio (pedidos, ODC, ST, plantillas, cruce) |
| `database/clients/` | ~2.500 líneas | Clientes SAP: middleware, Service Layer directo, OPENQUERY |
| `database/mappers/` | ~770 líneas | Conversión de ODC, ITR y facturas al formato SAP |
| `tasks/` + `celery_app.py` | ~1.600 líneas | 8 tareas, 5 programadas en Beat, 2 colas |
| `utils/` | ~4.700 líneas | Correo (15 tipos), PDF, Excel, SSE, auditoría |
| `models.py`, `schemas/` | ~1.600 líneas | Modelos Pydantic (contrato de entrada y salida) |
| `middleware/`, `security/` | ~900 líneas | JWT, permisos, límite de peticiones, manejo de errores, log de peticiones |
| `scripts/` | 75 migraciones SQL + runner | Manifest YAML y tabla de control de migraciones aplicadas |
| `tests/` | 117 archivos, ~16.800 líneas | Servicios, repositorios, mappers |

### 2.1 Rutas HTTP por módulo

| Módulo | Rutas | Ejemplos |
|---|---:|---|
| Sistema y autenticación | 3 | `/health`, `/api/auth/me` (también `/api/Auth/me`) |
| Despachos y MBA3 | 9 | `/consultar`, `/migrar/completo`, `POST /migrar`, `/procesar-oc`, `/despachos/*`, `/remisiones/*`, `/pruebas` |
| Integración SAP | 3 | `POST /integrar-sap`, `/sap/test`, `/sap/test/direct` |
| Órdenes de compra | 11 | `/ordenes-compra/*` (PDF, Excel de integración, reintentar ST, cambiar SKU), `/historial-ordenes` |
| Pedidos | ~60 | CRUD, estados, edición y auditoría, proveedor y El Rayo, exportaciones, redistribución, proceso completo SAP |
| Plantillas Excel | 14 | `upload`, `upload-async`, `stream`, `resultado`, archivos, `storage/health` |
| Cruce de productos | 12 | Sincronizar maestros de MBA3 y SAP, buscar SKU, sugerencias, proceso async |
| Homologaciones SKU | 5 | CRUD, `bulk-update`, `sincronizar` |
| Notificaciones | 11 | SSE `/notificaciones/stream`, catálogo de tipos de correo, personas por correo |
| Preferencias de usuario | 6 | Sidebar y columnas por tabla |

### 2.2 Dependencias externas

| Dependencia | Cómo se usa hoy |
|---|---|
| SQL Server principal | Base de datos de la aplicación (pyodbc, `autocommit=False`, commit al salir del bloque) |
| SQL Server "SAP" | Solo para `OPENQUERY` al servidor vinculado `[MYHANADB]`: sincronización masiva del catálogo y respaldo cuando falla el middleware |
| SQL Server `sc_maestros` | Servidor de producción, **solo lectura** (`dbo.almacenes_local`) |
| MBA3 | API HTTP con autenticación digest y login que devuelve un JWT; consulta de facturas y remisiones |
| api-middleware-sap (.NET) | Canal por defecto hacia SAP. Responde HTTP 202 con un job cuando SAP está saturado. |
| SAP Service Layer directo | Modo alternativo cuando `SAP_USE_MIDDLEWARE=false` |
| Redis | Cola de Celery, progreso de procesos, bloqueos distribuidos, caché de jobs en curso, heartbeat de workers, canal de notificaciones |
| MinIO / S3 | Guarda los Excel originales de las plantillas |
| SMTP | Envío autenticado (Office 365) con respaldo en relay interno |
| SCNexus.Core | Emite el JWT (HS256, mismo secreto, issuer y audience) |

---

## 3. Arquitectura propuesta

### 3.1 Estructura de la solución

```
SCNexus.Odc.sln
├── src/
│   ├── Odc.Api/                  # ASP.NET Core: controladores, SSE, autenticación, errores, OpenAPI
│   ├── Odc.Worker/               # Proceso aparte con el servidor Hangfire (reemplaza worker + beat)
│   ├── Odc.Application/          # Casos de uso por módulo, validaciones, interfaces de salida
│   │   ├── Despachos/
│   │   ├── OrdenesCompra/
│   │   ├── IntegracionSap/       # Envío de ODC, ITR/ST, cierre de pedido, reconciliaciones
│   │   ├── Pedidos/              # Crud, Estados, Edicion, Exportacion, Proveedor, Rayo
│   │   ├── Redistribucion/       # Borrador, confirmación, traslados, proceso completo SAP
│   │   ├── Plantillas/           # Parser Excel, detección de formato, validación SAP
│   │   ├── CruceProductos/
│   │   ├── Homologaciones/
│   │   ├── Remisiones/
│   │   ├── Notificaciones/       # SSE y catálogo de correos
│   │   └── Preferencias/
│   ├── Odc.Domain/               # Reglas puras, sin E/S (ver 3.3)
│   └── Odc.Infrastructure/
│       ├── Persistence/          # Fábricas de conexión (3 BD), sesión y transacción, repositorios Dapper
│       ├── Mba3/                 # Cliente HTTP con digest y JWT
│       ├── Sap/                  # Middleware, Service Layer directo, OPENQUERY y dispatcher con respaldo
│       ├── Jobs/                 # Hangfire, progreso de procesos, bloqueos distribuidos
│       ├── Storage/              # S3/MinIO
│       ├── Email/                # MailKit y plantillas
│       ├── Documents/            # Excel (ClosedXML) y PDF (QuestPDF)
│       └── Realtime/             # Bus de notificaciones y puente con Redis
├── tools/
│   └── Odc.Migrations/           # Runner que lee el mismo migrations_manifest.yaml
└── tests/
    ├── Odc.UnitTests/
    ├── Odc.IntegrationTests/     # SQL Server en contenedor (Testcontainers)
    ├── Odc.ContractTests/        # Compara respuestas Python contra .NET
    └── Odc.GoldenFiles/          # Excel y PDF de referencia con su salida esperada
```

La API y el Worker salen de la **misma imagen Docker** con distinto punto de entrada, igual que hoy `mba3-api` y `mba3-celery-worker`.

### 3.2 Equivalencias técnicas

| Hoy (Python) | .NET | Cuidado con |
|---|---|---|
| FastAPI con `register_*_endpoints(app)` | Controladores con `Asp.Versioning`, como en el middleware | Las rutas deben quedar idénticas, incluida `/api/Auth/me` |
| Pydantic (`models.py`) | DTOs como `record` y **FluentValidation** | JSON con `JsonNamingPolicy.SnakeCaseLower`, nulos y formato de fechas y decimales iguales a los de hoy |
| `pyodbc` más context manager | `IDbConnectionFactory` (principal, SAP, maestros) y `IDbSession` con transacción por operación | Mantener el comportamiento actual: commit al terminar bien, rollback si hay error. La conexión a maestros debe ser **de solo lectura** a nivel de código. |
| `asyncio.to_thread` y pool de 64 hilos | Código async de punta a punta | Ya no hace falta dimensionar un pool de hilos |
| Celery, Beat y las colas `celery`/`maintenance` | Hangfire: trabajos recurrentes, colas `default`/`maintenance`, 3 trabajos en paralelo | Zona horaria **America/Bogota** en los horarios programados; límite de 10 min por tarea; que un trabajo no se ejecute dos veces a la vez |
| `proceso_estado_service` (progreso en Redis) | `IProcesoEstadoStore` con Redis durante la convivencia | Mismas claves y prefijos `plantilla-`, `proceso-sap-`, `cruce-` |
| Bloqueos Redis `lock:envio-odc:{id}` y `lock:reintento-st:{id}` | `IDistributedLock` sobre Redis con **las mismas claves** | Imprescindible mientras conviven: los dos lados tienen que respetar el mismo bloqueo |
| Heartbeat de workers en Redis | Monitoreo de servidores de Hangfire | El respaldo síncrono cuando no hay worker debe seguir existiendo |
| `notification_manager` en memoria y `sse_redis_bridge` | `Channel<T>` por suscriptor y `TypedResults.ServerSentEvents` (.NET 10) | Mismo formato de evento. Hay que mantener la regla de `produccion-elrayo.view` (ver `NOTIFICACIONES_SSE.md`). |
| PyJWT y `require_permission` | `JwtBearer` y políticas de autorización propias | Mismos claims de Core, mismo mapeo de roles a permisos y mismo acceso total para Admin (ver 5.2 sobre los permisos legacy) |
| slowapi | `Microsoft.AspNetCore.RateLimiting` | |
| `logging_config` y `request_logging` | Serilog con OpenTelemetry, igual que el middleware | |
| Cachés en memoria de 30 s | `IMemoryCache` | Mantener la cabecera `X-Cache: HIT/MISS` y la invalidación al escribir |
| `requests` hacia el middleware y SAP | `HttpClient` tipado con `Microsoft.Extensions.Http.Resilience` | Respetar los reintentos actuales (ODC 3, ITR 3, prevalidación 5 con espera base de 5 s) y el manejo del HTTP 202 con job |
| pandas `read_excel` | ClosedXML | Celdas vacías, fechas guardadas como número de Excel, textos con espacios, SKU que parecen número |
| openpyxl con imágenes (Pillow) | ClosedXML con imágenes | |
| reportlab | QuestPDF | Revisar su licencia comunitaria (gratuita bajo cierto nivel de facturación) |
| rapidfuzz | FuzzySharp | **Los puntajes no son idénticos**, hay que recalibrar los umbrales con casos reales |
| boto3 | AWSSDK.S3 con `ForcePathStyle = true` para MinIO | |
| smtplib con dos perfiles | MailKit | Mismo orden: primero autenticado, luego relay; timeout de 5 s; redirección de destinatarios en desarrollo |
| `.env` y `config.py` | `appsettings.json`, variables de entorno y DotNetEnv, con opciones validadas al arrancar | Replicar los chequeos obligatorios de producción |
| `migration_runner.py` | `tools/Odc.Migrations` | Leer el **mismo** manifest y la **misma** tabla de control, para no perder el historial |

### 3.3 Qué va en Domain

Aquí va la lógica pura, sin acceso a BD ni a red. Es lo que más conviene cubrir con tests unitarios:

- **Máquina de estados del pedido:** los 25 `estado_id`, las transiciones permitidas y los conjuntos `ESTADOS_PERMITEN_REDISTRIBUCION`, `ESTADOS_VALIDOS_PARA_ODC` y `ESTADOS_BLOQUEADOS_PROVEEDOR`. Hoy vive en `pedido_estados.py` más validaciones repartidas por los endpoints.
- **Cierre del pedido** (`PedidoCierreService`): ODC enviada y ST correcta pasan a 12, ST con error pasa a 13, y un reintento posterior que sale bien vuelve a evaluar el cierre.
- **Reglas de reintento de ODC:** el allowlist de códigos SAP (`-1116`), el origen `SAP_CONNECTION` y la heurística por texto del mensaje.
- **Conversión de docenas a packs** y la tabla `pack_conversion`.
- **Consolidación y redistribución de cantidades**, validación de precios y reglas de cabecera.

---

## 4. Cómo conviven Python y .NET

```
                      ┌──────────────────────────┐
  web-scnexus ──────► │  YARP (proxy inverso)     │
                      │  rutas por módulo         │
                      └──────┬──────────────┬─────┘
                             │              │
                ruta migrada │              │ ruta aún no migrada
                             ▼              ▼
                     ┌────────────┐   ┌──────────────┐
                     │  Odc.Api   │   │ FastAPI (py) │
                     │  Odc.Worker│   │ Celery       │
                     └─────┬──────┘   └──────┬───────┘
                           │   Redis compartido (bloqueos, progreso, canal SSE)
                           └──────┬──────────┘
                                  ▼
                   SQL Server · MinIO · middleware SAP · MBA3
```

**Reglas durante la convivencia:**

1. **Cada módulo se migra completo.** Un módulo incluye sus rutas, sus tareas en segundo plano y sus rutas de progreso (`resultado` y `stream`). Nunca debe quedar una tarea programada corriendo en los dos lados a la vez.
2. **El flujo ODC → SAP → ST → cierre se pasa de una sola vez.** Esto incluye `integrar-sap`, el proceso completo SAP, `reintentar-st` y las dos reconciliaciones. Es el único punto donde un error puede crear documentos duplicados en SAP.
3. **El SSE se queda en Python hasta el final.** Las acciones de .NET publican sus notificaciones en el mismo canal Redis que ya lee `sse_redis_bridge`, con el mismo formato. En la fase 9 se pasa `/notificaciones/stream` a .NET.
4. **Solo cambios de esquema aditivos**, y se aplican con el runner de siempre. Hangfire crea su propio esquema (`HangFire`), así que no toca las tablas actuales.
5. **Volver atrás tiene que ser inmediato.** Cualquier ruta regresa a Python cambiando la configuración de YARP, sin desplegar nada.

---

## 5. Antes de empezar: qué no migrar

La migración es una buena oportunidad para no arrastrar código muerto. Cada punto necesita confirmación del equipo, porque retirar algo implica verificar primero que el frontend no lo usa.

### 5.1 Código candidato a no migrar

| Elemento | Evidencia |
|---|---|
| `POST /api/pedidos/{id}/redistribuir` y `/confirmar-redistribucion` | Rutas huérfanas: el frontend usa otras (`ESTADOS_PEDIDO.md`) |
| `POST /api/pedidos/{id}/cargar-respuesta-proveedor` | Ningún componente del frontend la llama (estado 5, ya desactivado) |
| Ramas hacia los estados 5, 6, 9, 11, 14, 15 y 16 | Desactivados, con 0 transiciones en producción |
| `_validate_stock_before_st` | Marcado como obsoleto, sin llamadas |
| `es_estado_valido()` | Código muerto |
| Migración automática de despachos (`ENABLE_AUTO_MIGRATE`) | Legacy y apagada por defecto |
| `/pruebas` | Endpoint de depuración |
| `/consultar` | **Está definido dos veces** (`despachos_consultar.py` y `despachos_migrar.py`). Hay que ver cuál responde hoy y migrar solo esa. |

### 5.2 Cosas que no conviene replicar tal cual

- **Permisos legacy** (`legacy_permission`): su fecha de retiro era el 30-jun-2026 y ya pasó. Hay que confirmar en los logs que nadie usa `[BACKWARD COMPAT]` y no migrarlos.
- **Secreto JWT por defecto** (`clave_super_secreta_para_jwt_12345`): en .NET, arrancar en producción sin un secreto real debe fallar. Esto depende de que Core cambie su secreto.
- **Errores 403 que listan los permisos del usuario:** el mensaje revela información interna. Conviene devolver un mensaje genérico.
- **Las tres copias casi iguales del código de conexión** en `connection.py`: se reemplazan por una sola fábrica.

---

## 6. Plan por fases

Cada fase termina con sus rutas funcionando en .NET detrás de YARP y con su criterio de salida cumplido. Las semanas corresponden a **un desarrollador trabajando con Claude Code**. Con dos personas, las fases 5 a 8 se pueden hacer en paralelo.

### Fase 0: preparación (1–2 semanas)

- Confirmar las exclusiones de la sección 5.
- Congelar el contrato: exportar el OpenAPI actual (`npm run sync:openapi` en el frontend) y guardarlo como referencia.
- **Juntar datos de referencia.** Hoy solo hay acceso a `store_control` en Docker local, sin bases remotas, así que esto hay que conseguirlo antes de empezar:
  - Excel reales de plantillas, al menos uno por formato de proveedor, y la salida actual del parser para cada uno.
  - Payloads reales enviados a SAP (ODC e ITR) y sus respuestas, tomados de `sap_integration_logs`.
  - Un respaldo anonimizado de la BD de test para las pruebas de integración.
- Definir un ambiente de SAP o del middleware en modo simulado para las pruebas de envío.

**Criterio de salida:** exclusiones aprobadas y datos de referencia disponibles en el repositorio de tests.

### Fase 1: base de la solución (2 semanas)

- Crear la solución, los proyectos y las reglas de estilo.
- Pipeline en `azure-pipeline/`, imagen Docker y servicios en `docker-compose` junto a los de Python.
- Configuración con opciones validadas al arrancar y las mismas variables de entorno.
- Serilog, OpenTelemetry, log de peticiones y manejo de errores **con el mismo formato de respuesta** que `exception_handlers.py`.
- Autenticación JWT, políticas de permisos, `require_any_permission`, `require_admin` y límite de peticiones.
- `IDbConnectionFactory` para las 3 BD, `IDbSession` con transacción y un repositorio base con Dapper.
- YARP con todas las rutas apuntando a Python al principio.
- Comparador de contrato: ejecuta la misma petición contra Python y .NET y compara el JSON, ignorando campos volátiles como fechas e ids nuevos.
- Port de `migration_runner` a `tools/Odc.Migrations`.

**Criterio de salida:** `/health` y `/api/auth/me` servidos por .NET, con el comparador de contrato en verde.

### Fase 2: módulos de solo lectura y bajo riesgo (1–2 semanas)

- Preferencias de usuario (6 rutas).
- Catálogo de correos: tipos y personas (9 rutas, solo Admin).
- Listados auxiliares de pedidos: `estados`, `creadores`, `modificadores`, `existe`, `tiendas/buscar`.
- Consultas de despachos y remisiones: `count` (con su caché de 30 s), `detalles`, `/remisiones`.
- Historial y logs de ODC: `/historial-ordenes`, `/ordenes-compra/logs`.

**Criterio de salida:** una semana en producción sin diferencias de contrato y con la vuelta atrás probada.

### Fase 3: integraciones de infraestructura (2–3 semanas)

No expone rutas nuevas, pero las fases siguientes dependen de esto:

- **Cliente MBA3:** autenticación digest, login con JWT, reintento de formatos ante el error 005 y renovación de sesión.
- **Clientes SAP:** middleware (manejo del 202 con consulta del estado del job, caché de jobs en curso), Service Layer directo y OPENQUERY. Encima va el dispatcher que prueba el middleware primero y cae a OPENQUERY si falla, controlado por `SAP_USE_MIDDLEWARE` y `USE_BATCH_VALIDATION`.
- **Caché de SAP en BD:** `producto_sap_cache` y `bodega_sap_cache`, con vigencia de `SAP_CACHE_DAYS`.
- **Storage S3/MinIO** y su chequeo de salud.
- **Correo:** los 15 tipos de `email_notifier.py` con sus plantillas, la resolución de destinatarios desde BD y la redirección en desarrollo. Validar comparando el HTML generado.
- **Hangfire, progreso de procesos y bloqueos distribuidos** sobre Redis compartido.
- **Publicación de notificaciones SSE** en el canal Redis existente.

**Criterio de salida:** tests de integración de cada cliente en verde contra simulaciones y contra el ambiente de test.

### Fase 4: flujo despachos → ODC → SAP (4–5 semanas, la más crítica)

Se migra **completa** y se activa en un solo cambio de YARP:

- Despachos: `/consultar`, `/migrar/completo`, `POST /migrar`, `/procesar-oc`, incluida la conversión de docenas a packs.
- Órdenes de compra: listado con caché, detalles, borrado, cambio de SKU en una línea, integración SAP, Excel de integración y **PDF de la ODC** con QuestPDF.
- `OCSAPService` (~1.900 líneas): prevalidación por lote o línea por línea, envío con reintentos, ODC encoladas y resolución de jobs previos, detección de ODC atascadas en ENVIANDO.
- `StockTransferService` (~2.100 líneas): creación de ITR por tienda, detección del origen, reintento de pendientes y nueva evaluación del cierre.
- `PedidoCierreService` y registro en `sap_integration_logs`.
- Mappers de SAP (`sap_oc_mapper`, `sap_stock_transfer_mapper`, `factura_mapper`). Se validan con **snapshots**: el JSON generado debe ser idéntico al de Python para los mismos datos de entrada.
- Tareas programadas: reconciliación de ODC encoladas (cada 5 min) y de ST (a diario de lunes a sábado y el domingo con ventana más amplia), con su alerta por falta de ejecución y el aviso a técnicos.

**Criterio de salida:**
- Los payloads a SAP coinciden al 100 % con Python en todos los casos de referencia.
- Una semana de ejecución en paralelo en test sin duplicados en SAP.
- Las tareas de Celery equivalentes quedan **apagadas** en el mismo despliegue.

### Fase 5: pedidos (3–4 semanas)

- CRUD, importación desde Excel y envío (`/enviar`).
- Transiciones de estado: gestionar, confirmar producción, confirmar para redistribución, despachar y facturar, finalizar, cancelar, cancelar por El Rayo, aceptar producción pospuesta. Todas pasan por la máquina de estados de Domain.
- Edición de costo, total y comentario, modificaciones de columnas y log de auditoría (`audit_context`, `audit_log_service`).
- Proveedor y El Rayo: formulario, respuesta, diferencia de producción, confirmar con diferencia y confirmaciones del Rayo.
- Exportaciones: para el proveedor, plano MBA, pedido y pedido original, CSV y Excel, Excel de margen.
- Notificaciones de cada acción, respetando la regla de `produccion-elrayo.view`.

**Criterio de salida:** los tests de la máquina de estados cubren las 25 × 25 combinaciones de transición y los Excel exportados coinciden con los de referencia.

### Fase 6: redistribución y proceso completo SAP (2–3 semanas)

- Borrador, distribución inicial, confirmación y ajuste de bodegas.
- Reporte de diferencias (JSON y Excel) y exportación de traslados en Excel.
- Proceso completo SAP en sus versiones síncrona y asíncrona (`proceso-completo-sap-async`, `resultado`, `stream`), con respaldo síncrono cuando no hay worker. Reutiliza lo construido en la fase 4.

**Criterio de salida:** el flujo E2E 2 de `ALINEACION_FRONT_ASYNC.md` pasa, incluida la reanudación a partir del `process_id`.

### Fase 7: plantillas Excel (2–3 semanas)

- Parser de pedidos (cabecera, detalle, tiendas y utilidades), detector y manejador de formatos, consolidador y validador de precios.
- Validación combinada de código, Pack y PVP contra SAP, con los mapas `correcciones_codigos` y `correcciones_pack_pvp` y reintento sin estado en el servidor.
- `upload`, `upload-async`, `resultado`, `stream`, `sap-info-productos`, gestión de archivos en MinIO y descarga del original.

**Criterio de salida:** **cada** Excel de referencia produce exactamente la misma salida que en Python. Es el módulo con más reglas implícitas: si un archivo no coincide, se investiga antes de continuar.

### Fase 8: cruce de productos y homologaciones (1–2 semanas)

- Sincronización de maestros de MBA3 y SAP hacia las tablas staging (lectura masiva por OPENQUERY), proceso asíncrono de cruce, búsqueda de SKU y sugerencias.
- Homologaciones SKU: CRUD, actualización masiva y sincronización.
- Umbrales de FuzzySharp recalibrados con pares reales ya homologados.

**Criterio de salida:** las sugerencias sobre el conjunto de referencia coinciden en al menos el X % con las de Python. **El equipo tiene que definir X**, porque los puntajes de las dos librerías no son idénticos.

### Fase 9: corte final y limpieza (1–2 semanas)

- Pasar `/notificaciones/stream` a .NET.
- Ejecución en paralelo durante 2 semanas con Python apagado pero listo para volver.
- Retirar FastAPI, Celery, Beat y Flower. **Decidir si Redis se queda** (por ejemplo, para escalar a varias instancias) o se reemplaza por SQL Server (`sp_getapplock` para los bloqueos, una tabla para el progreso y otra de salida para las notificaciones).
- Actualizar la documentación de `docs/` y los runbooks de despliegue.

---

## 7. Resumen de tiempos

| Fase | Semanas |
|---|---|
| 0. Preparación | 1–2 |
| 1. Base de la solución | 2 |
| 2. Solo lectura | 1–2 |
| 3. Integraciones | 2–3 |
| 4. Flujo ODC → SAP | 4–5 |
| 5. Pedidos | 3–4 |
| 6. Redistribución | 2–3 |
| 7. Plantillas | 2–3 |
| 8. Cruce y homologaciones | 1–2 |
| 9. Corte final | 1–2 |
| **Total (1 dev + Claude Code)** | **19–28 semanas** |

Esto queda por encima de la primera estimación (14–24 semanas). La revisión detallada encontró infraestructura que no se veía a simple vista: bloqueos y progreso en Redis, el puente de notificaciones SSE, tres bases de datos, la autenticación digest de MBA3 y el runner de migraciones. También suma el tiempo de convivencia en paralelo de las fases 4 y 9. Con dos desarrolladores desde la fase 5, el total baja a unas **16–22 semanas**.

---

## 8. Estrategia de pruebas

| Tipo | Qué cubre | Herramienta |
|---|---|---|
| Unitarias | Domain: estados, cierre, reintentos, conversión de packs, redistribución | xUnit |
| Port de pytest | Los 117 archivos actuales como especificación del comportamiento | xUnit |
| Integración | Repositorios con Dapper contra SQL Server real, con los scripts de `scripts/` aplicados | Testcontainers |
| Contrato | Misma petición a Python y a .NET, JSON comparado | `Odc.ContractTests` |
| Snapshots SAP | Payloads de ODC e ITR idénticos para las mismas entradas | Verify |
| Archivos de referencia | Salida del parser de Excel; Excel y PDF generados, comparando el contenido y no los bytes | `Odc.GoldenFiles` |
| E2E | Checklist de `ALINEACION_FRONT_ASYNC.md` y los Playwright `test:e2e:mba3` del frontend | Playwright |

---

## 9. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Documentos duplicados en SAP durante la convivencia | Alto | Mismos bloqueos Redis, el flujo SAP se migra en un solo cambio y las tareas se apagan del lado Python en el mismo despliegue |
| Diferencias al leer Excel (fechas, vacíos, tipos) | Alto | Archivos de referencia obligatorios en la fase 7 antes de activar |
| Sin acceso a datos reales (solo BD local) | Medio | Conseguir los datos de referencia en la fase 0; si no se consiguen, las fases 4 y 7 no pueden cerrarse |
| El proyecto Python sigue cambiando durante la migración | Medio | Congelar funcionalidades por módulo desde que empieza su fase; lo urgente se hace en los dos lados |
| Puntajes distintos entre FuzzySharp y rapidfuzz | Bajo | Recalibrar umbrales en la fase 8 |
| Licencia de QuestPDF | Bajo | Verificar el nivel de facturación; la alternativa es PdfSharp/MigraDoc |
| Zona horaria de los horarios programados | Bajo | Usar `America/Bogota` explícita en Hangfire y probar el cambio de día |

---

## 10. Decisiones pendientes del equipo

1. Aprobar las exclusiones de la sección 5.
2. Confirmar en los logs que los permisos legacy ya no se usan.
3. Definir el porcentaje X de coincidencia para el cruce de productos (fase 8).
4. Si al final Redis se queda o se reemplaza (fase 9).
5. Si la subida de Core y del middleware a .NET 10 se agenda junto con esta migración.
