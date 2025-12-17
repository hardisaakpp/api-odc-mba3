# Documentación Técnica

Índice completo de la documentación del proyecto MBA3 Consultas.

## 📚 Índice

### 🚀 Inicio Rápido

1. **[Configuración](CONFIGURACION.md)** - Variables de entorno y setup completo
   - Configuración de MBA3
   - Configuración de SQL Server (principal y SAP)
   - Configuración de SAP HANA y Service Layer
   - Configuración de servidor vinculado
   - Solución de problemas

### 📖 Documentación de API

2. **[Endpoints](ENDPOINTS.md)** - Documentación completa de la API REST
   - Endpoints principales (consultar, migrar, procesar-oc, integrar-sap)
   - Endpoints de facturas
   - Endpoints de SAP
   - Ejemplos de uso

3. **[Flujo Completo](FLUJO_COMPLETO.md)** - Flujo de los 4 endpoints principales
   - CONSULTAR → MIGRAR → PROCESAR → INTEGRAR
   - Descripción detallada de cada paso
   - Ejemplos de uso

### 🔌 Integración SAP

4. **[Integración SAP](INTEGRACION_SAP.md)** - Guía completa de integración con SAP
   - Conversión de unidades (docenas → packs)
   - Estructura de tablas
   - Configuración y requisitos
   - Flujo de trabajo
   - Pruebas y troubleshooting

### 🔒 Seguridad

5. **[Seguridad](SEGURIDAD.md)** - Configuración de seguridad opcional
   - Autenticación mediante API Keys
   - Rate limiting
   - CORS restrictivo
   - Ocultar Swagger en producción

### 🧪 Testing

6. **[Testing](TESTING.md)** - Guía de pruebas
   - Estructura de tests
   - Cómo ejecutar tests
   - Cómo escribir tests
   - Coverage

### 📋 Procesos de Negocio

7. **[Orden de Compra](ORDEN_COMPRA_COPIA.md)** - Proceso de copia a orden de compra
   - Descripción del proceso
   - Mapeo de datos
   - Estados de orden de compra

8. **[Homologaciones SKU](HOMOLOGACIONES_SKU.md)** ⭐ - Sistema de gestión de homologaciones SKU
   - Introducción y casos de uso
   - Arquitectura del sistema
   - Documentación de API (4 endpoints)
   - Modelos de datos
   - Guía de instalación
   - Ejemplos de uso

9. **[Quick Start - Homologaciones](QUICKSTART_HOMOLOGACIONES.md)** 🚀 - Instalación rápida en 3 pasos
   - Crear tabla en SQL Server
   - Reiniciar servidor
   - Primera sincronización
   - Tests rápidos

10. **[Implementación Homologaciones](IMPLEMENTACION_HOMOLOGACIONES_SKU.md)** - Resumen técnico
   - Componentes implementados
   - Archivos creados/modificados
   - Especificaciones cumplidas
   - Checklist de verificación

### 🧪 Pruebas

11. **[Guía de Pruebas](pruebas/README.md)** - Scripts y comandos para probar funcionalidades
   - Scripts PowerShell
   - Comandos de prueba
   - Ejemplos de uso

### 🔑 Autenticación

12. **[JWT Authentication](JWT_AUTHENTICATION.md)** - Sistema de autenticación JWT
   - Configuración
   - Uso de tokens
   - Endpoints protegidos

### 👤 Preferencias de Usuario

13. **[User Preferences](USER_PREFERENCES_IMPLEMENTATION.md)** - Sistema de preferencias
   - Preferencias de tablas
   - Preferencias de sidebar
   - API de preferencias

## 🗂️ Estructura de Documentación

```
docs/
├── README.md (este archivo - índice completo)
├── CONFIGURACION.md ⭐ (Configuración completa consolidada)
├── ENDPOINTS.md (Documentación de API REST)
├── FLUJO_COMPLETO.md (Flujo de 4 endpoints principales)
├── INTEGRACION_SAP.md ⭐ (Integración SAP consolidada)
├── SEGURIDAD.md (Configuración de seguridad)
├── TESTING.md (Guía de testing)
├── ORDEN_COMPRA_COPIA.md (Proceso de ODCs)
├── HOMOLOGACIONES_SKU.md ⭐ (Sistema de homologaciones)
├── QUICKSTART_HOMOLOGACIONES.md 🚀 (Inicio rápido)
├── IMPLEMENTACION_HOMOLOGACIONES_SKU.md (Resumen técnico)
├── JWT_AUTHENTICATION.md (Autenticación JWT)
├── USER_PREFERENCES_IMPLEMENTATION.md (Preferencias de usuario)
├── MENSAJES_SAP.md (Mensajes de integración SAP)
├── SAP_INTEGRATION_LOGS.md (Logs de integración)
├── REGISTRO_PERMISOS_CORE.md (Registro de permisos)
├── RESPUESTA_SAP_IMPLEMENTATION.md (Respuesta de SAP)
└── pruebas/
    ├── README.md
    ├── PRUEBAS_POWERSHELL.md
    └── test_endpoints.ps1
```

## 🚀 Guía de Inicio Rápido

1. **Setup inicial:** Ver [Configuración](CONFIGURACION.md)
2. **Entender el flujo:** Ver [Flujo Completo](FLUJO_COMPLETO.md) para entender los 4 endpoints principales
3. **Usar la API:** Ver [Endpoints](ENDPOINTS.md) para documentación detallada
4. **Integración SAP:** Ver [Integración SAP](INTEGRACION_SAP.md) si es necesario
5. **Homologaciones SKU:** Ver [Quick Start Homologaciones](QUICKSTART_HOMOLOGACIONES.md) 🚀
6. **Probar funcionalidades:** Ver [Guía de Pruebas](pruebas/README.md)

## 📝 Notas

- La documentación está organizada por temas y funcionalidades
- Los archivos marcados con ⭐ han sido consolidados y actualizados
- Los archivos marcados con 🚀 son guías de inicio rápido
- **Nuevo:** Sistema completo de Homologaciones SKU disponible
- Para problemas específicos, consulta la sección de troubleshooting en cada documento
- Toda la documentación está actualizada con las últimas implementaciones

## 🆕 Últimas Adiciones

### Módulo de Homologaciones SKU (Diciembre 2024)
- Sistema completo para gestionar correspondencias SKU entre MBA3 y SAP
- 4 endpoints REST: listar, actualizar, bulk update, sincronizar
- Detección automática de diferencias
- Ver [Quick Start](QUICKSTART_HOMOLOGACIONES.md) para comenzar en 3 pasos
- Ver [Documentación Completa](HOMOLOGACIONES_SKU.md) para detalles técnicos
