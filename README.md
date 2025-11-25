# MBA3 Consultas

Proyecto para interactuar con la API de MBA3 (4D):
- Obtener JWT (sesión) mediante LOGIN en los Servicios de Acceso Externo
- API HTTP (FastAPI) para recibir, validar y procesar consultas SQL

## Estructura del Proyecto

```
mba3-consultas/
├─ .gitignore
├─ .env                 # archivo local con credenciales (NO subir a git)
├─ requirements.txt
├─ ultima_consulta.json # archivo generado por el API (última consulta recibida)
├─ resultado_api.json   # resultado de consultas a MBA3
├─ src/                 # Backend (Python/FastAPI)
│  ├─ main.py              # Script principal para obtener JWT mediante LOGIN
│  ├─ mba3_client.py       # Cliente para realizar LOGIN y obtener JWT
│  ├─ mba3_query_client.py # Cliente para ejecutar consultas SQL
│  ├─ api_server.py        # Servidor FastAPI para recibir consultas
│  ├─ models.py            # Modelos Pydantic para la API
│  ├─ config.py            # Configuración y variables de entorno
│  ├─ database/            # Módulo de persistencia en SQL Server
│  │  ├─ connection.py     # Gestión de conexiones SQL Server
│  │  ├─ services/         # Servicios de negocio
│  │  ├─ repositories/     # Repositorios de datos
│  │  └─ mappers/          # Mapeo de datos MBA3 → SQL Server
│  ├─ endpoints.py         # Endpoints de la API
│  ├─ services/            # Servicios de la aplicación
│  └─ utils.py             # Utilidades y validaciones
├─ frontend/            # Frontend (Vue.js/TypeScript)
│  ├─ src/
│  │  ├─ main.ts           # Punto de entrada
│  │  ├─ App.vue            # Componente raíz
│  │  ├─ router/            # Rutas (Vue Router)
│  │  ├─ stores/            # Estado global (Pinia)
│  │  ├─ views/             # Vistas principales
│  │  ├─ components/        # Componentes reutilizables
│  │  ├─ services/          # Servicios API
│  │  └─ types/             # Tipos TypeScript
│  ├─ package.json
│  └─ vite.config.ts        # Configuración de Vite
└─ README.md
```

## Configuración

1. Clonar el repositorio
2. Crear un entorno virtual (recomendado):
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```
3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. Configurar variables de entorno:
   - Crear archivo `.env` en la raíz del proyecto con las siguientes variables:
     ```env
     # Configuración MBA3
     MBA3_BASE_URL=http://192.168.2.159:8081
     MBA3_CODIGO=tu_codigo_servicio
     MBA3_PWD=tu_contraseña_servicio
     
     # Configuración SQL Server
     SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}
     SQL_SERVER_SERVER=localhost
     SQL_SERVER_DATABASE=tu_base_de_datos
     SQL_SERVER_UID=tu_usuario
     SQL_SERVER_PWD=tu_contraseña
     
     # Habilitar guardado en SQL Server
     ENABLE_SQL_SERVER_STORAGE=true
     ```
   - **IMPORTANTE**: No subir el archivo `.env` a git
   - Para más detalles sobre configuración, ver `CONFIGURACION_ENV.md`

## Uso

### Obtener JWT (sesión) mediante LOGIN

Según la documentación técnica de MBA3, el primer paso es crear un LOGIN para obtener el JWT:

```bash
python src/main.py
```

Este script:
- Realiza el LOGIN con las credenciales configuradas en `.env`
- Obtiene el JWT (sesión)
- Muestra el JWT que debes usar en tus peticiones

**Nota**: El JWT tiene un tiempo de expiración limitado. Si expira, deberás ejecutar este script nuevamente.

### Uso programático

Para usar el cliente de login en tu propia aplicación:

```python
from mba3_client import MBA3Client

# Crear cliente
client = MBA3Client("https://tu-servidor.mba3.com")

# Obtener JWT mediante LOGIN
token = client.login("codigo_servicio", "password_servicio")

