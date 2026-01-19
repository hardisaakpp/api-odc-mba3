# Documentación Técnica

Índice completo de la documentación del proyecto MBA3 Consultas.

> 💡 **Nuevo**: Ver [Estructura de Documentación](ESTRUCTURA_DOCUMENTACION.md) para una guía visual completa de la organización.

## 📚 Índice

### 🚀 Inicio Rápido

1. **[Configuración](CONFIGURACION.md)** - Variables de entorno y setup completo
   - Configuración de MBA3
   - Configuración de SQL Server (principal y SAP)
   - Configuración de SAP HANA y Service Layer
   - Configuración de servidor vinculado
   - Solución de problemas

2. **[Celery Quick Start](CELERY_QUICKSTART.md)** 🚀 - Poner en marcha Celery en 5 pasos
   - Instalación de Redis
   - Configuración rápida
   - Ejecución de procesos
   - Verificación y troubleshooting

### 📖 Documentación de API

3. **[Endpoints](ENDPOINTS.md)** - Documentación completa de la API REST
   - Endpoints principales (consultar, migrar, procesar-oc, integrar-sap)
   - Endpoints de facturas
   - Endpoints de SAP
   - Ejemplos de uso

4. **[Flujo Completo](FLUJO_COMPLETO.md)** - Flujo de los 4 endpoints principales
   - CONSULTAR → MIGRAR → PROCESAR → INTEGRAR
   - Descripción detallada de cada paso
   - Ejemplos de uso

### ⚙️ Procesos Automáticos

5. **[Celery Implementation](CELERY_IMPLEMENTATION.md)** - Implementación completa de Celery
   - Arquitectura de procesos aislados
   - Configuración avanzada
   - Monitoreo con Flower
   - Troubleshooting detallado

### 🔌 Integración SAP

6. **[Integración SAP](INTEGRACION_SAP.md)** - Guía completa de integración con SAP
   - Conversión de unidades (docenas → packs)
   - Estructura de tablas
   - Configuración y requisitos
   - Flujo de trabajo
   - Pruebas y troubleshooting

### 🔒 Seguridad

7. **[Seguridad](SEGURIDAD.md)** - Configuración de seguridad opcional
   - Autenticación mediante API Keys
   - Rate limiting
   - CORS restrictivo
   - Ocultar Swagger en producción

### 🧪 Testing

8. **[Testing](TESTING.md)** - Guía de pruebas
   - Estructura de tests
   - Cómo ejecutar tests
   - Cómo escribir tests
   - Coverage

### 📋 Procesos de Negocio

9. **[Orden de Compra](ORDEN_COMPRA_COPIA.md)** - Proceso de copia a orden de compra
   - Descripción del proceso
   - Mapeo de datos
   - Estados de orden de compra

10. **[Homologaciones SKU](HOMOLOGACIONES_SKU.md)** ⭐ - Sistema de gestión de homologaciones SKU
   - Introducción y casos de uso
   - Arquitectura del sistema
   - Documentación de API (4 endpoints)
   - Modelos de datos
   - Guía de instalación
   - Ejemplos de uso

11. **[Quick Start - Homologaciones](QUICKSTART_HOMOLOGACIONES.md)** 🚀 - Instalación rápida en 3 pasos
   - Crear tabla en SQL Server
   - Reiniciar servidor
   - Primera sincronización
   - Tests rápidos

12. **[Implementación Homologaciones](IMPLEMENTACION_HOMOLOGACIONES_SKU.md)** - Resumen técnico
   - Componentes implementados
   - Archivos creados/modificados
   - Especificaciones cumplidas
   - Checklist de verificación

### 🧪 Pruebas

13. **[Guía de Pruebas](pruebas/README.md)** - Scripts y comandos para probar funcionalidades
   - Scripts PowerShell
   - Comandos de prueba
   - Ejemplos de uso

### 🔑 Autenticación

14. **[JWT Authentication](JWT_AUTHENTICATION.md)** - Sistema de autenticación JWT
   - Configuración
   - Uso de tokens
   - Endpoints protegidos

### 👤 Preferencias de Usuario

15. **[User Preferences](USER_PREFERENCES_IMPLEMENTATION.md)** - Sistema de preferencias
   - Preferencias de tablas
   - Preferencias de sidebar
   - API de preferencias

## 🗂️ Estructura de Documentación

