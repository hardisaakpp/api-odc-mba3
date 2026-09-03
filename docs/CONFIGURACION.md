# Configuración

Guía completa de configuración del sistema MBA3 Consultas.

## 📋 Variables de Entorno

### Archivos por ambiente (obligatorios)

La aplicación **exige** un archivo de entorno según `ENVIRONMENT` (no usa fallback silencioso a `.env`):

| ENVIRONMENT (normalizado) | Archivo requerido en la raíz del proyecto |
|---------------------------|-------------------------------------------|
| `development` / `develop` | `.env.develop` |
| `test` | `.env.test` |
| `staging` | `.env.staging` |
| `production` | `.env.production` |

Si falta el archivo correspondiente, el proceso **termina al iniciar** con un mensaje claro.

**Override:** define `ENV_FILE` con la ruta (absoluta o relativa al root del repo) a un archivo `.env` concreto; ese archivo también debe existir. Tiene prioridad sobre la tabla anterior.

**Orden de carga:** primero se elige el fichero (`ENV_FILE` o `.env.{ambiente}`), luego se carga con `python-dotenv`, y **después** se lee `ENVIRONMENT` para el modo lógico de la app. Así, en servidor puedes usar un solo archivo (p. ej. `/opt/odc-sap/.env`) con `ENVIRONMENT=production` dentro, sin depender de `.env.develop`.

### Desarrollo con Docker (perfil `app`)

Con `.\scripts\docker-app-up.ps1` el archivo **`.env.develop`** se monta en el contenedor. Compose sobrescribe solo:

- `REDIS_URL=redis://redis:6379/0`
- `FILE_STORAGE_ENDPOINT=http://minio:9000`

El resto (SQL, SAP, MBA3, JWT) sale de tu `.env.develop`. Si SQL Server corre en tu **máquina Windows** y en el `.env` tienes `SQL_SERVER_SERVER=localhost`, **desde el contenedor fallará**: usa `host.docker.internal` (con puerto, p. ej. `host.docker.internal,1433`) o el hostname/IP del servidor. Detalle: [DOCKER_COMPOSE.md](DOCKER_COMPOSE.md).

### systemd (Linux): API, Celery worker y Celery beat

En producción o test no uses `.env.develop` como única fuente en la unidad: apunta al fichero real del servidor y fija el ambiente explícitamente:

```ini
Environment=ENVIRONMENT=production
Environment=ENV_FILE=/opt/odc-sap/.env
```

(Ajusta la ruta al directorio de despliegue.) Repite las mismas líneas en los servicios del worker y de beat para que Celery use la misma configuración que la API. **Tras editar ese `.env`**, reinicia la API y los procesos Celery para que recarguen variables; los nombres típicos de unidades `systemd` en producción son `odc-sap-api`, `celery-worker` y `celery-beat` (no existen `mba3-api` ni `celery` sueltos). Detalle y comandos: [DEPLOY_PRODUCCION.md](DEPLOY_PRODUCCION.md).

### MBA3

```env
MBA3_BASE_URL=http://192.168.2.159:8081
MBA3_CODIGO=tu_codigo_servicio
MBA3_PWD=tu_contraseña
MBA3_DIGEST_USERNAME=tu_usuario  # Opcional
MBA3_DIGEST_PASSWORD=tu_contraseña  # Opcional
```

### SQL Server Principal (Almacenamiento)

```env
SQL_SERVER_DRIVER={ODBC Driver 18 for SQL Server}
SQL_SERVER_SERVER=210.17.1.54
SQL_SERVER_DATABASE=store_control
SQL_SERVER_UID=tu_usuario
SQL_SERVER_PWD=tu_contraseña
```

**Autenticación Windows:** Dejar `SQL_SERVER_UID` y `SQL_SERVER_PWD` vacíos.

**Propósito:** Almacenar datos de MBA3 y cache de productos SAP.
- Tablas: `despacho_cabecera`, `despacho_detalle`, `producto_sap_cache`, `pack_conversion`

### SQL Server SAP (Consultas OPENQUERY) - Opcional

Si usas un servidor SQL diferente para consultas SAP:

```env
SQL_SERVER_SAP_DRIVER={ODBC Driver 18 for SQL Server}
SQL_SERVER_SAP_SERVER=10.10.100.12
SQL_SERVER_SAP_DATABASE=STORECONTROL
SQL_SERVER_SAP_UID=usuario
SQL_SERVER_SAP_PWD=contraseña
```

**Nota:** Si no configuras estas variables, el sistema usará las del servidor principal como fallback.

