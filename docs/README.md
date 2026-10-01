# Documentación Técnica - MBA3 Consultas

**Documentación consolidada y simplificada del proyecto.**

---

## 🚀 Inicio Rápido (5 minutos)

| Necesitas | Documento |
|-----------|-----------|
| Instalar y configurar el proyecto | [CONFIGURACION.md](CONFIGURACION.md) |
| **Desarrollo local con Docker (API + Celery + Redis + MinIO)** | **[DOCKER_COMPOSE.md](DOCKER_COMPOSE.md)** 🐳 |
| **Alineación jobs async (front ↔ API)** | **[ALINEACION_FRONT_ASYNC.md](ALINEACION_FRONT_ASYNC.md)** |
| **Desplegar backend en servidor de pruebas (DESA)** | **[DEPLOY_TEST.md](DEPLOY_TEST.md)** 🧪 |
| **Producción con Docker (srv-mabuiosapi, MinIO en 192.168.2.211)** | **[DEPLOY_DOCKER_PRODUCCION.md](DEPLOY_DOCKER_PRODUCCION.md)** 🐳 |
| **Actualizar backend en producción (systemd, legado)** | **[DEPLOY_PRODUCCION.md](DEPLOY_PRODUCCION.md)** 🐧 |
| **Desplegar migraciones de BD** | **[DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md)** 🗄️ |
| Activar procesos automáticos (Celery) | [CELERY_QUICKSTART.md](CELERY_QUICKSTART.md) |
| Usar el sistema de homologaciones SKU | [HOMOLOGACIONES_SKU.md](HOMOLOGACIONES_SKU.md) |

---

## 📖 Documentación Esencial (11 archivos)

### 1. **[CONFIGURACION.md](CONFIGURACION.md)** ⚙️
Configuración completa del proyecto
- Variables de entorno
- SQL Server (principal y SAP)
- SAP HANA y Service Layer
- Solución de problemas

### 1b. **[DOCKER_COMPOSE.md](DOCKER_COMPOSE.md)** 🐳
Desarrollo con perfil `app` (stack recomendado)
- API, Celery worker/beat, Redis y MinIO en contenedor
- Variables `REDIS_URL` / MinIO dentro de la red Docker
- Enlace con scnexus-front y verificación (`docker-verify.ps1`)

### 2. **[REFERENCIA_API.md](REFERENCIA_API.md)** 🔌 y **[ENDPOINTS.md](ENDPOINTS.md)**
API REST
- **REFERENCIA_API.md**: todas las operaciones (generada desde el OpenAPI), con permiso, parámetros y respuestas
- **ENDPOINTS.md**: guía escrita a mano de los endpoints originales (despachos, migración, SAP)
- Ejemplos de uso

### 3. **[INTEGRACION_SAP.md](INTEGRACION_SAP.md)** 📦
Integración con SAP
- Configuración y requisitos
- Flujo de trabajo
- Mapeo de datos
- Troubleshooting

### 4. **[ESTRUCTURA_BD_PEDIDOS.md](ESTRUCTURA_BD_PEDIDOS.md)** 🗄️
Modelo de datos
- Tablas principales
- Relaciones
- Campos especiales

### 5. **[DEPLOY_TEST.md](DEPLOY_TEST.md)** 🧪
Desplegar en servidor de pruebas (DESA)
- Host `210.17.1.53` / `DESA-MABUIOSAPP`, usuario `admindesa`
- Linux: `/opt/odc-sap`, rama `test`, servicio `odc-sap-test`, Docker solo Redis/MinIO
- Variables: `ENV_FILE` según systemd, administrado por Azure DevOps (ver `systemctl cat`)
- Frontend: repo y script aparte (documentado en la misma guía)

### 6. **[DEPLOY_DOCKER_PRODUCCION.md](DEPLOY_DOCKER_PRODUCCION.md)** 🐳
Producción con Docker en `srv-mabuiosapi` (192.168.2.153)
- Stack: Redis + API + Celery en contenedor
- MinIO externo en `srv-mabuiosbdo` (192.168.2.211:9100)
- Un comando: `./deploy-prod.sh` (pull + compose + health + log)

### 6b. **[DEPLOY_PRODUCCION.md](DEPLOY_PRODUCCION.md)** 🐧
Actualizar backend en producción con systemd (legado)
- Ruta `/opt/odc-sap/`, servicios `odc-sap-api`, `celery-worker`, `celery-beat`
- git pull, pip install, systemctl restart