# Verificar si hay sesión activa
if client.is_logged_in():
    print(f"JWT obtenido: {token[:50]}...")
```

**Importante**: 
- El JWT debe enviarse en el header de cada petición a los servicios de MBA3
- Si el JWT expira, deberás obtener uno nuevo mediante `login()`
- Cada servicio debe tener su propio LOGIN y genera una sesión única

## Arquitectura

### Componentes

- `src/main.py`: Script principal para obtener JWT mediante LOGIN desde línea de comandos
- `src/mba3_client.py`: Cliente modular con método `login()` para obtener JWT

### Funcionalidad

Según la documentación técnica de MBA3:

1. **LOGIN**: 
   - Credenciales: `código` (código del servicio) y `pwd` (contraseña del servicio)
   - Endpoint: `/login_Servicio`
   - Respuesta: JWT (sesión) que debe almacenarse para uso en peticiones posteriores
   - Cada servicio debe tener un LOGIN, cada Login genera una sesión única

2. **Uso del JWT**:
   - El JWT obtenido debe usarse en todas las peticiones a los servicios de MBA3
   - Se envía en el header `Authorization` de las peticiones
   - El JWT tiene un tiempo de expiración limitado

---

## API HTTP (FastAPI)

El proyecto incluye un servidor HTTP con FastAPI que recibe, valida y procesa consultas SQL (SELECT).

### Características

- ✅ Recibe consultas SQL en múltiples formatos (JSON, form-data, url-encoded)
- ✅ Valida que solo sean consultas SELECT
- ✅ Bloquea operaciones peligrosas (INSERT, UPDATE, DELETE, DROP, etc.)
- ✅ Parsea consultas y extrae componentes (SELECT, FROM, WHERE, ORDER BY, LIMIT)
- ✅ Guarda consultas recibidas en `ultima_consulta.json`
- ✅ Logs detallados en consola

### Instalación

Asegúrate de tener instaladas todas las dependencias:

```bash
pip install -r requirements.txt
```

### Iniciar el servidor

Desde el directorio del proyecto:

```bash
# Opción 1: Ejecutar directamente con Python
python src/api_server.py

# Opción 2: Ejecutar con uvicorn
cd src
uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
```

El servidor estará disponible en: `http://localhost:8000`

### Endpoints

#### 1. GET `/health`

Endpoint de health check.

**Ejemplo con curl:**
```bash
curl http://localhost:8000/health
```

**Respuesta:**
```json
{
  "status": "ok",
  "time": "2025-01-21T12:00:00.123456"
}
```

#### 2. POST `/query`

Endpoint principal para recibir consultas SQL.

**Acepta múltiples formatos:**

##### JSON (Content-Type: application/json)

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"query":"select * from clnt_factura_principal where NUMERO_PEDIDO_SISTEMA='\''176120'\''"}'
```

##### Form-data

```bash
curl -X POST "http://localhost:8000/query" \
  -F "query=select * from clnt_factura_principal limit 10"
```

##### Con partes individuales

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "select": "*",
    "from": "clnt_factura_principal",
    "where": "NUMERO_PEDIDO_SISTEMA='\''176120'\''"
  }'
```

**Respuesta exitosa (200 OK):**
```json
{
  "original": "select * from clnt_factura_principal where NUMERO_PEDIDO_SISTEMA='176120'",
  "parsed": {
    "select": "*",
    "from": "clnt_factura_principal",
    "where": "NUMERO_PEDIDO_SISTEMA='176120'",
    "orderBy": null,
    "limit": null
  },
  "received_at": "2025-01-21T12:00:00-05:00",
  "source": "Postman",
  "note": "PARSE_OK"
}
```

**Errores (400 Bad Request):**
- Consulta vacía
- Consulta que no comienza con SELECT
- Contiene palabras peligrosas (INSERT, UPDATE, DELETE, etc.)
- Múltiples statements separados por punto y coma
- Excede longitud máxima (5000 caracteres)

#### 3. GET `/facturas` ⭐ **Recomendado para Frontend**