**Propósito:** Ejecutar consultas `OPENQUERY` a SAP HANA.
- Requisito: Debe tener el servidor vinculado `[MYHANADB]` configurado

### SAP HANA (Consultas)

```env
SAP_LINKED_SERVER=MYHANADB
SAP_DATABASE=SBO_MABEL_PROD
SAP_SCHEMA=SBO_MABEL_PROD
SAP_CACHE_DAYS=30
```

**Requisito:** El servidor vinculado `[MYHANADB]` debe estar configurado en SQL Server. Ver sección [Configurar Servidor Vinculado](#configurar-servidor-vinculado-para-sap).

### SAP Service Layer (Purchase Orders e Inventory Transfer Requests)

Contrato validado con Postman (puerto 50001): `Login`, `PurchaseOrders`, `InventoryTransferRequests`.

**Variables recomendadas (sin `/Login` en la URL):**

```env
SAP_SL_BASE_URL=http://10.128.240.4:50001/b1s/v1
SAP_COMPANY_DB=TEST_MABEL
SAP_USER=MZ-SIS-05
SAP_PASSWORD=***REMOVED***
SAP_SERVICE_LAYER_VERIFY_SSL=false
SAP_ST_FROM_WAREHOUSE=OUT-CON
```

**Compatibilidad:** También se aceptan `SAP_SERVICE_LAYER_URL`, `SAP_SERVICE_LAYER_DATABASE`, `SAP_SERVICE_LAYER_USERNAME`, `SAP_SERVICE_LAYER_PASSWORD`. La URL base no debe incluir `/Login`.

`SAP_ST_FROM_WAREHOUSE`: bodega origen para Inventory Transfer Requests (1 por bodega destino). Si no se define, se usa `codigo_bodega` de la cabecera de la OC.

**Nota:** Necesarias para `POST /integrar-sap` (OC con `WarehouseCode` por línea e ITR agrupadas por bodega).

### Notificaciones por Email

```env
# Configuración SMTP
EMAIL_SMTP_SERVER=mabeltrading-com-ec.mail.protection.outlook.com
EMAIL_SMTP_PORT=25
EMAIL_SMTP_USER=
EMAIL_SMTP_PASSWORD=
EMAIL_FROM=integrationsap@mabeltrading.com.ec
EMAIL_FROM_NAME=INTEGRACIÓN SAP

# Configuración de advertencias técnicas
EMAIL_WARNING_TIME_LIMIT_PERCENT=80
EMAIL_WARNING_HIGH_VOLUME_THRESHOLD=500
EMAIL_WARNING_FAILURES_THRESHOLD=3

# Override en desarrollo: TODOS los correos de notificación van a este destinatario,
# ignorando la BD. Solo aplica con ENVIRONMENT=development; no definir en producción.
EMAIL_DEV_OVERRIDE=cortiz@mabeltrading.com.ec
```

**Destinatarios por tipo de correo:** ya no se configuran por variable de entorno. Se administran en BD (`notificacion_persona_correo` / `notificacion_tipo_correo`) desde la interfaz "Personas y Correos" (`/mba3-consultas/admin/destinatarios`, solo Admin): cada persona se vincula a los correos específicos del catálogo que debe recibir. Si nadie está vinculado a un correo, ese correo no se envía (no hay fallback a `.env`).

**Tipos de Notificaciones (`tipo_notificacion` en el catálogo):**
- **OPERACIONES**: Administración El Rayo (nuevos despachos, confirmaciones, etc.)
- **MABEL_TRADING**: Confirmaciones y cierres de pedido que le corresponden a MABEL TRADING
- **HOMOLOGACIONES**: Productos no homologados detectados en SAP (solo productos nuevos, no se reenvían)
- **TECNICOS**: Errores del sistema, advertencias de capacidad y problemas técnicos
- **PRODUCCION_ELRAYO**: Notificaciones para el perfil Producción El Rayo (req. 1.8)

### Seguridad (Opcional)

```env
ENABLE_AUTH=false
API_KEY=tu-api-key-secreta
ENABLE_RATE_LIMITING=false
RATE_LIMIT_DEFAULT=100/minute
ENVIRONMENT=development
HIDE_SWAGGER_IN_PROD=true
```

Ver [SEGURIDAD.md](SEGURIDAD.md) para más detalles.

## 🔧 Configurar Servidor Vinculado para SAP

### Requisitos Previos

1. **SQL Server Management Studio (SSMS)** instalado
2. **Driver ODBC para SAP HANA** instalado (o driver OLE DB)
3. **Acceso al servidor SAP HANA**
4. **Credenciales** para conectarse a SAP HANA

### Método 1: Script SQL

1. Conéctate a tu instancia de SQL Server en SSMS
2. Ejecuta manualmente (ajustando los valores a tu entorno):

```sql
-- Ajusta estos valores según tu configuración
DECLARE @server NVARCHAR(128) = N'MYHANADB';
DECLARE @datasrc NVARCHAR(4000) = N'10.10.100.12';  -- Tu IP de SAP
DECLARE @catalog NVARCHAR(128) = N'SBO_MABEL_PROD';  -- Tu base de datos

-- Crear servidor vinculado
EXEC sp_addlinkedserver
    @server = @server,
    @srvproduct = N'HANA',
    @provider = N'MSDASQL',
    @datasrc = @datasrc,
    @catalog = @catalog;

-- Configurar autenticación
EXEC sp_addlinkedsrvlogin 
    @rmtsrvname = 'MYHANADB',
    @useself = 'false',
    @locallogin = NULL,
    @rmtuser = 'SYSTEM',  -- Usuario SAP
    @rmtpassword = 'tu_contraseña';
```

3. Verificar:

```sql
-- Ver servidores vinculados
SELECT * FROM sys.servers WHERE name = 'MYHANADB';

-- Probar conexión
SELECT * FROM OPENQUERY([MYHANADB], 'SELECT 1 AS Test');
```

### Método 2: Interfaz Gráfica (SSMS)

1. En SSMS, expande **Server Objects** → **Linked Servers**
2. Click derecho → **New Linked Server...**
3. **General:**
   - Linked server: `MYHANADB`
   - Server type: **Other data source**
   - Provider: `Microsoft OLE DB Provider for ODBC Drivers`
   - Product name: `HANA`
   - Data source: `10.10.100.12` (tu IP de SAP)
   - Catalog: `SBO_MABEL_PROD`
4. **Security:**
   - Selecciona **Be made using this security context**
   - Remote login: Usuario SAP
   - With password: Contraseña SAP
5. **Server Options:**
   - ✅ RPC: `True`
   - ✅ RPC Out: `True`
   - Connect timeout: `30`
   - Query timeout: `30`

### Verificar Configuración

```sql
-- Ver todos los servidores vinculados
SELECT * FROM sys.servers WHERE is_linked = 1;

-- Ver detalles específicos
SELECT 
    name AS ServerName,
    product AS Product,
    provider AS Provider,
    data_source AS DataSource,
    catalog AS Catalog
FROM sys.servers
WHERE name = 'MYHANADB';
```

## ✅ Verificación

```bash
# Verificar conexión MBA3
python src/main.py --login

# Verificar conexión SQL Server
python scripts/check_db_connection.py

# Probar consulta SAP
python scripts/test_sap_query.py --sku "5-0012.9"
```

## 🔍 Solución de Problemas

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

### Error: "Cannot find the server 'MYHANADB'"
- El servidor vinculado no está configurado
- Ver sección [Configurar Servidor Vinculado](#configurar-servidor-vinculado-para-sap)

### Error: "Invalid object name 'producto_sap_cache'"
- Estás conectado al servidor SAP en lugar del servidor principal
- Verifica que `SQL_SERVER_SERVER` y `SQL_SERVER_DATABASE` apunten al servidor principal

### Error: "Provider is not registered"
- Instala el driver ODBC o OLE DB para SAP HANA

### Error: "Login failed for user"
- Verifica las credenciales en `sp_addlinkedsrvlogin`
- Asegúrate de que el usuario tenga permisos en SAP HANA

## 📊 Resumen de Configuración

| Propósito | Servidor | Base de Datos | Variables |
|-----------|----------|---------------|-----------|
| Almacenar datos | 210.17.1.54 | store_control | `SQL_SERVER_*` |
| Consultas SAP | 10.10.100.12 | STORECONTROL | `SQL_SERVER_SAP_*` |

## 📝 Notas Importantes

1. **Nombre del servidor vinculado**: Debe coincidir exactamente con `SAP_LINKED_SERVER` en tu `.env`
2. **IP y Puerto**: Si SAP HANA usa un puerto específico, inclúyelo: `10.10.100.12:30015`
3. **Permisos**: Asegúrate de que el usuario tenga permisos de lectura en las tablas de SAP
4. **Cache**: El sistema usa cache para evitar consultas repetidas a SAP (configurable con `SAP_CACHE_DAYS`)
