"""
Endpoints de administración de destinatarios de notificaciones por email.

Gestiona la tabla notificacion_destinatarios: alta (solo filas base, sin
codigo_evento), baja y activar/desactivar (cualquier fila, incluidas las
exclusiones puntuales por evento ya existentes, ej. la de
nvelasquez@elrayo.com.ec para REDISTRIBUCION_CONFIRMADA). Crear una nueva
exclusión por evento sigue siendo manual vía script SQL; esta interfaz no
expone un selector de codigo_evento en el alta.

Restringido a usuarios con rol Admin (ver require_admin en jwt_auth.py):
es configuración que afecta el envío de correos de todos los tipos a la vez,
no un permiso de negocio puntual.
"""

import logging
from typing import Dict

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field

from src.database.connection import get_db_connection_context
from src.database.repositories.notificacion_destinatario_repository import (
    actualizar_activo_destinatario,
    crear_destinatario,
    eliminar_destinatario,
    listar_destinatarios,
)
from src.database.repositories.notificacion_tipo_correo_repository import listar_tipos_notificacion
from src.security.jwt_auth import require_admin, verify_jwt_token

logger = logging.getLogger(__name__)


class CrearDestinatarioRequest(BaseModel):
    tipo_notificacion: str = Field(..., description="Debe existir en el catálogo de correos (notificacion_tipo_correo)")
    email: str = Field(..., min_length=3)


class ActualizarActivoRequest(BaseModel):
    activo: bool


def _validar_tipo(tipo_notificacion: str, tipos_validos: list) -> str:
    tipo = (tipo_notificacion or "").strip().upper()
    if tipo not in tipos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"tipo_notificacion inválido. Valores permitidos: {', '.join(tipos_validos)}",
        )
    return tipo


def _validar_email(email: str) -> str:
    correo = (email or "").strip()
    if "@" not in correo or len(correo) < 3:
        raise HTTPException(status_code=400, detail=f"Email inválido: '{email}'")
    return correo


async def _listar_destinatarios_handler() -> Dict:
    with get_db_connection_context() as conn:
        destinatarios = listar_destinatarios(conn)
        tipos_notificacion = listar_tipos_notificacion(conn)
    return {"tipos_notificacion": tipos_notificacion, "destinatarios": destinatarios}


async def _crear_destinatario_handler(body: CrearDestinatarioRequest, user: Dict) -> Dict:
    correo = _validar_email(body.email)
    creado_por = user.get("username", "unknown")

    try:
        with get_db_connection_context() as conn:
            tipo = _validar_tipo(body.tipo_notificacion, listar_tipos_notificacion(conn))
            nuevo_id = crear_destinatario(conn, tipo, correo, creado_por)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    logger.info(f"✅ Destinatario creado por '{creado_por}': tipo={tipo}, email={correo}, id={nuevo_id}")
    return {"id": nuevo_id, "tipo_notificacion": tipo, "email": correo, "activo": True}


async def _actualizar_activo_handler(destinatario_id: int, body: ActualizarActivoRequest, user: Dict) -> Dict:
    modificado_por = user.get("username", "unknown")
    with get_db_connection_context() as conn:
        actualizado = actualizar_activo_destinatario(conn, destinatario_id, body.activo, modificado_por)

    if not actualizado:
        raise HTTPException(status_code=404, detail=f"Destinatario {destinatario_id} no encontrado")

    logger.info(f"✅ Destinatario {destinatario_id} {'activado' if body.activo else 'desactivado'} por '{modificado_por}'")
    return {"id": destinatario_id, "activo": body.activo}


async def _eliminar_destinatario_handler(destinatario_id: int, user: Dict) -> Dict:
    with get_db_connection_context() as conn:
        eliminado = eliminar_destinatario(conn, destinatario_id)

    if not eliminado:
        raise HTTPException(status_code=404, detail=f"Destinatario {destinatario_id} no encontrado")

    logger.info(f"✅ Destinatario {destinatario_id} eliminado por '{user.get('username', 'unknown')}'")
    return {"success": True}


def register_notificacion_destinatarios_endpoints(app: FastAPI):
    """Registra los endpoints de administración de destinatarios de notificaciones."""

    @app.get("/api/notificaciones/destinatarios", tags=["Notificaciones - Destinatarios"])
    async def listar_destinatarios_endpoint(
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """
        Lista todas las filas de notificacion_destinatarios.

        Solo Admin. Incluye activos e inactivos, y las filas de exclusión
        puntual por evento (codigo_evento) ya existentes.
        """
        return await _listar_destinatarios_handler()

    @app.post("/api/notificaciones/destinatarios", tags=["Notificaciones - Destinatarios"])
    async def crear_destinatario_endpoint(
        body: CrearDestinatarioRequest,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Agrega un nuevo destinatario (activo=1) para un tipo de notificación. Solo Admin."""
        return await _crear_destinatario_handler(body, user)

    @app.patch("/api/notificaciones/destinatarios/{destinatario_id}", tags=["Notificaciones - Destinatarios"])
    async def actualizar_activo_destinatario_endpoint(
        destinatario_id: int,
        body: ActualizarActivoRequest,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Activa o desactiva un destinatario existente. Solo Admin."""
        return await _actualizar_activo_handler(destinatario_id, body, user)

    @app.delete("/api/notificaciones/destinatarios/{destinatario_id}", tags=["Notificaciones - Destinatarios"])
    async def eliminar_destinatario_endpoint(
        destinatario_id: int,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_admin()),
    ):
        """Elimina definitivamente un destinatario. Solo Admin."""
        return await _eliminar_destinatario_handler(destinatario_id, user)
