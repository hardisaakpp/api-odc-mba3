# Configuración

## Variables de Entorno

Crear archivo `.env` en la raíz del proyecto.

### MBA3

```env
MBA3_BASE_URL=http://192.168.2.159:8081
MBA3_CODIGO=tu_codigo_servicio
MBA3_PWD=tu_contraseña
MBA3_DIGEST_USERNAME=tu_usuario  # Opcional
MBA3_DIGEST_PASSWORD=tu_contraseña  # Opcional
```

### SQL Server

```env
SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}
SQL_SERVER_SERVER=localhost
SQL_SERVER_DATABASE=tu_base_de_datos
SQL_SERVER_UID=tu_usuario
SQL_SERVER_PWD=tu_contraseña
ENABLE_SQL_SERVER_STORAGE=true
```

**Autenticación Windows:** Dejar `SQL_SERVER_UID` y `SQL_SERVER_PWD` vacíos.

### SAP (Opcional)

```env
SAP_LINKED_SERVER=MYHANADB
SAP_DATABASE=SBO_MABEL_PROD
SAP_SCHEMA=SBO_MABEL_PROD
ENABLE_SAP_QUERIES=true
SAP_CACHE_DAYS=30
```

### SQL Server SAP (Opcional)

Si usas un servidor SQL diferente para consultas SAP:

```env
SQL_SERVER_SAP_DRIVER={ODBC Driver 17 for SQL Server}
SQL_SERVER_SAP_SERVER=servidor_sap
SQL_SERVER_SAP_DATABASE=base_datos_sap
SQL_SERVER_SAP_UID=usuario
SQL_SERVER_SAP_PWD=contraseña
```

## Verificación

```bash
# Verificar conexión MBA3
python src/main.py --login

# Verificar conexión SQL Server
python scripts/check_db_connection.py
```

## Solución de Problemas

### Error: "Driver ODBC no encontrado"
- Instalar driver ODBC desde Microsoft
- Verificar con: `odbcinst -q -d`

### Error: "No se puede conectar a SQL Server"
- Verificar que el servidor esté corriendo
- Verificar credenciales
- Verificar permisos de usuario

### Error: "MBA3: Error 401"
- Verificar `MBA3_CODIGO` y `MBA3_PWD`
- Verificar que el servidor esté accesible
- Verificar la URL base

