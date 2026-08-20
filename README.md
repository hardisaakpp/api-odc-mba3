# MBA3 Consultas

Sistema para consultar y gestionar pedidos, despachos y órdenes de compra desde MBA3 (4D) con integración a SQL Server y SAP.

## 🚀 Inicio Rápido

### Requisitos Previos
- **Docker Desktop** (recomendado para desarrollo: stack completo con perfil `app`)
- Python 3.9+ (migraciones, tests, lint y alternativa host sin Docker)
- SQL Server
- Redis (incluido en Docker; en host solo si no usas el stack `app`)
- Acceso a MBA3 API y SAP (opcional)

### Instalación

```bash
# 1. Clonar repositorio
git clone <repo-url>
cd mba3-consultas

# 2. Crear entorno virtual
python -m venv venv
venv\Scripts\activate  # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
# Crear .env.develop / .env.test / .env.production según ambiente (obligatorios; ver CONFIGURACION.md)
# Arrancar con ENVIRONMENT acorde o usar .\run-dev.ps1 / .\run-test.ps1 / .\run-prod.ps1

# 5. Inicializar base de datos (primera vez)
python scripts/migration_runner.py --dry-run  # Validar
python scripts/migration_runner.py            # Ejecutar
```

### Iniciar Servidor

**Desarrollo recomendado — stack Docker (perfil `app`):**

Levanta Redis, MinIO, API, Celery worker y Celery beat en contenedores (misma aplicación que en producción, sin depender del `.venv` para esos procesos).

```powershell
# Primera vez o tras cambiar código Python del backend
.\scripts\docker-app-up.ps1

# Comprobar contenedores, /health, Redis, MinIO y Celery
.\scripts\docker-verify.ps1

# Frontend (repo scnexus-front): npm run dev → proxy a http://localhost:8000
```

Documentación completa: [docs/DOCKER_COMPOSE.md](docs/DOCKER_COMPOSE.md). Tras editar código Python: `.\scripts\docker-app-up.ps1` (la imagen copia el código en build; no hay hot-reload en contenedor). **No** levantes además la API en el host: el puerto **8000** quedaría en conflicto.

SQL Server, SAP, MBA3 y el Core siguen **fuera** de Docker; configúralos en `.env.develop` (desde el contenedor, evita `SQL_SERVER_SERVER=localhost` si la BD está en tu PC — usa `host.docker.internal` o el host real).

---

**Alternativa — procesos en el host (venv):**

Útil si necesitas `uvicorn --reload` al guardar archivos o depurar con el IDE sin rebuild.

```powershell
# Stack completo en Docker (recomendado): Redis + MinIO + API + Celery
.\scripts\docker-app-up.ps1
.\scripts\docker-verify.ps1

# Producción Linux (srv-mabuiosapi): desde /opt/odc-sap
# ./deploy-prod.sh   — ver docs/DEPLOY_DOCKER_PRODUCCION.md y deploy/README.md
```

```powershell
# Solo API estable (sin Celery en el mismo script)
.\start_api.ps1          # sin recarga — menos ECONNRESET con Vite
.\start_api.ps1 -Dev     # con --reload
```

Ver también [docs/CELERY_QUICKSTART.md](docs/CELERY_QUICKSTART.md).

---

- **API Backend:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health
- **MinIO consola (stack Docker):** http://localhost:9101

Si el frontend (Vite) muestra **ECONNRESET** o **ECONNREFUSED**, comprueba que el stack `app` o la API en host estén arriba en el puerto 8000. Con `uvicorn --reload` en host, reinicios breves pueden cortar peticiones; con el stack Docker el proceso API es estable hasta que reconstruyas la imagen.

## 📋 Estructura del Proyecto

