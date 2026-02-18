# ✅ Checklist de Despliegue a Producción

Guía paso a paso para desplegar migraciones de forma segura en producción.

---

## 🔴 ANTES DE EMPEZAR

### Requisitos Previos

- [ ] Acceso a servidor de producción
- [ ] Credenciales de BD con permisos DDL (ALTER, CREATE)
- [ ] Variables de entorno configuradas (`.env`)
- [ ] PyYAML instalado (`pip install PyYAML>=6.0.1`)
- [ ] Coordinación con equipo (si aplica)
- [ ] Ventana de mantenimiento agendada (si aplica)

---

## 📋 FASE 1: Preparación

### 1.1 Validar Sistema Localmente

```bash
# Terminal local (desarrollo)
cd mba3-consultas

# Validar que el sistema funciona
python scripts/test_migration_system.py
```

**Resultado esperado:** ✅ Todas las validaciones pasaron

---

### 1.2 Ver Migraciones Pendientes

```bash
# Ver qué migraciones hay pendientes
python scripts/migration_runner.py --status
```

**Anotar:**
- Número de migraciones pendientes: _________
- Categorías involucradas: _________________
- ¿Hay migraciones manuales? ☐ Sí  ☐ No
- ¿Hay warnings críticos? ☐ Sí  ☐ No

---

### 1.3 Dry-Run Local

```bash
# Validar sin ejecutar
python scripts/migration_runner.py --dry-run --verbose
```

**Resultado esperado:** ✅ Todas las migraciones son válidas

---

### 1.4 Revisar Migraciones Manualmente

**Migraciones críticas a revisar:**

- [ ] Migraciones de datos (categoría `data`)
- [ ] Cambios de esquema grandes (categoría `alter`)
- [ ] Renumeraciones de estados
- [ ] Configuraciones SAP

**Pregunta:** ¿Alguna migración requiere downtime?

☐ **No** - Continuar normalmente  
☐ **Sí** - Coordinar ventana de mantenimiento

---

## 🔶 FASE 2: Backup (¡CRÍTICO!)

### 2.1 Backup de Base de Datos

```bash
# Conectar a servidor de producción

# Opción A: SQL Server Management Studio
# → Click derecho en BD → Tasks → Back Up

# Opción B: sqlcmd
sqlcmd -S <servidor> -d store_control -Q "BACKUP DATABASE store_control TO DISK = 'C:\Backups\store_control_pre_migracion_YYYYMMDD.bak' WITH FORMAT, COMPRESSION;"
```

**Verificar:**
- [ ] Backup completado sin errores
- [ ] Tamaño del archivo es razonable (> 0 bytes)
- [ ] Ubicación del backup: _____________________
- [ ] Fecha/hora del backup: ____________________

---

### 2.2 Guardar Estado Actual

```bash
# Desde servidor de producción
python scripts/migration_runner.py --status > estado_pre_migracion.txt
```

**Guardar archivo:** `estado_pre_migracion.txt`

---

## 🟡 FASE 3: Validación en Producción

### 3.1 Validar Sistema

```bash
# En servidor de producción
python scripts/test_migration_system.py
```

**Resultado esperado:** ✅ Todas las validaciones pasaron

**Si falla:**
- Verificar `.env` tiene las credenciales correctas
- Verificar conexión a BD: `python scripts/check_db_connection.py`

---

### 3.2 Ver Estado en Producción

```bash
python scripts/migration_runner.py --status
```

**Comparar con estado local:**
- [ ] Número de pendientes coincide
- [ ] Las versiones pendientes son las esperadas

---

### 3.3 Dry-Run en Producción

```bash
# ¡IMPORTANTE! Validar sin ejecutar
python scripts/migration_runner.py --dry-run --verbose
```

**Resultado esperado:** ✅ Todas las migraciones son válidas

**Si falla:**
- Revisar logs detallados
- Verificar que scripts existen
- Validar sintaxis SQL

---

## 🟢 FASE 4: Ejecución

### 4.1 Notificar Inicio (si aplica)

- [ ] Notificar a usuarios (si hay downtime)
- [ ] Detener servicios dependientes (si es necesario)
- [ ] Poner sistema en modo mantenimiento (si aplica)

**Hora de inicio:** ______________

---

### 4.2 Ejecutar Migraciones

```bash
# Opción A: Por categoría (recomendado para primeras veces)
python scripts/migration_runner.py --category base
python scripts/migration_runner.py --category alter
python scripts/migration_runner.py --category data
python scripts/migration_runner.py --category config

# Opción B: Todas a la vez (si estás seguro)
python scripts/migration_runner.py

# Opción C: Hasta una versión específica
python scripts/migration_runner.py --up-to 301
```

**Monitorear:**
- [ ] Logs sin errores
- [ ] Migraciones completadas exitosamente
- [ ] Tiempos de ejecución razonables

---

### 4.3 Verificar Aplicación

```bash
# Ver estado post-migración
python scripts/migration_runner.py --status

# Verificar tabla de control
sqlcmd -S <servidor> -d store_control -Q "SELECT TOP 10 * FROM schema_migrations ORDER BY applied_at DESC"
```

**Verificar:**
- [ ] Todas las migraciones esperadas están aplicadas
- [ ] Timestamps son correctos
- [ ] No hay errores en logs