Endpoint principal diseñado para uso en producción desde el frontend. **No requiere que el usuario ingrese SQL** - la query está integrada en el backend.

**Características:**
- ✅ Query integrada en el backend (no requiere SQL del frontend)
- ✅ Ejecuta consultas contra MBA3 automáticamente
- ✅ Guarda automáticamente resultados en SQL Server
- ✅ Filtros configurables mediante query parameters
- ✅ Retorna JSON con los datos de MBA3 y metadata

**Query integrada (valores por defecto):**
```sql
SELECT CODIGO_FACTURA, ANULADA, NUMERO_PEDIDO_SISTEMA, NUMERO_ORDEN, 
       NUMERO_FACTURA, CODIGO_DESPACHO, EMPRESA, CODIGO_CLIENTE, 
       FECHA_FACTURA, TIPO_DOCUMENTO, ObjDatosFactura, ORDEN_COMPRA, 
       ORDEN_COMPRA_CLIENTE, Remision_Facturada, NumIDFacturaRelacionada, 
       CONFIRMADO, CODIGO_BODEGA
FROM CLNT_FACTURA_PRINCIPAL
WHERE ANULADA='false' 
  AND CONFIRMADO='true' 
  AND Remision_Facturada='false' 
  AND ObjDatosFactura IS NOT NULL
```

**Parámetros de filtrado (query parameters):**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `anulada` | boolean | `false` | `false` = no anuladas, `true` = anuladas |
| `confirmado` | boolean | `true` | `true` = confirmadas, `false` = no confirmadas |
| `remision_facturada` | boolean | `false` | `false` = sin remisión, `true` = con remisión |
| `include_obj_datos` | boolean | `true` | Si `true`, solo incluye facturas con ObjDatosFactura |
| `save_to_db` | boolean | `true` | Si `true`, guarda los resultados en SQL Server |

**Ejemplos de uso:**

##### Uso básico (valores por defecto)
```bash
curl "http://localhost:8000/facturas"
```

##### Con filtros personalizados
```bash
curl "http://localhost:8000/facturas?anulada=false&confirmado=true&remision_facturada=false"
```

##### Desde JavaScript (fetch)
```javascript
fetch('http://localhost:8000/facturas?anulada=false&confirmado=true')
  .then(response => response.json())
  .then(data => {
    console.log('Facturas:', data.data);
    console.log('Total:', data.metadata.count);
  });
```

**Respuesta exitosa (200 OK):**
```json
{
  "status": "success",
  "data": [
    {
      "CODIGO_FACTURA": "FE-1002000124372-TRAYO",
      "NUMERO_FACTURA": 1002000124372,
      "EMPRESA": "TRAYO",
      "CODIGO_CLIENTE": "CLI0513",
      "FECHA_FACTURA": "2025-11-20",
      "ObjDatosFactura": {
        "GrabarLineasProd": [...]
      },
      ...
    }
  ],
  "metadata": {
    "count": 2,
    "filters": {
      "anulada": false,
      "confirmado": true,
      "remision_facturada": false,
      "include_obj_datos": true
    },
    "save_status": {
      "status": "success",
      "facturas_guardadas": 2,
      "total_detalles": 5
    }
  }
}
```

**Headers de respuesta:**
- `X-Count`: Número total de facturas retornadas
- `X-Saved-To-DB`: Estado del guardado en SQL Server
- `X-DB-Facturas`: Cantidad de facturas guardadas/actualizadas

**Nota:** Este endpoint es el recomendado para uso en producción, ya que no requiere que el frontend envíe consultas SQL. La query está integrada y segura en el backend.

#### 4. POST `/consulta`

Endpoint para ejecutar consultas SQL dinámicas contra MBA3 y guardar resultados en SQL Server.

**⚠️ Nota:** Este endpoint requiere enviar SQL desde el frontend. Para uso en producción, se recomienda usar el endpoint `/facturas` en su lugar.

