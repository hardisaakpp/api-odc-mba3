# Guía de Testing

Esta guía explica cómo ejecutar y escribir tests para la aplicación.

## 🧪 Estructura de Tests

```
tests/
├── __init__.py          # Inicialización del módulo
├── conftest.py          # Fixtures compartidas
└── test_endpoints.py    # Tests de endpoints
```

## 📦 Instalación

### 1. Instalar Dependencias de Testing

```bash
pip install -r requirements.txt
```

Esto instalará:
- `pytest` - Framework de testing
- `pytest-asyncio` - Soporte para async/await
- `pytest-cov` - Coverage de código
- `httpx` - Cliente HTTP para testing de FastAPI

### 2. Verificar Instalación

```bash
pytest --version
```

## 🚀 Ejecutar Tests

### Ejecutar Todos los Tests

```bash
# Desde la raíz del proyecto
pytest

# Con output verbose
pytest -v

# Con coverage
pytest --cov=src --cov-report=html
```

### Ejecutar Tests Específicos

```bash
# Un archivo específico
pytest tests/test_endpoints.py

# Una clase específica
pytest tests/test_endpoints.py::TestHealthEndpoint

# Un test específico
pytest tests/test_endpoints.py::TestHealthEndpoint::test_health_check
```

### Ejecutar con Filtros

```bash
# Solo tests marcados como "unit"
pytest -m unit

# Excluir tests lentos
pytest -m "not slow"
```

## 📝 Escribir Nuevos Tests

### Estructura Básica

```python
import pytest
from fastapi.testclient import TestClient

class TestMiEndpoint:
    """Tests para mi endpoint."""
    
    def test_caso_exitoso(self, client: TestClient):
        """Verifica que el endpoint funciona correctamente."""
        response = client.get("/mi-endpoint")
        assert response.status_code == 200
        data = response.json()
        assert "campo_esperado" in data
```

### Usar Fixtures

```python
def test_con_fixture(self, client: TestClient, api_key: str):
    """Test que usa fixtures."""
    response = client.get(
        "/endpoint-protegido",
        headers={"X-API-Key": api_key}
    )
    assert response.status_code == 200
```

---

## 🧪 Testing Manual - Comandos PowerShell

### Requisitos Previos

1. **Servidor API corriendo:**
   ```powershell
   python src/api_server.py
   ```

2. **Variables de entorno configuradas** en `.env`

3. **SQL Server accesible** (para pruebas de guardado)

4. **SAP configurado** (para pruebas de integración SAP)

### Orden Recomendada de Pruebas

1. **Health Check** - Verificar que el servidor esté funcionando
2. **Consultar Despachos** - Consultar sin guardar
3. **Migrar Despachos** - Consultar y guardar en BD
4. **Procesar Orden de Compra** - Copiar a OC
5. **Proceso Completo** - Flujo completo end-to-end
6. **Consultar SAP** - Consultar productos en SAP
7. **Integrar con SAP** - Enviar ODCs a SAP

### Comandos Individuales

#### 1. Health Check

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
```

#### 2. Consultar Despachos (GET /consultar)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/consultar" -Method Get
```

#### 3. Migrar Despachos (GET /migrar/completo)

Requiere JWT con permiso `mabel.view` (igual que en el navegador/Swagger).

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/migrar/completo" -Method Get -Headers @{ Authorization = "Bearer TU_JWT" }
```

#### 4. Procesar Orden de Compra (GET /procesar-oc)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/procesar-oc" -Method Get
```

#### 5. Proceso Completo (GET /pruebas)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/pruebas" -Method Get
```

#### 6. Consultar SAP

```powershell
# Con cache
Invoke-RestMethod -Uri "http://localhost:8000/sap/test?sku=5-0012.9" -Method Get

# Directo (sin cache)
Invoke-RestMethod -Uri "http://localhost:8000/sap/test/direct?sku=5-0012.9" -Method Get
```

#### 7. Integrar con SAP (POST /integrar-sap)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/integrar-sap" -Method Post
```

### Ver Resultados Formateados

```powershell
$result = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
$result | ConvertTo-Json -Depth 10
```

### Testing Automatizado

Un script de prueba automatizado está disponible en `scripts/test_endpoints.ps1`. Este script prueba todos los endpoints en orden y muestra los resultados formateados:

```powershell
# Ejecutar desde la raíz del proyecto
.\scripts\test_endpoints.ps1
```

### Tests con Mocking

```python
from unittest.mock import patch, MagicMock

def test_con_mock(self, client: TestClient):
    """Test que usa mocks."""
    with patch('src.services.mba3_service.MBA3Service') as mock_service:
        mock_service.return_value.get_data.return_value = {"test": "data"}
        
        response = client.get("/endpoint")
        assert response.status_code == 200
```

## 🎯 Tests Disponibles

### TestHealthEndpoint
- ✅ `test_health_check` - Verifica que `/health` funciona

### TestQueryEndpoint
- ✅ `test_query_validation_select` - Acepta queries SELECT válidas
- ✅ `test_query_rejects_insert` - Rechaza queries INSERT
- ✅ `test_query_rejects_delete` - Rechaza queries DELETE

### TestConsultarEndpoint
- ✅ `test_consultar_endpoint_exists` - Verifica que el endpoint existe

### TestProcesarOCEndpoint
- ✅ `test_procesar_oc_endpoint_exists` - Verifica que el endpoint existe

### TestIntegrarSAPEndpoint
- ✅ `test_integrar_sap_endpoint_exists` - Verifica que el endpoint existe

## 📊 Coverage

### Ver Coverage

```bash
# Generar reporte HTML
pytest --cov=src --cov-report=html

# Abrir reporte
# Abre htmlcov/index.html en tu navegador
```

### Coverage Mínimo Recomendado

- **Endpoints**: 80%+
- **Services**: 70%+
- **Repositories**: 60%+
- **Overall**: 70%+

## 🔧 Configuración

### pytest.ini

El archivo `pytest.ini` contiene la configuración de pytest:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

### Variables de Entorno para Tests

Puedes crear un archivo `.env.test` para tests:

```env
# .env.test
ENABLE_AUTH=false
ENABLE_RATE_LIMITING=false
ENVIRONMENT=test
```

## 🐛 Troubleshooting

### Error: "Module not found"
```bash
# Asegúrate de estar en la raíz del proyecto
cd /ruta/al/proyecto
pytest
```

### Error: "Import error"
```bash
# Instala dependencias
pip install -r requirements.txt
```

### Tests muy lentos
```bash
# Ejecuta solo tests rápidos
pytest -m "not slow"
```

## 📚 Mejores Prácticas

1. **Nombres Descriptivos**: `test_debe_rechazar_query_insert` es mejor que `test1`
2. **Un Test, Una Aserción**: Cada test debe verificar una cosa
3. **Usar Fixtures**: Reutiliza código común con fixtures
4. **Mockear Servicios Externos**: No dependas de MBA3/SAP en tests
5. **Tests Independientes**: Cada test debe poder ejecutarse solo
6. **Tests Rápidos**: Los tests deben ejecutarse rápido (< 1 segundo cada uno)

## 🚧 Próximos Tests a Agregar

- [ ] Tests unitarios para servicios
- [ ] Tests unitarios para repositorios
- [ ] Tests de integración completos
- [ ] Tests de seguridad (autenticación, rate limiting)
- [ ] Tests de mappers
- [ ] Tests de validación SQL

