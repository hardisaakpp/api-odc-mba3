"""
Middleware para logging de requests HTTP.

Implementa buenas prácticas de logging técnico (Guía Sección 5):
- Fecha/hora del request (timestamp)
- Usuario autenticado (extraído del JWT)
- Método y endpoint
- Request body (truncado)
- Response body (truncado)
- Código de respuesta
- Tiempo de ejecución (ms)
- IP de origen
- ID de correlación (X-Correlation-ID)

Referencia: Guía de Buenas Prácticas - Sección 5. Logs obligatorios
"""

import time
import uuid
import json
import logging
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
import jwt

from src.config import JWT_SECRET, JWT_ISSUER, JWT_AUDIENCE

logger = logging.getLogger(__name__)

# Constantes de configuración
MAX_BODY_LOG_SIZE = 1000  # Máximo de caracteres para loguear del body
SENSITIVE_FIELDS = {'password', 'pwd', 'secret', 'token', 'authorization', 'api_key', 'apikey'}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware para logging completo de requests HTTP.
    
    Registra información técnica de cada request cumpliendo con las
    buenas prácticas de logging (Sección 5):
    - Fecha/hora (timestamp)
    - Usuario (del JWT)
    - Endpoint (método + path)
    - Request body (truncado, sin datos sensibles)
    - Response body (truncado)
    - Tiempo de ejecución
    - IP de origen
    - ID de correlación
    
    Logs generados:
    - INFO: Request completado exitosamente (2xx, 3xx)
    - WARNING: Request con error de cliente (4xx) o lento
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
        Procesa el request y registra métricas completas.
        
        Args:
            request: Request HTTP entrante
            call_next: Función para continuar la cadena de middleware
            
        Returns:
            Response HTTP
        """
        # Excluir endpoints de health check y documentación
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)
        
        # Generar o extraer ID de correlación
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        
        # Guardar correlation_id en el request state para uso en otros lugares
        request.state.correlation_id = correlation_id
        
        # Capturar información del request
        start_time = time.perf_counter()
        method = request.method
        path = request.url.path
        query_string = str(request.query_params) if request.query_params else ""
        
        # Obtener IP de origen (considera proxies)
        client_ip = self._get_client_ip(request)
        
        # Extraer usuario del JWT (sin validar, solo para logging)
        username = self._extract_username_from_jwt(request)
        
        # Capturar request body (solo para POST/PUT/PATCH)
        request_body = None
        if method in ("POST", "PUT", "PATCH"):
            request_body = await self._capture_request_body(request)
        
        # Ejecutar el request y capturar response
        response = None
        response_body = None
        error_detail = None
        
        try:
            response = await call_next(request)
            
            # Capturar response body
            response_body, response = await self._capture_response_body(response)
            
        except Exception as e:
            error_detail = str(e)
            raise
        finally:
            # Calcular tiempo de ejecución
            duration_ms = (time.perf_counter() - start_time) * 1000
            status_code = response.status_code if response else 500
            
            # Construir mensaje de log completo
            log_data = {
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "query": query_string[:100] if query_string else None,
                "status": status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": client_ip,
                "user": username,
                "request_body": request_body,
                "response_body": response_body,
            }
            
            # Agregar detalle de error si existe
            if error_detail:
                log_data["error"] = error_detail[:200]
            
            # Registrar el log con el nivel apropiado
            self._log_request(log_data, status_code, duration_ms)
        
        # Agregar correlation_id al response header
        if response:
            response.headers["X-Correlation-ID"] = correlation_id
        
        return response
    
    def _extract_username_from_jwt(self, request: Request) -> str:
        """
        Extrae el username del token JWT sin validar (solo para logging).
        
        Args:
            request: Request HTTP
            
        Returns:
            Username o 'anonymous' si no hay token
        """
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return "anonymous"
            
            token = auth_header.split(" ")[1]
            
            # Decodificar sin validar para extraer el username (solo logging)
            # Usamos options para no validar firma/expiración aquí
            try:
                # Intentar decodificar con validación completa primero
                data = jwt.decode(
                    token,
                    JWT_SECRET,
                    algorithms=["HS256"],
                    issuer=JWT_ISSUER,
                    audience=JWT_AUDIENCE
                )
            except jwt.exceptions.PyJWTError:
                # Si falla, decodificar sin validar solo para logging
                data = jwt.decode(token, options={"verify_signature": False})
            
            # Extraer username de los claims
            username = data.get(
                'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name',
                data.get('name', data.get('sub', 'unknown'))
            )
            return username or 'unknown'
            
        except Exception:
            return "anonymous"
    
    async def _capture_request_body(self, request: Request) -> Optional[str]:
        """
        Captura y sanitiza el request body para logging.
        
        Args:
            request: Request HTTP
            
        Returns:
            Body sanitizado y truncado, o None
        """
        try:
            # Leer el body
            body_bytes = await request.body()
            if not body_bytes:
                return None
            
            body_str = body_bytes.decode('utf-8', errors='replace')
            
            # Intentar parsear como JSON para sanitizar
            try:
                body_dict = json.loads(body_str)
                body_dict = self._sanitize_sensitive_data(body_dict)
                body_str = json.dumps(body_dict, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
            
            # Truncar si es muy largo
            if len(body_str) > MAX_BODY_LOG_SIZE:
                return body_str[:MAX_BODY_LOG_SIZE] + "...[TRUNCATED]"
            
            return body_str
            
        except Exception:
            return "[ERROR READING BODY]"
    
    async def _capture_response_body(self, response: Response) -> tuple:
        """
        Captura el response body para logging.
        
        Args:
            response: Response HTTP
            
        Returns:
            Tuple (body_string, new_response)
        """
        try:
            # Para StreamingResponse, necesitamos consumir y recrear
            if isinstance(response, StreamingResponse):
                body_chunks = []
                async for chunk in response.body_iterator:
                    body_chunks.append(chunk)
                
                body_bytes = b"".join(body_chunks)
                body_str = body_bytes.decode('utf-8', errors='replace')
                
                # Truncar para logging
                logged_body = body_str[:MAX_BODY_LOG_SIZE]
                if len(body_str) > MAX_BODY_LOG_SIZE:
                    logged_body += "...[TRUNCATED]"
                
                # Recrear el response con el body
                new_response = Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )
                
                return logged_body, new_response
            
            return None, response
            
        except Exception:
            return "[ERROR READING RESPONSE]", response
    
    def _sanitize_sensitive_data(self, data: dict) -> dict:
        """
        Remueve datos sensibles del diccionario para logging.
        
        Args:
            data: Diccionario con datos del request
            
        Returns:
            Diccionario con datos sensibles enmascarados
        """
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_sensitive_data(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize_sensitive_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
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
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _log_request(self, data: dict, status_code: int, duration_ms: float) -> None:
        """
        Registra el request con el nivel de log apropiado.
        
        Args:
            data: Diccionario con todos los datos del request
            status_code: Código HTTP de respuesta
            duration_ms: Tiempo de ejecución en milisegundos
        """
        # Formato estructurado para el log
        log_parts = [
            f"[{data['correlation_id'][:8]}]",
            f"{data['method']} {data['path']}",
            f"[{data['status']}]",
            f"{data['duration_ms']}ms",
            f"User:{data['user']}",
            f"IP:{data['client_ip']}",
        ]
        
        if data.get("query"):
            log_parts.append(f"Query:{data['query']}")
        
        log_message = " - ".join(log_parts)
        
        # Log detallado (request/response body) en nivel DEBUG
        detail_parts = []
        if data.get("request_body"):
            detail_parts.append(f"ReqBody:{data['request_body']}")
        if data.get("response_body"):
            detail_parts.append(f"RespBody:{data['response_body'][:200]}")
        if data.get("error"):
            detail_parts.append(f"Error:{data['error']}")
        
        detail_message = " | ".join(detail_parts) if detail_parts else ""
        
        # Seleccionar nivel de log según código de estado
        if status_code >= 500:
            logger.error(f"❌ {log_message}")
            if detail_message:
                logger.error(f"   └─ {detail_message}")
        elif status_code >= 400:
            logger.warning(f"⚠️ {log_message}")
            if detail_message:
                logger.warning(f"   └─ {detail_message}")
        elif duration_ms > self.SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(f"🐢 SLOW: {log_message}")
            if detail_message:
                logger.debug(f"   └─ {detail_message}")
        else:
            logger.info(f"📊 {log_message}")
            if detail_message:
                logger.debug(f"   └─ {detail_message}")


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
    logger.info("✅ Middleware de logging de requests configurado (Buenas Prácticas Sección 5)")
