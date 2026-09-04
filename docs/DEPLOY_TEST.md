# Desplegar en servidor de pruebas (DESA)

Guía para **actualizar backend** (este repo, `mba3-consultas`) y **referencia al frontend** que consume la API en el ambiente de test.

---

## Resumen ejecutivo (checklist)

1. SSH al servidor de test (usuario y host acordados con infraestructura).
2. **Backend:** `cd` al directorio del repo → activar `venv` → `git pull` de la rama de test → `pip install -r requirements.txt`.
3. **Migraciones SQL** solo si el release lo requiere (ver [DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md)).
4. **Reiniciar** la unidad systemd de la API de test (en DESA Linux suele ser `odc-sap-test`, no `odc-sap-api`).
5. **Infra Docker** (Redis/MinIO del repo): solo si toca actualizar o recrear contenedores; usar `docker compose up -d`.
6. **Celery** (worker/beat): reiniciar si aplica y si cambió código o dependencias de tareas.
7. **Frontend:** despliegue en **otro repositorio** y script propio del servidor (ver sección más abajo).
8. Verificar: `systemctl status`, logs, `GET /health` (puerto real del servicio).

---

## Servidor de test

| Dato | Valor habitual |
|------|----------------|
| **IP** | `210.17.1.53` |
| **Nombre de host** | `DESA-MABUIOSAPP` (en Linux el hostname puede verse en minúsculas, p. ej. `desa-mabuiosapp`) |
| **Usuario SSH** | `admindesa` |

### Seguridad: credenciales

- **No** incluyas contraseñas ni secretos en el repositorio.
- Cadenas de conexión, JWT, MinIO, etc. viven en archivos de entorno en el servidor (no commiteados). Ver [CONFIGURACION.md](CONFIGURACION.md).

---

## Conectar al servidor

```bash
ssh admindesa@210.17.1.53
# o, según DNS interno:
ssh admindesa@DESA-MABUIOSAPP
```

---

## Layout real en DESA (Linux) — backend

En el servidor de pruebas el backend suele estar desplegado así:

| Elemento | Valor típico |
|----------|----------------|
| **Ruta del repo** | `/opt/odc-sap/` |
| **Entorno virtual** | `/opt/odc-sap/venv/` |
| **Rama Git para test** | `test` (confirmar con `git branch` en el servidor) |
| **Servicio API (systemd)** | `odc-sap-test` (el nombre `odc-sap-api` suele ser de **producción** u otro host; si `restart` falla con “unit not found”, ejecuta `systemctl list-units --type=service --no-legend` y busca unidades cuyo nombre contenga `odc`) |

La API **no** tiene por qué ir dentro de Docker en este host: en muchos despliegos solo **Redis** y **MinIO** están en `docker-compose.yml` del repo; **uvicorn** corre vía **systemd**.

---

## Variables de entorno en el servidor

La aplicación elige el archivo `.env` según `ENV_FILE` (o, si no está definida, `.env` en la raíz del proyecto). Resumen en [CONFIGURACION.md](CONFIGURACION.md):

- En este servidor la unidad systemd define `ENV_FILE` apuntando al archivo real administrado por el equipo de Azure DevOps (ej. `/opt/odc-sap/.env`) — no depende de un `.env` dentro del checkout del repo.

**Qué editar antes de reiniciar:** no asumas; revisa la unidad:

```bash
systemctl cat odc-sap-test
```

Busca `Environment=`, `EnvironmentFile=` y el `ExecStart`. Ahí verás qué archivo carga el proceso y con qué `ENVIRONMENT`.

---

## Despliegue rutinario del backend (Linux)

Ejecutar como usuario con permiso `sudo` para `systemctl` (p. ej. `admindesa`):

```bash
cd /opt/odc-sap
source venv/bin/activate

# Rama de integración en test (ajustar si el equipo usa otra)
git pull origin test

pip install -r requirements.txt
```

### Migraciones de base de datos

Solo si el cambio incluye scripts o instrucciones de BD:

```bash
python scripts/migration_runner.py --dry-run --verbose
python scripts/migration_runner.py
```

Más detalle: [DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md).

### Reinicio de la API

```bash
sudo systemctl restart odc-sap-test
sudo systemctl status odc-sap-test --no-pager
```

Logs recientes:

```bash
journalctl -u odc-sap-test -n 100 --no-pager
```

### Redis y MinIO (`docker-compose.yml` del repo)

Este compose **solo** define servicios de apoyo (Redis, MinIO), alineados con variables como `REDIS_URL` y `FILE_STORAGE_ENDPOINT` en tu `.env` de test.

- **Uso recomendado** (segundo plano, no bloquea la sesión SSH):

  ```bash
  cd /opt/odc-sap
  docker compose up -d
  ```

- Evita dejar una sesión con `docker compose up` **sin** `-d` a menos que quieras ver logs en primer plano; al cerrar con **Ctrl+C** puedes detener los contenedores.
- Tras **recrear** Redis, si hay workers Celery, conviene **reiniciar** también sus unidades systemd (si existen) para evitar conexiones colgadas.

---

## Verificación del backend

1. Puerto: el que defina `ExecStart` o el reverse proxy (no siempre es `8000` en el host).

   ```bash
   # Ejemplo si la API escucha en 8000 en localhost:
   curl -sS http://127.0.0.1:8000/health
   ```

2. Confirmar commit desplegado:

   ```bash
   cd /opt/odc-sap && git log -1 --oneline
   ```

---

## Frontend (no es este repositorio)

La UI que llama a esta API suele vivir en **otro repo** (por ejemplo `scnexus-front`) y desplegarse con un **script del servidor**, no con `git pull` dentro de `/opt/odc-sap`.

Patrón observado en DESA:

- Script en el home del usuario de despliegue, p. ej. `~/deploys/nexus_frontend.sh`.
- Ese script hace `git pull` de la rama acordada del frontend (p. ej. `develop`), `npm install` y levanta el proceso en background; los logs pueden estar en un archivo tipo `~/deploys/dev.log`.

**Importante:** rutas y nombres del script pueden variar; confirma con el equipo o revisa el contenido del `.sh` en el servidor.

---

## Despliegue rutinario (Windows Server)

Si el backend de test corriera en Windows (menos frecuente en el layout actual):

```powershell
cd RUTA_PROYECTO
.\venv\Scripts\Activate.ps1
$env:ENVIRONMENT = "test"

git pull origin test

pip install -r requirements.txt
```

Migraciones y reinicio del servicio (NSSM, tarea programada, etc.) según cómo esté instalado. No uses `--reload` en servidor compartido.

---

## Relación con otros documentos

| Acción | Documento |
|--------|------------|
| Variables por ambiente / `ENV_FILE` | [CONFIGURACION.md](CONFIGURACION.md) |
| Producción Linux | [DEPLOY_PRODUCCION.md](DEPLOY_PRODUCCION.md) |
| Migraciones | [DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md) |
| Celery / Redis | [CELERY_QUICKSTART.md](CELERY_QUICKSTART.md) |

---

## Errores frecuentes

| Síntoma | Qué revisar |
|---------|-------------|
| `Unit odc-sap-api.service not found` | En test suele ser **`odc-sap-test`**. Lista servicios y busca `odc`: `systemctl list-units --type=service --no-legend`. |
| API arranca pero no lee tus cambios en `.env` | `systemctl cat odc-sap-test` — confirma a qué archivo apunta **`ENV_FILE`**. |
| Frontend sin cambios | El front se actualiza con el **script/repo del frontend**, no solo con pull del backend. |
| Celery falla tras recrear Redis | Reiniciar worker (y beat si aplica) tras `docker compose up`. |
