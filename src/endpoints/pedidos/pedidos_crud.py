"""
Endpoints CRUD para gestión de pedidos.
"""

import logging
import re
import csv
import io
from typing import Dict, Optional
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Path, Query, Body, status
from fastapi.responses import JSONResponse, StreamingResponse

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository
from src.database.pedido_estados import (
    ESTADO_GESTIONAR_PEDIDO,
    ESTADO_NUEVO_PEDIDO,
    ESTADO_REDISTRIBUCION,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADO_FINALIZADO,
    ESTADO_CANCELADO,
    ESTADOS_PUEDE_DESCARTAR,
    ESTADOS_PUEDE_ELIMINAR,
    ESTADO_LIMITE_CANCELAR_PEDIDO,
)
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.exceptions import BusinessException
from src.models import (
    ModificarPedidoCabeceraRequest,
    ModificarPedidoCabeceraResponse,
    CrearPedidoRequest,
    CrearPedidoResponse
)
from .utils import get_user_id, MAX_FILE_SIZE

logger = logging.getLogger(__name__)


def register_crud_endpoints(app: FastAPI):
    """Registra los endpoints CRUD de pedidos."""
    
    @app.get("/api/pedidos", tags=["Pedidos"])
    async def listar_pedidos(
        estado: Optional[str] = Query(None, description="Filtrar por estado del pedido"),
        fecha_desde: Optional[str] = Query(None, description="Filtrar desde fecha (YYYY-MM-DD)"),
        fecha_hasta: Optional[str] = Query(None, description="Filtrar hasta fecha (YYYY-MM-DD)"),
        proveedor_nombre: Optional[str] = Query(None, description="Buscar por nombre de proveedor (parcial)"),
        numero_pedido: Optional[str] = Query(None, description="Buscar por número de pedido (parcial)"),
        creado_por: Optional[str] = Query(None, description="Filtrar por usuario que creó el pedido"),
        limit: Optional[int] = Query(50, description="Límite de registros por página"),
        offset: Optional[int] = Query(0, description="Offset para paginación"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Lista pedidos con filtros y paginación.
        Los pedidos en estado BORRADOR no se incluyen (solo NUEVO PEDIDO y posteriores).
        
        **HU-02 y HU-07: Visualizar estado de pedidos con filtros**
        
        Este endpoint permite a los usuarios de Mabel Trading y El Rayo visualizar
        los pedidos con múltiples filtros y seguimiento del estado.
        
        **Query Parameters:**
        - `estado` (string, opcional) - Filtrar por estado (ej: "PENDIENTE_CONFIRMACION_PROVEEDOR", "CONFIRMADO_PROVEEDOR")
        - `fecha_desde` (string, opcional) - Filtrar desde fecha (YYYY-MM-DD)
        - `fecha_hasta` (string, opcional) - Filtrar hasta fecha (YYYY-MM-DD)
        - `proveedor_nombre` (string, opcional) - Búsqueda parcial por nombre de proveedor
        - `numero_pedido` (string, opcional) - Búsqueda parcial por número de pedido
        - `creado_por` (string, opcional) - Filtrar por usuario que creó el pedido
        - `limit` (int, default: 50) - Límite de registros por página
        - `offset` (int, default: 0) - Offset para paginación
        
        **Ejemplo:**
        ```
        GET /api/pedidos?estado=PENDIENTE_CONFIRMACION_PROVEEDOR&limit=20&offset=0
        GET /api/pedidos?fecha_desde=2025-01-01&fecha_hasta=2025-01-31&proveedor_nombre=RAYO
        ```
        
        **Respuesta:**
        ```json
        {
            "status": "success",
            "data": [
                {
                    "pedido_id": "...",
                    "numero_pedido": "P-12.48 - 12 - 2025",
                    "fecha_pedido": "2025-01-21",
                    "proveedor_nombre": "TEXTILES EL RAYO S.A.",
                    "estado": "PENDIENTE_CONFIRMACION_PROVEEDOR",
                    ...
                }
            ],
            "metadata": {
                "total": 150,
                "limit": 50,
                "offset": 0,
                "has_more": true
            }
        }
        ```
        
        Returns:
            JSON con lista de pedidos y metadata de paginación
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                resultado = repo.get_pedidos_con_filtros(
                    estado=estado,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    proveedor_nombre=proveedor_nombre,
                    numero_pedido=numero_pedido,
                    creado_por=creado_por,
                    limit=limit,
                    offset=offset,
                    excluir_borrador=True,
                )
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "data": resultado["data"],
                        "metadata": {
                            "total": resultado["total"],
                            "limit": resultado["limit"],
                            "offset": resultado["offset"],
                            "has_more": resultado["has_more"]
                        }
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error al listar pedidos: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al listar pedidos: {str(e)}"
            )

    @app.get("/api/pedidos/confirmados", tags=["Pedidos"])
    async def listar_pedidos_confirmados(
        page: Optional[int] = Query(1, ge=1, description="Número de página (1-based)"),
        page_size: Optional[int] = Query(50, ge=1, le=100, description="Tamaño de página (snake_case)"),
        pageSize: Optional[int] = Query(None, ge=1, le=100, description="Tamaño de página (camelCase, alias de page_size)"),
        limit: Optional[int] = Query(None, description="Límite de registros (alternativa a page_size)"),
        offset: Optional[int] = Query(None, description="Offset (alternativa a page)"),
        redistribucion_confirmada: Optional[str] = Query(
            None,
            description="Si 'true', solo pedidos con redistribución ya confirmada (estado CONFIRMADO REDISTRIBUCION)"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Lista pedidos en estado confirmado, ordenados por creado_en DESC.
        Para pantalla Redistribución: lista de pedidos confirmados y/o con redistribución confirmada.

        **Query Parameters:**
        - `page` (int, default: 1) - Número de página
        - `page_size` o `pageSize` (int, default: 50) - Registros por página
        - `redistribucion_confirmada` - Si "true", solo pedidos en estado CONFIRMADO REDISTRIBUCION
        - `limit` / `offset` - Alternativa para paginación (si se usan, ignoran page/page_size)

        **Formato de respuesta (compatible con frontend):**
        - `data`: array de pedidos; cada uno con `cabecera: { pedido_id, numero_pedido, fecha_pedido, estado, ... }`
        - `total`, `page`, `pageSize`, `totalPages`
        """
        try:
            # Tamaño de página: prioridad pageSize (frontend) > page_size
            size = pageSize if pageSize is not None else page_size
            if limit is not None:
                use_limit, use_offset = limit, offset or 0
            else:
                use_size = size if size is not None else 50
                use_limit = use_size
                use_offset = ((page or 1) - 1) * use_size

            solo_redistribucion = (
                redistribucion_confirmada is not None
                and str(redistribucion_confirmada).lower() in ("true", "1")
            )

            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                resultado = repo.get_pedidos_confirmados(
                    limit=use_limit,
                    offset=use_offset,
                    solo_redistribucion_confirmada=solo_redistribucion
                )

            # Formato esperado por frontend: cada item con cabecera.*
            data = []
            for row in resultado["data"]:
                data.append({
                    "cabecera": {
                        "pedido_id": row.get("pedido_id"),
                        "numero_pedido": row.get("numero_pedido"),
                        "fecha_pedido": row.get("fecha_pedido"),
                        "fecha_entrega": row.get("fecha_entrega"),
                        "estado": row.get("estado"),
                        "proveedor_nombre": row.get("proveedor_nombre"),
                        "creado_por": row.get("creado_por"),
                        "creado_en": row.get("creado_en"),
                    },
                    "pedido_id": row.get("pedido_id"),
                    "numero_pedido": row.get("numero_pedido"),
                    "fecha_pedido": row.get("fecha_pedido"),
                    "estado": row.get("estado"),
                })

            total = resultado["total"]
            total_pages = (total + size - 1) // size if size else 0

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "data": data,
                    "total": total,
                    "page": page,
                    "pageSize": size,
                    "totalPages": total_pages,
                },
            )
        except Exception as e:
            logger.error(f"❌ Error al listar pedidos confirmados: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al listar pedidos confirmados: {str(e)}"
            )

    @app.get("/api/pedidos/ultimo-redistribucion", tags=["Pedidos"])
    async def get_ultimo_pedido_redistribucion(
        solo_usuario: Optional[bool] = Query(
            True,
            description="Si true, último pedido CONFIRMADO o CONFIRMADO REDISTRIBUCION del usuario; si false, último en todo el sistema"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Obtiene el último pedido con estado CONFIRMADO (4) o CONFIRMADO REDISTRIBUCION (10).
        Para la pantalla Revisar Redistribución: al entrar en /redistribucion sin número de pedido,
        el front llama a este endpoint y, si hay resultado, redirige a
        /pedidos/{numero_pedido}/redistribucion. Así se pueden visualizar tanto pedidos listos
        para redistribuir (CONFIRMADO) como ya con redistribución confirmada (CONFIRMADO REDISTRIBUCION).

        **Query Parameters:**
        - `solo_usuario` (bool, default: true) - Si true, último pedido del usuario en esos estados; si false, último global.

        **Respuesta:** Objeto con cabecera básica (pedido_id, numero_pedido, estado, ...) o null.

        **Comportamiento por permiso:**
        - Usuario con solo odcsap.view (EL RAYO): se ignora solo_usuario y se devuelve siempre
          el último pedido en estado para redistribución visible en el sistema (sin filtrar por
          creado_por), para que pueda ver el pedido que acaba de confirmar un usuario MABEL.
        - Usuario con mabel.view (MABEL): se respeta solo_usuario (true = último del usuario,
          false = último global).
        """
        try:
            permissions = user.get("permissions") or []
            has_odcsap = "odcsap.view" in permissions
            has_mabel = "mabel.view" in permissions
            # EL RAYO (solo odcsap.view): siempre último global para que vea pedidos confirmados por MABEL
            if has_odcsap and not has_mabel:
                user_id = None
            else:
                user_id = get_user_id(user) if solo_usuario else None
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                ultimo = repo.get_ultimo_pedido_respuesta_proveedor_cargada(usuario_id=user_id)
            if not ultimo:
                return JSONResponse(status_code=200, content=None)
            return JSONResponse(status_code=200, content=ultimo)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener último pedido redistribución: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener último pedido para redistribución: {str(e)}"
            )

    @app.get("/api/pedidos/existe", tags=["Pedidos"])
    async def verificar_pedidos_existen(
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Verifica si existe al menos un pedido guardado en la base de datos.
        
        Este endpoint es útil para el frontend para determinar si debe mostrar
        el botón "Gestionar Pedido" o cualquier otra funcionalidad relacionada
        con pedidos existentes.
        
        **Respuesta:**
        ```json
        {
            "status": "success",
            "tiene_pedidos": true,
            "message": "Existen pedidos en el sistema"
        }
        ```
        
        Returns:
            JSON indicando si hay pedidos guardados
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                tiene_pedidos = repo.tiene_pedidos()
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "tiene_pedidos": tiene_pedidos,
                        "message": "Existen pedidos en el sistema" if tiene_pedidos else "No hay pedidos en el sistema"
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error al verificar existencia de pedidos: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al verificar existencia de pedidos: {str(e)}"
            )
    
    @app.get("/api/plantillas/{identificador}", tags=["Plantillas"])
    async def get_pedido(
        identificador: str = Path(..., description="Número de pedido (ej: 'P-12.48 - 12 - 2025') o UUID del pedido (para compatibilidad)"),
        incluir_respuesta: bool = Query(False, description="Incluir respuesta del proveedor si existe"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Obtiene un pedido completo con cabecera, detalles y distribuciones por tienda.
        Acepta número de pedido (recomendado) o UUID (para compatibilidad).
        Opcionalmente incluye la respuesta del proveedor.
        
        **Path Parameters:**
        - `identificador` (string, requerido) - Puede ser:
          - Número de pedido (business key, ej: 'P-12.48 - 12 - 2025') ⭐ RECOMENDADO
          - UUID del pedido (ej: 'AEDEC52D-D007-416F-8A09-9F0D31282EEE') ⚠️ Compatibilidad
        
        **Query Parameters:**
        - `incluir_respuesta` (bool, default: false): Si true, incluye respuesta del proveedor si existe
        
        **Respuesta exitosa:**
        ```json
        {
            "cabecera": {
                "pedido_id": "...",
                "numero_pedido": "...",
                "fecha_pedido": "...",
                ...
            },
            "detalles": [
                {
                    "pedido_detalle_id": "...",
                    "codigo_interno": "...",
                    "descripcion_sap": "...",
                    "tiendas": [
                        {
                            "tienda_id": "...",
                            "codigo": "RECREO",
                            "nombre": "...",
                            "cantidad": 10
                        }
                    ]
                }
            ],
            "respuesta_proveedor": {
                "cabecera": {...},
                "detalles": [...]
            }
        }
        ```
        
        Returns:
            JSON con pedido completo
        """
        try:
            # Detectar si es UUID (formato: 8-4-4-4-12 caracteres hexadecimales)
            uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            es_uuid = uuid_pattern.match(identificador.strip()) is not None
            
            with get_db_connection_context() as conn:
                repository = PedidoRepository(conn)
                
                # Usar método apropiado según el formato detectado
                if es_uuid:
                    logger.info(f"🔍 Detectado UUID: {identificador}, usando get_pedido_completo")
                    pedido = repository.get_pedido_completo(identificador)
                    if not pedido:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Pedido no encontrado con UUID: {identificador}"
                        )
                else:
                    logger.info(f"🔍 Detectado numero_pedido: {identificador}, usando get_pedido_completo_por_numero")
                    pedido = repository.get_pedido_completo_por_numero(identificador)
                    if not pedido:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Pedido no encontrado con número: {identificador}"
                        )
                
                # Agregar respuesta si se solicita y existe (usando pedido_id de la cabecera)
                if incluir_respuesta:
                    respuesta_repo = PedidoRespuestaRepository(conn)
                    pedido_id = pedido["cabecera"]["pedido_id"]
                    respuesta = respuesta_repo.obtener_respuesta_activa(pedido_id)
                    if respuesta:
                        pedido["respuesta_proveedor"] = respuesta

                # Descartar (Cargar Plantilla): solo Borrador o Nuevo Pedido. Cancelar Pedido (Redistribución): deshabilitar desde Confirmado redistribución (10) en adelante.
                _eid = pedido.get("cabecera", {}).get("estado_id")
                try:
                    _eid = int(_eid) if _eid is not None else None
                except (TypeError, ValueError):
                    _eid = None
                pedido["puede_descartar"] = _eid in ESTADOS_PUEDE_DESCARTAR
                pedido["puede_eliminar"] = _eid in ESTADOS_PUEDE_ELIMINAR
                pedido["puede_cancelar_pedido"] = _eid is not None and _eid < ESTADO_LIMITE_CANCELAR_PEDIDO
                pedido["puede_descargar_csv"] = _eid == ESTADO_REDISTRIBUCION  # Solo en estado CONFIRMADO (4)

                return JSONResponse(status_code=200, content=pedido)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener pedido: {str(e)}"
            )

    @app.post("/api/pedidos/{pedido_id}/gestionar", tags=["Pedidos"])
    async def marcar_pedido_gestionar(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Marca el pedido como GESTIONAR PEDIDO (al hacer clic en "Ver Detalle" desde la tabla Pedidos).
        Si el pedido está en estado NUEVO PEDIDO, actualiza a GESTIONAR PEDIDO y devuelve el pedido completo.
        Si ya está en otro estado, solo devuelve el pedido sin cambiar estado.
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                pedido = repo.get_pedido_completo(pedido_id)
                if not pedido:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"error": "not_found", "message": "No se encontró el pedido."}
                    )
                estado_id = pedido.get("cabecera", {}).get("estado_id")
                try:
                    estado_id = int(estado_id) if estado_id is not None else None
                except (TypeError, ValueError):
                    estado_id = None
                if estado_id == ESTADO_NUEVO_PEDIDO:
                    repo.update_estado(pedido_id, ESTADO_GESTIONAR_PEDIDO)
                    pedido = repo.get_pedido_completo(pedido_id)
                _eid = pedido.get("cabecera", {}).get("estado_id")
                try:
                    _eid = int(_eid) if _eid is not None else None
                except (TypeError, ValueError):
                    _eid = None
                pedido["puede_descartar"] = _eid in ESTADOS_PUEDE_DESCARTAR
                pedido["puede_eliminar"] = _eid in ESTADOS_PUEDE_ELIMINAR
                pedido["puede_cancelar_pedido"] = _eid is not None and _eid < ESTADO_LIMITE_CANCELAR_PEDIDO
                pedido["puede_descargar_csv"] = _eid == ESTADO_REDISTRIBUCION  # Solo en estado CONFIRMADO (4)
                return JSONResponse(status_code=status.HTTP_200_OK, content=pedido)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al marcar pedido como gestionar {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "internal_error", "message": str(e)}
            )

    @app.post("/api/pedidos/{pedido_id}/confirmar-para-redistribucion", tags=["Pedidos"])
    async def confirmar_para_redistribucion(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Confirma el pedido para redistribución: cambia estado de GESTIONAR PEDIDO a CONFIRMADO.

        Se usa cuando el usuario hace clic en "Confirmar" en la página de detalle del pedido
        (estado actual = GESTIONAR PEDIDO). Solo se permite si el pedido está en ese estado.

        - **404**: Pedido no encontrado.
        - **400**: Pedido no está en estado GESTIONAR PEDIDO.
        - **200**: Estado actualizado a CONFIRMADO; devuelve el pedido completo.
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                pedido = repo.get_pedido_completo(pedido_id)
                if not pedido:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"error": "not_found", "message": "No se encontró el pedido."}
                    )
                estado_id = pedido.get("cabecera", {}).get("estado_id")
                try:
                    estado_id = int(estado_id) if estado_id is not None else None
                except (TypeError, ValueError):
                    estado_id = None
                if estado_id != ESTADO_GESTIONAR_PEDIDO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "estado_no_gestionar",
                            "message": "Solo se puede confirmar para redistribución cuando el pedido está en estado GESTIONAR PEDIDO."
                        }
                    )
                repo.update_estado(pedido_id, ESTADO_REDISTRIBUCION)
                pedido = repo.get_pedido_completo(pedido_id)
                _eid = pedido.get("cabecera", {}).get("estado_id")
                try:
                    _eid = int(_eid) if _eid is not None else None
                except (TypeError, ValueError):
                    _eid = None
                pedido["puede_descartar"] = _eid in ESTADOS_PUEDE_DESCARTAR
                pedido["puede_eliminar"] = _eid in ESTADOS_PUEDE_ELIMINAR
                pedido["puede_cancelar_pedido"] = _eid is not None and _eid < ESTADO_LIMITE_CANCELAR_PEDIDO
                pedido["puede_descargar_csv"] = _eid == ESTADO_REDISTRIBUCION  # Solo en estado CONFIRMADO (4)
                return JSONResponse(status_code=status.HTTP_200_OK, content=pedido)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al confirmar pedido para redistribución {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "internal_error", "message": str(e)}
            )

    @app.post("/api/pedidos/{pedido_id}/marcar-despachar-y-facturar", tags=["Pedidos"])
    async def marcar_despachar_y_facturar(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Marca el pedido como "Despachar y Facturar" (estado indicativo).

        Solo se permite cuando el pedido está en estado **Confirmado y Enviado**
        (estado_id = CONFIRMADO_ENVIADO), es decir, cuando la ODC fue enviada a SAP
        y se generaron las solicitudes de transferencia (estado ENVIADA en orden de compra).

        - **404**: Pedido no encontrado.
        - **400**: Pedido no está en estado Confirmado y Enviado.
        - **200**: Estado actualizado a Despachar y Facturar; devuelve el pedido completo.
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                pedido = repo.get_pedido_completo(pedido_id)
                if not pedido:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"error": "not_found", "message": "No se encontró el pedido."}
                    )
                estado_id = pedido.get("cabecera", {}).get("estado_id")
                try:
                    estado_id = int(estado_id) if estado_id is not None else None
                except (TypeError, ValueError):
                    estado_id = None
                if estado_id != ESTADO_CONFIRMADO_ENVIADO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "estado_no_confirmado_enviado",
                            "message": "Solo se puede marcar como Despachar y Facturar cuando el pedido está en estado Confirmado y Enviado (ODC enviada a SAP)."
                        }
                    )
                repo.update_estado(pedido_id, ESTADO_DESPACHAR_Y_FACTURAR)
                pedido = repo.get_pedido_completo(pedido_id)
                _eid = pedido.get("cabecera", {}).get("estado_id")
                try:
                    _eid = int(_eid) if _eid is not None else None
                except (TypeError, ValueError):
                    _eid = None
                pedido["puede_descartar"] = _eid in ESTADOS_PUEDE_DESCARTAR
                pedido["puede_eliminar"] = _eid in ESTADOS_PUEDE_ELIMINAR
                pedido["puede_cancelar_pedido"] = _eid is not None and _eid < ESTADO_LIMITE_CANCELAR_PEDIDO
                pedido["puede_descargar_csv"] = _eid == ESTADO_REDISTRIBUCION  # Solo en estado CONFIRMADO (4)
                return JSONResponse(status_code=status.HTTP_200_OK, content=pedido)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al marcar pedido como Despachar y Facturar {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "internal_error", "message": str(e)}
            )

    @app.post("/api/pedidos/{pedido_id}/marcar-finalizado", tags=["Pedidos"])
    async def marcar_finalizado(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Marca el pedido como "Finalizado" (estado final del flujo).

        Solo se permite cuando el pedido está en estado **Despachar y Facturar**
        (estado_id = 17). Es el estado final de todo el flujo.

        - **404**: Pedido no encontrado.
        - **400**: Pedido no está en estado Despachar y Facturar.
        - **200**: Estado actualizado a Finalizado; devuelve el pedido completo.
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                pedido = repo.get_pedido_completo(pedido_id)
                if not pedido:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"error": "not_found", "message": "No se encontró el pedido."}
                    )
                estado_id = pedido.get("cabecera", {}).get("estado_id")
                try:
                    estado_id = int(estado_id) if estado_id is not None else None
                except (TypeError, ValueError):
                    estado_id = None
                if estado_id != ESTADO_DESPACHAR_Y_FACTURAR:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "estado_no_despachar_y_facturar",
                            "message": "Solo se puede marcar como Finalizado cuando el pedido está en estado Despachar y Facturar."
                        }
                    )
                repo.update_estado(pedido_id, ESTADO_FINALIZADO)
                pedido = repo.get_pedido_completo(pedido_id)
                _eid = pedido.get("cabecera", {}).get("estado_id")
                try:
                    _eid = int(_eid) if _eid is not None else None
                except (TypeError, ValueError):
                    _eid = None
                pedido["puede_descartar"] = _eid in ESTADOS_PUEDE_DESCARTAR
                pedido["puede_eliminar"] = _eid in ESTADOS_PUEDE_ELIMINAR
                pedido["puede_cancelar_pedido"] = _eid is not None and _eid < ESTADO_LIMITE_CANCELAR_PEDIDO
                pedido["puede_descargar_csv"] = _eid == ESTADO_REDISTRIBUCION  # Solo en estado CONFIRMADO (4)
                return JSONResponse(status_code=status.HTTP_200_OK, content=pedido)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al marcar pedido como Finalizado {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "internal_error", "message": str(e)}
            )

    @app.post("/pedidos/importar-excel", tags=["Pedidos"])
    async def importar_excel_pedido(
        file: UploadFile = File(..., description="Archivo Excel (.xlsx) con hojas 'cabecera' y 'detalle' (formato v1.0)"),
        hoja_cabecera: str = Query("cabecera", description="Nombre de la hoja de cabecera (default: 'cabecera')"),
        hoja_detalle: str = Query("detalle", description="Nombre de la hoja de detalle (default: 'detalle')"),
        validar_sap: bool = Query(True, description="Validar códigos de producto contra SAP"),
        sap_obligatorio: bool = Query(True, description="Si True, errores de SAP bloquean la importación. Si False, solo genera warnings"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Importa y parsea un archivo Excel de pedido en formato v1.0.
        
        **Formato esperado (Template_Pedido_Inicial_v1.0.xlsx):**
        - **Hoja 1: "cabecera"** - Formato clave-valor (Campo | Valor | Ejemplo)
        - **Hoja 2: "detalle"** - Formato tabular con:
          - Columnas A-J: Información del producto (CODIGO PRODUCTO, MARCA, CODIGO BARRAS, etc.)
          - Columnas K-M: Bodegas centrales (RL-CD, OUT-CD, REG-CD) - NO incluidas en SUBTOTAL
          - Columnas N+: Tiendas individuales - SÍ incluidas en SUBTOTAL (parsea hasta última columna con información)
        
        **Solo parsing técnico:** lee, normaliza y valida estructura.
        NO aplica reglas de negocio, NO consolida duplicados.
        NO calcula SUBTOTAL ni TOTAL - solo parsea los valores que contiene el Excel.
        
        **Validaciones técnicas:**
        - Extensión: .xlsx
        - Tamaño máximo: 10 MB
        - Hojas obligatorias: "cabecera" y "detalle" (en minúsculas)
        - Columnas obligatorias en detalle: CODIGO PRODUCTO (columna A)
        - Parsea desde columna N (índice 13) hasta la última columna con información
        
        **Estructura de respuesta:**
        ```json
        {
            "cabecera": {...},
            "resumen": {
                "filasLeidas": 120,
                "filasValidas": 115,
                "filasInvalidas": 5
            },
            "errores": [...],
            "data": [...]
        }
        ```
        
        Returns:
            JSON con resultado del parsing técnico incluyendo cabecera y detalle
        """
        try:
            # Validar archivo
            file_name = file.filename.lower() if file.filename else ""
            if not file_name.endswith('.xlsx'):
                raise HTTPException(
                    status_code=400,
                    detail="Formato de archivo no permitido. Solo se permiten archivos .xlsx"
                )
            
            # Leer contenido del archivo
            content = await file.read()
            file_size = len(content)
            
            # Validar tamaño
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"El archivo es demasiado grande. Tamaño máximo: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
                )
            
            if file_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail="El archivo está vacío"
                )
            
            # Parsear Excel (solo parsing técnico)
            from src.database.services.pedido_service import PedidoService
            
            service = PedidoService()
            resultado = service.parsear_excel_pedido(
                file_content=content,
                hoja_cabecera=hoja_cabecera,
                hoja_detalle=hoja_detalle
            )
            
            # ✅ VALIDACIÓN SAP POST-PARSING (si está habilitada)
            if validar_sap and resultado.get("data"):
                from src.database.services.pedido_validator import PedidoValidator
                
                # Extraer códigos únicos de productos (performance: validar una vez por código)
                codigos_productos = list(set([
                    item.get("codigoProducto")
                    for item in resultado.get("data", [])
                    if item.get("codigoProducto")
                ]))
                
                if codigos_productos:
                    validator = PedidoValidator()
                    validacion_sap = validator.validar_productos_existen_en_sap_con_sugerencias(
                        codigos_productos=codigos_productos,
                        usar_cache=True,
                        sap_obligatorio=sap_obligatorio,
                        incluir_sugerencias=True,
                        limite_sugerencias=20
                    )
                    
                    # Mapear códigos a filas para reportar errores por fila
                    codigo_a_filas = {}
                    for item in resultado.get("data", []):
                        codigo = item.get("codigoProducto")
                        fila = item.get("filaOrigen")
                        if codigo and fila:
                            if codigo not in codigo_a_filas:
                                codigo_a_filas[codigo] = []
                            codigo_a_filas[codigo].append(fila)
                    
                    # Agregar errores y warnings por fila
                    codigos_no_encontrados = set(validacion_sap.get("no_encontrados", []))
                    codigos_errores = set(validacion_sap.get("errores", []))
                    codigos_warnings = set(validacion_sap.get("warnings", []))
                    
                    # Errores: códigos no encontrados o errores críticos
                    for codigo in (codigos_no_encontrados | codigos_errores):
                        detalle_codigo = validacion_sap.get("detalle", {}).get(codigo, {})
                        mensaje = detalle_codigo.get("mensaje") or f"El código de producto '{codigo}' no es válido en SAP"
                        
                        for fila in codigo_a_filas.get(codigo, []):
                            resultado["errores"].append({
                                "fila": fila,
                                "campo": "CodigoProducto",
                                "tipo": "ERROR",
                                "mensaje": mensaje
                            })
                    
                    # Warnings
                    for codigo in codigos_warnings:
                        detalle_codigo = validacion_sap.get("detalle", {}).get(codigo, {})
                        mensaje = detalle_codigo.get("mensaje") or f"No se pudo validar el código '{codigo}' en SAP"
                        
                        for fila in codigo_a_filas.get(codigo, []):
                            resultado["errores"].append({
                                "fila": fila,
                                "campo": "CodigoProducto",
                                "tipo": "WARNING",
                                "mensaje": mensaje
                            })
                    
                    # Recalcular filasValidas/filasInvalidas
                    filas_con_errores_criticos = set()
                    for error in resultado.get("errores", []):
                        if error.get("tipo") == "ERROR":
                            fila = error.get("fila")
                            if fila and fila > 0:
                                filas_con_errores_criticos.add(fila)
                    
                    filas_leidas = resultado["resumen"].get("filasLeidas", 0)
                    filas_invalidas_originales = resultado["resumen"].get("filasInvalidas", 0)
                    filas_invalidas_finales = max(filas_invalidas_originales, len(filas_con_errores_criticos))
                    
                    resultado["resumen"]["filasInvalidas"] = filas_invalidas_finales
                    resultado["resumen"]["filasValidas"] = max(0, filas_leidas - filas_invalidas_finales)
                    
                    # Agregar resumen de validación SAP
                    resultado["validacion_sap"] = {
                        "total_codigos": len(codigos_productos),
                        "validos": len(validacion_sap.get("validos", [])),
                        "no_encontrados": len(codigos_no_encontrados),
                        "errores": len(codigos_errores),
                        "warnings": len(codigos_warnings),
                        "todos_validos": validacion_sap.get("todos_validos", False),
                        "detalle_validacion": {
                            codigo: {
                                "existe": info.get("existe"),
                                "severity": info.get("severity"),
                                "error": info.get("error"),
                                "mensaje": info.get("mensaje"),
                                "mba3": info.get("mba3"),
                                "sugerencias_sap": info.get("sugerencias_sap", [])
                            }
                            for codigo, info in validacion_sap.get("detalle", {}).items()
                        }
                    }
                    
                    logger.info(
                        f"📊 Validación SAP: {len(validacion_sap.get('validos', []))} válidos, "
                        f"{len(codigos_no_encontrados)} no encontrados, "
                        f"{len(codigos_errores)} errores, {len(codigos_warnings)} warnings"
                    )
            
            return JSONResponse(status_code=200, content=resultado)
            
        except HTTPException:
            raise
        except BusinessException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al importar Excel: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al importar el archivo: {str(e)}"
            )
    
    @app.post("/api/pedidos", 
             response_model=CrearPedidoResponse,
             tags=["Pedidos"])
    async def crear_pedido_manual(
        request_body: CrearPedidoRequest = Body(..., description="Datos del pedido a crear"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Crea un pedido manualmente desde la pantalla web (HU-01 - Carga por Pantalla).
        
        Este endpoint permite crear pedidos directamente desde la interfaz web
        sin necesidad de subir un archivo Excel.
        
        Returns:
            JSON con resultado completo de creación del pedido
        """
        try:
            from src.database.services.pedido_service import PedidoService
            
            service = PedidoService()
            usuario_id = user.get("sub") or user.get("user_id")
            
            datos_pedido = request_body.model_dump(exclude_none=False)
            
            logger.debug(f"📦 Datos recibidos para crear pedido manual: {datos_pedido}")
            if datos_pedido.get("articulos"):
                logger.debug(f"📦 Primer artículo recibido: {datos_pedido['articulos'][0]}")
            
            resultado = service.crear_pedido_manual(
                datos_pedido=datos_pedido,
                usuario_id=usuario_id,
                validar_productos=datos_pedido.get("validar_productos", True),
                validar_tiendas=datos_pedido.get("validar_tiendas", True)
            )
            
            # Determinar código de estado HTTP
            status_code = 200
            if resultado["status"] == "validation_error":
                status_code = 400
            elif resultado["status"] == "error":
                if resultado.get("error_tipo") == "numero_pedido_duplicado":
                    status_code = 400
                else:
                    status_code = 500
            
            return JSONResponse(status_code=status_code, content=resultado)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al crear pedido manual: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al crear el pedido: {str(e)}"
            )
    
    @app.put("/api/pedidos/{pedido_id}",
             response_model=ModificarPedidoCabeceraResponse,
             tags=["Pedidos - Edición"])
    async def modificar_pedido_cabecera(
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: ModificarPedidoCabeceraRequest = Body(..., description="Datos de la cabecera a modificar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Modifica la cabecera de un pedido (HU-03 - Modificación de pedidos).
        
        Este endpoint permite modificar los datos de la cabecera del pedido.
        
        Returns:
            JSON con resultado de la modificación
        """
        try:
            datos_cabecera = request_body.model_dump(exclude_unset=True)
            campos_modificados = list(datos_cabecera.keys())
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                pedido_existente = repo.get_pedido_completo(pedido_id)
                if not pedido_existente:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                resultado = repo.update_cabecera(pedido_id, datos_cabecera)
                
                if not resultado:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "update_failed",
                            "message": "No se pudo actualizar la cabecera del pedido"
                        }
                    )
            
            logger.info(f"✅ Cabecera del pedido {pedido_id} actualizada por usuario {user.get('username', 'UNKNOWN')}")
            
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "success",
                    "message": "Cabecera del pedido actualizada correctamente",
                    "pedido_id": pedido_id,
                    "campos_modificados": campos_modificados
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al modificar cabecera del pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al modificar cabecera del pedido: {str(e)}"
                }
            )

    @app.post("/api/pedidos/{pedido_id}/enviar", tags=["Pedidos"])
    async def enviar_pedido(
        pedido_id: str = Path(..., description="UUID del pedido a enviar a EL RAYO"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Enviar pedido a EL RAYO: cambia estado de BORRADOR a NUEVO_PEDIDO y envía notificación por correo.

        Solo se permite para pedidos en estado BORRADOR (estado_id = 1).
        Valida que el pedido tenga detalles; si el correo falla, el pedido no se marca como enviado.

        - **404**: Pedido no encontrado.
        - **400**: Pedido no en BORRADOR, sin detalles o fallo al enviar correo.
        - **200**: Pedido enviado (estado actualizado, correo enviado).
        """
        try:
            from src.database.services.pedido_service import PedidoService
            service = PedidoService()
            usuario_id = get_user_id(user)
            resultado = service.enviar_pedido(pedido_id=pedido_id, usuario_id=usuario_id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=resultado
            )
        except BusinessException as e:
            if e.error_code == "not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": e.error_code, "message": e.message}
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": e.error_code, "message": e.message}
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al enviar pedido {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error al enviar el pedido: {str(e)}"
                }
            )

    @app.post("/api/pedidos/{pedido_id}/cancelar", tags=["Pedidos"])
    async def cancelar_pedido(
        pedido_id: str = Path(..., description="UUID del pedido a cancelar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Cancelar un pedido (cambiar estado a CANCELADO y notificar a EL RAYO).
        
        **Usado desde:** Vista Redistribución, botón "Cancelar Pedido".
        
        **Comportamiento:**
        - Cambia el estado del pedido a CANCELADO (estado_id = 19).
        - Envía correo a EL RAYO notificando la cancelación.
        - **No elimina** el pedido de la base de datos.
        
        **Restricciones:**
        - Solo permitido en estados anteriores a Confirmado redistribución (estado_id < 10).
        - El botón debe estar deshabilitado desde Confirmado redistribución en adelante.
        
        **Respuestas:**
        - **200**: Pedido cancelado correctamente, devuelve el pedido actualizado.
        - **404**: Pedido no encontrado.
        - **400**: Pedido no está en estado permitido para cancelar.
        - **500**: Error interno.
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                pedido = repo.get_pedido_completo(pedido_id)
                
                if not pedido:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                # Validar estado: solo permitir cancelar si estado_id < ESTADO_LIMITE_CANCELAR_PEDIDO (10)
                cabecera = pedido.get("cabecera", {})
                estado_id = cabecera.get("estado_id")
                if estado_id is None:
                    from src.database.pedido_estados import estado_id_desde_legacy
                    estado_id = estado_id_desde_legacy(cabecera.get("estado"))
                try:
                    estado_id = int(estado_id) if estado_id is not None else None
                except (TypeError, ValueError):
                    estado_id = None
                
                if estado_id is None or estado_id >= ESTADO_LIMITE_CANCELAR_PEDIDO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "estado_no_permitido",
                            "message": "El pedido no puede cancelarse porque está en estado Confirmado redistribución o posterior."
                        }
                    )
                
                # Cambiar estado a CANCELADO
                repo.update_estado(pedido_id, ESTADO_CANCELADO)
                
                # Obtener pedido actualizado
                pedido_actualizado = repo.get_pedido_completo(pedido_id)
                numero_pedido = (pedido_actualizado.get("cabecera") or {}).get("numero_pedido")
                
                # Notificar a EL RAYO
                try:
                    from src.utils.email_notifier import send_pedido_cancelado_notification
                    send_pedido_cancelado_notification(
                        pedido_id=pedido_id,
                        numero_pedido=numero_pedido,
                        usuario_id=user.get("username") or user.get("sub"),
                    )
                except Exception as notif_err:
                    logger.warning(f"⚠️ No se pudo enviar notificación de pedido cancelado a EL RAYO: {notif_err}")
                
                # Calcular flags de UI
                _eid = pedido_actualizado.get("cabecera", {}).get("estado_id")
                try:
                    _eid = int(_eid) if _eid is not None else None
                except (TypeError, ValueError):
                    _eid = None
                pedido_actualizado["puede_descartar"] = _eid in ESTADOS_PUEDE_DESCARTAR
                pedido_actualizado["puede_cancelar_pedido"] = _eid is not None and _eid < ESTADO_LIMITE_CANCELAR_PEDIDO
                
                logger.info(f"✅ Pedido {pedido_id} cancelado por usuario {user.get('username', 'UNKNOWN')}")
                return JSONResponse(status_code=200, content=pedido_actualizado)
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al cancelar pedido {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al cancelar el pedido: {str(e)}"
                }
            )

    @app.delete("/api/pedidos/{pedido_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Pedidos"])
    async def descartar_o_cancelar_pedido(
        pedido_id: str = Path(..., description="UUID del pedido a eliminar"),
        notificar_el_rayo: bool = Query(
            False,
            description="Si True, envía correo a EL RAYO notificando la cancelación (usar solo desde 'Cancelar Pedido' en Redistribución). Si False, determina automáticamente si notificar según el estado del pedido.",
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Eliminar un pedido (Descartar o Cancelar Pedido).

        **Dos flujos en el frontend:**
        
        1. **Descartar (Cargar Plantilla)**: llamar sin `notificar_el_rayo` o con `notificar_el_rayo=false`.
           - Interfaz: `/cargar-plantilla/{numero_pedido}`
           - Estados permitidos: **BORRADOR (1)** y **NUEVO PEDIDO (2)**
           - Si el estado es **BORRADOR (1)**: NO envía email (solo elimina).
           - Si el estado es **NUEVO PEDIDO (2)**: envía email a EL RAYO notificando el descarte.
        
        2. **Cancelar Pedido (Redistribución)**: llamar con `notificar_el_rayo=true`. 
           - Interfaz: `/redistribucion`
           - Borra el pedido **y** envía correo a EL RAYO.
           - Permitido solo en estados **anteriores** a Confirmado redistribución (estado_id < 10).

        **Nota:** Para eliminar desde **Detalle del Pedido** (estado GESTIONAR PEDIDO), 
        usar el endpoint `/api/pedidos/{pedido_id}/eliminar` en su lugar.

        **Restricciones:**
        - No se permite si el pedido tiene respuesta de proveedor, redistribución confirmada u orden de compra

        **Respuestas:**
        - **204**: Pedido eliminado correctamente
        - **400**: Pedido no está en estado permitido
        - **404**: Pedido no encontrado
        - **409**: Pedido tiene información asociada
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                ok, error_code, message = repo.validar_puede_descartar(
                    pedido_id, es_cancelar_pedido=notificar_el_rayo
                )
                if not ok:
                    if error_code == "not_found":
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": error_code, "message": message}
                        )
                    if error_code in ("estado_no_borrador", "estado_no_permitido"):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"error": error_code, "message": message}
                        )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={"error": error_code, "message": message}
                    )
                
                # Obtener estado_id y numero_pedido antes de eliminar
                pedido_data = repo.get_pedido_completo(pedido_id)
                numero_pedido = (pedido_data.get("cabecera") or {}).get("numero_pedido") if pedido_data else None
                estado_id = (pedido_data.get("cabecera") or {}).get("estado_id") if pedido_data else None
                
                # Eliminar el pedido
                repo.delete_pedido(pedido_id)
                
                # Determinar si se debe enviar notificación a EL RAYO
                enviar_notificacion = False
                
                if notificar_el_rayo:
                    # Caso 1: "Cancelar Pedido" desde Redistribución → siempre notificar
                    enviar_notificacion = True
                elif estado_id == ESTADO_NUEVO_PEDIDO:
                    # Caso 2: "Descartar" desde Cargar Plantilla en estado NUEVO PEDIDO (2) → notificar
                    enviar_notificacion = True
                # Caso 3: "Descartar" en estado BORRADOR (1) o GESTIONAR PEDIDO (3) → NO notificar
                
                if enviar_notificacion:
                    try:
                        from src.utils.email_notifier import send_pedido_descartado_notification
                        send_pedido_descartado_notification(
                            pedido_id=pedido_id,
                            numero_pedido=numero_pedido,
                            usuario_id=user.get("username") or user.get("sub"),
                        )
                        logger.info(f"📧 Notificación de pedido descartado enviada a EL RAYO (estado_id={estado_id})")
                    except Exception as notif_err:
                        logger.warning(f"⚠️ No se pudo enviar notificación de pedido descartado a EL RAYO: {notif_err}")
                else:
                    logger.info(f"⏭️ No se envía notificación (estado={estado_id}, notificar_el_rayo={notificar_el_rayo})")
                    
            logger.info(f"✅ Pedido {pedido_id} eliminado por usuario {user.get('username', 'UNKNOWN')} (notificar_el_rayo={notificar_el_rayo}, estado_id={estado_id})")
            return None
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al descartar pedido {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error al descartar el pedido: {str(e)}"
                }
            )

    @app.delete("/api/pedidos/{pedido_id}/eliminar", status_code=status.HTTP_204_NO_CONTENT, tags=["Pedidos"])
    async def eliminar_pedido(
        pedido_id: str = Path(..., description="UUID del pedido a eliminar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Eliminar un pedido desde la interfaz de Detalle del Pedido (botón "Eliminar Pedido").
        
        **Uso exclusivo:**
        - Interfaz: **Detalle del Pedido** (`/pedidos/{pedido_id}`)
        - Estado permitido: **GESTIONAR PEDIDO (3)** únicamente
        - Comportamiento: Elimina el pedido y **envía notificación a MABEL TRADING**
        
        **Notificaciones:**
        - ✅ Se envía email a MABEL TRADING confirmando la eliminación
        - ❌ NO se envía email a EL RAYO
        
        **Diferencia con "Descartar":**
        - "Descartar": Desde Cargar Plantilla, estados 1-2, notifica a EL RAYO solo en estado 2
        - "Eliminar Pedido": Desde Detalle, estado 3 solamente, notifica a MABEL TRADING
        
        **Restricciones:**
        - No se permite si el pedido tiene respuesta de proveedor, redistribución confirmada u orden de compra
        
        **Respuestas:**
        - **204**: Pedido eliminado correctamente
        - **400**: Pedido no está en estado GESTIONAR PEDIDO (3)
        - **404**: Pedido no encontrado
        - **409**: Pedido tiene información asociada
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Validar que se puede eliminar (solo estado GESTIONAR PEDIDO)
                ok, error_code, message = repo.validar_puede_eliminar(pedido_id)
                
                if not ok:
                    if error_code == "not_found":
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": error_code, "message": message}
                        )
                    if error_code == "estado_no_permitido":
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"error": error_code, "message": message}
                        )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={"error": error_code, "message": message}
                    )
                
                # Obtener datos antes de eliminar (para logging y notificación)
                pedido_data = repo.get_pedido_completo(pedido_id)
                numero_pedido = (pedido_data.get("cabecera") or {}).get("numero_pedido") if pedido_data else None
                estado_id = (pedido_data.get("cabecera") or {}).get("estado_id") if pedido_data else None
                
                # Eliminar el pedido
                repo.delete_pedido(pedido_id)
                
                # Enviar notificación a MABEL TRADING
                try:
                    from src.utils.email_notifier import send_pedido_eliminado_mabel_notification
                    send_pedido_eliminado_mabel_notification(
                        pedido_id=pedido_id,
                        numero_pedido=numero_pedido,
                        usuario_id=user.get("username") or user.get("sub"),
                    )
                    logger.info(f"📧 Notificación de pedido eliminado enviada a MABEL TRADING")
                except Exception as notif_err:
                    logger.warning(f"⚠️ No se pudo enviar notificación de pedido eliminado a MABEL TRADING: {notif_err}")
                
                logger.info(f"✅ Pedido {pedido_id} eliminado desde Detalle del Pedido (botón Eliminar) por usuario {user.get('username', 'UNKNOWN')} (estado_id={estado_id}, numero_pedido={numero_pedido})")
                
            return None
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al eliminar pedido {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error al eliminar el pedido: {str(e)}"
                }
            )

    @app.get("/api/pedidos/{pedido_id}/descargar-csv", tags=["Pedidos"])
    @app.get("/api/pedidos/{pedido_id}/descargar-excel", tags=["Pedidos"])
    async def descargar_pedido_excel(
        pedido_id: str = Path(..., description="UUID del pedido a descargar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Descargar información del pedido en formato Excel (.xlsx).
        
        **Uso:**
        - Interfaz: Detalle del Pedido (`/pedidos/{pedido_id}`)
        - Botón: "Descargar Excel"
        - Estado requerido: **CONFIRMADO (4)** (ESTADO_REDISTRIBUCION)
        
        **Contenido del Excel:**
        - Información de cabecera del pedido
        - Detalles de todos los artículos
        - Distribuciones por tienda
        
        **Formato:**
        - Archivo Excel (.xlsx) con 3 hojas:
          - Hoja 1: Información de cabecera
          - Hoja 2: Detalles de artículos
          - Hoja 3: Distribución por tiendas
        
        **Respuestas:**
        - **200**: Archivo Excel descargado correctamente
        - **400**: Pedido no está en estado CONFIRMADO (4)
        - **404**: Pedido no encontrado
        """
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Obtener pedido completo
                pedido_data = repo.get_pedido_completo(pedido_id)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"error": "not_found", "message": "Pedido no encontrado"}
                    )
                
                cabecera = pedido_data.get("cabecera", {})
                estado_id = cabecera.get("estado_id")
                
                # Validar que esté en estado CONFIRMADO (4)
                if estado_id != ESTADO_REDISTRIBUCION:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "estado_no_permitido",
                            "message": f"El pedido debe estar en estado CONFIRMADO para descargar. Estado actual: {cabecera.get('estado_nombre', 'Desconocido')}"
                        }
                    )
                
                # Crear libro de Excel
                wb = Workbook()
                wb.remove(wb.active)  # Eliminar la hoja por defecto
                
                # Estilos
                header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                header_font = Font(bold=True, color="FFFFFF", size=12)
                title_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
                title_font = Font(bold=True, size=14)
                border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )
                
                # === HOJA 1: INFORMACIÓN DE CABECERA ===
                ws_cabecera = wb.create_sheet("Información del Pedido")
                
                # Título
                ws_cabecera['A1'] = "INFORMACIÓN DEL PEDIDO"
                ws_cabecera['A1'].font = title_font
                ws_cabecera['A1'].fill = title_fill
                ws_cabecera.merge_cells('A1:B1')
                
                # Datos de cabecera
                row = 3
                info_fields = [
                    ("Número de Pedido", cabecera.get("numero_pedido", "N/A")),
                    ("Pedido ID", pedido_id),
                    ("Estado", cabecera.get("estado_nombre", "N/A")),
                    ("Fecha Pedido", cabecera.get("fecha_pedido", "N/A")),
                    ("Fecha Entrega", cabecera.get("fecha_entrega", "N/A")),
                    ("Proveedor", cabecera.get("proveedor_nombre", "N/A")),
                    ("Comprador", cabecera.get("comprador_nombre", "N/A")),
                    ("Código Comprador", cabecera.get("comprador_codigo", "N/A")),
                    ("ODC", cabecera.get("odc", "N/A")),
                    ("Forma de Pago", cabecera.get("forma_pago", "N/A")),
                    ("Origen Traslado", cabecera.get("origen_traslado", "N/A")),
                    ("Serie", cabecera.get("serie", "N/A")),
                    ("Archivo", cabecera.get("archivo_nombre", "N/A")),
                    ("Creado Por", cabecera.get("creado_por", "N/A")),
                    ("Fecha de Creación", cabecera.get("creado_en", "N/A")),
                ]
                
                for field, value in info_fields:
                    ws_cabecera[f'A{row}'] = field
                    ws_cabecera[f'A{row}'].font = Font(bold=True)
                    ws_cabecera[f'B{row}'] = value
                    row += 1
                
                # Ajustar anchos de columna
                ws_cabecera.column_dimensions['A'].width = 25
                ws_cabecera.column_dimensions['B'].width = 50
                
                # === HOJA 2: DETALLES DE ARTÍCULOS ===
                ws_detalles = wb.create_sheet("Detalles de Artículos")
                
                # Título
                ws_detalles['A1'] = "DETALLES DE ARTÍCULOS"
                ws_detalles['A1'].font = title_font
                ws_detalles['A1'].fill = title_fill
                ws_detalles.merge_cells('A1:H1')
                
                # Determinar si usamos datos de distribucion_confirmada o pedido_detalle
                usar_distribucion_confirmada = estado_id == ESTADO_REDISTRIBUCION
                
                # Encabezados de la tabla de detalles
                headers = [
                    "Código Producto",
                    "Descripción",
                    "Total Original",
                    "Costo Unitario",
                    "Total Confirmado",
                    "PACK",
                    "Código de Barras",
                    "Comentario"
                ]
                
                for col_num, header in enumerate(headers, 1):
                    cell = ws_detalles.cell(row=3, column=col_num)
                    cell.value = header
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    cell.border = border
                
                row = 4
                total_cantidad = 0
                total_valor = 0.0
                detalles_para_distribucion = []
                version_actual = None
                
                # Intentar usar datos de distribucion_confirmada si está en estado CONFIRMADO
                rows_data = []
                if usar_distribucion_confirmada:
                    # ✅ ESTADO CONFIRMADO: Intentar usar datos de distribucion_confirmada
                    try:
                        from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
                        
                        dist_repo = DistribucionConfirmadaRepository(conn)
                        version_actual = dist_repo.get_version_actual(pedido_id)
                        
                        if version_actual:
                            logger.info(f"📊 Intentando usar datos de distribucion_confirmada (versión {version_actual})")
                            
                            # Query directo para obtener datos agregados con costos
                            # Incluye LEFT JOIN con pedido_sap_procesamiento_detalle para obtener item_code_sap y unidad_sap
                            cursor = conn.cursor()
                            cursor.execute("""
                                SELECT 
                                    dc.pedido_detalle_id,
                                    pd.codigo_interno,
                                    pd.descripcion_sap,
                                    pd.codigo_barras,
                                    pd.pack,
                                    SUM(dc.cantidad_asignada) AS total_asignada,
                                    MAX(dc.costo_unitario_ajustado) AS costo_unitario_ajustado,
                                    SUM(dc.subtotal_ajustado) AS subtotal_ajustado,
                                    ps.item_code_sap,
                                    ps.unidad_sap,
                                    pd.comentario
                                FROM distribucion_confirmada dc
                                INNER JOIN pedido_detalle pd ON dc.pedido_detalle_id = pd.pedido_detalle_id
                                LEFT JOIN pedido_sap_procesamiento_detalle ps ON pd.pedido_detalle_id = ps.pedido_detalle_id
                                WHERE dc.pedido_id = ? AND dc.version = ?
                                GROUP BY dc.pedido_detalle_id, pd.codigo_interno, pd.descripcion_sap, 
                                         pd.codigo_barras, pd.pack, ps.item_code_sap, ps.unidad_sap, pd.comentario
                                ORDER BY pd.codigo_interno
                            """, (pedido_id, version_actual))
                            
                            rows_data = cursor.fetchall()
                            cursor.close()
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo obtener datos de distribucion_confirmada: {e}")
                        rows_data = []
                
                # FALLBACK: Si no hay datos en distribucion_confirmada, usar pedido_detalle directamente
                if usar_distribucion_confirmada and len(rows_data) == 0:
                    logger.info(f"⚠️ No hay datos en distribucion_confirmada, usando pedido_detalle directamente")
                    # Obtener datos directamente de pedido_detalle con suma de cantidades de tiendas
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT 
                            pd.pedido_detalle_id,
                            pd.codigo_interno,
                            pd.descripcion_sap,
                            pd.codigo_barras,
                            pd.pack,
                            ISNULL(SUM(pdt.cantidad), 0) AS total_cantidad,
                            pd.costo_doc_sin_iva AS costo_unitario,
                            pd.total AS total_linea,
                            ps.item_code_sap,
                            ps.unidad_sap,
                            pd.comentario
                        FROM pedido_detalle pd
                        LEFT JOIN pedido_detalle_tienda pdt ON pd.pedido_detalle_id = pdt.pedido_detalle_id
                        LEFT JOIN pedido_sap_procesamiento_detalle ps ON pd.pedido_detalle_id = ps.pedido_detalle_id
                        WHERE pd.pedido_id = ?
                        GROUP BY pd.pedido_detalle_id, pd.codigo_interno, pd.descripcion_sap, 
                                 pd.codigo_barras, pd.pack, pd.costo_doc_sin_iva, pd.total,
                                 ps.item_code_sap, ps.unidad_sap, pd.comentario
                        ORDER BY pd.codigo_interno
                    """, (pedido_id,))
                    
                    rows_data = cursor.fetchall()
                    cursor.close()
                
                # Procesar datos (ya sea de distribucion_confirmada o pedido_detalle)
                if usar_distribucion_confirmada and len(rows_data) > 0:
                    # Procesar filas obtenidas
                    for row_data in rows_data:
                        pedido_detalle_id = str(row_data[0])
                        codigo_interno = row_data[1] or ""
                        descripcion = row_data[2] or ""
                        codigo_barras = row_data[3] or ""
                        pack_original = row_data[4] or ""
                        cantidad = row_data[5] or 0
                        costo_unitario = float(row_data[6]) if row_data[6] is not None else 0.0
                        total_linea = float(row_data[7]) if row_data[7] is not None else 0.0
                        item_code_sap = row_data[8] or ""  # De pedido_sap_procesamiento
                        unidad_sap = row_data[9] or ""  # De pedido_sap_procesamiento
                        comentario = row_data[10] or ""  # Comentario
                        
                        # Usar item_code_sap si existe, sino codigo_interno
                        sku_sap = item_code_sap if item_code_sap else codigo_interno
                        # Usar unidad_sap si existe, sino pack original
                        unidad = unidad_sap if unidad_sap else pack_original
                        
                        total_cantidad += cantidad
                        total_valor += total_linea
                        
                        # Escribir fila en Excel
                        ws_detalles.cell(row=row, column=1, value=codigo_interno)
                        ws_detalles.cell(row=row, column=2, value=descripcion)
                        ws_detalles.cell(row=row, column=3, value=cantidad)
                        ws_detalles.cell(row=row, column=4, value=costo_unitario)
                        ws_detalles.cell(row=row, column=5, value=total_linea)
                        ws_detalles.cell(row=row, column=6, value=unidad)
                        ws_detalles.cell(row=row, column=7, value=codigo_barras)
                        ws_detalles.cell(row=row, column=8, value=comentario)
                        
                        # Aplicar formato numérico
                        ws_detalles.cell(row=row, column=4).number_format = '#,##0.00'
                        ws_detalles.cell(row=row, column=5).number_format = '#,##0.00'
                        
                        row += 1
                        
                        # Obtener distribuciones por tienda para este producto
                        distribuciones = []
                        try:
                            if version_actual:
                                # Desde distribucion_confirmada (si existe)
                                cursor_dist = conn.cursor()
                                cursor_dist.execute("""
                                    SELECT 
                                        t.codigo AS tienda_codigo,
                                        t.nombre AS tienda_nombre,
                                        dc.cantidad_asignada,
                                        dc.costo_unitario_ajustado,
                                        dc.subtotal_ajustado
                                    FROM distribucion_confirmada dc
                                    INNER JOIN tienda t ON dc.tienda_id = t.tienda_id
                                    WHERE dc.pedido_detalle_id = ? AND dc.pedido_id = ? AND dc.version = ?
                                    ORDER BY t.codigo
                                """, (pedido_detalle_id, pedido_id, version_actual))
                                
                                for dist_row in cursor_dist.fetchall():
                                    distribuciones.append({
                                        "tienda_codigo": dist_row[0],
                                        "tienda_nombre": dist_row[1],
                                        "cantidad_asignada": dist_row[2],
                                        "costo_unitario_ajustado": float(dist_row[3]) if dist_row[3] is not None else 0.0,
                                        "subtotal_ajustado": float(dist_row[4]) if dist_row[4] is not None else 0.0
                                    })
                                cursor_dist.close()
                            else:
                                # FALLBACK: Desde pedido_detalle_tienda (sin costos ajustados)
                                cursor_dist = conn.cursor()
                                cursor_dist.execute("""
                                    SELECT 
                                        t.codigo AS tienda_codigo,
                                        t.nombre AS tienda_nombre,
                                        pdt.cantidad,
                                        pd.costo_doc_sin_iva AS costo_unitario,
                                        (pdt.cantidad * pd.costo_doc_sin_iva) AS subtotal
                                    FROM pedido_detalle_tienda pdt
                                    INNER JOIN tienda t ON pdt.tienda_id = t.tienda_id
                                    INNER JOIN pedido_detalle pd ON pdt.pedido_detalle_id = pd.pedido_detalle_id
                                    WHERE pdt.pedido_detalle_id = ?
                                    ORDER BY t.codigo
                                """, (pedido_detalle_id,))
                                
                                for dist_row in cursor_dist.fetchall():
                                    distribuciones.append({
                                        "tienda_codigo": dist_row[0],
                                        "tienda_nombre": dist_row[1],
                                        "cantidad_asignada": dist_row[2],
                                        "costo_unitario_ajustado": float(dist_row[3]) if dist_row[3] is not None else 0.0,
                                        "subtotal_ajustado": float(dist_row[4]) if dist_row[4] is not None else 0.0
                                    })
                                cursor_dist.close()
                        except Exception as e:
                            logger.warning(f"⚠️ No se pudieron obtener distribuciones para detalle {pedido_detalle_id}: {e}")
                        
                        # Guardar para sección de distribución
                        detalles_para_distribucion.append({
                            "codigo_interno": codigo_interno,
                            "descripcion": descripcion,
                            "distribuciones": distribuciones
                        })
                else:
                    # Estado NO CONFIRMADO: Usar datos originales de pedido_detalle
                    detalles = pedido_data.get("detalles", [])
                    
                    for detalle in detalles:
                        codigo_interno = detalle.get("codigo_interno", "")
                        sku_sap = detalle.get("sku_sap", "")
                        descripcion = detalle.get("descripcion_sap", detalle.get("nombre_producto", ""))
                        cantidad = detalle.get("cantidad_total", 0)
                        precio_unitario = detalle.get("precio_unitario", 0.0)
                        total_linea = cantidad * precio_unitario
                        unidad = detalle.get("unidad_sap", "")
                        codigo_barras = detalle.get("codigo_barras", "")
                        comentario = detalle.get("comentario", "")
                        
                        total_cantidad += cantidad
                        total_valor += total_linea
                        
                        # Escribir fila en Excel
                        ws_detalles.cell(row=row, column=1, value=codigo_interno)
                        ws_detalles.cell(row=row, column=2, value=descripcion)
                        ws_detalles.cell(row=row, column=3, value=cantidad)
                        ws_detalles.cell(row=row, column=4, value=precio_unitario)
                        ws_detalles.cell(row=row, column=5, value=total_linea)
                        ws_detalles.cell(row=row, column=6, value=unidad)
                        ws_detalles.cell(row=row, column=7, value=codigo_barras)
                        ws_detalles.cell(row=row, column=8, value=comentario)
                        
                        # Aplicar formato numérico
                        ws_detalles.cell(row=row, column=4).number_format = '#,##0.00'
                        ws_detalles.cell(row=row, column=5).number_format = '#,##0.00'
                        
                        row += 1
                        
                        # Guardar para sección de distribución
                        detalles_para_distribucion.append({
                            "codigo_interno": codigo_interno,
                            "descripcion": descripcion,
                            "distribuciones": detalle.get("distribuciones", [])
                        })
                
                # Totales
                row += 1
                ws_detalles.cell(row=row, column=1, value="TOTALES").font = Font(bold=True)
                ws_detalles.cell(row=row, column=3, value=total_cantidad).font = Font(bold=True)
                ws_detalles.cell(row=row, column=5, value=total_valor).font = Font(bold=True)
                ws_detalles.cell(row=row, column=5).number_format = '#,##0.00'
                
                # Ajustar anchos de columna
                ws_detalles.column_dimensions['A'].width = 18  # Código Producto
                ws_detalles.column_dimensions['B'].width = 40  # Descripción
                ws_detalles.column_dimensions['C'].width = 14  # Total Original
                ws_detalles.column_dimensions['D'].width = 15  # Costo Unitario
                ws_detalles.column_dimensions['E'].width = 16  # Total Confirmado
                ws_detalles.column_dimensions['F'].width = 12  # PACK
                ws_detalles.column_dimensions['G'].width = 20  # Código de Barras
                ws_detalles.column_dimensions['H'].width = 30  # Comentario
                
                # === HOJA 3: DISTRIBUCIÓN POR TIENDAS ===
                ws_distribucion = wb.create_sheet("Distribución por Tiendas")
                
                # Título
                ws_distribucion['A1'] = "DISTRIBUCIÓN POR TIENDAS"
                ws_distribucion['A1'].font = title_font
                ws_distribucion['A1'].fill = title_fill
                ws_distribucion.merge_cells('A1:F1' if usar_distribucion_confirmada else 'A1:E1')
                
                # Encabezados de distribución
                if usar_distribucion_confirmada:
                    dist_headers = [
                        "Código Producto",
                        "Descripción",
                        "Código Tienda",
                        "Nombre Tienda",
                        "Cantidad Asignada",
                        "Costo Unitario"
                    ]
                else:
                    dist_headers = [
                        "Código Producto",
                        "Descripción",
                        "Código Tienda",
                        "Nombre Tienda",
                        "Cantidad Distribuida"
                    ]
                
                for col_num, header in enumerate(dist_headers, 1):
                    cell = ws_distribucion.cell(row=3, column=col_num)
                    cell.value = header
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    cell.border = border
                
                row = 4
                
                # Agrupar distribuciones por artículo
                for detalle in detalles_para_distribucion:
                    codigo_interno = detalle.get("codigo_interno", "")
                    descripcion = detalle.get("descripcion", "")
                    distribuciones = detalle.get("distribuciones", [])
                    
                    if distribuciones:
                        for dist in distribuciones:
                            if usar_distribucion_confirmada:
                                # Con costos para estado CONFIRMADO
                                ws_distribucion.cell(row=row, column=1, value=codigo_interno)
                                ws_distribucion.cell(row=row, column=2, value=descripcion)
                                ws_distribucion.cell(row=row, column=3, value=dist.get("tienda_codigo", ""))
                                ws_distribucion.cell(row=row, column=4, value=dist.get("tienda_nombre", ""))
                                ws_distribucion.cell(row=row, column=5, value=dist.get("cantidad_asignada", 0))
                                ws_distribucion.cell(row=row, column=6, value=float(dist.get('costo_unitario_ajustado', 0.0) or 0.0))
                                
                                ws_distribucion.cell(row=row, column=6).number_format = '#,##0.00'
                            else:
                                # Sin costos para otros estados
                                ws_distribucion.cell(row=row, column=1, value=codigo_interno)
                                ws_distribucion.cell(row=row, column=2, value=descripcion)
                                ws_distribucion.cell(row=row, column=3, value=dist.get("codigo_tienda", ""))
                                ws_distribucion.cell(row=row, column=4, value=dist.get("nombre_tienda", ""))
                                ws_distribucion.cell(row=row, column=5, value=dist.get("cantidad", 0))
                            
                            row += 1
                    else:
                        # Sin distribución
                        ws_distribucion.cell(row=row, column=1, value=codigo_interno)
                        ws_distribucion.cell(row=row, column=2, value=descripcion)
                        ws_distribucion.cell(row=row, column=3, value="Sin distribución")
                        row += 1
                
                # Ajustar anchos de columna
                ws_distribucion.column_dimensions['A'].width = 15
                ws_distribucion.column_dimensions['B'].width = 40
                ws_distribucion.column_dimensions['C'].width = 15
                ws_distribucion.column_dimensions['D'].width = 30
                ws_distribucion.column_dimensions['E'].width = 15
                if usar_distribucion_confirmada:
                    ws_distribucion.column_dimensions['F'].width = 15
                    ws_distribucion.column_dimensions['G'].width = 15
                
                # Agregar información de descarga en la hoja de cabecera
                row = ws_cabecera.max_row + 2
                ws_cabecera[f'A{row}'] = "Descargado por:"
                ws_cabecera[f'A{row}'].font = Font(bold=True)
                ws_cabecera[f'B{row}'] = user.get("username", "Desconocido")
                
                row += 1
                ws_cabecera[f'A{row}'] = "Fecha de descarga:"
                ws_cabecera[f'A{row}'].font = Font(bold=True)
                ws_cabecera[f'B{row}'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Guardar el libro de Excel en memoria
                excel_buffer = io.BytesIO()
                wb.save(excel_buffer)
                excel_buffer.seek(0)
                
                # Nombre del archivo
                numero_pedido = cabecera.get("numero_pedido", pedido_id)
                # Limpiar nombre para evitar caracteres inválidos en nombre de archivo
                numero_pedido_safe = re.sub(r'[^\w\-_\. ]', '_', numero_pedido)
                filename = f"pedido_{numero_pedido_safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                
                logger.info(f"✅ Excel generado para pedido {pedido_id} ({numero_pedido}) por usuario {user.get('username', 'UNKNOWN')}")
                
                # Retornar archivo Excel
                return StreamingResponse(
                    excel_buffer,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}",
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al generar Excel del pedido {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error al generar Excel del pedido: {str(e)}"
                }
            )