```
mba3-consultas/
├── src/                       # Código fuente
│   ├── api_server.py         # Servidor FastAPI
│   ├── celery_app.py         # Configuración Celery
│   ├── config.py             # Configuración general
│   ├── database/             # Capa de datos
│   │   ├── connection.py    # Conexiones DB
│   │   ├── repositories/    # Repositorios (acceso a datos)
│   │   ├── services/        # Servicios de negocio
│   │   └── mappers/         # Mapeo MBA3 ↔ SQL Server
│   ├── endpoints/           # Endpoints FastAPI
│   ├── services/            # Servicios de aplicación
│   ├── tasks/               # Tareas Celery
│   └── security/            # Autenticación y seguridad
├── docs/                    # Documentación técnica
├── scripts/                 # Scripts SQL y utilidades
└── tests/                   # Tests unitarios e integración
```

## 🎯 Funcionalidades Principales

### Gestión de Pedidos
- ✅ Creación y validación de pedidos desde Excel
- ✅ Validación de SKUs con homologaciones MBA3 ↔ SAP
- ✅ Gestión de distribuciones por tienda
- ✅ Validación de precios, descuentos e IVA
- ✅ Envío automático a MBA3

### Integración MBA3
- ✅ Consulta de despachos con autenticación automática
- ✅ Sincronización bidireccional con SQL Server
- ✅ Procesamiento de órdenes de compra
- ✅ Gestión de remisiones

### Integración SAP
- ✅ Envío de órdenes de compra a SAP Service Layer
- ✅ Consulta de productos y conversión de unidades
- ✅ Validación de tiendas contra catálogo SAP
- ✅ Logs detallados de integración

### Procesos Automáticos
- ✅ Sincronización automática con Celery
- ✅ Procesamiento en background
- ✅ Monitoreo con Flower

## 📚 Documentación

La documentación completa está organizada en el directorio `docs/`. 

### 📖 Guías de Inicio
- **[Índice de Documentación](docs/README.md)** ⭐ - Punto de entrada principal
- **[Docker Compose (stack `app`)](docs/DOCKER_COMPOSE.md)** 🐳 - Desarrollo con API + Celery + Redis + MinIO en contenedor
- **[Alineación jobs async (front ↔ API)](docs/ALINEACION_FRONT_ASYNC.md)** - Contrato polling/SSE y checklist E2E
- **[Configuración](docs/CONFIGURACION.md)** - Setup completo de variables de entorno
- **[Desplegar en servidor de pruebas (DESA)](docs/DEPLOY_TEST.md)** 🧪 - Backend (rama `test`, systemd, Docker Redis/MinIO) y referencia al despliegue del frontend
- **[Actualizar backend en producción (Linux)](docs/DEPLOY_PRODUCCION.md)** 🐧 - git pull, pip install, systemctl restart
- **[Sistema de Migraciones](docs/DEPLOY_MIGRATIONS.md)** 🗄️ - Despliegue seguro de BD
- **[Celery Quick Start](docs/CELERY_QUICKSTART.md)** 🚀 - Procesos automáticos en 5 pasos
- **[Quick Start Homologaciones](docs/QUICKSTART_HOMOLOGACIONES.md)** 🚀 - SKU en 3 pasos

### 📋 Documentación de API
- **[Endpoints](docs/ENDPOINTS.md)** - Referencia completa de API REST
- **[Flujo Completo](docs/FLUJO_COMPLETO.md)** - Flujo de procesamiento end-to-end
- **[Estructura BD](docs/ESTRUCTURA_BD_PEDIDOS.md)** - Modelo de datos completo

### ⚙️ Guías Especializadas
- **[Integración SAP](docs/INTEGRACION_SAP.md)** - Configuración e integración con SAP
- **[Homologaciones SKU](docs/HOMOLOGACIONES_SKU.md)** - Sistema de gestión de SKUs
- **[Celery Implementation](docs/CELERY_IMPLEMENTATION.md)** - Documentación completa de Celery
- **[Seguridad](docs/SEGURIDAD.md)** - Autenticación y seguridad
- **[Testing](docs/TESTING.md)** - Guía de pruebas

> 💡 **Tip:** Comienza por [docs/README.md](docs/README.md) para una guía completa organizada por objetivos

## 🔌 Endpoints Principales

