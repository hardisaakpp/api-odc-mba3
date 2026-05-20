# MBA3 Consultas - Imagen para API y Celery
# Usa la misma imagen para api y celery-worker; el comando se sobrescribe en docker-compose.
FROM python:3.11-slim

WORKDIR /app

# ODBC Driver 18 para SQL Server (alineado con SQL_SERVER_DRIVER en producción)
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc-dev \
    curl \
    gnupg \
    apt-transport-https \
    ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Solo dependencias de runtime (sin ruff/pyright/pre-commit; el lint vive en desarrollo y en CI).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Variables de entorno se inyectan via docker-compose (env_file / environment)
ENV PYTHONPATH=/app
EXPOSE 8000

# Por defecto arranca la API; celery-worker usa otro CMD en docker-compose
CMD ["uvicorn", "src.api_server:app", "--host", "0.0.0.0", "--port", "8000"]
