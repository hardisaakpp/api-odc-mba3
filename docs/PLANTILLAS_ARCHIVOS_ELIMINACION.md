# Eliminación de Archivos en Plantillas

Esta documentación describe la funcionalidad de eliminación de archivos en plantillas Excel, con soporte para eliminación lógica (soft delete) y física (hard delete).

## Descripción General

El sistema soporta **dos modos de eliminación** de archivos para balancear la recuperación accidental con la liberación de espacio en storage:

- **Soft Delete (por defecto)**: Marca como inactivo sin eliminar del storage
- **Hard Delete (opcional)**: Elimina física y lógicamente

## 1. Soft Delete (Por Defecto)

Cuando llamas a `DELETE /api/plantillas/archivos/{archivo_id}` **sin parámetros adicionales**:

### Comportamiento

- ✅ Marca el archivo como inactivo en la base de datos (`activo = 0`)
- ✅ El archivo **permanece en MinIO/S3** para auditoría
- ✅ El archivo ya **no aparece en listados** del usuario
- ✅ Es **reversible** (un admin puede reactivarlo cambiando `activo = 1`)

### Ejemplo de Uso

```bash
DELETE /api/plantillas/archivos/123
```

### Respuesta

```json
{
  "success": true,
  "mensaje": "Archivo marcado como inactivo",
  "archivo_id": 123
}
```

### Cuándo Usar

- ✅ Eliminaciones por error que podrían necesitar recuperarse
- ✅ Archivos que deben mantenerse para auditoría
- ✅ Cuando necesitas respetar trazabilidad y cumplimiento normativo
- ✅ **Por defecto en todas las operaciones de eliminación**

---

## 2. Eliminación Física (Hard Delete)

Cuando llamas con el parámetro `eliminar_fisicamente=true`:

### Comportamiento

- ✅ Marca el archivo como inactivo en la BD
- ✅ **TAMBIÉN elimina el archivo del storage MinIO/S3**
- ⚠️ Esta operación es **IRREVERSIBLE**

### Ejemplo de Uso

```bash
DELETE /api/plantillas/archivos/123?eliminar_fisicamente=true
```

### Respuesta

```json
{
  "success": true,
  "mensaje": "Archivo eliminado de forma física",
  "archivo_id": 123,
  "storage_deleted": true
}
```

### Cuándo Usar

- ✅ Cumplimiento con políticas de retención de datos
- ✅ Necesidad de liberar espacio en MinIO/S3
- ✅ Datos sensibles que deben eliminarse completamente
- ⚠️ **Usar con cuidado - Es irreversible**

---

## 3. ¿Por Qué Este Diseño?

El **soft delete por defecto** es intencional para:

### 1. **Auditoría**
- Mantener registro histórico de qué archivos existieron
- Trazabilidad completa del ciclo de vida de documentos
- Cumplimiento normativo (retención de datos)

### 2. **Recuperación**
- Poder restaurar un archivo eliminado por error
- Segunda oportunidad ante eliminaciones accidentales
- Reduce riesgo de pérdida de datos

### 3. **Seguridad**
- Evitar pérdidas accidentales de datos críticos
- Requiere intención explícita para eliminación física
- El parámetro `eliminar_fisicamente` es una decisión consciente

### 4. **Flexibilidad**
- Cada usuario decide si necesita hard delete
- Diferentes casos de uso requieren diferentes estrategias
- Balance entre recuperación y cumplimiento normativo

---

## 4. Flujo de Eliminación

```
DELETE /api/plantillas/archivos/{id}
                    |
                    ├─ Sin parámetros → Soft Delete
                    │   └─ activo = 0 (en BD)
                    │   └─ Archivo permanece en MinIO
                    │   └─ REVERSIBLE
                    │
                    └─ eliminar_fisicamente=true → Hard Delete
                        └─ activo = 0 (en BD)
                        └─ Archivo se elimina de MinIO
                        └─ IRREVERSIBLE
```

---