**Características:**
- ✅ Ejecuta consultas SQL contra MBA3
- ✅ Valida que solo sean consultas SELECT
- ✅ Guarda automáticamente resultados en SQL Server
- ✅ Retorna JSON con los datos de MBA3

**Acepta múltiples formatos:**

##### JSON (Content-Type: application/json)

```bash
curl -X POST "http://localhost:8000/consulta" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT * FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='\''176120'\''"}'
```

##### Form-data

```bash
curl -X POST "http://localhost:8000/consulta" \
  -F "query=SELECT * FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"
```

**Respuesta exitosa (200 OK):**
- Retorna el JSON completo de MBA3
- Headers incluyen: `X-Saved-To-DB` (status del guardado), `X-DB-Facturas` (cantidad guardada)

**Ejemplo con Postman:**
- **Método:** POST
- **URL:** `http://localhost:8000/consulta`
- **Body:** raw JSON
  ```json
  {
    "query": "SELECT CODIGO_FACTURA, NUMERO_PEDIDO_SISTEMA, EMPRESA, CODIGO_CLIENTE, FECHA_FACTURA, ObjDatosFactura FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"
  }
  ```

**Nota:** Los datos se guardan automáticamente en SQL Server si está configurado. Ver sección de **Integración con SQL Server** para más detalles.

#### 5. GET `/consulta` 🔍 **Útil para pruebas desde navegador/Postman**

Endpoint equivalente al POST `/consulta` pero usando método GET con query parameter. **Ideal para pruebas desde Postman o el navegador.**

**Características:**
- ✅ Mismo comportamiento que POST `/consulta`
- ✅ Ejecuta consultas SQL contra MBA3
- ✅ Valida que solo sean consultas SELECT
- ✅ Guarda automáticamente resultados en SQL Server
- ✅ Retorna JSON con los datos de MBA3
- ✅ Útil para pruebas rápidas desde el navegador o Postman

**Parámetros:**
- `query` (requerido): Consulta SQL a ejecutar

**Ejemplo con curl:**
```bash
curl "http://localhost:8000/consulta?query=SELECT%20CODIGO_FACTURA%2CANULADA%2CNUMERO_PEDIDO_SISTEMA%20FROM%20CLNT_FACTURA_PRINCIPAL%20WHERE%20ANULADA%3D'false'"
```

**Ejemplo con Postman:**
- **Método:** GET
- **URL:** `http://localhost:8000/consulta`
- **Params (query parameters):**
  - `query`: `SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND ObjDatosFactura IS NOT NULL`

**Ejemplo desde el navegador:**
```
http://localhost:8000/consulta?query=SELECT CODIGO_FACTURA, NUMERO_FACTURA, EMPRESA FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'
```

**Respuesta exitosa (200 OK):**
- Retorna el JSON completo de MBA3 (array de facturas)
- Headers incluyen: `X-Saved-To-DB` (status del guardado), `X-DB-Facturas` (cantidad guardada), `X-Query` (primeros 100 caracteres de la query)

**Ejemplo de respuesta:**
```json
[
  {
    "CODIGO_FACTURA": "FE-1002000092292-TRAYO",
    "NUMERO_FACTURA": 1002000092292,
    "EMPRESA": "TRAYO",
    "CODIGO_CLIENTE": "CLI0839",
    "FECHA_FACTURA": "2022-12-12",
    "NUMERO_ORDEN": 99391,
    "ANULADA": false,
    "CODIGO_DESPACHO": 0,
    "CONFIRMADO": true,
    "CODIGO_BODEGA": "BPT",
    "TIPO_DOCUMENTO": "FACT",
    "NUMERO_PEDIDO_SISTEMA": 128900,
    "ORDEN_COMPRA_CLIENTE": "",
    "ORDEN_COMPRA": "3-1109",
    "ObjDatosFactura": {},
    "Remision_Facturada": false,
    "NumIDFacturaRelacionada": 0
  }
]
```

**Nota:** 
- Las consultas complejas con caracteres especiales pueden requerir encoding URL
- Para consultas muy largas, se recomienda usar POST `/consulta` en su lugar
- Los datos se guardan automáticamente en SQL Server si está configurado