---

### 4.4 Validación Manual (si aplica)

```sql
-- Verificar tablas críticas existen
SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_NAME IN ('pedido', 'pedido_estado', 'orden_compra_cabecera');

-- Verificar datos de estados
SELECT * FROM pedido_estado ORDER BY orden;

-- Verificar campos críticos existen
SELECT TABLE_NAME, COLUMN_NAME 
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'orden_compra_cabecera' 
AND COLUMN_NAME IN ('doc_entry', 'pedido_id');
```

**Resultados:**
- [ ] Todas las consultas retornan resultados esperados
- [ ] No hay valores NULL inesperados
- [ ] Estructura coincide con lo esperado

---

## 🔵 FASE 5: Post-Despliegue

### 5.1 Reiniciar Servicios

En el servidor Linux (ruta `/opt/odc-sap/`):

```bash
cd /opt/odc-sap/
source venv/bin/activate
# Si actualizaste código: git pull origin main && pip install -r requirements.txt
sudo systemctl restart odc-sap-api
# Si usas Celery: sudo systemctl restart <servicio-celery>
```

- [ ] Reiniciar API (`sudo systemctl restart odc-sap-api`)
- [ ] Reiniciar Celery (si fue detenido)
- [ ] Reiniciar servicios dependientes
- [ ] Quitar modo mantenimiento (si aplica)

**Documentación completa:** [docs/DEPLOY_PRODUCCION.md](../docs/DEPLOY_PRODUCCION.md) — actualizar backend y comandos en producción.

**Hora de reinicio:** ______________

---

### 5.2 Verificar Funcionalidad

```bash
# Probar health check
curl http://<servidor>:8000/health

# Probar endpoint crítico
curl -X GET "http://<servidor>:8000/pedidos" -H "Authorization: Bearer <token>"
```

**Verificar:**
- [ ] API responde
- [ ] No hay errores 500
- [ ] Endpoints funcionan correctamente
- [ ] Logs de aplicación sin errores

---

### 5.3 Pruebas de Humo

**Funcionalidades críticas a probar:**

- [ ] Listar pedidos
- [ ] Ver detalle de pedido
- [ ] Crear pedido desde Excel
- [ ] Consultar homologaciones
- [ ] Enviar a SAP (si aplica)

---

### 5.4 Notificar Completado

- [ ] Notificar a equipo que despliegue completó
- [ ] Notificar a usuarios que sistema está disponible
- [ ] Actualizar ticket/issue correspondiente

**Hora de finalización:** ______________

---

## 🔴 ROLLBACK (Si algo sale mal)

### Opción 1: Restaurar Backup

```bash
# DETENER SERVICIOS PRIMERO

# Desconectar usuarios
sqlcmd -S <servidor> -d master -Q "ALTER DATABASE store_control SET SINGLE_USER WITH ROLLBACK IMMEDIATE;"

# Restaurar backup
sqlcmd -S <servidor> -d master -Q "RESTORE DATABASE store_control FROM DISK = 'C:\Backups\store_control_pre_migracion_YYYYMMDD.bak' WITH REPLACE;"

# Reconectar usuarios
sqlcmd -S <servidor> -d master -Q "ALTER DATABASE store_control SET MULTI_USER;"

# REINICIAR SERVICIOS
```

---

### Opción 2: Migración de Rollback (si existe)

```bash
# Solo si hay migraciones de rollback definidas
python scripts/migration_runner.py --category rollback --include-manual
```

---

### Opción 3: Corrección Forward

```bash
# Corregir script problemático
# Actualizar manifest si es necesario
# Re-ejecutar
python scripts/migration_runner.py
```

---

## 📊 Resumen del Despliegue

**Fecha:** ______________  
**Hora inicio:** ______________  
**Hora fin:** ______________  
**Duración total:** ______________

**Migraciones aplicadas:**
- Base: _____ migraciones
- Alter: _____ migraciones
- Data: _____ migraciones
- Config: _____ migraciones
- Otras: _____ migraciones

**Total:** _____ migraciones

**Estado final:** ☐ Exitoso  ☐ Rollback  ☐ Parcial

**Observaciones:**
_____________________________________________
_____________________________________________
_____________________________________________

---

## 📝 Notas Adicionales

### Errores Comunes

**Error:** `Table already exists`  
**Solución:** Script no es idempotente, pero es OK si la tabla existe. Continuar.

**Error:** `Cannot drop column because it is referenced by constraint`  
**Solución:** Eliminar constraint primero o verificar orden de migraciones.

**Error:** `Timeout expired`  
**Solución:** Migración de datos grande, aumentar timeout o ejecutar manualmente.

**Error:** `Dependencies not met`  
**Solución:** Ejecutar migraciones en orden sin filtros de categoría.

---

### Contactos de Emergencia

**DBA:** __________________________  
**DevOps:** ________________________  
**Tech Lead:** _____________________

---

## ✅ Firma de Aprobación

**Ejecutado por:** _____________________  
**Revisado por:** ______________________  
**Fecha:** _____________________________

---

**Documentación completa:** `docs/DEPLOY_MIGRATIONS.md`  
**Sistema de validación:** `python scripts/test_migration_system.py`
