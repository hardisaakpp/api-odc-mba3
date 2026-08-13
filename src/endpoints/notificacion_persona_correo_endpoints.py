"""
Endpoints de administración de notificacion_persona_correo (organización
persona-céntrica de correos). Solo Admin, igual que los otros endpoints de
notificaciones. Ver docstring del repositorio: es la fuente real de
destinatarios del envío de correos.
"""

import logging
from typing import Dict

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field

from src.database.connection import get_db_connection_context
from src.database.repositories.notificacion_persona_correo_repository import (
    crear_link_persona_correo,
    eliminar_link_persona_correo,
    eliminar_persona,
    listar_personas_correo,
)
from src.security.jwt_auth import require_admin, verify_jwt_token

logger = logging.getLogger(__name__)


class CrearLinkRequest(BaseModel):
    nombre: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    tipo_correo_id: int


async def _listar_handler() -> Dict:
    with get_db_connection_context() as conn:
        filas = listar_personas_correo(conn)
    return {"personas_correo": filas}


async def _crear_link_handler(body: CrearLinkRequest, user: Dict) -> Dict:
    correo = body.email.strip()
    if "@" not in correo:
        raise HTTPException(status_code=400, detail=f"Email inválido: '{body.email}'")

    creado_por = user.get("username", "unknown")
    try:
        with get_db_connection_context() as conn:
            nuevo_id = crear_link_persona_correo(conn, body.nombre, correo, body.tipo_correo_id, creado_por)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    logger.info(f"✅ Link persona-correo creado por '{creado_por}': email={correo}, tipo_correo_id={body.tipo_correo_id}")
    return {"id": nuevo_id, "nombre": body.nombre, "email": correo, "tipo_correo_id": body.tipo_correo_id}


async def _eliminar_link_handler(link_id: int) -> Dict:
    with get_db_connection_context() as conn:
        eliminado = eliminar_link_persona_correo(conn, link_id)

    if not eliminado:
        raise HTTPException(status_code=404, detail=f"Link {link_id} no encontrado")
    return {"success": True}


async def _eliminar_persona_handler(email: str) -> Dict:
    with get_db_connection_context() as conn:
        eliminado = eliminar_persona(conn, email)

    if not eliminado:
        raise HTTPException(status_code=404, detail=f"No se encontró a '{email}'")
    return {"success": True}


def register_notificacion_persona_correo_endpoints(app: FastAPI):
    """Registra los endpoints de administración de notificacion_persona_correo."""

    @app.get("/api/notificaciones/personas-correo", tags=["Notificaciones - Personas y Correos"])
    async def listar_personas_correo_endpoint(
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Lista todos los vínculos persona-correo. Solo Admin."""
        return await _listar_handler()

    @app.post("/api/notificaciones/personas-correo", tags=["Notificaciones - Personas y Correos"])
    async def crear_link_persona_correo_endpoint(
        body: CrearLinkRequest,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Vincula una persona a un correo del catálogo. Solo Admin."""
        return await _crear_link_handler(body, user)

    @app.delete("/api/notificaciones/personas-correo/{link_id}", tags=["Notificaciones - Personas y Correos"])
    async def eliminar_link_persona_correo_endpoint(
        link_id: int,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Desvincula un correo específico de una persona. Solo Admin."""
        return await _eliminar_link_handler(link_id)

    @app.delete("/api/notificaciones/personas-correo/persona/{email}", tags=["Notificaciones - Personas y Correos"])
    async def eliminar_persona_endpoint(
        email: str,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Elimina a una persona por completo (todos sus correos vinculados). Solo Admin."""
        return await _eliminar_persona_handler(email)