#### 6. POST `/query/forward`

Endpoint placeholder para reenvío de consultas a MBA3 (deprecated, usar `/consulta` en su lugar).

**Respuesta (501 Not Implemented):**
```json
{
  "status": "not_implemented",
  "message": "La ejecución remota de consultas contra MBA3 se implementará en una siguiente etapa"
}
```

### Validaciones de seguridad

El servidor bloquea automáticamente:
- ❌ Consultas que no sean SELECT
- ❌ Operaciones peligrosas: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `EXEC`, etc.
- ❌ Múltiples statements separados por `;`
- ❌ Consultas que excedan 5000 caracteres

### Ejemplos con Postman

#### 1. Health Check
- **Método:** GET
- **URL:** `http://localhost:8000/health`

#### 2. Ejecutar consulta SQL con GET (Recomendado para pruebas)
- **Método:** GET
- **URL:** `http://localhost:8000/consulta`
- **Params (query parameters):**
  - `query`: `SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND ObjDatosFactura IS NOT NULL`
- **Respuesta:** Array JSON con las facturas encontradas

#### 3. Ejecutar consulta SQL con POST
- **Método:** POST
- **URL:** `http://localhost:8000/consulta`
- **Headers:** `Content-Type: application/json`
- **Body (raw JSON):**
  ```json
  {
    "query": "SELECT CODIGO_FACTURA, NUMERO_PEDIDO_SISTEMA, EMPRESA FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"
  }
  ```

#### 4. Enviar consulta SQL (solo validación)
- **Método:** POST
- **URL:** `http://localhost:8000/query`
- **Headers:** `Content-Type: application/json`
- **Body (raw JSON):**
  ```json
  {
    "query": "select CODIGO_FACTURA, NUMERO_PEDIDO_SISTEMA from CLNT_FACTURA_PRINCIPAL where NUMERO_PEDIDO_SISTEMA='176120'"
  }
  ```

#### 5. Enviar consulta con form-data
- **Método:** POST
- **URL:** `http://localhost:8000/query`
- **Body:** form-data
- **Campo:** `query` = `select * from clnt_factura_principal limit 10`

### Archivo de almacenamiento

Todas las consultas recibidas se guardan automáticamente en:
- **Archivo:** `ultima_consulta.json` (en el directorio raíz del proyecto)
- **Formato:** JSON con indentación
- **Contenido:** Consulta original, parseada, timestamp y metadata

### Logs

El servidor registra en consola:
- Hora de recepción de cada consulta
- Fuente (Postman, API, etc.)
- Consulta original
- Estado del parseo
- Campos parseados

**Ejemplo de log:**
```
======================================================================
2025-01-21 12:00:00,123 - INFO - Consulta recibida a las 2025-01-21T12:00:00.123456
2025-01-21 12:00:00,124 - INFO - Fuente: Postman
2025-01-21 12:00:00,125 - INFO - Consulta original: select * from clnt_factura_principal where NUMERO_PEDIDO_SISTEMA='176120'
2025-01-21 12:00:00,126 - INFO - Parseo: PARSE_OK
2025-01-21 12:00:00,127 - INFO - Campos parseados: {
  "select": "*",
  "from": "clnt_factura_principal",
  "where": "NUMERO_PEDIDO_SISTEMA='176120'"
}
======================================================================
```

### Formato de respuesta de MBA3

Cuando se implemente el endpoint `/query/forward`, la API de MBA3 devuelve datos en el siguiente formato JSON:

```json
{
  "CODIGO_FACTURA": "REMSI-900125351-TRAYO",
  "NUMERO_FACTURA": 900125351,
  "EMPRESA": "TRAYO",
  "CODIGO_CLIENTE": "CLI0513",
  "FECHA_FACTURA": "2025-11-20",
  "FECHA_VENCIMIENTO": "2026-02-18",
  "NUMERO_ORDEN": 129165,
  "NUMERO_PEDIDO_SISTEMA": 176120,
  "VALOR_FACTURA": 2438.46,
  "TOTAL_IMPUESTOS": 318.06,
  "ObjDatosFactura": {
    "Lineas": [
      {
        "Codigo": "5-0012.9",
        "Nombre": "MDS TOB M/FELPA T.9-11",
        "Cantidad": 456,
        "PrecioUnitario": 4.65,
        "TotalLinea": 2120.4
      }
    ]
  }
}
```

