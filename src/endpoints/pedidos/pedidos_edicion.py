"""
Endpoints de edición de detalles de pedidos.
"""

import logging
import uuid as uuid_module
from typing import Dict, Optional
from fastapi import FastAPI, Depends, HTTPException, Path, Body, status
from fastapi.responses import JSONResponse

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.pedido_estados import ESTADO_GESTIONAR_PEDIDO
from src.security.jwt_auth import verify_jwt_token
from src.models import (
    ActualizarCostoRequest,
    ActualizarTotalRequest,
    ActualizarComentarioRequest,
    GuardarModificacionesColumnasRequest,
    GuardarModificacionesColumnasResponse,
    ObtenerModificacionesColumnasResponse,
    ModificacionColumnaItem
)
from .pedidos_crud_helpers import calcular_totales_detalles
from .utils import get_user_id

logger = logging.getLogger(__name__)


DESC_NUMERO_PEDIDO = "Número del pedido o pedido_id (UUID); el backend acepta ambos."
DESC_PEDIDO_DETALLE_ID = "UUID del detalle del pedido"
MSG_ERROR_ESTADO_NO_EDITABLE = "Solo se pueden editar COSTO UNIT., TOTAL y COMENTARIO cuando el pedido está en estado GESTIONAR PEDIDO."


def _get_pedido_por_identificador(repo: PedidoRepository, identificador: str) -> Optional[Dict]:
    """
    Obtiene el pedido completo por pedido_id (UUID) o por numero_pedido.
    El frontend puede enviar la URL con UUID (ej. /api/pedidos/EFB69529-.../detalle/...)
    o con numero_pedido (ej. /api/pedidos/P-12.23 - 12 - 2025/detalle/...).
    """
    if not identificador or not identificador.strip():
        return None
    identificador = identificador.strip()
    try:
        uuid_module.UUID(identificador)
        return repo.get_pedido_completo(identificador)
    except (ValueError, TypeError):
        return repo.get_pedido_completo_por_numero(identificador)

def _obtener_pedido_existente(repo: PedidoRepository, numero_pedido: str) -> Dict:
    pedido = _get_pedido_por_identificador(repo, numero_pedido)
    if not pedido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                          detail={"error": "pedido_not_found", "message": f"No se encontró el pedido: {numero_pedido}"})
    return pedido

def _validar_pedido_editable(repo: PedidoRepository, numero_pedido: str) -> Dict:
    pedido = _obtener_pedido_existente(repo, numero_pedido)
    estado_id = pedido.get("cabecera", {}).get("estado_id")
    try:
        estado_id = int(estado_id) if estado_id is not None else None
    except (TypeError, ValueError):
        estado_id = None
    if estado_id != ESTADO_GESTIONAR_PEDIDO:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                          detail={"error": "estado_no_editable",
                                 "message": MSG_ERROR_ESTADO_NO_EDITABLE})
    return pedido

def _logic_actualizar_costo_detalle(numero_pedido: str, pedido_detalle_id: str, request_body: ActualizarCostoRequest, user: Dict):
    try:
        nuevo_costo = request_body.costo_doc_sin_iva
        
        if nuevo_costo is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "validation_error", "message": "El costo no puede ser null"})
        if not isinstance(nuevo_costo, (int, float)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "validation_error", "message": "El costo debe ser un número válido"})
        if nuevo_costo < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "validation_error", "message": "El costo no puede ser negativo"})
        if nuevo_costo > 1000000:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "validation_error", 
                                     "message": f"El costo ({nuevo_costo}) excede el límite máximo permitido (1,000,000)"})
        
        user_id = get_user_id(user)
        totales = None
        
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = _validar_pedido_editable(repo, numero_pedido)
            
            resultado = repo.update_costo_detalle(pedido_detalle_id, nuevo_costo, modificado_por=user_id)
            if resultado.get("success"):
                pedido_actualizado = _get_pedido_por_identificador(repo, numero_pedido)
                totales = calcular_totales_detalles(pedido_actualizado.get("detalles", [])) if pedido_actualizado else {}
        
        if resultado["success"]:
            logger.info(f"✅ Costo actualizado para detalle {pedido_detalle_id} por usuario {user.get('username', 'UNKNOWN')}")
            content = {"status": "success", "message": resultado["mensaje"],
                      "pedido_detalle_id": resultado["pedido_detalle_id"],
                      "costo_anterior": resultado["costo_anterior"],
                      "costo_nuevo": resultado["costo_nuevo"]}
            if totales is not None:
                content["totales"] = totales
            return JSONResponse(status_code=status.HTTP_200_OK, content=content)
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                              detail={"error": "detalle_not_found", "message": resultado["mensaje"]})
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al actualizar costo: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail={"error": "internal_error", "message": f"Error interno al actualizar costo: {str(e)}"})

