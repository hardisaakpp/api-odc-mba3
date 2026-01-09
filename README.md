# MBA3 Consultas

Sistema para consultar y gestionar facturas desde la API de MBA3 (4D), con integración a SQL Server y SAP.

## 🚀 Inicio Rápido

### Instalación

```bash
# 1. Clonar repositorio
git clone <repo-url>
cd mba3-consultas

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env  # Editar con tus credenciales
```

### Configuración

Crear archivo `.env` en la raíz del proyecto. Ver [docs/CONFIGURACION.md](docs/CONFIGURACION.md) para detalles completos.

```env
# MBA3
MBA3_BASE_URL=http://192.168.2.159:8081
MBA3_CODIGO=tu_codigo_servicio
MBA3_PWD=tu_contraseña

# SQL Server
SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}
SQL_SERVER_SERVER=210.17.1.54
SQL_SERVER_DATABASE=store_control
SQL_SERVER_UID=tu_usuario
SQL_SERVER_PWD=tu_contraseña
ENABLE_SQL_SERVER_STORAGE=true

# SAP (opcional)
SAP_LINKED_SERVER=MYHANADB
SAP_DATABASE=SBO_MABEL_PROD
ENABLE_SAP_QUERIES=true
ENABLE_SAP_SERVICE_LAYER=true

# JWT Authentication (integración con SCNexus.Core)
JWT_SECRET=clave_super_secreta_para_jwt_12345
JWT_ISSUER=SCNexus.Core
JWT_AUDIENCE=SCNexus.Users
ENABLE_JWT_AUTH=true
```

### Iniciar Servidor

```bash
# Backend
python src/api_server.py
uvicorn src.api_server:app --reload --host 0.0.0.0 --port 8000

# Frontend (en otra terminal)
cd frontend
npm install
npm run dev
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173
- API Docs: http://localhost:8000/docs

## 📋 Estructura del Proyecto

```
mba3-consultas/
├── src/                    # Backend Python/FastAPI
│   ├── api_server.py       # Servidor FastAPI
│   ├── endpoints.py        # Endpoints de la API
│   ├── main.py            # Script CLI para login
│   ├── database/          # Módulo de persistencia
│   │   ├── connection.py  # Conexiones SQL Server
│   │   ├── services/      # Servicios de negocio
│   │   ├── repositories/  # Repositorios de datos
│   │   └── mappers/       # Mapeo MBA3 → SQL Server
│   └── services/          # Servicios de aplicación
├── frontend/              # Frontend Vue.js/TypeScript
│   └── src/
│       ├── views/         # Vistas principales
│       ├── components/    # Componentes reutilizables
│       └── stores/        # Estado global (Pinia)
├── docs/                  # Documentación técnica
└── scripts/              # Scripts SQL y utilidades
```

## 🔌 Endpoints Principales

### Flujo Completo de Procesamiento (4 Endpoints)

1. **GET `/consultar`** - Consultar despachos desde MBA3 (solo lectura)
2. **GET `/migrar`** - Consultar y guardar en `despacho_cabecera`/`despacho_detalle`
3. **GET `/procesar-oc`** - Copiar despachos a `orden_compra_cabecera`/`orden_compra_detalle` (estado: PENDIENTE)
4. **POST `/integrar-sap`** ⭐ - Enviar ODCs a SAP Service Layer (estado: PENDIENTE → ENVIADA)

### Otros Endpoints

- **GET `/health`** - Health check
- **GET `/sap/test?sku=...`** - Consultar producto en SAP (usa cache)

Ver [docs/ENDPOINTS.md](docs/ENDPOINTS.md) para documentación completa.

## 🎯 Funcionalidades

### Backend

- ✅ Consultas a API MBA3 con autenticación JWT automática
- ✅ Guardado automático en SQL Server
- ✅ Integración con SAP HANA (OPENQUERY) para conversión de unidades
- ✅ Integración con SAP Service Layer (Purchase Orders)
- ✅ Validación de consultas SQL (solo SELECT)
- ✅ Mapeo automático MBA3 → SQL Server
- ✅ Procesamiento de orden de compra
- ✅ Envío de órdenes de compra a SAP Service Layer

### Frontend

- ✅ Vista de facturas con filtros
- ✅ Consulta SQL dinámica
- ✅ Tabla interactiva con paginación
- ✅ Modal de detalles
- ✅ Tema claro/oscuro

## 📚 Documentación

La documentación está organizada en el directorio `docs/`. Ver el [índice completo](docs/README.md) para una guía detallada.

### Documentación Principal

- **[Índice de Documentación](docs/README.md)** ⭐ - Índice completo de documentación técnica
- **[Configuración](docs/CONFIGURACION.md)** - Variables de entorno y setup completo
- **[Endpoints](docs/ENDPOINTS.md)** - Documentación completa de API
- **[Flujo Completo](docs/FLUJO_COMPLETO.md)** - Flujo de los 4 endpoints principales
- **[Estructura de BD](docs/ESTRUCTURA_BD_PEDIDOS.md)** - Modelo de datos completo

### Guías de Inicio Rápido 🚀

- [Celery Quick Start](docs/CELERY_QUICKSTART.md) - Procesos automáticos con Celery en 5 pasos
- [Quick Start Homologaciones](docs/QUICKSTART_HOMOLOGACIONES.md) - Instalación en 3 pasos

### Documentación Especializada

- [Celery Implementation](docs/CELERY_IMPLEMENTATION.md) - Documentación completa de Celery
- [Integración SAP](docs/INTEGRACION_SAP.md) - Configuración e integración con SAP
- [Homologaciones SKU](docs/HOMOLOGACIONES_SKU.md) ⭐ - Sistema de gestión de homologaciones SKU
- [Seguridad](docs/SEGURIDAD.md) - Configuración de seguridad opcional
- [Testing](docs/TESTING.md) - Guía de pruebas
- [Frontend](frontend/README.md) - Guía del frontend Vue.js

> 💡 **Nota**: La documentación histórica y de referencia se encuentra en [docs/archivo/](docs/archivo/README.md)

## 🛠️ Desarrollo

### Scripts Útiles

```bash
# Obtener JWT de MBA3
python src/main.py --login