**Nota:** La API de MBA3 puede devolver un array de objetos o un objeto individual, dependiendo de la consulta. El campo `ObjDatosFactura` puede contener diferentes estructuras como `Lineas`, `CtrlEliminados1-4`, `CtrlEliminadosA-B`, `GrabarLineasProd`, etc.

Los modelos Pydantic para este formato están disponibles en `src/models.py` (`FacturaMBA3`, `ObjDatosFactura`, `LineaFactura`) para su uso futuro en el endpoint `/query/forward`.

---

## Integración con SQL Server

El proyecto incluye integración completa con SQL Server para almacenar automáticamente los datos obtenidos de MBA3.

### Características

- ✅ **Guardado automático**: Los resultados de consultas a MBA3 se guardan automáticamente en SQL Server
- ✅ **Mapeo de datos**: Transformación automática de JSON de MBA3 a estructura de tablas SQL Server
- ✅ **Manejo de errores**: Continúa procesando aunque falle una factura
- ✅ **Logging detallado**: Logs completos de operaciones de guardado

### Tablas SQL Server

El sistema guarda datos en las siguientes tablas:

#### `despacho_cabecera`
Almacena información de cabecera de las facturas/despachos:
- `despacho_id` (PK, UUID)
- `codigo_factura`, `numero_factura`, `empresa`, `codigo_cliente`
- `fecha_factura`, `fecha_despacho`, `tipo_documento`
- `numero_pedido_sistema`, `numero_orden`
- `anulada`, `remision_facturada`, `codigo_despacho`, `codigo_bodega`
- Y más campos...

#### `despacho_detalle`
Almacena las líneas de detalle de cada factura/despacho:
- `detalle_id` (PK, UUID)
- `despacho_id` (FK a `despacho_cabecera`)
- `sku`, `nombre_producto`, `cantidad`, `precio_unitario`
- `total_linea`, `descuento`, `impuesto`, `reg_num`
- `tipo_linea` (identifica el tipo: GrabarLineasProd, CtrlEliminados1-8, etc.)

### Configuración

1. **Configurar variables de entorno en `.env`:**
   ```env
   SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}
   SQL_SERVER_SERVER=localhost
   SQL_SERVER_DATABASE=tu_base_de_datos
   SQL_SERVER_UID=tu_usuario
   SQL_SERVER_PWD=tu_contraseña
   
   # O para autenticación Windows (dejar vacíos UID y PWD):
   # SQL_SERVER_UID=
   # SQL_SERVER_PWD=
   
   ENABLE_SQL_SERVER_STORAGE=true
   ```

2. **Verificar driver ODBC instalado:**
   ```bash
   # En PowerShell o CMD:
   odbcinst -q -d
   ```
   Debe mostrar `ODBC Driver 17 for SQL Server` o similar.

3. **Crear tablas en SQL Server:**
   - Ejecutar el script SQL proporcionado para crear las tablas necesarias
   - Ver estructura de tablas en la sección anterior

### Uso

Una vez configurado, el guardado es automático:

1. **Hacer consulta desde Postman:**
   ```
   POST http://localhost:8000/consulta
   Body: {"query": "SELECT * FROM CLNT_FACTURA_PRINCIPAL WHERE ..."}
   ```

2. **El sistema automáticamente:**
   - Ejecuta la consulta contra MBA3
   - Recibe el JSON con los datos
   - Guarda cada factura en `despacho_cabecera`
   - Guarda cada línea en `despacho_detalle`
   - Retorna el JSON original a Postman

