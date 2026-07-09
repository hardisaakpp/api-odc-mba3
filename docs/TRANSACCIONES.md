# Política de Transacciones - Backend MBA3

## Resumen

Este documento describe la política de manejo de transacciones en el backend de MBA3-Consultas.

## Configuración de Conexiones

### Funciones de Conexión

El proyecto provee dos funciones principales para obtener conexiones a la base de datos:

1. **`get_db_connection()`** - Conexión básica
2. **`get_db_connection_context()`** - Conexión con context manager (recomendada)

Ambas funciones configuran `autocommit = False`, lo que significa que las transacciones son **implícitas** y requieren un `commit()` explícito para persistir cambios.

### Context Manager (Recomendado)

```python
from src.database.connection import get_db_connection_context

# Uso recomendado para operaciones de escritura
with get_db_connection_context() as conn:
    repo = MiRepository(conn)
    repo.insert(datos)
    # El commit se realiza automáticamente al salir del with
    # Si hay una excepción, se hace rollback automáticamente
```

**Ventajas:**
- Cierre automático de la conexión
- Commit automático al finalizar exitosamente
- Rollback automático en caso de excepción
- Código más limpio y menos propenso a errores

### Conexión Básica (Legado)

```python
from src.database.connection import get_db_connection

conn = get_db_connection()
try:
    repo = MiRepository(conn)
    repo.insert(datos)
    conn.commit()  # Commit manual requerido
finally:
    conn.close()  # Cierre manual requerido
```

**Nota:** Esta forma aún existe en algunas partes del código pero se recomienda usar el context manager para nuevas implementaciones.

## Comportamiento de Transacciones

### Operaciones de Escritura

Para operaciones que modifican datos (INSERT, UPDATE, DELETE):

1. **Usar siempre `get_db_connection_context()`**
2. La transacción inicia automáticamente al obtener la conexión
3. El commit se realiza al salir del bloque `with` sin excepciones
4. El rollback se realiza automáticamente si hay una excepción

### Operaciones de Lectura

Para operaciones de solo lectura (SELECT):

1. Se puede usar cualquiera de las dos funciones
2. Para lecturas dentro de `asyncio.to_thread()`, usar `get_db_connection()` con `try/finally`
3. El context manager también funciona para lecturas

## Patrones de Uso

### Endpoint con Operación de Escritura

```python
@app.post("/items")
async def crear_item(item: ItemCreate, user: dict = Depends(verify_jwt_token)):
    with get_db_connection_context() as conn:
        repo = ItemRepository(conn)
        nuevo_item = repo.insert(item.dict())
        return {"status": "success", "item": nuevo_item}
```

### Endpoint con Múltiples Operaciones

```python
@app.post("/proceso-completo")
async def proceso_completo(datos: DatosRequest):
    # Una sola transacción para múltiples operaciones
    with get_db_connection_context() as conn:
        repo_a = RepositoryA(conn)
        repo_b = RepositoryB(conn)
        
        resultado_a = repo_a.insert(datos.parte_a)
        resultado_b = repo_b.insert(datos.parte_b)
        
        # Si cualquiera falla, se hace rollback de todo
        return {"status": "success", "resultados": [resultado_a, resultado_b]}
```

### Operación Async con Thread Pool

```python
@app.get("/items")
async def obtener_items():
    def _query_items():
        # Para operaciones en thread pool, usar try/finally explícito
        # o context manager dentro de la función helper
        with get_db_connection_context() as conn:
            repo = ItemRepository(conn)
            return repo.get_all()
    
    items = await asyncio.to_thread(_query_items)
    return {"items": items}
```

## Manejo de Errores

### Con Context Manager

```python
try:
    with get_db_connection_context() as conn:
        repo = MiRepository(conn)
        repo.operacion_riesgosa()
        # Si falla aquí, rollback automático
except Exception as e:
    # La conexión ya está cerrada y el rollback hecho
    logger.error(f"Error en operación: {e}")
    raise HTTPException(status_code=500, detail=str(e))
```

### Sin Context Manager (Legado)

```python
conn = get_db_connection()
try:
    repo = MiRepository(conn)
    repo.operacion_riesgosa()
    conn.commit()
except Exception as e:
    conn.rollback()  # Rollback manual
    raise
finally:
    conn.close()  # Cierre manual obligatorio
```

## Implementación del Context Manager

El context manager está implementado en `src/database/connection.py`:

```python
@contextmanager
def get_db_connection_context():
    """
    Context manager para conexiones a base de datos.
    Garantiza commit/rollback y cierre automático.
    """
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()  # Commit automático si no hay excepción
    except Exception:
        conn.rollback()  # Rollback automático en caso de error
        raise
    finally:
        conn.close()  # Cierre automático siempre
```

## Consideraciones Especiales

### Conexiones de Larga Duración

Para procesos que requieren múltiples operaciones independientes (como integración SAP), se deben usar múltiples conexiones cortas con context manager en lugar de una conexión larga:

```python
# Evitar: una conexión larga para todo
conn = get_db_connection()
# ... muchas operaciones ...
conn.close()

# Preferir: múltiples conexiones cortas
with get_db_connection_context() as conn:
    # Operación 1

with get_db_connection_context() as conn:
    # Operación 2
```

### Tareas de Celery

Las tareas de Celery deben usar el context manager:

```python
@celery_app.task
def mi_tarea():
    with get_db_connection_context() as conn:
        repo = MiRepository(conn)
        repo.proceso()
```

## Migración de Código Existente

Cuando se migra código existente de `get_db_connection()` a `get_db_connection_context()`:

1. Reemplazar `conn = get_db_connection()` por `with get_db_connection_context() as conn:`
2. Eliminar llamadas explícitas a `conn.commit()`
3. Eliminar llamadas explícitas a `conn.close()`
4. Eliminar el bloque `finally: conn.close()` si existe
5. Ajustar la indentación del código dentro del nuevo bloque `with`

## Archivos Relevantes

- `src/database/connection.py` - Funciones de conexión
- `src/endpoints/*.py` - Endpoints que usan conexiones
- `src/database/repositories/*.py` - Repositorios que reciben conexiones

## Referencias

- [pyodbc Documentation](https://github.com/mkleehammer/pyodbc/wiki)
- [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [Python Context Managers](https://docs.python.org/3/library/contextlib.html)
