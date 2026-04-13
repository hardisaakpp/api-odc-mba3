# Desplegar backend en servidor de pruebas (DESA)

Guía para aplicar y verificar el backend en el **ambiente de test**. El comportamiento de variables de entorno es el mismo que en otros ambientes: con `ENVIRONMENT=test` la aplicación **exige** el archivo **`.env.test`** en la raíz del proyecto (ver [CONFIGURACION.md](CONFIGURACION.md)).

---

## Servidor de test

| Dato | Valor |
|------|--------|
| **IP** | `210.17.1.53` |
| **Nombre de host** | `DESA-MABUIOSAPP` |
| **Usuario SSH / acceso** | `admindesa` |

### Seguridad: credenciales

- **No incluyas contraseñas ni secretos en archivos del repositorio** (ni en este documento).
- Guarda la contraseña de `admindesa` en un **gestor de secretos** corporativo o solicítala al administrador.
- Las cadenas de conexión a SQL Server, SAP, JWT, etc. van en **`.env.test`** en el servidor (ese archivo **no** debe committearse).

---

## Conectar al servidor

Desde tu PC (PowerShell, terminal o cliente SSH):

```bash
ssh admindesa@210.17.1.53
```

Si tu política usa el nombre de host:

```bash
ssh admindesa@DESA-MABUIOSAPP
```

La primera vez confirma la huella del host si el cliente la muestra.

---

## Qué debe existir en el servidor (una vez)

1. **Clon del repositorio** en una ruta acordada (por ejemplo bajo `D:\`, `C:\Apps\` o, si fuera Linux, `/opt/odc-sap/`). **Confirma la ruta real** al conectarte.
2. **Python 3.9+** y entorno virtual (`venv`) en la carpeta del proyecto.
3. **Archivo `.env.test`** en la raíz del repo, con `ENVIRONMENT=test` y el resto de variables según [CONFIGURACION.md](CONFIGURACION.md) (SQL de **desarrollo/pruebas**, Redis si usas Celery, etc.).
4. **Redis** si utilizas workers Celery (misma idea que [CELERY_QUICKSTART.md](CELERY_QUICKSTART.md)).
5. **ODBC Driver for SQL Server** instalado en la máquina donde corre Python (en Windows: instalador Microsoft; en Linux: paquete `msodbcsql17` o el que use el proyecto).

---

## Despliegue rutinario (actualizar código)

Tras conectar por SSH, usa la sección que corresponda al **sistema operativo** del servidor.

### Opción A — Windows Server (PowerShell)

Ajusta `RUTA_PROYECTO` a la carpeta real del repo en DESA.

```powershell
cd RUTA_PROYECTO
.\venv\Scripts\Activate.ps1
$env:ENVIRONMENT = "test"

git pull origin main

pip install -r requirements.txt
```

**Migraciones de base de datos** (si hay scripts nuevos; siempre validar antes en test):

```powershell
python scripts/migration_runner.py --dry-run --verbose
python scripts/migration_runner.py
```

**Reinicio del servicio de la API:** depende de cómo esté instalado en DESA (NSSM, tarea programada, `sc`, etc.). Reinicia el servicio o proceso que ejecute `uvicorn` y apunte a este proyecto con `ENVIRONMENT=test`. Si aún no hay servicio y solo pruebas en consola:

```powershell
python -m uvicorn src.api_server:app --host 0.0.0.0 --port 8000
```

No uses `--reload` en un servidor compartido.

**Celery** (si aplica en test): reinicia también el worker y, si existe, Celery Beat con los mismos comandos que en [README.md](../README.md) y [CELERY_QUICKSTART.md](CELERY_QUICKSTART.md), con el entorno activado y `ENVIRONMENT=test`.

### Opción B — Linux (bash)

Si el host de test es Linux y el layout coincide con producción:

```bash
cd /ruta/del/proyecto
source venv/bin/activate
export ENVIRONMENT=test

git pull origin main
pip install -r requirements.txt

python scripts/migration_runner.py --dry-run --verbose
python scripts/migration_runner.py

sudo systemctl restart NOMBRE_SERVICIO_API_TEST
```

Sustituye `NOMBRE_SERVICIO_API_TEST` por el nombre real del unit de systemd en DESA (puede diferir de `odc-sap-api` de producción).

---

## Verificación

En el propio servidor:

```bash
curl http://localhost:8000/health
```

Desde otra máquina (si el firewall y la red lo permiten), usa la IP `210.17.1.53` y el puerto expuesto (habitualmente **8000**).

Si la API va detrás de un reverse proxy o otro puerto, usa la URL que defina el equipo.

---

## Relación con otros documentos

| Acción | Documento |
|--------|------------|
| Variables por ambiente (`.env.test`) | [CONFIGURACION.md](CONFIGURACION.md) |
| Actualizar backend en **producción** (Linux) | [DEPLOY_PRODUCCION.md](DEPLOY_PRODUCCION.md) |
| Migraciones de BD | [DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md) |
| Checklist detallado de migraciones | [scripts/PRODUCTION_DEPLOYMENT_CHECKLIST.md](../scripts/PRODUCTION_DEPLOYMENT_CHECKLIST.md) (adaptar al SQL de **test**) |
| Celery / Redis | [CELERY_QUICKSTART.md](CELERY_QUICKSTART.md) |

---

## Resumen rápido

1. `ssh admindesa@210.17.1.53`
2. Ir al directorio del proyecto, activar `venv`, `ENVIRONMENT=test`
3. `git pull` → `pip install -r requirements.txt`
4. Migraciones si corresponde (`migration_runner.py`, primero `--dry-run`)
5. Reiniciar API (y Celery si aplica)
6. Comprobar `GET /health`
