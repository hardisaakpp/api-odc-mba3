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
├─ src/
│  ├─ main.py              # Script principal para obtener JWT mediante LOGIN
│  ├─ mba3_client.py       # Cliente para realizar LOGIN y obtener JWT
│  ├─ mba3_query_client.py # Cliente para ejecutar consultas SQL
│  ├─ api_server.py        # Servidor FastAPI para recibir consultas
│  └─ models.py            # Modelos Pydantic para la API
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
   - Crear archivo `.env` con las siguientes variables:
     ```
     MBA3_BASE_URL=https://tu-servidor.mba3.com
     MBA3_CODIGO=tu_codigo_servicio
     MBA3_PWD=tu_contraseña_servicio
     ```
   - **IMPORTANTE**: No subir el archivo `.env` a git

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

#### 3. POST `/query/forward`

Endpoint placeholder para reenvío de consultas a MBA3 (implementación futura).

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

#### 2. Enviar consulta SQL
- **Método:** POST
- **URL:** `http://localhost:8000/query`
- **Headers:** `Content-Type: application/json`
- **Body (raw JSON):**
  ```json
  {
    "query": "select CODIGO_FACTURA, NUMERO_PEDIDO_SISTEMA from CLNT_FACTURA_PRINCIPAL where NUMERO_PEDIDO_SISTEMA='176120'"
  }
  ```

#### 3. Enviar consulta con form-data
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

### Próximas etapas

- 🔄 Implementar endpoint `/query/forward` para ejecutar consultas contra MBA3 usando `MBA3APIClient`
  - Utilizar los modelos Pydantic (`FacturaMBA3`) para validar las respuestas
  - Devolver datos en el mismo formato que MBA3 o transformarlos según necesidades
- 🔐 Agregar autenticación (JWT, API keys, etc.)
- 💾 Almacenar consultas en base de datos (SQL Server)
- 📊 Dashboard de consultas ejecutadas
- 🔍 Historial de consultas

---

## Arquitectura

### Componentes del Cliente

- `src/main.py`: Script principal para obtener JWT mediante LOGIN desde línea de comandos
- `src/mba3_client.py`: Cliente modular con método `login()` para obtener JWT
- `src/mba3_query_client.py`: Cliente para ejecutar consultas SQL usando el JWT

### Componentes del API

- `src/api_server.py`: Servidor FastAPI con endpoints para recibir consultas
- `src/models.py`: Modelos Pydantic para validación de datos (QueryRequest, QueryResponse)

