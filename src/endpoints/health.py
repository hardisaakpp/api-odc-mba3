"""
Endpoints relacionados con health check y estado del sistema.
"""

from datetime import datetime
from fastapi import FastAPI
from models import HealthResponse


def register_health_endpoints(app: FastAPI):
    """
    Registra los endpoints de health check en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.get("/health", response_model=HealthResponse, tags=["Sistema"])
    async def health_check():
        """
        Endpoint de health check.
        
        Returns:
            JSON con status "ok" y timestamp ISO8601
        """
        return {
            "status": "ok",
            "time": datetime.now().isoformat()
        }

