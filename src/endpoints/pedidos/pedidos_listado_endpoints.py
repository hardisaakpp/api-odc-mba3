"""
Endpoints de listados y maestros de pedidos.
"""

import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.responses import JSONResponse

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.pedido_estados import ESTADO_BORRADOR, ESTADO_REDISTRIBUCION
from src.security.jwt_auth import verify_jwt_token, require_any_permission
from src.schemas import READ_RESPONSES
from .utils import get_user_id

logger = logging.getLogger(__name__)


def register_pedidos_listado_endpoints(app: FastAPI):
    """Registra endpoints de listados y maestros de pedidos."""

    @app.get("/api/pedidos", tags=["Pedidos"], responses=READ_RESPONSES)
    async def listar_pedidos(
        estado: Optional[str] = Query(None, description="Filtrar por estado del pedido"),
        fecha_desde: Optional[str] = Query(None, description="Filtrar desde fecha (YYYY-MM-DD)"),
        fecha_hasta: Optional[str] = Query(None, description="Filtrar hasta fecha (YYYY-MM-DD)"),
        proveedor_nombre: Optional[str] = Query(None, description="Buscar por nombre de proveedor (parcial)"),
        numero_pedido: Optional[str] = Query(None, description="Buscar por número de pedido (parcial)"),
        creado_por: Optional[str] = Query(None, description="Filtrar por usuario que creó el pedido"),
        limit: Optional[int] = Query(None, description="Límite de registros por página"),
        offset: Optional[int] = Query(None, description="Offset para paginación"),
        page: Optional[int] = Query(1, ge=1, description="Número de página (1-based, alternativa a offset)"),
        page_size: Optional[int] = Query(10, ge=1, le=100, description="Tamaño de página (snake_case)"),
        pageSize: Optional[int] = Query(None, ge=1, le=100, description="Tamaño de página (camelCase)"),
        solo_redistribucion: Optional[str] = Query(
            None,
            description="Si 'true', solo pedidos aptos para redistribución (estado >= CONFIRMADO POR EL RAYO, excluye CANCELADO y CANCELADO POR EL RAYO)"
        ),
        solo_pendientes_accion: Optional[str] = Query(
            None,
            description="Si 'true', solo pedidos que requieren acción (pendiente confirmación / respuesta proveedor / confirmado proveedor)"
        ),
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
        - `solo_redistribucion` (string, opcional) - Si "true", solo pedidos aptos para redistribución
          (estado >= "CONFIRMADO POR EL RAYO" y != "CANCELADO"). Para la vista /redistribucion.
        
        **Ejemplo:**
        ```
        GET /api/pedidos?estado=PENDIENTE_CONFIRMACION_PROVEEDOR&limit=20&offset=0
        GET /api/pedidos?fecha_desde=2025-01-01&fecha_hasta=2025-01-31&proveedor_nombre=RAYO
        GET /api/pedidos?solo_redistribucion=true&limit=10  # Para vista de redistribución
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
            # Parsear parámetro solo_redistribucion
            filtrar_redistribucion = (
                solo_redistribucion is not None
                and str(solo_redistribucion).lower() in ("true", "1")
            )
            filtrar_pendientes = (
                solo_pendientes_accion is not None
                and str(solo_pendientes_accion).lower() in ("true", "1")
            )
            size = pageSize if pageSize is not None else page_size
            if limit is not None:
                use_limit, use_offset = limit, offset or 0
            else:
                use_limit = size if size is not None else 10
                use_offset = ((page or 1) - 1) * use_limit
            
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                resultado = repo.get_pedidos_con_filtros(
                    estado=estado,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    proveedor_nombre=proveedor_nombre,
                    numero_pedido=numero_pedido,
                    creado_por=creado_por,
                    limit=use_limit,
                    offset=use_offset,
                    excluir_borrador=True,
                    solo_redistribucion=filtrar_redistribucion,
                    solo_pendientes_accion=filtrar_pendientes,
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
        page_size: Optional[int] = Query(10, ge=1, le=100, description="Tamaño de página (snake_case)"),
        pageSize: Optional[int] = Query(None, ge=1, le=100, description="Tamaño de página (camelCase, alias de page_size)"),
        limit: Optional[int] = Query(None, description="Límite de registros (alternativa a page_size)"),
        offset: Optional[int] = Query(None, description="Offset (alternativa a page)"),
        fecha_desde: Optional[str] = Query(None, description="Filtrar desde fecha (YYYY-MM-DD)"),
        fecha_hasta: Optional[str] = Query(None, description="Filtrar hasta fecha (YYYY-MM-DD)"),
        proveedor_nombre: Optional[str] = Query(None, description="Búsqueda parcial por proveedor"),
        numero_pedido: Optional[str] = Query(None, description="Búsqueda parcial por número de pedido"),
        creado_por: Optional[str] = Query(None, description="Filtrar por usuario creador"),
        redistribucion_confirmada: Optional[str] = Query(
            None,
            description="Si 'true', solo pedidos con redistribución ya confirmada (estado CONFIRMADO REDISTRIBUCION)"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Lista pedidos para la pantalla Revisar Redistribución, ordenados por creado_en DESC.
        
        **Filtro de estados:** Solo incluye pedidos enviados.
        
        **Estado incluido:**
        - CONFIRMADO_ENVIADO (12)

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
                use_size = size if size is not None else 10
                use_limit = use_size
                use_offset = ((page or 1) - 1) * use_size

            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                resultado = repo.get_pedidos_confirmados(
                    limit=use_limit,
                    offset=use_offset,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    proveedor_nombre=proveedor_nombre,
                    numero_pedido=numero_pedido,
                    creado_por=creado_por,
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
                        # Nombre del comprador (para columna COMPRADOR en frontend)
                        "comprador_nombre": row.get("comprador_nombre"),
                        # Alias genérico por compatibilidad con posibles UIs
                        "comprador": row.get("comprador_nombre"),
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
            description="Si true, último pedido apto para redistribución del usuario; si false, último en todo el sistema"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Obtiene el último pedido para la pantalla Revisar Redistribución.
        
        **Filtro de estados:** Solo incluye pedidos enviados.
        
        **Estado incluido:**
        - CONFIRMADO_ENVIADO (12)
        
        Para la pantalla Revisar Redistribución: al entrar en /redistribucion sin número de pedido,
        el front llama a este endpoint y, si hay resultado, redirige a
        /pedidos/{numero_pedido}/redistribucion.

        **Query Parameters:**
        - `solo_usuario` (bool, default: true) - Si true, último pedido del usuario; si false, último global.

        **Respuesta:** Objeto con cabecera básica (pedido_id, numero_pedido, estado, ...) o null.

        **Comportamiento por permiso:**
        - Usuario con solo odcsap.view (EL RAYO): se ignora solo_usuario y se devuelve siempre
          el último pedido visible en el sistema (sin filtrar por creado_por).
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

    @app.get("/api/pedidos/estados", tags=["Pedidos"], responses=READ_RESPONSES)
    async def listar_estados_pedido(
        contexto: Optional[str] = Query(
            None,
            description=(
                "Contexto de la vista para filtrar estados relevantes. "
                "Valores posibles: 'pedidos' (excluye BORRADOR), "
                "'cargar-plantilla' (incluye BORRADOR, solo del flujo de carga), "
                "'redistribucion' (solo estados aptos para redistribucion). "
                "Si no se indica, devuelve todos los estados activos."
            ),
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Devuelve la lista de estados de pedido disponibles para el dropdown
        del contenedor "Filtros de Búsqueda".
        
        Este endpoint alimenta los selects/dropdowns de filtro por estado en todas
        las interfaces de listas de pedidos. Devuelve únicamente los estados que
        el usuario visualiza en la UI, consultados directamente de la tabla
        maestra `pedido_estado`.
        
        **Query Parameters:**
        - `contexto` (string, opcional) - Determina qué estados incluir:
          - Sin valor / `null`: todos los estados activos
          - `"pedidos"`: excluye BORRADOR (para /mba3-consultas/pedidos)
          - `"cargar-plantilla"`: incluye BORRADOR (para /mba3-consultas/cargar-plantilla)
          - `"redistribucion"`: solo estados del flujo de redistribución
            (CONFIRMADO POR EL RAYO en adelante, sin CANCELADO ni finales)
        
        **Ejemplo:**
        ```
        GET /api/pedidos/estados
        GET /api/pedidos/estados?contexto=pedidos
        GET /api/pedidos/estados?contexto=redistribucion
        ```
        
        **Respuesta:**
        ```json
        {
            "status": "success",
            "data": [
                { "id": 1, "nombre": "BORRADOR", "orden": 1 },
                { "id": 2, "nombre": "NUEVO PEDIDO", "orden": 2 },
                ...
            ]
        }
        ```
        
        Returns:
            JSON con lista de estados disponibles para el filtro
        """
        try:
            # Determinar filtros según contexto
            excluir_ids: Optional[List[int]] = None
            solo_ids: Optional[List[int]] = None

            if contexto == "pedidos":
                # Lista general: excluir BORRADOR (no se muestran pedidos en ese estado)
                excluir_ids = [ESTADO_BORRADOR]
            elif contexto == "redistribucion":
                # Vista redistribución: solo estados relevantes para ese flujo
                from src.database.pedido_estados import (
                    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
                    ESTADO_CONFIRMADO_PROVEEDOR,
                    ESTADO_REDISTRIBUIDO,
                    ESTADO_PEDIDO_CONFIRMADO,
                    ESTADO_CONFIRMADO_ENVIADO,
                    ESTADO_PENDIENTE_LOGISTICA,
                    ESTADO_ERROR_DATOS_MAESTROS,
                )
                solo_ids = [
                    ESTADO_REDISTRIBUCION,               # 4  - CONFIRMADO POR EL RAYO
                    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,  # 5
                    ESTADO_CONFIRMADO_PROVEEDOR,         # 6
                    ESTADO_REDISTRIBUIDO,                 # 9
                    ESTADO_PEDIDO_CONFIRMADO,             # 10 - CONFIRMADO REDISTRIBUCION
                    ESTADO_CONFIRMADO_ENVIADO,            # 12
                    ESTADO_PENDIENTE_LOGISTICA,           # 13
                    ESTADO_ERROR_DATOS_MAESTROS,          # 14
                ]
            # contexto == "cargar-plantilla" o None -> todos los estados activos (incluye BORRADOR)

            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                estados = repo.get_estados(
                    solo_activos=True,
                    excluir_ids=excluir_ids,
                    solo_ids=solo_ids,
                )

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "data": estados,
                }
            )

        except Exception as e:
            logger.error(f"❌ Error al listar estados de pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al listar estados de pedido: {str(e)}"
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