### 7. **[DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md)** 🚀
Sistema de migraciones para producción
- Despliegue seguro de BD
- Trazabilidad completa
- Dry-run y rollback
- Proceso paso a paso

### 8. **[CELERY_QUICKSTART.md](CELERY_QUICKSTART.md)** ⚡
Procesos automáticos
- Setup en 5 pasos
- Ejecución
- Monitoreo

### 9. **[SEGURIDAD.md](SEGURIDAD.md)** 🔒
Configuración de seguridad
- API Keys
- Rate limiting
- CORS
- Autenticación JWT

### 10. **[TESTING.md](TESTING.md)** 🧪
Pruebas y validación
- Estructura de tests unitarios
- Cómo ejecutar tests
- Coverage
- Comandos PowerShell para testing manual
- Script automatizado en `scripts/test_endpoints.ps1`

### 11. **[HOMOLOGACIONES_SKU.md](HOMOLOGACIONES_SKU.md)** 🏷️
Sistema de homologaciones
- Gestión de correspondencias SKU
- API bajo `/api/homologaciones-sku` (listado, alta, edición, bulk, sincronizar)
- Ejemplos de uso

---

## 📚 Documentación Complementaria

### Flujos y Procesos
- [FLUJO_COMPLETO.md](FLUJO_COMPLETO.md) - Flujo MBA3 → SQL → OC → SAP
- [TRANSACCIONES.md](TRANSACCIONES.md) - Uso de transacciones en servicios

### Pedidos, permisos y UI
- [ESTADOS_PEDIDO.md](ESTADOS_PEDIDO.md) - Estados y transiciones
- [PERMISOS_Y_CAPABILITIES.md](PERMISOS_Y_CAPABILITIES.md) - Permisos y capabilities JWT
- [NOTIFICACIONES_SSE.md](NOTIFICACIONES_SSE.md) - Notificaciones en tiempo real (SSE)
- [REFACTORIZACION_PEDIDOS_CRUD.md](REFACTORIZACION_PEDIDOS_CRUD.md) - Organización de módulos de pedidos

### Formatos y Datos
- [FORMATOS_Y_ESTRUCTURAS.md](FORMATOS_Y_ESTRUCTURAS.md) - Requests, Excel, mapeos

### Características Implementadas
- [IMPLEMENTACION_FEATURES.md](IMPLEMENTACION_FEATURES.md) - Features específicas

### Personalización
- [PERSONALIZACION.md](PERSONALIZACION.md) - Campos modificados, preferencias

### Frontend
- [FRONTEND.md](FRONTEND.md) - Requerimientos y guías UI

### Estándares y operación
- [DOCKER_COMPOSE.md](DOCKER_COMPOSE.md) — desarrollo local con perfil `app`
- [API_STANDARDS.md](API_STANDARDS.md), [CACHE.md](CACHE.md), [BUENAS_PRACTICAS_SQL.md](BUENAS_PRACTICAS_SQL.md)

*Hay más guías en `docs/` (despliegue Excel, auditoría, SAP logs, etc.); el índice anterior cubre lo más consultado.*

---

## 🗂️ Estructura Final

```
docs/
├── README.md                    (este archivo)
├── CONFIGURACION.md             ⭐ ESENCIAL
├── REFERENCIA_API.md            ⭐ ESENCIAL (generada: scripts/generar_referencia_api.py)
├── ENDPOINTS.md                 (endpoints originales, a mano)
├── INTEGRACION_SAP.md           ⭐ ESENCIAL
├── ESTRUCTURA_BD_PEDIDOS.md     ⭐ ESENCIAL
├── DEPLOY_TEST.md               ⭐ ESENCIAL (servidor DESA / pruebas)
├── DEPLOY_PRODUCCION.md         ⭐ ESENCIAL (actualizar backend Linux)
├── DEPLOY_MIGRATIONS.md         ⭐ ESENCIAL (migraciones BD)
├── CATALOGO_MIGRACIONES.md      (generado: las 113 migraciones en orden)
├── ESQUEMA_BD.md                (generado: tablas y columnas de la BD real)
├── Manual_del_usuario/          (manual de usuario del módulo Gestión ODC SAP)
├── CELERY_QUICKSTART.md         ⭐ ESENCIAL
├── SEGURIDAD.md                 ⭐ ESENCIAL
├── TESTING.md                   ⭐ ESENCIAL
├── HOMOLOGACIONES_SKU.md        ⭐ ESENCIAL
├── ALINEACION_FRONT_ASYNC.md    ⭐ ESENCIAL (contrato jobs async front ↔ API)
├── FLUJO_COMPLETO.md
├── FORMATOS_Y_ESTRUCTURAS.md
├── IMPLEMENTACION_FEATURES.md
├── PERSONALIZACION.md
├── FRONTEND.md
├── HISTORIAL.md                 📦 HISTÓRICO
└── … (más de 30 temas adicionales: Excel, SAP logs, migraciones resumidas, etc.)
```

