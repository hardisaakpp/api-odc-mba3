# Actualizar Backend en Producción (Linux)

Guía para aplicar cambios del backend en el servidor de producción (Linux). El servidor usa **systemd** para ejecutar la API.

---

## 📍 Entorno de Producción

- **Ruta del proyecto:** `/opt/odc-sap/`
- **Servicio systemd:** `odc-sap-api` (usar siempre este nombre en `systemctl status/restart`, no `odc-sap`)
- **Puerto API:** 8000

La aplicación resuelve el fichero de entorno según `src/config.py`: en servidor se recomienda **`ENV_FILE=/opt/odc-sap/.env`** y **`ENVIRONMENT=production`** en la unidad systemd (ver [CONFIGURACION.md](CONFIGURACION.md)). Sin `ENV_FILE`, se usaría `.env.production` en la raíz del proyecto.

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

# 5. Reiniciar el servicio de la API para aplicar los cambios
sudo systemctl restart odc-sap-api
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

Si después de una migración de base de datos debes reiniciar la API, usa los pasos de la sección **Actualizar Cambios** (al menos `sudo systemctl restart odc-sap-api`).
