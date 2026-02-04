# Documentación Técnica - MBA3 Consultas

**Documentación consolidada y simplificada del proyecto.**

---

## 🚀 Inicio Rápido (5 minutos)

| Necesitas | Documento |
|-----------|-----------|
| Instalar y configurar el proyecto | [CONFIGURACION.md](CONFIGURACION.md) |
| **Desplegar migraciones de BD** | **[DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md)** 🗄️ |
| Activar procesos automáticos (Celery) | [CELERY_QUICKSTART.md](CELERY_QUICKSTART.md) |
| Usar el sistema de homologaciones SKU | [HOMOLOGACIONES_SKU.md](HOMOLOGACIONES_SKU.md) |

---

## 📖 Documentación Esencial (8 archivos)

### 1. **[CONFIGURACION.md](CONFIGURACION.md)** ⚙️
Configuración completa del proyecto
- Variables de entorno
- SQL Server (principal y SAP)
- SAP HANA y Service Layer
- Solución de problemas

### 2. **[ENDPOINTS.md](ENDPOINTS.md)** 🔌
API REST completa
- Todos los endpoints disponibles
- Parámetros y respuestas
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

### 5. **[DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md)** 🚀
Sistema de migraciones para producción
- Despliegue seguro de BD
- Trazabilidad completa
- Dry-run y rollback
- Proceso paso a paso

### 6. **[CELERY_QUICKSTART.md](CELERY_QUICKSTART.md)** ⚡
Procesos automáticos
- Setup en 5 pasos
- Ejecución
- Monitoreo

### 7. **[SEGURIDAD.md](SEGURIDAD.md)** 🔒
Configuración de seguridad
- API Keys
- Rate limiting
- CORS
- Autenticación JWT

### 8. **[TESTING.md](TESTING.md)** 🧪
Pruebas y validación
- Estructura de tests unitarios
- Cómo ejecutar tests
- Coverage
- Comandos PowerShell para testing manual
- Script automatizado en `scripts/test_endpoints.ps1`

### 9. **[HOMOLOGACIONES_SKU.md](HOMOLOGACIONES_SKU.md)** 🏷️
Sistema de homologaciones
- Gestión de correspondencias SKU
- 4 endpoints REST
- Ejemplos de uso

---

## 📚 Documentación Complementaria (6 archivos)

### Flujos y Procesos
- [FLUJO_COMPLETO.md](FLUJO_COMPLETO.md) - Flujo end-to-end de pedidos

### Formatos y Datos
- [FORMATOS_Y_ESTRUCTURAS.md](FORMATOS_Y_ESTRUCTURAS.md) - Requests, Excel, mapeos

### Características Implementadas
- [IMPLEMENTACION_FEATURES.md](IMPLEMENTACION_FEATURES.md) - Features específicas

### Personalización
- [PERSONALIZACION.md](PERSONALIZACION.md) - Campos modificados, preferencias

### Frontend
- [FRONTEND.md](FRONTEND.md) - Requerimientos y guías UI

---

## 🗂️ Estructura Final

```
docs/
├── README.md                    (este archivo)
├── CONFIGURACION.md             ⭐ ESENCIAL
├── ENDPOINTS.md                 ⭐ ESENCIAL
├── INTEGRACION_SAP.md           ⭐ ESENCIAL
├── ESTRUCTURA_BD_PEDIDOS.md     ⭐ ESENCIAL
├── DEPLOY_MIGRATIONS.md         ⭐ ESENCIAL (NUEVO)
├── CELERY_QUICKSTART.md         ⭐ ESENCIAL
├── SEGURIDAD.md                 ⭐ ESENCIAL
├── TESTING.md                   ⭐ ESENCIAL
├── HOMOLOGACIONES_SKU.md        ⭐ ESENCIAL
├── FLUJO_COMPLETO.md
├── FORMATOS_Y_ESTRUCTURAS.md
├── IMPLEMENTACION_FEATURES.md
├── PERSONALIZACION.md
├── FRONTEND.md
├── HISTORIAL.md                 📦 HISTÓRICO
└── pruebas/
    └── README.md
```

---

## 🎯 Guía de Referencia Rápida

| Pregunta | Respuesta |
|----------|-----------|
| ¿Cómo instalo el proyecto? | [CONFIGURACION.md](CONFIGURACION.md) |
| **¿Cómo despliego migraciones?** | **[DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md)** 🚀 |
| ¿Cuáles son los endpoints? | [ENDPOINTS.md](ENDPOINTS.md) |
| ¿Cómo integro con SAP? | [INTEGRACION_SAP.md](INTEGRACION_SAP.md) |
| ¿Cómo activo Celery? | [CELERY_QUICKSTART.md](CELERY_QUICKSTART.md) |
| ¿Cómo uso homologaciones? | [HOMOLOGACIONES_SKU.md](HOMOLOGACIONES_SKU.md) |
| ¿Cuál es el modelo de datos? | [ESTRUCTURA_BD_PEDIDOS.md](ESTRUCTURA_BD_PEDIDOS.md) |
| ¿Cómo ejecuto tests? | [TESTING.md](TESTING.md) |
| ¿Cómo configuro seguridad? | [SEGURIDAD.md](SEGURIDAD.md) |
| ¿Qué formatos usa? | [FORMATOS_Y_ESTRUCTURAS.md](FORMATOS_Y_ESTRUCTURAS.md) |
| ¿Qué features hay? | [IMPLEMENTACION_FEATURES.md](IMPLEMENTACION_FEATURES.md) |
| ¿Cómo personalizo? | [PERSONALIZACION.md](PERSONALIZACION.md) |
| ¿Guía para frontend? | [FRONTEND.md](FRONTEND.md) |

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
✓ **Documentación consolidada (21 archivos principales)**