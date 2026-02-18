# Actualizar Backend en Producción (Linux)

Guía para aplicar cambios del backend en el servidor de producción (Linux). El servidor usa **systemd** para ejecutar la API.

---

## 📍 Entorno de Producción

- **Ruta del proyecto:** `/opt/odc-sap/`
- **Servicio systemd:** `odc-sap-api`
- **Puerto API:** 8000

La aplicación carga las variables de entorno desde `/opt/odc-sap/.env` (ver `src/api_server.py`).

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
| **Desplegar migraciones de BD** | [DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md) y [scripts/PRODUCTION_DEPLOYMENT_CHECKLIST.md](../scripts/PRODUCTION_DEPLOYMENT_CHECKLIST.md) |
| **Reiniciar API/Celery tras migraciones** | Incluye los mismos comandos de este documento |

Si después de una migración de base de datos debes reiniciar la API, usa los pasos de la sección **Actualizar Cambios** (al menos `sudo systemctl restart odc-sap-api`).