## 5. Estados de un Archivo

| Estado | `activo` | En MinIO | Visible | Recuperable |
|--------|----------|----------|---------|-------------|
| 🟢 Activo | `1` | ✅ Sí | ✅ Sí | N/A |
| 🟡 Soft Deleted | `0` | ✅ Sí | ❌ No | ✅ Sí |
| 🔴 Hard Deleted | `0` | ❌ No | ❌ No | ❌ No |

---

## 6. Consideraciones de Implementación

### Base de Datos

```sql
-- Campo para marcar archivos inactivos
ALTER TABLE archivos_plantillas ADD COLUMN activo BIT DEFAULT 1;

-- Índice para filtros de usuario
CREATE INDEX idx_activo ON archivos_plantillas(activo);
```

### API Endpoint

```python
@router.delete("/api/plantillas/archivos/{archivo_id}")
async def eliminar_archivo(
    archivo_id: int,
    eliminar_fisicamente: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Elimina un archivo de plantilla.
    
    - Por defecto: Soft delete (marca como inactivo)
    - Con eliminar_fisicamente=true: Hard delete (elimina de storage)
    """
    archivo = get_archivo(archivo_id)
    
    # Validar permisos
    if archivo.usuario_id != current_user.id:
        raise PermissionDenied()
    
    # Marcar como inactivo
    archivo.activo = 0
    guardar_en_bd(archivo)
    
    # Si es hard delete, eliminar del storage
    if eliminar_fisicamente:
        eliminar_de_minio(archivo.ruta_storage)
        return {"mensaje": "Archivo eliminado de forma física"}
    
    return {"mensaje": "Archivo marcado como inactivo"}
```

### Listados de Usuario

```python
# SIEMPRE filtrar archivos inactivos en listados
SELECT * FROM archivos_plantillas 
WHERE usuario_id = ? AND activo = 1
```

---

## 7. Preguntas Frecuentes

**P: ¿Puedo recuperar un archivo que hice soft delete?**
- R: Sí, un administrador puede cambiar `activo = 1` en la BD para reactivarlo.

**P: ¿Qué pasa si elimino físicamente pero la BD se corrompe?**
- R: El archivo ya no está en MinIO, así que no puede recuperarse del storage.

**P: ¿Cuál debería usar por defecto?**
- R: Soft delete. Es más seguro. Solo usa hard delete cuando realmente necesites liberar espacio.

**P: ¿Se cobra espacio en MinIO por archivos soft deleted?**
- R: Sí, los archivos soft deleted ocupan espacio. Por eso existe la opción hard delete.

**P: ¿Hay un proceso de limpieza automático?**
- R: No por defecto. Puedes configurar un job que elimine archivos después de X días de inactividad.

---

## 8. Migraciones SQL

Si necesitas implementar esto en una BD existente:

```sql
-- Paso 1: Agregar columna activo
ALTER TABLE archivos_plantillas ADD COLUMN activo BIT DEFAULT 1;

-- Paso 2: Marcar como activos todos los existentes
UPDATE archivos_plantillas SET activo = 1 WHERE activo IS NULL;

-- Paso 3: Crear índice para mejorar filtros
CREATE INDEX idx_plantillas_activo ON archivos_plantillas(activo);
CREATE INDEX idx_plantillas_usuario_activo ON archivos_plantillas(usuario_id, activo);

-- Paso 4: (Opcional) Crear tabla de auditoría para registrar eliminaciones
CREATE TABLE archivos_eliminaciones (
    id INT PRIMARY KEY IDENTITY,
    archivo_id INT NOT NULL,
    usuario_id INT NOT NULL,
    fecha_eliminacion DATETIME DEFAULT GETDATE(),
    tipo_eliminacion VARCHAR(10) DEFAULT 'soft', -- 'soft' o 'hard'
    FOREIGN KEY (archivo_id) REFERENCES archivos_plantillas(id)
);
```

---

## 9. Cambio de Comportamiento por Defecto