---

## 🎯 Guía de Referencia Rápida

| Pregunta | Respuesta |
|----------|-----------|
| ¿Cómo instalo el proyecto? | [CONFIGURACION.md](CONFIGURACION.md) |
| **¿Cómo despliego en el servidor de pruebas (DESA)?** | **[DEPLOY_TEST.md](DEPLOY_TEST.md)** 🧪 |
| **¿Cómo actualizo el backend en producción (Linux)?** | **[DEPLOY_PRODUCCION.md](DEPLOY_PRODUCCION.md)** 🐧 |
| **¿Cómo despliego migraciones?** | **[DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md)** 🚀 |
| ¿Qué hace cada migración? | [CATALOGO_MIGRACIONES.md](CATALOGO_MIGRACIONES.md) |
| ¿Qué tablas y columnas tiene la base de datos? | [ESQUEMA_BD.md](ESQUEMA_BD.md) |
| ¿Cómo uso el módulo Gestión ODC SAP (usuarios)? | [Manual de Usuario](Manual_del_usuario/Manual%20de%20Usuario%20-%20Modulo%20Gesti%C3%B3n%20ODC%20SAP%20-%20SCNexus.md) |
| ¿Cuáles son los endpoints y qué permiso exige cada uno? | [REFERENCIA_API.md](REFERENCIA_API.md) |
| ¿Cómo integro con SAP? | [INTEGRACION_SAP.md](INTEGRACION_SAP.md) |
| ¿Cómo activo Celery? | [CELERY_QUICKSTART.md](CELERY_QUICKSTART.md) |
| ¿Cómo uso homologaciones? | [HOMOLOGACIONES_SKU.md](HOMOLOGACIONES_SKU.md) |
| ¿Contrato async / polling / SSE con el front? | [ALINEACION_FRONT_ASYNC.md](ALINEACION_FRONT_ASYNC.md) |
| ¿Cuál es el modelo de datos? | [ESTRUCTURA_BD_PEDIDOS.md](ESTRUCTURA_BD_PEDIDOS.md) |
| ¿Cómo ejecuto tests? | [TESTING.md](TESTING.md) |
| ¿Cómo configuro seguridad? | [SEGURIDAD.md](SEGURIDAD.md) |
| ¿Qué formatos usa? | [FORMATOS_Y_ESTRUCTURAS.md](FORMATOS_Y_ESTRUCTURAS.md) |
| ¿Qué features hay? | [IMPLEMENTACION_FEATURES.md](IMPLEMENTACION_FEATURES.md) |
| ¿Cómo personalizo? | [PERSONALIZACION.md](PERSONALIZACION.md) |
| ¿Guía para frontend? | [FRONTEND.md](FRONTEND.md) |
| ¿Estados y permisos de pedidos? | [ESTADOS_PEDIDO.md](ESTADOS_PEDIDO.md), [PERMISOS_Y_CAPABILITIES.md](PERMISOS_Y_CAPABILITIES.md) |
| ¿SSE / notificaciones? | [NOTIFICACIONES_SSE.md](NOTIFICACIONES_SSE.md) |

---

## 📦 Documentación Histórica

Para referencia sobre cambios previos e implementaciones completadas:
- Ver [HISTORIAL.md](HISTORIAL.md) - Resumen consolidado de toda la documentación histórica
- **Nota:** La carpeta `archivo/` con 32 archivos históricos fue eliminada. Toda la información relevante está en HISTORIAL.md o en el historial de Git.

---

## ✅ Estado Actual

✓ Sistema en producción  
✓ Integración SAP operacional  
✓ Homologaciones SKU implementadas  
✓ Celery procesando automáticamente  
✓ Seguridad configurada  
✓ Tests ejecutados y validados  
✓ **Documentación en `docs/`: ~40 archivos** (11 esenciales arriba + complementarias + histórico)  
✓ **Última revisión índice:** mayo 2026