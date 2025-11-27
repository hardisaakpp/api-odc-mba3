# Guía de Pruebas

Esta carpeta contiene scripts y documentación para probar todas las funcionalidades del sistema.

## 📋 Contenido

- **[PRUEBAS_POWERSHELL.md](PRUEBAS_POWERSHELL.md)** - Comandos PowerShell para probar endpoints individualmente
- **[test_endpoints.ps1](test_endpoints.ps1)** - Script automatizado que prueba todos los endpoints

## 🚀 Uso Rápido

### Script Automatizado (Recomendado)

```powershell
# Desde la raíz del proyecto
.\docs\pruebas\test_endpoints.ps1
```

Este script prueba todos los endpoints en orden y muestra los resultados formateados.

### Comandos Individuales

Ver [PRUEBAS_POWERSHELL.md](PRUEBAS_POWERSHELL.md) para comandos individuales de cada endpoint.

## 📝 Orden de Pruebas

1. **Health Check** - Verificar que el servidor esté funcionando
2. **Test Endpoint** - Probar comunicación básica
3. **Validar Consulta SQL** - Validar sintaxis SQL
4. **Ejecutar Consulta SQL** - Ejecutar consultas contra MBA3
5. **Consultar Despachos** - Consultar sin guardar
6. **Migrar Despachos** - Consultar y guardar en BD
7. **Procesar Orden de Compra** - Copiar a OC
8. **Proceso Completo** - Flujo completo end-to-end
9. **Consultar Facturas** - Endpoint principal con filtros
10. **Integración SAP** - Consultar productos en SAP

## ⚠️ Pre-requisitos

1. **Servidor API corriendo:**
   ```powershell
   python src/api_server.py
   ```

2. **Variables de entorno configuradas** en `.env`

3. **SQL Server accesible** (para pruebas de guardado)

4. **SAP configurado** (para pruebas de integración SAP)

## 🔍 Ver Resultados

Los resultados se muestran en formato JSON. Para verlos más legibles:

```powershell
$result | ConvertTo-Json -Depth 10
```

## 📖 Más Información

- Ver [Documentación de Endpoints](../ENDPOINTS.md) para detalles de cada endpoint
- Ver [Configuración](../CONFIGURACION.md) para setup del entorno