Si en el futuro necesitas cambiar el comportamiento por defecto:

### Cambiar a Hard Delete por Defecto (NO RECOMENDADO)

```python
# En config.py
ARCHIVO_DELETE_MODE = os.getenv("ARCHIVO_DELETE_MODE", "soft")  # 'soft' o 'hard'

# En el endpoint
if eliminar_fisicamente is None:
    # Usar valor por defecto de config
    eliminar_fisicamente = (ARCHIVO_DELETE_MODE == "hard")
```

### ⚠️ Advertencia

Cambiar a hard delete por defecto es **MÁS PELIGROSO** porque:
- No hay segunda oportunidad ante errores
- Usuarios pueden perder datos sin intención
- Viola principios de auditoría
- No se recomienda en ningún caso

---

## 10. 🛠️ Recomendaciones Prácticas

### Estrategia Recomendada: Job de Limpieza Automática

La mejor práctica es **mantener soft delete como opción por defecto**, pero implementar un **job de limpieza programado** que elimine físicamente archivos que cumplan criterios específicos.

#### ✅ Opción 1: Job de Limpieza (RECOMENDADO)

Mantén soft delete, pero elimina físicamente archivos inactivos después de un tiempo:

**Criterios de eliminación física automática:**

```sql
-- Archivos inactivos más de 90 días atrás
DELETE FROM archivos_plantillas
WHERE activo = 0 
  AND fecha_eliminacion < NOW() - INTERVAL '90 days'
```

**Beneficios:**

- ✅ Mantiene **auditoría reciente** (90 días de reversibilidad)
- ✅ Evita que **MinIO crezca sin control**
- ✅ Balance entre recuperación y liberación de espacio
- ✅ Archivos antiguos se eliminan automáticamente
- ✅ Usuarios pueden recuperar errores recientes (90 días)

**Implementación en Python (Celery/APScheduler):**

```python
# tasks.py o similar
from celery import shared_task
from datetime import timedelta
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@shared_task(name='limpiar_archivos_antiguos')
def limpiar_archivos_inactivos(dias=90):
    """
    Elimina físicamente archivos inactivos más antiguos que X días.
    
    Args:
        dias: Número de días desde la eliminación lógica (default: 90)
    """
    from app.models import ArchivoPlantilla
    from app.storage import eliminar_de_minio
    
    fecha_limite = timezone.now() - timedelta(days=dias)
    
    # Buscar archivos candidatos para eliminación física
    archivos_a_eliminar = ArchivoPlantilla.objects.filter(
        activo=0,
        fecha_eliminacion__lt=fecha_limite,
        ruta_storage__isnull=False
    )
    
    contador = 0
    for archivo in archivos_a_eliminar:
        try:
            # Eliminar del storage
            eliminar_de_minio(archivo.ruta_storage)
            
            # Marcar como permanentemente eliminado
            archivo.eliminado_fisicamente = True
            archivo.save(update_fields=['eliminado_fisicamente'])
            
            contador += 1
            logger.info(f"✅ Archivo {archivo.id} eliminado físicamente de MinIO")
            
        except Exception as e:
            logger.error(f"❌ Error eliminando archivo {archivo.id}: {str(e)}")
            continue
    
    logger.info(f"🧹 Limpieza completada: {contador} archivos eliminados")
    return {"eliminados": contador}
```

**Configuración en celery beat (celerybeat-schedule):**

```python
# config.py o settings.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'limpiar-archivos-inactivos': {
        'task': 'limpiar_archivos_antiguos',
        'schedule': crontab(hour=2, minute=0),  # Ejecutar a las 2 AM diariamente
        'kwargs': {'dias': 90}  # Mantener 90 días de auditoría
    },
}
```

**O usando APScheduler:**