# Ejecutar consulta de prueba
python src/main.py --query

# Verificar conexión SQL Server
python scripts/check_db_connection.py

# Probar consulta SAP
python scripts/test_sap_query.py --sku "5-0012.9"
```

### Testing

```bash
# Backend
python -m pytest tests/

# Frontend
cd frontend
npm run test
```

## 🔒 Seguridad

- ✅ Validación de consultas SQL (solo SELECT)
- ✅ Bloqueo de operaciones peligrosas (INSERT, UPDATE, DELETE, etc.)
- ✅ Variables de entorno para credenciales
- ✅ `.env` en `.gitignore`
- ✅ Autenticación opcional mediante API Keys
- ✅ Rate limiting opcional

Ver [docs/SEGURIDAD.md](docs/SEGURIDAD.md) para más detalles.

## 📝 Notas

- El JWT de MBA3 se obtiene y renueva automáticamente
- Los datos se guardan automáticamente en SQL Server si está habilitado
- Las consultas SAP usan cache para mejorar rendimiento
- Ver logs en consola para debugging

## 🔧 Refactorizaciones Recientes

### ✅ pedido_validator.py (2026-01-08)

Se refactorizó el validador de pedidos siguiendo principios SOLID:

**Estructura anterior:**
- Un archivo monolítico de 802 líneas

**Estructura actual:**
- `pedido_validation_types.py` - Tipos comunes reutilizables
- `pedido_cabecera_validator.py` - Validación de cabecera
- `pedido_precio_validator.py` - Validación de precios e impuestos
- `pedido_validator.py` - Facade que orquesta validadores

**Beneficios:**
- ✅ Reducción de complejidad ~50% por archivo
- ✅ Separación de responsabilidades (SRP)
- ✅ Mayor testabilidad y reutilización
- ✅ 100% compatible con código existente
- ✅ 33/33 tests pasando

Ver [REFACTORIZACION_COMPLETADA.md](REFACTORIZACION_COMPLETADA.md) para detalles completos.

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto es privado y confidencial.
