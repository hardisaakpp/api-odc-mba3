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

Crear archivo `.env` en la raíz del proyecto:

```env
# MBA3
MBA3_BASE_URL=http://192.168.2.159:8081
MBA3_CODIGO=tu_codigo_servicio
MBA3_PWD=tu_contraseña

# SQL Server
SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}
SQL_SERVER_SERVER=localhost
SQL_SERVER_DATABASE=tu_base_de_datos
SQL_SERVER_UID=tu_usuario
SQL_SERVER_PWD=tu_contraseña
ENABLE_SQL_SERVER_STORAGE=true

# SAP (opcional)
SAP_LINKED_SERVER=MYHANADB
SAP_DATABASE=SBO_MABEL_PROD
ENABLE_SAP_QUERIES=true
```

Ver [docs/CONFIGURACION.md](docs/CONFIGURACION.md) para más detalles.

### Iniciar Servidor

```bash
# Backend
python src/api_server.py

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

### Consultas

- **GET `/health`** - Health check
- **GET `/facturas`** - Obtener facturas con filtros (recomendado para frontend)
- **GET `/consultar`** - Consultar despachos (solo lectura)
- **GET `/migrar`** - Consultar y guardar en despacho
- **GET `/pruebas`** - Proceso completo (consulta + guarda + copia a OC)
- **GET `/procesar-oc`** - Copiar despachos a orden de compra
- **POST `/consulta`** - Ejecutar consulta SQL dinámica
- **POST `/query`** - Validar y parsear consulta SQL

### SAP

- **GET `/sap/test?sku=...`** - Consultar producto en SAP
- **GET `/sap/test/direct?sku=...`** - Consulta directa a SAP (sin cache)

Ver [docs/ENDPOINTS.md](docs/ENDPOINTS.md) para documentación completa.

## 🎯 Funcionalidades

### Backend

- ✅ Consultas a API MBA3 con autenticación JWT
- ✅ Guardado automático en SQL Server
- ✅ Integración con SAP HANA (OPENQUERY)
- ✅ Validación de consultas SQL (solo SELECT)
- ✅ Mapeo automático MBA3 → SQL Server
- ✅ Procesamiento de orden de compra

### Frontend

- ✅ Vista de facturas con filtros
- ✅ Consulta SQL dinámica
- ✅ Tabla interactiva con paginación
- ✅ Modal de detalles
- ✅ Tema claro/oscuro

## 📚 Documentación

### Documentación Principal

- [README de Documentación](docs/README.md) - Índice completo de documentación técnica
- [Configuración](docs/CONFIGURACION.md) - Variables de entorno y setup
- [Endpoints](docs/ENDPOINTS.md) - Documentación completa de API
- [Guía de Pruebas](docs/pruebas/README.md) - Scripts y comandos para probar funcionalidades

### Documentación Especializada

- [Integración SAP](docs/INTEGRACION_SAP.md) - Configuración e integración con SAP
- [Frontend](frontend/README.md) - Guía del frontend Vue.js

## 🛠️ Desarrollo

### Scripts Útiles

```bash
# Obtener JWT de MBA3
python src/main.py --login

# Ejecutar consulta de prueba
python src/main.py --query

# Verificar conexión SQL Server
python scripts/check_db_connection.py
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

## 📝 Notas

- El JWT de MBA3 tiene tiempo de expiración limitado
- Los datos se guardan automáticamente en SQL Server si está habilitado
- Las consultas SAP usan cache para mejorar rendimiento
- Ver logs en consola para debugging

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto es privado y confidencial.