```python
# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from tasks import limpiar_archivos_inactivos

def iniciar_scheduler():
    scheduler = BackgroundScheduler()
    
    # Ejecutar limpieza diariamente a las 2:00 AM
    scheduler.add_job(
        func=limpiar_archivos_inactivos.delay,
        trigger="cron",
        hour=2,
        minute=0,
        id='cleanup_old_files',
        name='Limpiar archivos inactivos de MinIO',
        replace_existing=True
    )
    
    scheduler.start()
    return scheduler
```

#### Schema de BD necesario:

```sql
-- Agregar campos para auditoría de eliminación
ALTER TABLE archivos_plantillas ADD COLUMN 
    fecha_eliminacion DATETIME NULL;  -- Cuándo se hizo soft delete

ALTER TABLE archivos_plantillas ADD COLUMN 
    eliminado_fisicamente BIT DEFAULT 0;  -- Fue hard deleted

-- Índices para buscar candidatos a limpieza
CREATE INDEX idx_limpieza 
    ON archivos_plantillas(activo, fecha_eliminacion);
```

#### ❌ Opción 2: No Hacer Limpieza (NO RECOMENDADO)

Si no implementas limpieza automática:

- ❌ MinIO crecerá indefinidamente
- ❌ Coste de almacenamiento aumentará sin control
- ❌ Necesitarás limpieza manual periódica (humana, propensa a errores)
- ❌ Difícil de mantener en producción

**No se recomienda esta opción.**

---

## 11. Plan de Implementación

### Fase 1: Habilitar Soft Delete (Inmediato)

```sql
-- Agregar soporte para soft delete
ALTER TABLE archivos_plantillas ADD COLUMN 
    activo BIT DEFAULT 1;

ALTER TABLE archivos_plantillas ADD COLUMN 
    fecha_eliminacion DATETIME NULL;

CREATE INDEX idx_activo ON archivos_plantillas(activo);
```

### Fase 2: Implementar API (Semana 1)

- Endpoint DELETE con parámetro `eliminar_fisicamente`
- Filtros en listados para `WHERE activo = 1`
- Logs de eliminación

### Fase 3: Job de Limpieza (Semana 2)

- Agregar task a Celery/APScheduler
- Configurar cron para ejecutarse a las 2 AM
- Monitoreo de logs de limpieza

### Fase 4: Documentación (Immediate)

- ✅ Este documento (completado)
- Actualizar ENDPOINTS.md con parámetro `eliminar_fisicamente`
- Guía para administradores sobre recuperación manual

---

## 12. Monitoreo y Alertas

**Dashboard de estadísticas de storage:**

```sql
-- Ver archivos inactivos esperando limpieza
SELECT 
    COUNT(*) as archivos_inactivos,
    SUM(tamaño_bytes) / 1024 / 1024 / 1024 as espacio_gb,
    MIN(fecha_eliminacion) as archivo_más_antiguo
FROM archivos_plantillas
WHERE activo = 0
    AND fecha_eliminacion < NOW() - INTERVAL '90 days';

-- Ver cronograma de limpieza futuro
SELECT 
    COUNT(*) as proximos_a_eliminar,
    SUM(tamaño_bytes) / 1024 / 1024 / 1024 as espacio_a_liberar,
    MAX(fecha_eliminacion) + INTERVAL '90 days' as fecha_eliminación_estimada
FROM archivos_plantillas
WHERE activo = 0
    AND fecha_eliminacion >= NOW() - INTERVAL '90 days';
```

**Alertas sugeridas:**

- ⚠️ Si MinIO > 80% de capacidad
- ⚠️ Si hay > 1000 archivos inactivos
- ⚠️ Si la limpieza falla (revisar logs)

---

## 13. Relación con Otros Documentos

- Ver [ENDPOINTS.md](ENDPOINTS.md) para detalles de todos los endpoints de plantillas
- Ver [INTEGRACION_SAP.md](INTEGRACION_SAP.md) para integración de archivos SAP
- Ver [SEGURIDAD.md](SEGURIDAD.md) para políticas de retención de datos
- Ver [CELERY_IMPLEMENTATION.md](CELERY_IMPLEMENTATION.md) para configurar tasks automáticas