```
docs/
├── README.md (este archivo - índice completo)
│
├── 🚀 INICIO RÁPIDO
│   ├── CONFIGURACION.md ⭐
│   ├── CELERY_QUICKSTART.md 🚀
│   └── QUICKSTART_HOMOLOGACIONES.md 🚀
│
├── 📖 API Y FLUJOS
│   ├── ENDPOINTS.md
│   ├── FLUJO_COMPLETO.md
│   └── ORDEN_COMPRA_COPIA.md
│
├── 🗄️ BASE DE DATOS
│   ├── ESTRUCTURA_BD_PEDIDOS.md ⭐
│   ├── ESTRUCTURA_REQUEST_CREAR_PEDIDO.md
│   └── FORMATO_EXCEL_PEDIDOS.md
│
├── ⚙️ PROCESOS Y SERVICIOS
│   ├── CELERY_IMPLEMENTATION.md ⭐
│   ├── IMPLEMENTACION_PEDIDO_SAP_PROCESAMIENTO.md
│   └── IMPLEMENTACION_CARGAR_ULTIMO_PEDIDO.md
│
├── 🔌 INTEGRACIÓN SAP
│   ├── INTEGRACION_SAP.md ⭐
│   ├── MENSAJES_SAP.md
│   ├── RESPUESTA_SAP_IMPLEMENTATION.md
│   └── SAP_INTEGRATION_LOGS.md
│
├── 🏷️ HOMOLOGACIONES
│   ├── HOMOLOGACIONES_SKU.md ⭐
│   ├── QUICKSTART_HOMOLOGACIONES.md 🚀
│   └── IMPLEMENTACION_HOMOLOGACIONES_SKU.md
│
├── 🔒 SEGURIDAD
│   ├── SEGURIDAD.md ⭐
│   └── REGISTRO_PERMISOS_CORE.md
│
├── 👤 PREFERENCIAS
│   ├── USER_PREFERENCES_IMPLEMENTATION.md
│   ├── PERSISTENCIA_CAMPOS_MODIFICADOS.md
│   └── RESUMEN_IMPLEMENTACION_CAMPOS_MODIFICADOS.md
│
├── 🔧 REFACTORIZACIONES Y MEJORAS
│   ├── REFACTORIZACION_ENDPOINTS_PEDIDOS.md
│   ├── REFACTORIZACION_PEDIDO_VALIDATOR.md
│   ├── REFACTORIZACION_PEDIDO_VALIDATOR_SUMMARY.md
│   ├── REFACTORIZACION_DESPACHO_REPOSITORY.md
│   ├── CHECKLIST_REFACTORIZACION_DESPACHO.md
│   ├── VALIDACION_TEMPRANA_NUMERO_PEDIDO.md
│   ├── MEJORA_ERROR_NUMERO_PEDIDO_DUPLICADO.md
│   ├── ANALISIS_REDUNDANCIAS.md
│   └── FRONTEND_PRODUCTOS_PROCESADOS.md
│
├── 🧪 TESTING
│   ├── TESTING.md
│   └── pruebas/
│       ├── README.md
│       └── PRUEBAS_POWERSHELL.md
│
└── 📦 ARCHIVO
    └── archivo/ (documentación histórica)
        └── README.md
```

## 🚀 Guía de Inicio Rápido

1. **Setup inicial:** Ver [Configuración](CONFIGURACION.md)
2. **Setup Celery:** Ver [Celery Quick Start](CELERY_QUICKSTART.md) 🚀 para procesos automáticos
3. **Entender el flujo:** Ver [Flujo Completo](FLUJO_COMPLETO.md) para entender los 4 endpoints principales
4. **Usar la API:** Ver [Endpoints](ENDPOINTS.md) para documentación detallada
5. **Integración SAP:** Ver [Integración SAP](INTEGRACION_SAP.md) si es necesario
6. **Homologaciones SKU:** Ver [Quick Start Homologaciones](QUICKSTART_HOMOLOGACIONES.md) 🚀
7. **Probar funcionalidades:** Ver [Guía de Pruebas](pruebas/README.md)

## 📝 Notas

- La documentación está organizada por temas y funcionalidades
- Los archivos marcados con ⭐ han sido consolidados y actualizados
- Los archivos marcados con 🚀 son guías de inicio rápido
- **Nuevo:** Sistema completo de Homologaciones SKU disponible
- Para problemas específicos, consulta la sección de troubleshooting en cada documento
- Toda la documentación está actualizada con las últimas implementaciones## 🆕 Últimas Adiciones### Módulo de Homologaciones SKU (Diciembre 2024)
- Sistema completo para gestionar correspondencias SKU entre MBA3 y SAP
- 4 endpoints REST: listar, actualizar, bulk update, sincronizar
- Detección automática de diferencias
- Ver [Quick Start](QUICKSTART_HOMOLOGACIONES.md) para comenzar en 3 pasos
- Ver [Documentación Completa](HOMOLOGACIONES_SKU.md) para detalles técnicos