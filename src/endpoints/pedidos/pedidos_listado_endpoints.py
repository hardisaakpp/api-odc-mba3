"""
Endpoints de listados y maestros de pedidos.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.responses import JSONResponse

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository, PedidosFiltros
from src.database.pedido_estados import (
    ESTADO_BORRADOR,
    ESTADO_REDISTRIBUCION,
    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_REDISTRIBUIDO,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_PENDIENTE_LOGISTICA,
    ESTADO_ERROR_DATOS_MAESTROS,
    ESTADO_LISTO_PARA_REDISTRIBUCION,
)
from src.security.jwt_auth import verify_jwt_token, require_any_permission
from src.schemas import READ_RESPONSES
from .utils import get_user_id

logger = logging.getLogger(__name__)

_PERM_MABEL = 'mabel.view'
_PERM_ODCSAP = 'odcsap.view'
_PERM_PRODUCCION_ELRAYO = 'produccion-elrayo.view'
_PERMS_LISTADO = [_PERM_MABEL, _PERM_ODCSAP, _PERM_PRODUCCION_ELRAYO]


def _es_solo_produccion_elrayo(user: Dict) -> bool:
    """True si el usuario solo tiene produccion-elrayo.view (sin mabel.view ni odcsap.view).

    Req. 1.8: el perfil Producción El Rayo solo puede ver pedidos en
    NUEVO_PEDIDO/GESTIONAR_PEDIDO; Administración El Rayo (odcsap.view) y
    Mabel (mabel.view) siguen viendo el listado completo.
    """
    permissions = user.get("permissions") or []
    return (
        _PERM_PRODUCCION_ELRAYO in permissions
        and _PERM_MABEL not in permissions
        and _PERM_ODCSAP not in permissions
    )


def _debe_excluir_estados_el_rayo(user: Dict) -> bool:
    """True si el usuario tiene odcsap.view pero NO produccion-elrayo.view:
    NUEVO_PEDIDO/GESTIONAR_PEDIDO pasan a ser exclusivos de Producción El Rayo
    (req. 1.8, segunda fase); Administración El Rayo deja de verlos y de poder
    acceder a su detalle. Si además tiene produccion-elrayo.view (cuenta con
    ambos permisos), no se restringe: ese permiso nunca pierde acceso a estos
    2 estados."""
    permissions = user.get("permissions") or []
    return _PERM_ODCSAP in permissions and _PERM_PRODUCCION_ELRAYO not in permissions


class _Paginacion:
    """Agrupa los parámetros de paginación para reducir la aridad de los endpoints."""
    def __init__(
        self,
        limit: Optional[int] = Query(None, le=500, description="Límite de registros por página"),
        offset: Optional[int] = Query(None, description="Offset para paginación"),
        page: Optional[int] = Query(1, ge=1, description="Número de página (1-based, alternativa a offset)"),
        page_size: Optional[int] = Query(10, ge=1, le=100, description="Tamaño de página (snake_case)"),
        page_size_camel: Optional[int] = Query(None, alias="pageSize", ge=1, le=100, description="Tamaño de página (camelCase)"),
    ):
        self.limit = limit
        self.offset = offset
        self.page = page
        self.page_size = page_size
        self.page_size_camel = page_size_camel


class _FiltrosBusquedaPedido:
    """Agrupa los filtros de búsqueda de listar_pedidos para reducir su aridad."""
    def __init__(
        self,
        estado: Optional[str] = Query(None, description="Filtrar por estado del pedido"),
        fecha_desde: Optional[str] = Query(None, description="Filtrar desde fecha (YYYY-MM-DD)"),
        fecha_hasta: Optional[str] = Query(None, description="Filtrar hasta fecha (YYYY-MM-DD)"),
        tipo_fecha: Optional[str] = Query(
            None,
            description=(
                "Columna sobre la que aplica fecha_desde/fecha_hasta: 'pedido' (default), "
                "'creacion', 'modificacion', 'entrega' o 'facturacion'"
            ),
        ),
        proveedor_nombre: Optional[str] = Query(None, description="Buscar por nombre de proveedor (parcial)"),
        numero_pedido: Optional[str] = Query(None, description="Buscar por número de pedido (parcial)"),
        creado_por: Optional[str] = Query(None, description="Filtrar por usuario que creó el pedido (parcial)"),
        modificado_por: Optional[str] = Query(None, description="Filtrar por usuario que modificó por última vez el pedido (parcial)"),
    ):
        self.estado = estado
        self.fecha_desde = fecha_desde
        self.fecha_hasta = fecha_hasta
        self.tipo_fecha = tipo_fecha
        self.proveedor_nombre = proveedor_nombre
        self.numero_pedido = numero_pedido
        self.creado_por = creado_por
        self.modificado_por = modificado_por


def _query_listar_pedidos(filtros: PedidosFiltros, limit: Optional[int], offset: Optional[int]):
    """Ejecuta la consulta bloqueante de listado (pyodbc); se llama vía asyncio.to_thread
    para no congelar el event loop si SQL Server tarda o no responde."""
    with get_db_connection_context() as conn:
        repo = PedidoRepository(conn)
        return repo.get_pedidos_con_filtros(filtros, limit=limit, offset=offset)


async def _listar_pedidos_handler(
    estado: Optional[str],
    fecha_desde: Optional[str],
    fecha_hasta: Optional[str],
    proveedor_nombre: Optional[str],
    numero_pedido: Optional[str],
    creado_por: Optional[str],
    modificado_por: Optional[str],
    paginacion: _Paginacion,
    solo_redistribucion: Optional[str],
    solo_pendientes_accion: Optional[str],
    solo_produccion_elrayo: Optional[str],
    user: Dict,
    tipo_fecha: Optional[str] = None,
):
    try:
        filtrar_redistribucion = (
            solo_redistribucion is not None
            and str(solo_redistribucion).lower() in ("true", "1")
        )
        filtrar_pendientes = (
            solo_pendientes_accion is not None
            and str(solo_pendientes_accion).lower() in ("true", "1")
        )
        # El mismo parámetro `solo_pendientes_accion` significa cosas distintas según la pantalla
        # que comparte este endpoint: en Redistribución (solo_redistribucion=true) es Confirmado por
        # El Rayo/Listo para Redistribución (ver ESTADOS_REQUIERE_ACCION_REDISTRIBUCION_* en
        # pedido_estados.py); en Pedidos (EL RAYO) es Confirmado por Producción/Confirmado y Enviado
        # (ver ESTADOS_REQUIERE_ACCION_PEDIDOS_*) -- cada pantalla activa solo su propio flag en
        # PedidosFiltros.
        filtrar_pendientes_redistribucion = filtrar_pendientes and filtrar_redistribucion
        filtrar_pendientes_pedidos = filtrar_pendientes and not filtrar_redistribucion
        # Restringe a NUEVO_PEDIDO/GESTIONAR_PEDIDO (req. 1.8): ya sea porque la
        # pantalla de Producción El Rayo lo pide explícitamente (solo_produccion_elrayo),
        # o como defensa adicional cuando el llamador solo tiene ese permiso.
        filtrar_produccion_elrayo = (
            solo_produccion_elrayo is not None
            and str(solo_produccion_elrayo).lower() in ("true", "1")
        ) or _es_solo_produccion_elrayo(user)
        # Req. 1.8 (segunda fase): odcsap.view ya no ve NUEVO_PEDIDO/GESTIONAR_PEDIDO,
        # ahora exclusivos de Producción El Rayo.
        excluir_estados_el_rayo = _debe_excluir_estados_el_rayo(user)
        size = paginacion.page_size_camel if paginacion.page_size_camel is not None else paginacion.page_size
        if paginacion.limit is not None:
            use_limit, use_offset = paginacion.limit, paginacion.offset or 0
        else:
            use_limit = size if size is not None else 10
            use_offset = ((paginacion.page or 1) - 1) * use_limit

        resultado = await asyncio.to_thread(
            _query_listar_pedidos,
            PedidosFiltros(
                estado=estado,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                tipo_fecha=tipo_fecha,
                proveedor_nombre=proveedor_nombre,
                numero_pedido=numero_pedido,
                creado_por=creado_por,
                modificado_por=modificado_por,
                excluir_borrador=True,
                solo_redistribucion=filtrar_redistribucion,
                solo_pendientes_accion_redistribucion=filtrar_pendientes_redistribucion,
                solo_pendientes_accion_pedidos=filtrar_pendientes_pedidos,
                restringir_produccion_el_rayo=filtrar_produccion_elrayo,
                excluir_estados_produccion_el_rayo=excluir_estados_el_rayo,
                # LISTO_PARA_REDISTRIBUCION (25, botón "Aceptar") solo debe verse en /redistribucion
                excluir_listo_para_redistribucion=not filtrar_redistribucion,
            ),
            use_limit,
            use_offset,
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


def _query_listar_pedidos_confirmados(**kwargs):
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        repo = PedidoRepository(conn)
        return repo.get_pedidos_confirmados(**kwargs)


async def _listar_pedidos_confirmados_handler(
    page: Optional[int],
    page_size: Optional[int],
    page_size_camel: Optional[int],
    limit: Optional[int],
    offset: Optional[int],
    fecha_desde: Optional[str],
    fecha_hasta: Optional[str],
    proveedor_nombre: Optional[str],
    numero_pedido: Optional[str],
    creado_por: Optional[str],
    modificado_por: Optional[str] = None,
    tipo_fecha: Optional[str] = None,
):
    try:
        size = page_size_camel if page_size_camel is not None else page_size
        if limit is not None:
            use_limit, use_offset = limit, offset or 0
        else:
            use_size = size if size is not None else 10
            use_limit = use_size
            use_offset = ((page or 1) - 1) * use_size

        resultado = await asyncio.to_thread(
            _query_listar_pedidos_confirmados,
            limit=use_limit,
            offset=use_offset,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            tipo_fecha=tipo_fecha,
            proveedor_nombre=proveedor_nombre,
            numero_pedido=numero_pedido,
            creado_por=creado_por,
            modificado_por=modificado_por,
        )

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
                    "comprador_nombre": row.get("comprador_nombre"),
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


def _query_ultimo_pedido_redistribucion(usuario_id):
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        repo = PedidoRepository(conn)
        return repo.get_ultimo_pedido_respuesta_proveedor_cargada(usuario_id=usuario_id)


async def _get_ultimo_pedido_redistribucion_handler(
    solo_usuario: Optional[bool],
    user: Dict,
):
    try:
        permissions = user.get("permissions") or []
        has_odcsap = _PERM_ODCSAP in permissions
        has_mabel = _PERM_MABEL in permissions
        if has_odcsap and not has_mabel:
            user_id = None
        else:
            user_id = get_user_id(user) if solo_usuario else None
        ultimo = await asyncio.to_thread(_query_ultimo_pedido_redistribucion, user_id)
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


def _query_estados_pedido(excluir_ids, solo_ids, solo_con_pedidos=False):
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        repo = PedidoRepository(conn)
        return repo.get_estados(
            solo_activos=True,
            excluir_ids=excluir_ids,
            solo_ids=solo_ids,
            solo_con_pedidos=solo_con_pedidos,
        )


async def _listar_estados_pedido_handler(contexto: Optional[str], user: Dict):
    try:
        excluir_ids: Optional[List[int]] = None
        solo_ids: Optional[List[int]] = None
        solo_con_pedidos = False

        if contexto == "produccion" or _es_solo_produccion_elrayo(user):
            from src.database.pedido_estados import ESTADOS_PRODUCCION_EL_RAYO_IDS
            solo_ids = list(sorted(ESTADOS_PRODUCCION_EL_RAYO_IDS))
        elif contexto == "pedidos":
            # LISTO_PARA_REDISTRIBUCION (25, botón "Aceptar") solo se ve en /redistribucion
            excluir_ids = [ESTADO_BORRADOR, ESTADO_LISTO_PARA_REDISTRIBUCION]
        elif contexto == "cargar-plantilla":
            # LISTO_PARA_REDISTRIBUCION (25, botón "Aceptar") solo se ve en /redistribucion.
            # solo_con_pedidos: acota el dropdown a estados que algún pedido real tiene hoy --
            # get_pedidos_con_filtros para este listado no aplica ninguna otra restricción
            # (ver _listar_pedidos_plantillas_handler en plantillas.py), así que "pedido real
            # en ese estado_id" refleja exactamente el universo que este listado puede mostrar.
            excluir_ids = [ESTADO_LISTO_PARA_REDISTRIBUCION]
            solo_con_pedidos = True
        elif contexto == "redistribucion":
            solo_ids = [
                ESTADO_REDISTRIBUCION,
                ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
                ESTADO_CONFIRMADO_PROVEEDOR,
                ESTADO_REDISTRIBUIDO,
                ESTADO_PEDIDO_CONFIRMADO,
                ESTADO_CONFIRMADO_ENVIADO,
                ESTADO_PENDIENTE_LOGISTICA,
                ESTADO_ERROR_DATOS_MAESTROS,
                ESTADO_LISTO_PARA_REDISTRIBUCION,
            ]

        # Req. 1.8 (segunda fase): odcsap.view ya no ve NUEVO_PEDIDO/GESTIONAR_PEDIDO
        # (exclusivos de Producción El Rayo). No aplica si solo_ids ya restringe a otra
        # lista (ej. contexto "produccion" o "redistribucion", que no los incluyen o
        # son mutuamente excluyentes con tener odcsap.view).
        if solo_ids is None and _debe_excluir_estados_el_rayo(user):
            from src.database.pedido_estados import ESTADOS_PRODUCCION_EL_RAYO_IDS
            excluir_ids = list(excluir_ids or []) + list(sorted(ESTADOS_PRODUCCION_EL_RAYO_IDS))

        estados = await asyncio.to_thread(_query_estados_pedido, excluir_ids, solo_ids, solo_con_pedidos)

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


def _query_tiene_pedidos():
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        repo = PedidoRepository(conn)
        return repo.tiene_pedidos()


async def _verificar_pedidos_existen_handler():
    try:
        tiene_pedidos = await asyncio.to_thread(_query_tiene_pedidos)

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


def _query_creadores_pedido():
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        repo = PedidoRepository(conn)
        return repo.get_creadores_distintos()


async def _listar_creadores_pedido_handler():
    try:
        creadores = await asyncio.to_thread(_query_creadores_pedido)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": creadores,
            }
        )

    except Exception as e:
        logger.error(f"❌ Error al listar creadores de pedido: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al listar creadores de pedido: {str(e)}"
        )


def _query_modificadores_pedido():
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        repo = PedidoRepository(conn)
        return repo.get_modificadores_distintos()


async def _listar_modificadores_pedido_handler():
    try:
        modificadores = await asyncio.to_thread(_query_modificadores_pedido)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": modificadores,
            }
        )

    except Exception as e:
        logger.error(f"❌ Error al listar modificadores de pedido: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al listar modificadores de pedido: {str(e)}"
        )


def register_pedidos_listado_endpoints(app: FastAPI):
    """Registra endpoints de listados y maestros de pedidos."""

    @app.get("/api/pedidos", tags=["Pedidos"], responses=READ_RESPONSES)
    async def listar_pedidos(
        filtros: _FiltrosBusquedaPedido = Depends(_FiltrosBusquedaPedido),
        paginacion: _Paginacion = Depends(_Paginacion),
        solo_redistribucion: Optional[str] = Query(
            None,
            description="Si 'true', solo pedidos aptos para redistribución (estado >= CONFIRMADO POR EL RAYO, excluye CANCELADO y CANCELADO POR EL RAYO)"
        ),
        solo_pendientes_accion: Optional[str] = Query(
            None,
            description="Si 'true', solo pedidos que requieren acción (pendiente confirmación / respuesta proveedor / confirmado proveedor)"
        ),
        solo_produccion_elrayo: Optional[str] = Query(
            None,
            description="Si 'true', restringe a NUEVO_PEDIDO/GESTIONAR_PEDIDO (pantalla Producción El Rayo, req. 1.8)"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(_PERMS_LISTADO))
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
        - `tipo_fecha` (string, opcional) - Columna de fecha a filtrar: "pedido" (default), "creacion", "modificacion", "entrega" o "facturacion"
        - `proveedor_nombre` (string, opcional) - Búsqueda parcial por nombre de proveedor
        - `numero_pedido` (string, opcional) - Búsqueda parcial por número de pedido
        - `creado_por` (string, opcional) - Búsqueda parcial por usuario que creó el pedido
        - `modificado_por` (string, opcional) - Búsqueda parcial por usuario que modificó por última vez el pedido
        - `limit` (int, default: 50) - Límite de registros por página
        - `offset` (int, default: 0) - Offset para paginación
        - `solo_redistribucion` (string, opcional) - Si "true", solo pedidos aptos para redistribución
          (estado >= "CONFIRMADO POR EL RAYO" y != "CANCELADO"). Para la vista /redistribucion.
        - `solo_produccion_elrayo` (string, opcional) - Si "true", restringe a NUEVO_PEDIDO/GESTIONAR_PEDIDO.
          Para la pantalla /mba3-consultas/produccion/pedidos (req. 1.8).

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
        return await _listar_pedidos_handler(
            estado=filtros.estado,
            fecha_desde=filtros.fecha_desde,
            fecha_hasta=filtros.fecha_hasta,
            tipo_fecha=filtros.tipo_fecha,
            proveedor_nombre=filtros.proveedor_nombre,
            numero_pedido=filtros.numero_pedido,
            creado_por=filtros.creado_por,
            modificado_por=filtros.modificado_por,
            paginacion=paginacion,
            solo_redistribucion=solo_redistribucion,
            solo_pendientes_accion=solo_pendientes_accion,
            solo_produccion_elrayo=solo_produccion_elrayo,
            user=user,
        )

    @app.get("/api/pedidos/confirmados", tags=["Pedidos"])
    async def listar_pedidos_confirmados(
        paginacion: _Paginacion = Depends(_Paginacion),
        fecha_desde: Optional[str] = Query(None, description="Filtrar desde fecha (YYYY-MM-DD)"),
        fecha_hasta: Optional[str] = Query(None, description="Filtrar hasta fecha (YYYY-MM-DD)"),
        tipo_fecha: Optional[str] = Query(
            None,
            description=(
                "Columna sobre la que aplica fecha_desde/fecha_hasta: 'pedido' (default), "
                "'creacion', 'modificacion', 'entrega' o 'facturacion'"
            ),
        ),
        proveedor_nombre: Optional[str] = Query(None, description="Búsqueda parcial por proveedor"),
        numero_pedido: Optional[str] = Query(None, description="Búsqueda parcial por número de pedido"),
        creado_por: Optional[str] = Query(None, description="Búsqueda parcial por usuario creador"),
        modificado_por: Optional[str] = Query(None, description="Búsqueda parcial por usuario que modificó por última vez el pedido"),
        redistribucion_confirmada: Optional[str] = Query(
            None,
            description="Si 'true', solo pedidos con redistribución ya confirmada (estado CONFIRMADO REDISTRIBUCION)"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(_PERMS_LISTADO))
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
        return await _listar_pedidos_confirmados_handler(
            page=paginacion.page,
            page_size=paginacion.page_size,
            page_size_camel=paginacion.page_size_camel,
            limit=paginacion.limit,
            offset=paginacion.offset,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            tipo_fecha=tipo_fecha,
            proveedor_nombre=proveedor_nombre,
            numero_pedido=numero_pedido,
            creado_por=creado_por,
            modificado_por=modificado_por,
        )

    @app.get("/api/pedidos/ultimo-redistribucion", tags=["Pedidos"])
    async def get_ultimo_pedido_redistribucion(
        solo_usuario: Optional[bool] = Query(
            True,
            description="Si true, último pedido apto para redistribución del usuario; si false, último en todo el sistema"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(_PERMS_LISTADO))
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
        return await _get_ultimo_pedido_redistribucion_handler(
            solo_usuario=solo_usuario,
            user=user,
        )

    @app.get("/api/pedidos/estados", tags=["Pedidos"], responses=READ_RESPONSES)
    async def listar_estados_pedido(
        contexto: Optional[str] = Query(
            None,
            description=(
                "Contexto de la vista para filtrar estados relevantes. "
                "Valores posibles: 'pedidos' (excluye BORRADOR), "
                "'cargar-plantilla' (incluye BORRADOR, solo del flujo de carga), "
                "'redistribucion' (solo estados aptos para redistribucion), "
                "'produccion' (solo NUEVO_PEDIDO/GESTIONAR_PEDIDO, pantalla Producción El Rayo, req. 1.8). "
                "Si no se indica, devuelve todos los estados activos."
            ),
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(_PERMS_LISTADO))
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
        return await _listar_estados_pedido_handler(contexto=contexto, user=user)

    @app.get("/api/pedidos/creadores", tags=["Pedidos"], responses=READ_RESPONSES)
    async def listar_creadores_pedido(
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(_PERMS_LISTADO))
    ):
        """
        Devuelve la lista de usuarios (creado_por) que han creado al menos un
        pedido, para el <select> de "Creado Por" del contenedor "Filtros de
        Búsqueda". Antes era un input de texto libre; se reemplazó por un
        selector para no obligar al usuario a adivinar qué escribir.

        **Ejemplo:**
        ```
        GET /api/pedidos/creadores
        ```

        **Respuesta:**
        ```json
        {
            "status": "success",
            "data": ["ana.torres@mabeltrading.com.ec", "SYSTEM", "cortiz@mabeltrading.com.ec"]
        }
        ```

        Returns:
            JSON con lista de valores distintos de creado_por
        """
        return await _listar_creadores_pedido_handler()

    @app.get("/api/pedidos/modificadores", tags=["Pedidos"], responses=READ_RESPONSES)
    async def listar_modificadores_pedido(
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(_PERMS_LISTADO))
    ):
        """
        Devuelve la lista de usuarios (modificado_por) que han modificado al
        menos un pedido, para el <select> de "Modificado Por" del contenedor
        "Filtros de Búsqueda".

        **Ejemplo:**
        ```
        GET /api/pedidos/modificadores
        ```

        **Respuesta:**
        ```json
        {
            "status": "success",
            "data": ["ana.torres@mabeltrading.com.ec", "SYSTEM", "cortiz@mabeltrading.com.ec"]
        }
        ```

        Returns:
            JSON con lista de valores distintos de modificado_por
        """
        return await _listar_modificadores_pedido_handler()

    @app.get("/api/pedidos/existe", tags=["Pedidos"])
    async def verificar_pedidos_existen(
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(_PERMS_LISTADO))
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
        return await _verificar_pedidos_existen_handler()
