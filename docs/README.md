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

### 🧪 Pruebas

8. **[Guía de Pruebas](pruebas/README.md)** - Scripts y comandos para probar funcionalidades
   - Scripts PowerShell
   - Comandos de prueba
   - Ejemplos de uso

## 🗂️ Estructura de Documentación

```
docs/
├── README.md (este archivo)
├── CONFIGURACION.md ⭐ (Configuración completa consolidada)
├── ENDPOINTS.md
├── FLUJO_COMPLETO.md
├── INTEGRACION_SAP.md ⭐ (Integración SAP consolidada)
├── SEGURIDAD.md
├── TESTING.md
├── ORDEN_COMPRA_COPIA.md
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
5. **Probar funcionalidades:** Ver [Guía de Pruebas](pruebas/README.md)

## 📝 Notas

- La documentación está organizada por temas
- Los archivos marcados con ⭐ han sido consolidados y actualizados
- Para problemas específicos, consulta la sección de troubleshooting en cada documento
