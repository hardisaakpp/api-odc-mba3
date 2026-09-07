# Actualizar Backend en Producción (Linux)

Guía para aplicar cambios del backend en el servidor de producción (Linux).

> **Despliegue Docker (recomendado en srv-mabuiosapi):** un comando `./deploy-prod.sh` desde `/opt/odc-sap` (pull + build + health). Ver **[DEPLOY_DOCKER_PRODUCCION.md](DEPLOY_DOCKER_PRODUCCION.md)** y **[deploy/README.md](../deploy/README.md)**.
>
> Esta página describe el flujo **systemd + venv** (legado), útil si aún no migraste o para rollback.

---

## 📍 Entorno de Producción

- **Ruta del proyecto:** `/opt/odc-sap/`
- **Puerto API:** 8000
- **Servicios systemd (producción):** tres unidades — `odc-sap-api`, `celery-worker`, `celery-beat` (detalle y nombres prohibidos en la tabla siguiente).

La aplicación resuelve el fichero de entorno según `src/config.py`: en servidor se recomienda **`ENV_FILE=/opt/odc-sap/.env`** y **`ENVIRONMENT=production`** en la unidad systemd (ver [CONFIGURACION.md](CONFIGURACION.md)). Sin `ENV_FILE`, se usaría `.env` en la raíz del proyecto (el archivo de desarrollo local; test/producción se administran fuera de este repo).

### Nombres exactos de las unidades systemd (no inventar otros)

En el servidor de producción donde vive el backend (p. ej. `srv-mabuiosapi` con `/opt/odc-sap`), las unidades **reales** suelen ser:

| Rol | Unidad (con o sin `.service`) | Descripción típica en `systemctl` |
|-----|-------------------------------|-----------------------------------|
| API FastAPI | **`odc-sap-api`** | ODC-SAP API (FastAPI) |
| Cola de tareas | **`celery-worker`** | Celery Worker - odc-sap |
| Programador | **`celery-beat`** | Celery Beat - odc-sap |

**No existen** unidades con nombres genéricos como `mba3-api` o `celery`. Si `systemctl restart …` devuelve *Unit not found*, el nombre es incorrecto.

**Comprobar** qué unidades hay registradas en **tu** máquina:

```bash
systemctl list-units --type=service --all --no-legend | grep -iE 'celery|odc'
systemctl list-unit-files | grep -iE 'celery|odc'
```

Salida esperada (ejemplo): `odc-sap-api.service`, `celery-worker.service`, `celery-beat.service` — todas *enabled* y *active*.

**Tras cambiar el `.env`** (MinIO/S3, `REDIS_URL`, claves, etc.), hay que reiniciar **API y Celery** para que vuelvan a leer variables: como mínimo `odc-sap-api` y `celery-worker`; incluye también `celery-beat` si quieres un criterio único “reinicio completo”. Los mismos comandos están en la subsección **Reinicio controlado del flujo completo** (más abajo).

---

## 🔄 Actualizar Cambios (después de modificar el backend)

Conectar por SSH al servidor Linux y ejecutar, en este orden:

```bash
# 1. Ir al directorio del proyecto
cd /opt/odc-sap/

# 2. Activar el entorno virtual
source venv/bin/activate

# 3. Traer los últimos cambios del repositorio
git pull origin main

# 4. Instalar o actualizar dependencias (por si cambió requirements.txt)
pip install -r requirements.txt

# 5. Reiniciar servicios
#    Solo código / dependencias (sin cambios en .env leídos por workers):
sudo systemctl restart odc-sap-api
#    Si además cambió .env (FILE_STORAGE_*, REDIS_URL, etc.) o quieres alinear workers:
# sudo systemctl restart odc-sap-api celery-worker celery-beat
```

**Verificación rápida:**

```bash
# Estado del servicio
sudo systemctl status odc-sap-api

# Health check (desde el servidor o desde otra máquina)
curl http://localhost:8000/health
```

---

## 📡 Monitoreo operativo (equivalente a DEV)

En desarrollo se suele monitorear 3 procesos: API (`run-dev.ps1`), `worker` y `beat`.
En producción, el equivalente corre como servicios `systemd`:

- **API:** `odc-sap-api.service`
- **Celery Worker:** `celery-worker.service`
- **Celery Beat:** `celery-beat.service`

### Ver estado de los 3 servicios

```bash
sudo systemctl status odc-sap-api.service celery-worker.service celery-beat.service
```

### Seguir logs en vivo (abrir 3 terminales)

```bash
# Terminal 1: API
sudo journalctl -u odc-sap-api.service -f
```

```bash
# Terminal 2: Worker
sudo journalctl -u celery-worker.service -f
```

```bash
# Terminal 3: Beat
sudo journalctl -u celery-beat.service -f
```

### Ver últimos logs (snapshot)

```bash
sudo journalctl -u odc-sap-api.service -n 120 --no-pager
sudo journalctl -u celery-worker.service -n 120 --no-pager
sudo journalctl -u celery-beat.service -n 120 --no-pager
```

### Ver solo errores recientes

```bash
sudo journalctl -u odc-sap-api.service -p err --since "2 hours ago"
sudo journalctl -u celery-worker.service -p err --since "2 hours ago"
sudo journalctl -u celery-beat.service -p err --since "2 hours ago"
```

### Reinicio controlado del flujo completo

```bash
sudo systemctl restart odc-sap-api.service
sudo systemctl restart celery-worker.service
sudo systemctl restart celery-beat.service
```

---

## 🖥️ Ejecutar la API manualmente (solo para pruebas/debug)

Si necesitas levantar la API a mano (por ejemplo para ver logs en consola o depurar):

```bash
cd /opt/odc-sap/
source venv/bin/activate
uvicorn src.api_server:app --host 0.0.0.0 --port 8000
```

**Nota:** En producción normal la API se ejecuta con systemd; no uses `--reload` en el servidor.

---

## 📋 Relación con otros despliegues

| Acción | Documento |
|--------|-----------|
| **Actualizar código del backend** (git pull + restart) | Este documento |
| **Desplegar en servidor de pruebas (DESA)** | [DEPLOY_TEST.md](DEPLOY_TEST.md) |
| **Desplegar migraciones de BD** | [DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md) y [scripts/PRODUCTION_DEPLOYMENT_CHECKLIST.md](../scripts/PRODUCTION_DEPLOYMENT_CHECKLIST.md) |
| **Reiniciar API/Celery tras migraciones** | Incluye los mismos comandos de este documento |

Si después de una migración de base de datos debes reiniciar procesos, usa la sección **Actualizar Cambios**; como mínimo `sudo systemctl restart odc-sap-api`. Si los workers Celery deben ver el mismo estado de entorno o de código, reinicia también `celery-worker` (y opcionalmente `celery-beat`), igual que en **Reinicio controlado del flujo completo** al final de este documento.
