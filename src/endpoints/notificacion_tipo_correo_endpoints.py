"""
Endpoints de administración del catálogo de correos (notificacion_tipo_correo).

Documenta qué correo (asunto) envía el sistema y a qué tipo_notificacion
pertenece. Solo Admin.
"""

import asyncio
import logging
from typing import Dict, Optional

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field

from src.database.connection import get_db_connection_context
from src.database.repositories.notificacion_tipo_correo_repository import (
    actualizar_activo_tipo_correo,
    crear_tipo_correo,
    eliminar_tipo_correo,
    listar_tipos_correo,
    listar_tipos_notificacion,
    obtener_tipo_correo,
)
from src.security.jwt_auth import require_admin, verify_jwt_token
from src.utils.email_preview import construir_vista_previa

logger = logging.getLogger(__name__)


class CrearTipoCorreoRequest(BaseModel):
    tipo_notificacion: str = Field(..., min_length=1)
    tipo_correo: str = Field(..., min_length=1)
    descripcion: Optional[str] = None


class ActualizarActivoTipoCorreoRequest(BaseModel):
    activo: bool


def _db_listar_tipos_correo() -> Dict:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        tipos_correo = listar_tipos_correo(conn)
        tipos_notificacion = listar_tipos_notificacion(conn)
    return {"tipos_notificacion": tipos_notificacion, "tipos_correo": tipos_correo}


async def _listar_tipos_correo_handler() -> Dict:
    return await asyncio.to_thread(_db_listar_tipos_correo)


def _db_crear_tipo_correo(tipo: str, asunto: str, descripcion: Optional[str], creado_por: str) -> int:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        return crear_tipo_correo(conn, tipo, asunto, descripcion, creado_por)


async def _crear_tipo_correo_handler(body: CrearTipoCorreoRequest, user: Dict) -> Dict:
    tipo = body.tipo_notificacion.strip().upper()
    asunto = body.tipo_correo.strip()
    if not tipo or not asunto:
        raise HTTPException(status_code=400, detail="tipo_notificacion y tipo_correo son requeridos")

    creado_por = user.get("username", "unknown")
    try:
        nuevo_id = await asyncio.to_thread(_db_crear_tipo_correo, tipo, asunto, body.descripcion, creado_por)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    logger.info(f"✅ Catálogo de correo creado por '{creado_por}': tipo={tipo}, correo={asunto}, id={nuevo_id}")
    return {
        "id": nuevo_id,
        "tipo_notificacion": tipo,
        "tipo_correo": asunto,
        "descripcion": body.descripcion,
        "orden_flujo": None,
        "activo": True,
    }


def _db_actualizar_activo_tipo_correo(tipo_correo_id: int, activo: bool, modificado_por: str) -> bool:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        return actualizar_activo_tipo_correo(conn, tipo_correo_id, activo, modificado_por)


async def _actualizar_activo_tipo_correo_handler(
    tipo_correo_id: int, body: ActualizarActivoTipoCorreoRequest, user: Dict
) -> Dict:
    modificado_por = user.get("username", "unknown")
    actualizado = await asyncio.to_thread(
        _db_actualizar_activo_tipo_correo, tipo_correo_id, body.activo, modificado_por
    )

    if not actualizado:
        raise HTTPException(status_code=404, detail=f"Catálogo de correo {tipo_correo_id} no encontrado")

    return {"id": tipo_correo_id, "activo": body.activo}


def _db_preview_tipo_correo(tipo_correo_id: int) -> Dict:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        fila = obtener_tipo_correo(conn, tipo_correo_id)

    if not fila:
        raise HTTPException(status_code=404, detail=f"Catálogo de correo {tipo_correo_id} no encontrado")

    resultado = construir_vista_previa(fila["tipo_notificacion"], fila["tipo_correo"])
    if resultado is None:
        raise HTTPException(
            status_code=404,
            detail="Sin vista previa disponible: este correo no está asociado a un código de envío real "
            "(por ejemplo, fue agregado manualmente al catálogo).",
        )

    subject, html = resultado
    return {"subject": subject, "html": html}


async def _preview_tipo_correo_handler(tipo_correo_id: int) -> Dict:
    return await asyncio.to_thread(_db_preview_tipo_correo, tipo_correo_id)


def _db_eliminar_tipo_correo(tipo_correo_id: int) -> bool:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        return eliminar_tipo_correo(conn, tipo_correo_id)


async def _eliminar_tipo_correo_handler(tipo_correo_id: int, user: Dict) -> Dict:
    eliminado = await asyncio.to_thread(_db_eliminar_tipo_correo, tipo_correo_id)

    if not eliminado:
        raise HTTPException(status_code=404, detail=f"Catálogo de correo {tipo_correo_id} no encontrado")

    logger.info(f"✅ Catálogo de correo {tipo_correo_id} eliminado por '{user.get('username', 'unknown')}'")
    return {"success": True}


def register_notificacion_tipo_correo_endpoints(app: FastAPI):
    """Registra los endpoints de administración del catálogo de correos."""

    @app.get("/api/notificaciones/tipos-correo", tags=["Notificaciones - Catálogo de Correos"])
    async def listar_tipos_correo_endpoint(
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Lista el catálogo de correos y los tipos de notificación distintos activos. Solo Admin."""
        return await _listar_tipos_correo_handler()

    @app.post("/api/notificaciones/tipos-correo", tags=["Notificaciones - Catálogo de Correos"])
    async def crear_tipo_correo_endpoint(
        body: CrearTipoCorreoRequest,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Agrega una fila al catálogo de correos. Solo Admin."""
        return await _crear_tipo_correo_handler(body, user)

    @app.patch("/api/notificaciones/tipos-correo/{tipo_correo_id}", tags=["Notificaciones - Catálogo de Correos"])
    async def actualizar_activo_tipo_correo_endpoint(
        tipo_correo_id: int,
        body: ActualizarActivoTipoCorreoRequest,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Activa o desactiva una fila del catálogo de correos. Solo Admin."""
        return await _actualizar_activo_tipo_correo_handler(tipo_correo_id, body, user)

    @app.get("/api/notificaciones/tipos-correo/{tipo_correo_id}/preview", tags=["Notificaciones - Catálogo de Correos"])
    async def preview_tipo_correo_endpoint(
        tipo_correo_id: int,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Vista previa (asunto + HTML de ejemplo) de un correo del catálogo. Solo Admin."""
        return await _preview_tipo_correo_handler(tipo_correo_id)

    @app.delete("/api/notificaciones/tipos-correo/{tipo_correo_id}", tags=["Notificaciones - Catálogo de Correos"])
    async def eliminar_tipo_correo_endpoint(
        tipo_correo_id: int,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Elimina definitivamente una fila del catálogo de correos. Solo Admin."""
        return await _eliminar_tipo_correo_handler(tipo_correo_id, user)