3. **Ver logs:**
   - Los logs muestran el proceso de guardado
   - Indican cuántas facturas y detalles se guardaron
   - Muestran errores si los hay

### Mapeo de Datos

El sistema mapea automáticamente los datos de MBA3 a SQL Server:

| MBA3 (JSON) | SQL Server |
|------------|-----------|
| `CODIGO_FACTURA` | `despacho_cabecera.codigo_factura` |
| `EMPRESA` | `despacho_cabecera.empresa` |
| `CODIGO_CLIENTE` | `despacho_cabecera.codigo_cliente` |
| `CODIGO_BODEGA` | `despacho_cabecera.codigo_bodega` |
| `ObjDatosFactura.GrabarLineasProd[]` | `despacho_detalle` (con `tipo_linea='GrabarLineasProd'`) |
| `ObjDatosFactura.CtrlEliminados1[]` | `despacho_detalle` (con `tipo_linea='CtrlEliminados1'`) |
| Y más...

### Deshabilitar Guardado

Para deshabilitar el guardado automático (útil para pruebas):

```env
ENABLE_SQL_SERVER_STORAGE=false
```

### Diagnóstico

Si hay problemas de conexión, ejecutar:

```bash
python src/database/test_connection.py
```

Este script diagnostica problemas de configuración y conexión.

### Próximas etapas

- ✅ Integración con SQL Server completada
- ✅ Endpoint `/consulta` para ejecutar consultas contra MBA3
- 🔐 Agregar autenticación (JWT, API keys, etc.)
- 📊 Dashboard de consultas ejecutadas
- 🔍 Historial de consultas
- 🔄 Implementar upsert (actualizar si existe, insertar si no)

---

## Frontend Vue.js

El proyecto incluye un frontend moderno desarrollado con Vue.js 3, TypeScript, Pinia y Vue Router.

### Características del Frontend

- ✅ **Interfaz moderna y responsive** con soporte para tema claro/oscuro
- ✅ **Vista de facturas** con filtros configurables (anulada, confirmado, remisión facturada)
- ✅ **Vista de consulta SQL dinámica** para ejecutar consultas personalizadas
- ✅ **Tabla interactiva** con paginación y visualización de detalles
- ✅ **Logs detallados en consola** del navegador para debugging
- ✅ **Integración completa** con la API del backend

### Estructura del Frontend

```
frontend/
├── src/
│   ├── main.ts              # Punto de entrada
│   ├── App.vue              # Componente raíz
│   ├── router/              # Rutas (Vue Router)
│   │   └── index.ts
│   ├── stores/              # Estado global (Pinia)
│   │   ├── facturas.ts      # Store de facturas
│   │   └── theme.ts         # Store de tema (claro/oscuro)
│   ├── views/               # Vistas principales
│   │   ├── FacturasView.vue # Vista de facturas con filtros
│   │   └── ConsultaView.vue # Vista de consulta SQL dinámica
│   ├── components/          # Componentes reutilizables
│   │   ├── FacturaTable.vue # Tabla de facturas
│   │   ├── FacturaModal.vue # Modal de detalles
│   │   ├── FacturaFilters.vue # Filtros de facturas
│   │   ├── LineasList.vue   # Lista de líneas de factura
│   │   ├── Pagination.vue   # Componente de paginación
│   │   └── ThemeToggle.vue  # Toggle de tema
│   ├── services/            # Servicios API
│   │   └── api.ts           # Cliente Axios para API
│   ├── types/               # Tipos TypeScript
│   │   └── factura.ts       # Interfaces de facturas
│   └── assets/              # Estilos y recursos
│       └── main.css
├── package.json
├── vite.config.ts           # Configuración de Vite
└── tsconfig.json            # Configuración de TypeScript
```

### Instalación del Frontend

1. **Navegar al directorio del frontend:**
   ```bash
   cd frontend
   ```

2. **Instalar dependencias:**
   ```bash
   npm install
   ```

3. **Configurar variables de entorno:**
   Crear archivo `.env.local` en el directorio `frontend/`:
   ```env
   VITE_API_URL=http://localhost:8000
   ```

