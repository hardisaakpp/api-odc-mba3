# Configuración del archivo .env

Este documento describe todas las variables de entorno que puedes configurar en el archivo `.env` ubicado en la raíz del proyecto.

## Ubicación

```
mba3-consultas/
└── .env  ← Este archivo (NO subir a git)
```

## Variables de Configuración

### Configuración de MBA3

Estas variables se usan para conectarse a la API de MBA3 (4D).

```env
# URL base del servidor MBA3
MBA3_BASE_URL=http://192.168.2.159:8081

# Código de servicio (usuario)
MBA3_CODIGO=CDB002
# O alternativamente:
# MBA3_SERVICE_CODE=CDB002

# Contraseña del servicio
MBA3_PWD=***REMOVED***
# O alternativamente:
# MBA3_SERVICE_PASSWORD=***REMOVED***

# Usuario para autenticación Digest (opcional, por defecto usa MBA3_CODIGO)
MBA3_DIGEST_USERNAME=CDB002

# Contraseña para autenticación Digest (opcional, por defecto usa MBA3_PWD)
MBA3_DIGEST_PASSWORD=***REMOVED***

# Consulta SQL opcional para scripts (opcional)
MBA3_QUERY=SELECT * FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'
```

### Configuración de SQL Server

Estas variables se usan para conectarse a SQL Server y guardar los datos de MBA3.

```env
# Driver ODBC para SQL Server
# Windows común: {ODBC Driver 17 for SQL Server}
# Windows alternativo: {SQL Server}
# Linux: {ODBC Driver 17 for SQL Server} (instalado separadamente)
SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}

# Nombre del servidor SQL Server
# Ejemplos:
# - localhost
# - servidor.local
# - 192.168.1.100
# - servidor\\instancia
SQL_SERVER_SERVER=localhost

# Nombre de la base de datos
SQL_SERVER_DATABASE=TuBaseDeDatos

# Autenticación con Usuario/Contraseña
SQL_SERVER_UID=tu_usuario
SQL_SERVER_PWD=tu_contraseña

# O para autenticación Windows (Trusted Connection):
# Deja UID y PWD vacíos o no los incluyas
# SQL_SERVER_UID=
# SQL_SERVER_PWD=
```

### Configuración de Funcionalidades

```env
# Habilitar o deshabilitar el guardado automático en SQL Server
# Valores válidos: true, false
# Por defecto: true
ENABLE_SQL_SERVER_STORAGE=true
```

## Ejemplo Completo de .env

```env
# ============================================================================
# CONFIGURACIÓN MBA3
# ============================================================================
MBA3_BASE_URL=http://192.168.2.159:8081
MBA3_CODIGO=CDB002
MBA3_PWD=***REMOVED***
MBA3_DIGEST_USERNAME=CDB002
MBA3_DIGEST_PASSWORD=***REMOVED***

# ============================================================================
# CONFIGURACIÓN SQL SERVER
# ============================================================================
# Opción 1: Autenticación con Usuario/Contraseña
SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}
SQL_SERVER_SERVER=localhost
SQL_SERVER_DATABASE=tu_base_de_datos
SQL_SERVER_UID=tu_usuario
SQL_SERVER_PWD=tu_contraseña

# Opción 2: Autenticación Windows (Trusted Connection)
# SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}
# SQL_SERVER_SERVER=localhost
# SQL_SERVER_DATABASE=tu_base_de_datos
# SQL_SERVER_UID=
# SQL_SERVER_PWD=

# ============================================================================
# CONFIGURACIÓN GENERAL
# ============================================================================
ENABLE_SQL_SERVER_STORAGE=true
```

## Notas Importantes

1. **Seguridad**: 
   - ⚠️ **NUNCA** subas el archivo `.env` a git
   - El archivo `.env` contiene credenciales sensibles
   - Ya debería estar en `.gitignore`

2. **Valores por Defecto**:
   - Si no configuras una variable, el sistema usará valores por defecto
   - Consulta `src/config.py` para ver los valores por defecto

3. **Compatibilidad**:
   - Las variables de MBA3 aceptan tanto `MBA3_CODIGO` como `MBA3_SERVICE_CODE`
   - Las variables de MBA3 aceptan tanto `MBA3_PWD` como `MBA3_SERVICE_PASSWORD`
   - Esto asegura compatibilidad con código existente

4. **Windows Authentication**:
   - Para usar autenticación Windows, deja `SQL_SERVER_UID` y `SQL_SERVER_PWD` vacíos
   - El sistema usará la cuenta de Windows actual

5. **Driver ODBC**:
   - Verifica que el driver ODBC esté instalado en tu sistema
   - En Windows, puedes verificar con: `odbcinst -q -d`
   - Si necesitas instalar el driver, descárgalo de Microsoft

## Verificación

Después de configurar el `.env`, puedes verificar que todo funcione:

1. **Verificar conexión a MBA3**:
   ```bash
   python src/main.py --login
   ```

2. **Verificar conexión a SQL Server**:
   - Ejecuta el servidor API: `python src/api_server.py`
   - Haz una consulta desde Postman al endpoint `/consulta`
   - Revisa los logs para ver si se conectó correctamente a SQL Server

## Solución de Problemas

### Error: "Driver ODBC no encontrado"
- Instala el driver ODBC desde Microsoft
- Verifica el nombre exacto del driver con `odbcinst -q -d`
- Asegúrate de que el nombre coincida exactamente (incluyendo llaves y mayúsculas)

### Error: "No se puede conectar a SQL Server"
- Verifica que el servidor SQL Server esté corriendo
- Verifica el nombre del servidor y la base de datos
- Verifica las credenciales (usuario/contraseña)
- Si usas autenticación Windows, asegúrate de que tu cuenta tenga permisos

### Error: "MBA3: Error 401"
- Verifica que `MBA3_CODIGO` y `MBA3_PWD` sean correctos
- Verifica que el servidor MBA3 esté accesible
- Verifica la URL base (`MBA3_BASE_URL`)