### Flujo de Procesamiento
1. **GET `/consultar`** - Consultar despachos desde MBA3 (solo lectura)
2. **GET `/migrar/completo`** - Consultar MBA3 y guardar en SQL Server (`despacho_*`). Alternativa: **POST `/migrar`** para persistir un payload ya obtenido (ver OpenAPI `/docs`)
3. **GET `/procesar-oc`** - Crear órdenes de compra desde despachos
4. **POST `/integrar-sap`** - Enviar ODC pendientes a SAP Service Layer

### Gestión de Pedidos
La API de pedidos vive bajo el prefijo **`/api/pedidos`**. Resumen:
- **POST `/pedidos/importar-excel`** - Importar pedido desde Excel
- **GET `/api/pedidos`** - Listar pedidos (filtros en query)
- **GET/POST/PATCH/DELETE** en **`/api/pedidos/...`** - CRUD, estados, exportación, redistribución, integración SAP, etc.

### Homologaciones
- **GET `/api/homologaciones-sku`** - Listar homologaciones SKU (paginado)
- **POST `/api/homologaciones-sku/sincronizar`** - Sincronizar desde despachos

Ver [docs/ENDPOINTS.md](docs/ENDPOINTS.md) para documentación completa.

## 🗄️ Migraciones de Base de Datos

El proyecto usa un **sistema automatizado de migraciones** para despliegues seguros y trazables.

```bash
# Ver estado de migraciones
python scripts/migration_runner.py --status

# Validar sin ejecutar (dry-run)
python scripts/migration_runner.py --dry-run

# Ejecutar migraciones pendientes
python scripts/migration_runner.py

# Ejecutar solo migraciones base
python scripts/migration_runner.py --category base
```

**Documentación completa:** [docs/DEPLOY_MIGRATIONS.md](docs/DEPLOY_MIGRATIONS.md)

### Características
- ✅ Trazabilidad completa (quién, cuándo, cuánto tardó)
- ✅ Idempotencia (no ejecuta dos veces la misma migración)
- ✅ Orden garantizado con dependencias
- ✅ Dry-run para validación segura
- ✅ Rollback automático en caso de error
- ✅ Categorización para despliegues parciales

## 🛠️ Scripts Útiles

```bash
# Verificar conexión a SQL Server
python scripts/check_db_connection.py

# Probar consulta SAP
python scripts/test_sap_query.py --sku "5-0012.9"

# Obtener JWT de MBA3
python src/main.py --login

# Ejecutar tests
pytest tests/ -v
```

## 🔒 Seguridad

- ✅ Autenticación JWT con SCNexus.Core
- ✅ Validación de consultas SQL (solo SELECT)
- ✅ Variables de entorno para credenciales sensibles
- ✅ Rate limiting opcional
- ✅ CORS configurable

Ver [docs/SEGURIDAD.md](docs/SEGURIDAD.md) para más detalles.

## 🏗️ Arquitectura

### Patrón de Capas
```
Endpoints (FastAPI)
    ↓
Services (Lógica de negocio)
    ↓
Repositories (Acceso a datos)
    ↓
Database (SQL Server)
```

### Principios Aplicados
- ✅ **SOLID** - Código modular y mantenible
- ✅ **Repository Pattern** - Abstracción de acceso a datos
- ✅ **Service Layer** - Lógica de negocio aislada
- ✅ **Dependency Injection** - Desacoplamiento de componentes

## 🧪 Testing

```bash
# Ejecutar todos los tests
pytest tests/

# Tests específicos
pytest tests/test_services/ -v

# Con coverage
pytest --cov=src tests/
```

Ver [docs/TESTING.md](docs/TESTING.md) para más información.

## 📝 Notas Importantes

- El JWT de MBA3 se obtiene y renueva automáticamente
- Los datos se guardan en SQL Server cuando `ENABLE_SQL_SERVER_STORAGE=true`
- Las consultas SAP usan cache para optimizar rendimiento
- Celery requiere Redis ejecutándose
- Ver logs para debugging detallado

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Add nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto es privado y confidencial.

---

**Versión API (OpenAPI):** 2.1.0  
**Última actualización documentación:** mayo 2026  
**Documentación completa:** [docs/README.md](docs/README.md)