4. **Iniciar servidor de desarrollo:**
   ```bash
   npm run dev
   ```
   
   El frontend estará disponible en: `http://localhost:5173`

### Uso del Frontend

#### Vista de Facturas (`/facturas`)

- **Filtros disponibles:**
  - Anulada (false/true)
  - Confirmado (true/false)
  - Remisión facturada (false/true)
  - Incluir ObjDatosFactura (true/false)
  
- **Características:**
  - Tabla con todas las facturas
  - Paginación configurable
  - Modal para ver detalles completos
  - Visualización de líneas de factura

#### Vista de Consulta SQL (`/consulta`)

- **Funcionalidad:**
  - Ejecutar consultas SQL dinámicas contra MBA3
  - Ver resultados en tabla interactiva
  - Logs detallados en consola del navegador (F12)
  
- **Ejemplo de uso:**
  1. Ir a la ruta `/consulta`
  2. Hacer clic en "Cargar Ejemplo" para cargar una consulta de ejemplo
  3. Hacer clic en "Ejecutar Consulta"
  4. Abrir la consola del navegador (F12) para ver:
     - URL completa de la petición
     - Query SQL ejecutada
     - Total de facturas recibidas
     - Lista de campos disponibles
     - Primera factura completa en JSON
     - Array completo con todas las facturas

- **Logs en consola:**
  El frontend muestra información detallada en la consola del navegador:
  ```
  ======================================================================
  🌐 GET /consulta - Ejecutando consulta SQL
  🌐 URL: http://localhost:8000/consulta?query=...
  🌐 Query: SELECT CODIGO_FACTURA, ...
  ======================================================================
  📊 RESPUESTA DE /consulta:
     Total facturas recibidas: 1
     Campos en primera factura: 17 campos
     Lista de campos: ["CODIGO_FACTURA", "NUMERO_FACTURA", ...]
  
  📋 PRIMERA FACTURA COMPLETA:
  {
    "CODIGO_FACTURA": "FE-1002000092292-TRAYO",
    ...
  }
  ======================================================================
  ```

### Scripts Disponibles

- `npm run dev` - Inicia servidor de desarrollo
- `npm run build` - Compila para producción
- `npm run preview` - Previsualiza el build de producción
- `npm run lint` - Ejecuta el linter

### Configuración de Proxy

El frontend está configurado con un proxy en `vite.config.ts` para redirigir peticiones `/api` al backend:

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, '')
    }
  }
}
```

### Integración con Backend

El frontend se comunica con el backend mediante:

- **GET `/facturas`**: Obtiene facturas con filtros configurables
- **GET `/consulta?query=...`**: Ejecuta consultas SQL dinámicas

Ambos endpoints retornan JSON con los datos de MBA3 y se muestran en la interfaz del usuario.

---

## Arquitectura

### Componentes del Cliente

- `src/main.py`: Script principal para obtener JWT mediante LOGIN desde línea de comandos
- `src/mba3_client.py`: Cliente modular con método `login()` para obtener JWT
- `src/mba3_query_client.py`: Cliente para ejecutar consultas SQL usando el JWT

### Componentes del API

- `src/api_server.py`: Servidor FastAPI con endpoints para recibir consultas
- `src/endpoints.py`: Definición de todos los endpoints de la API
- `src/models.py`: Modelos Pydantic para validación de datos (QueryRequest, QueryResponse, FacturaMBA3)
- `src/config.py`: Configuración y carga de variables de entorno desde `.env`
- `src/database/`: Módulo completo de persistencia en SQL Server
  - `connection.py`: Gestión de conexiones a SQL Server
  - `services/factura_service.py`: Servicio para guardar facturas de MBA3
  - `repositories/despacho_repository.py`: Repositorio para operaciones de datos
  - `mappers/factura_mapper.py`: Mapeo de datos MBA3 → SQL Server
- `src/services/`: Servicios de la aplicación (mba3_service, query_service)
- `src/utils.py`: Utilidades y funciones de validación de consultas SQL