def _logic_actualizar_total_detalle(numero_pedido: str, pedido_detalle_id: str, request_body: ActualizarTotalRequest, user: Dict):
    try:
        nuevo_total = request_body.total
        
        if nuevo_total is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "validation_error", "message": "El total no puede ser null"})
        if not isinstance(nuevo_total, (int, float)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "validation_error", "message": "El total debe ser un número válido"})

        nuevo_total = float(nuevo_total)

        if nuevo_total < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "validation_error", "message": "El total no puede ser negativo"})
        if nuevo_total > 10000000:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "validation_error",
                                     "message": f"El total ({nuevo_total}) excede el límite máximo permitido (10,000,000)"})
        
        user_id = get_user_id(user)
        totales = None
        
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = _validar_pedido_editable(repo, numero_pedido)
            
            resultado = repo.update_total_detalle(pedido_detalle_id, nuevo_total, modificado_por=user_id)
            if resultado.get("success"):
                pedido_actualizado = _get_pedido_por_identificador(repo, numero_pedido)
                totales = calcular_totales_detalles(pedido_actualizado.get("detalles", [])) if pedido_actualizado else {}
        
        if resultado["success"]:
            logger.info(f"✅ Total actualizado para detalle {pedido_detalle_id} por usuario {user.get('username', 'UNKNOWN')}")
            content = {"status": "success", "message": resultado["mensaje"],
                      "pedido_detalle_id": resultado["pedido_detalle_id"],
                      "total_anterior": resultado["total_anterior"],
                      "total_nuevo": resultado["total_nuevo"],
                      "costo_actualizado": resultado["costo_actualizado"]}
            if totales is not None:
                content["totales"] = totales
            return JSONResponse(status_code=status.HTTP_200_OK, content=content)
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                              detail={"error": "detalle_not_found", "message": resultado["mensaje"]})
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al actualizar total: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail={"error": "internal_error", "message": f"Error interno al actualizar total: {str(e)}"})

def _logic_actualizar_comentario_detalle(numero_pedido: str, pedido_detalle_id: str, request_body: ActualizarComentarioRequest, user: Dict):
    try:
        nuevo_comentario = request_body.comentario
        
        if nuevo_comentario is not None:
            if not isinstance(nuevo_comentario, str):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                  detail={"error": "validation_error", 
                                         "message": "El comentario debe ser una cadena de texto"})
            if len(nuevo_comentario) > 2000:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                  detail={"error": "validation_error",
                                         "message": f"El comentario excede la longitud máxima permitida (2000 caracteres). Longitud actual: {len(nuevo_comentario)}"})
            if nuevo_comentario.strip() == "":
                nuevo_comentario = None
        
        user_id = get_user_id(user)
        
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = _validar_pedido_editable(repo, numero_pedido)
            
            resultado = repo.update_comentario_detalle(pedido_detalle_id, nuevo_comentario, modificado_por=user_id)
        
        if resultado["success"]:
            logger.info(f"✅ Comentario actualizado para detalle {pedido_detalle_id} por usuario {user.get('username', 'UNKNOWN')}")
            return JSONResponse(status_code=status.HTTP_200_OK,
                              content={"status": "success", "message": resultado["mensaje"],
                                      "pedido_detalle_id": resultado["pedido_detalle_id"],
                                      "comentario_anterior": resultado["comentario_anterior"],
                                      "comentario_nuevo": resultado["comentario_nuevo"],
                                      "costo_nuevo": None, "total_actualizado": None})
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                              detail={"error": "detalle_not_found", "message": resultado["mensaje"]})
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al actualizar comentario: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail={"error": "internal_error", "message": f"Error interno al actualizar comentario: {str(e)}"})

def _logic_guardar_modificaciones_columnas(numero_pedido: str, request_body: GuardarModificacionesColumnasRequest, user: Dict):
    try:
        if request_body.numero_pedido != numero_pedido:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "numero_pedido_mismatch",
                                     "message": f"El número de pedido en la URL ({numero_pedido}) no coincide con el del body ({request_body.numero_pedido})"})
        
        modificaciones_list = [{"pedido_detalle_id": mod.pedido_detalle_id, "columna_key": mod.columna_key}
                              for mod in request_body.modificaciones]
        user_id = get_user_id(user)
        
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = _validar_pedido_editable(repo, numero_pedido)
            
            numero_pedido_real = pedido.get("cabecera", {}).get("numero_pedido") or numero_pedido
            resultado = repo.guardar_modificaciones_columnas(
                numero_pedido=numero_pedido_real, modificaciones=modificaciones_list, modificado_por=user_id)
        
        if resultado["success"]:
            logger.info(f"✅ Modificaciones guardadas para pedido {numero_pedido_real} por usuario {user.get('username', 'UNKNOWN')}")
            return GuardarModificacionesColumnasResponse(
                status="success", message=resultado["mensaje"],
                numero_pedido=numero_pedido_real, modificaciones_guardadas=resultado["modificaciones_guardadas"])
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                              detail={"error": "pedido_not_found", "message": resultado["mensaje"]})
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al guardar modificaciones de columnas: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail={"error": "internal_error", "message": f"Error interno al guardar modificaciones: {str(e)}"})

