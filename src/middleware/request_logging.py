"""
Middleware para logging de requests HTTP.

Implementa buenas prácticas de logging técnico:
- Fecha/hora del request
- Método y endpoint
- Código de respuesta
- Tiempo de ejecución (ms)
- IP de origen (cuando disponible)

Referencia: Guía de Buenas Prácticas - Sección 5. Logs obligatorios
"""

import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware para logging de tiempo de respuesta y métricas de requests.
    
    Registra información técnica de cada request sin modificar la lógica
    de los endpoints existentes.
    
    Logs generados:
    - INFO: Request completado exitosamente (2xx, 3xx)
    - WARNING: Request con error de cliente (4xx)
    - ERROR: Request con error de servidor (5xx)
    """
    
    # Endpoints a excluir del logging (health checks, assets estáticos)
    EXCLUDED_PATHS = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }
    
    # Umbral en ms para advertir sobre requests lentos
    SLOW_REQUEST_THRESHOLD_MS = 5000  # 5 segundos
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Procesa el request y registra métricas de tiempo.
        
        Args:
            request: Request HTTP entrante
            call_next: Función para continuar la cadena de middleware
            
        Returns:
            Response HTTP
        """
        # Excluir endpoints de health check y documentación
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)
        
        # Capturar información del request
        start_time = time.perf_counter()
        method = request.method
        path = request.url.path
        query_string = str(request.query_params) if request.query_params else ""
        
        # Obtener IP de origen (considera proxies)
        client_ip = self._get_client_ip(request)
        
        # Ejecutar el request
        response = None
        error_detail = None
        try:
            response = await call_next(request)
        except Exception as e:
            error_detail = str(e)
            raise
        finally:
            # Calcular tiempo de ejecución
            duration_ms = (time.perf_counter() - start_time) * 1000
            status_code = response.status_code if response else 500
            
            # Construir mensaje de log
            log_data = {
                "method": method,
                "path": path,
                "query": query_string[:100] if query_string else None,  # Truncar queries largos
                "status": status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": client_ip,
            }
            
            # Agregar detalle de error si existe
            if error_detail:
                log_data["error"] = error_detail[:200]  # Truncar errores largos
            
            # Seleccionar nivel de log según código de estado
            log_message = self._format_log_message(log_data)
            
            if status_code >= 500:
                logger.error(f"❌ {log_message}")
            elif status_code >= 400:
                logger.warning(f"⚠️ {log_message}")
            elif duration_ms > self.SLOW_REQUEST_THRESHOLD_MS:
                logger.warning(f"🐢 SLOW REQUEST: {log_message}")
            else:
                logger.info(f"📊 {log_message}")
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Obtiene la IP del cliente, considerando proxies y load balancers.
        
        Orden de prioridad:
        1. X-Forwarded-For (primer IP)
        2. X-Real-IP
        3. request.client.host
        
        Args:
            request: Request HTTP
            
        Returns:
            IP del cliente como string
        """
        # X-Forwarded-For puede contener múltiples IPs separadas por coma
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Tomar la primera IP (cliente original)
            return forwarded_for.split(",")[0].strip()
        
        # X-Real-IP (usado por algunos proxies)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fallback a la IP directa
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _format_log_message(self, data: dict) -> str:
        """
        Formatea los datos del log en un mensaje legible.
        
        Args:
            data: Diccionario con datos del request
            
        Returns:
            String formateado para logging
        """
        parts = [
            f"{data['method']} {data['path']}",
            f"[{data['status']}]",
            f"{data['duration_ms']}ms",
        ]
        
        if data.get("client_ip") and data["client_ip"] != "unknown":
            parts.append(f"IP:{data['client_ip']}")
        
        if data.get("query"):
            parts.append(f"query:{data['query']}")
        
        if data.get("error"):
            parts.append(f"error:{data['error']}")
        
        return " - ".join(parts)


def setup_request_logging(app):
    """
    Configura el middleware de logging de requests en la aplicación FastAPI.
    
    Uso en api_server.py:
        from src.middleware.request_logging import setup_request_logging
        setup_request_logging(app)
    
    Args:
        app: Instancia de FastAPI
    """
    app.add_middleware(RequestLoggingMiddleware)
    logger.info("✅ Middleware de logging de requests configurado")
