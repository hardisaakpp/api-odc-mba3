# Configuración de Dos Servidores SQL

Este proyecto utiliza **dos servidores SQL Server diferentes** con propósitos distintos:

## 🗄️ Servidores SQL

### 1. Servidor Principal (Almacenamiento de Datos)
- **Servidor**: `210.17.1.54`
- **Base de datos**: `store_control`
- **Propósito**: Almacenar datos de MBA3 y cache de productos SAP
- **Tablas**: 
  - `despacho_cabecera`
  - `despacho_detalle`
  - `producto_sap_cache`
  - `pack_conversion`

### 2. Servidor SAP (Consultas OPENQUERY)
- **Servidor**: `10.10.100.12`
- **Base de datos**: `STORECONTROL`
- **Propósito**: Ejecutar consultas OPENQUERY a SAP HANA
- **Requisito**: Debe tener el servidor vinculado `[MYHANADB]` configurado

## ⚙️ Configuración en `.env`

Configura ambas conexiones en tu archivo `.env`:

```env
# ============================================================================
# CONFIGURACIÓN SQL SERVER PRINCIPAL (Almacenamiento)
# ============================================================================
SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}
SQL_SERVER_SERVER=210.17.1.54
SQL_SERVER_DATABASE=store_control
SQL_SERVER_UID=desadmin
SQL_SERVER_PWD=tu_contraseña

# ============================================================================
# CONFIGURACIÓN SQL SERVER SAP (Consultas OPENQUERY)
# ============================================================================
# Si no se configuran estas variables, se usan las del servidor principal
SQL_SERVER_SAP_DRIVER={ODBC Driver 17 for SQL Server}
SQL_SERVER_SAP_SERVER=10.10.100.12
SQL_SERVER_SAP_DATABASE=STORECONTROL
SQL_SERVER_SAP_UID=consultas
SQL_SERVER_SAP_PWD=tu_contraseña

# ============================================================================
# CONFIGURACIÓN SAP (HANA)
# ============================================================================
SAP_LINKED_SERVER=MYHANADB
SAP_DATABASE=SBO_MABEL_PROD
SAP_SCHEMA=SBO_MABEL_PROD
ENABLE_SAP_QUERIES=true
SAP_CACHE_DAYS=30
```

## 📝 Variables de Configuración

### Servidor Principal (Almacenamiento)
- `SQL_SERVER_DRIVER` - Driver ODBC
- `SQL_SERVER_SERVER` - IP o nombre del servidor
- `SQL_SERVER_DATABASE` - Nombre de la base de datos
- `SQL_SERVER_UID` - Usuario (opcional para Windows Auth)
- `SQL_SERVER_PWD` - Contraseña (opcional para Windows Auth)

### Servidor SAP (Consultas OPENQUERY)
- `SQL_SERVER_SAP_DRIVER` - Driver ODBC (por defecto usa el principal)
- `SQL_SERVER_SAP_SERVER` - IP o nombre del servidor SAP
- `SQL_SERVER_SAP_DATABASE` - Nombre de la base de datos SAP
- `SQL_SERVER_SAP_UID` - Usuario (por defecto usa el principal)
- `SQL_SERVER_SAP_PWD` - Contraseña (por defecto usa la principal)

**Nota**: Si no configuras las variables `SQL_SERVER_SAP_*`, el sistema usará las del servidor principal como fallback.

## 🔄 Flujo de Trabajo

1. **Consulta SAP**: 
   - Se conecta al servidor SAP (`10.10.100.12 STORECONTROL`)
   - Ejecuta `OPENQUERY` usando el servidor vinculado `[MYHANADB]`
   - Obtiene información del producto (ItemCode, ItemName, U_IXX_PACK)

2. **Almacenamiento**:
   - Se conecta al servidor principal (`210.17.1.54 store_control`)
   - Guarda información en `producto_sap_cache`
   - Guarda facturas en `despacho_cabecera` y `despacho_detalle`

## ✅ Verificación

Para verificar que ambas conexiones están configuradas correctamente:

```bash
python scripts/check_db_connection.py
```

Este script mostrará:
- Configuración del servidor principal
- Configuración del servidor SAP
- Estado de las tablas en cada servidor

## 🔧 Solución de Problemas

### Error: "Invalid object name 'producto_sap_cache'"

**Causa**: Estás conectado al servidor SAP en lugar del servidor principal.

**Solución**: Verifica que `SQL_SERVER_SERVER=210.17.1.54` y `SQL_SERVER_DATABASE=store_control` estén configurados correctamente.

### Error: "Cannot find the server 'MYHANADB'"

**Causa**: El servidor vinculado no está configurado en el servidor SAP.

**Solución**: Configura el servidor vinculado `[MYHANADB]` en el servidor `10.10.100.12`.

### Las consultas SAP no funcionan

**Causa**: Estás usando el servidor principal que no tiene el servidor vinculado.

**Solución**: Verifica que `SQL_SERVER_SAP_SERVER=10.10.100.12` esté configurado correctamente.

## 📊 Resumen

| Propósito | Servidor | Base de Datos | Variables |
|-----------|----------|---------------|-----------|
| Almacenar datos | 210.17.1.54 | store_control | `SQL_SERVER_*` |
| Consultas SAP | 10.10.100.12 | STORECONTROL | `SQL_SERVER_SAP_*` |