def _logic_obtener_modificaciones_columnas(numero_pedido: str, user: Dict):
    try:
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = _obtener_pedido_existente(repo, numero_pedido)
            
            numero_pedido_real = pedido.get("cabecera", {}).get("numero_pedido") or numero_pedido
            resultado = repo.obtener_modificaciones_columnas(numero_pedido=numero_pedido_real)
        
        if not resultado["success"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                              detail={"error": "pedido_not_found", "message": resultado["mensaje"]})
        
        modificaciones_items = [ModificacionColumnaItem(
            pedido_detalle_id=mod["pedido_detalle_id"], columna_key=mod["columna_key"],
            modificado_por=mod["modificado_por"], fecha_modificacion=mod["fecha_modificacion"])
            for mod in resultado["modificaciones"]]
        
        logger.info(f"✅ Modificaciones obtenidas para pedido {numero_pedido_real} por usuario {user.get('username', 'UNKNOWN')}")
        return ObtenerModificacionesColumnasResponse(
            status="success", numero_pedido=numero_pedido_real, modificaciones=modificaciones_items)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al obtener modificaciones de columnas: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail={"error": "internal_error", "message": f"Error interno al obtener modificaciones: {str(e)}"})


def register_edicion_endpoints(app: FastAPI):
    """Registra los endpoints de edición de detalles de pedidos."""
    
    @app.patch("/api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/costo", tags=["Pedidos - Edición"])
    async def actualizar_costo_detalle(
        numero_pedido: str = Path(..., description=DESC_NUMERO_PEDIDO),
        pedido_detalle_id: str = Path(..., description=DESC_PEDIDO_DETALLE_ID),
        request_body: ActualizarCostoRequest = Body(..., description="Datos del costo a actualizar"),
        user: Dict = Depends(verify_jwt_token),
    ):
        """Actualiza el costo unitario de una línea de detalle del pedido. Cualquier usuario autenticado puede editar (estado GESTIONAR PEDIDO). Devuelve totales recalculados."""
        return _logic_actualizar_costo_detalle(numero_pedido, pedido_detalle_id, request_body, user)
    
    @app.patch("/api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/total", tags=["Pedidos - Edición"])
    async def actualizar_total_detalle(
        numero_pedido: str = Path(..., description=DESC_NUMERO_PEDIDO),
        pedido_detalle_id: str = Path(..., description=DESC_PEDIDO_DETALLE_ID),
        request_body: ActualizarTotalRequest = Body(..., description="Datos del total a actualizar"),
        user: Dict = Depends(verify_jwt_token),
    ):
        """Actualiza el total de una línea de detalle del pedido. Cualquier usuario autenticado puede editar (estado GESTIONAR PEDIDO). Devuelve totales recalculados."""
        return _logic_actualizar_total_detalle(numero_pedido, pedido_detalle_id, request_body, user)
    
    @app.patch("/api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/comentario", tags=["Pedidos - Edición"])
    async def actualizar_comentario_detalle(
        numero_pedido: str = Path(..., description=DESC_NUMERO_PEDIDO),
        pedido_detalle_id: str = Path(..., description=DESC_PEDIDO_DETALLE_ID),
        request_body: ActualizarComentarioRequest = Body(..., description="Datos del comentario a actualizar"),
        user: Dict = Depends(verify_jwt_token),
    ):
        """Actualiza el comentario de una línea de detalle del pedido."""
        return _logic_actualizar_comentario_detalle(numero_pedido, pedido_detalle_id, request_body, user)
    
    @app.post("/api/pedidos/{numero_pedido}/modificaciones-columnas",
              response_model=GuardarModificacionesColumnasResponse,
              tags=["Pedidos - Modificaciones"])
    async def guardar_modificaciones_columnas(
        numero_pedido: str = Path(..., description=DESC_NUMERO_PEDIDO),
        request_body: GuardarModificacionesColumnasRequest = Body(..., description="Datos de las modificaciones"),
        user: Dict = Depends(verify_jwt_token),
    ):
        """Guarda o actualiza las modificaciones de columnas para un pedido."""
        return _logic_guardar_modificaciones_columnas(numero_pedido, request_body, user)
    
    @app.get("/api/pedidos/{numero_pedido}/modificaciones-columnas",
             response_model=ObtenerModificacionesColumnasResponse,
             tags=["Pedidos - Modificaciones"])
    async def obtener_modificaciones_columnas(
        numero_pedido: str = Path(..., description=DESC_NUMERO_PEDIDO),
        user: Dict = Depends(verify_jwt_token),
    ):
        """Obtiene las modificaciones de columnas para un pedido."""
        return _logic_obtener_modificaciones_columnas(numero_pedido, user)
