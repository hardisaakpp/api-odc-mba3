"""
Repositorio para operaciones de pedido en SQL Server.

REFACTORIZADO: Ahora delega a repositorios especializados:
- PedidoCabeceraRepository: Operaciones de cabecera
- PedidoDetalleRepository: Operaciones de detalle
- PedidoTiendaRepository: Operaciones de tiendas y distribuciones

Mantiene la misma interfaz pública para compatibilidad hacia atrás.

CHANGELOG:
- 2026-02-06: Agregado soporte para AuditContext en métodos delegados (Buenas Prácticas - Sección 3)
- 2026-01-23: Refactorizado como facade que delega a repositorios especializados
- 2026-01-23: Movidas utilidades compartidas a pedido.pedido_utils
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from src.utils.audit_context import AuditContext

# Importar repositorios especializados
from .pedido.pedido_cabecera_repository import PedidoCabeceraRepository, PedidosFiltros
from .pedido.pedido_detalle_repository import PedidoDetalleRepository
from .pedido.pedido_tienda_repository import PedidoTiendaRepository
from ..pedido_estados import ESTADO_LIMITE_CANCELAR_PEDIDO, ESTADOS_PUEDE_DESCARTAR, ESTADOS_PUEDE_CANCELAR_POR_EL_RAYO, estado_id_desde_legacy

logger = logging.getLogger(__name__)


class PedidoRepository:
    """
    Repositorio para operaciones de pedido.
    
    REFACTORIZADO: Facade que delega a repositorios especializados.
    Mantiene la misma interfaz pública para compatibilidad hacia atrás.
    """

    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
        # Inicializar repositorios especializados
        self.cabecera_repo = PedidoCabeceraRepository(conn)
        self.detalle_repo = PedidoDetalleRepository(conn)
        self.tienda_repo = PedidoTiendaRepository(conn)

    # ========== Métodos de Cabecera (delegados) ==========

    def insert_cabecera(
        self, 
        datos_cabecera: Dict[str, Any], 
        audit_context: Optional["AuditContext"] = None
    ) -> str:
        """
        Inserta un registro en pedido.
        
        Args:
            datos_cabecera: Diccionario con datos de cabecera
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)
        
        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.insert(datos_cabecera, audit_context=audit_context)

    def update_cabecera(
        self,
        pedido_id: str,
        datos_cabecera: Dict[str, Any],
        audit_context: Optional["AuditContext"] = None,
    ) -> bool:
        """
        Actualiza la cabecera de un pedido.
        
        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.update(pedido_id, datos_cabecera, audit_context=audit_context)

    def update_estado(
        self, 
        pedido_id: str, 
        estado: "int | str",
        audit_context: Optional["AuditContext"] = None
    ) -> bool:
        """
        Actualiza el estado de un pedido.
        
        Args:
            pedido_id: UUID del pedido
            estado: estado_id (int) o nombre legacy (str)
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)
            
        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.update_estado(pedido_id, estado, audit_context=audit_context)

    def get_pedido_completo(self, pedido_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un pedido completo con cabecera, detalles, tiendas y distribuciones.
        
        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_pedido_completo(pedido_id)

    def get_pedido_completo_por_numero(self, numero_pedido: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un pedido completo con cabecera, detalles, tiendas y distribuciones por número de pedido.

        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_pedido_completo_por_numero(numero_pedido)

    def get_fecha_confirmacion_estado(
        self, pedido_id: str, estado_id: int
    ) -> Optional[datetime]:
        """
        Obtiene la fecha/hora (hora Colombia) en que el pedido transicionó a `estado_id`,
        según la bitácora pedido_estado_historial. None si no hay registro.

        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_fecha_confirmacion_estado(pedido_id, estado_id)

    def get_by_estado(self, estado: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los pedidos con un estado específico.
        
        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_by_estado(estado)

    def get_pedidos_con_filtros(
        self,
        filtros: Optional[PedidosFiltros] = None,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene pedidos con filtros y paginación.

        DELEGADO a PedidoCabeceraRepository.

        Args:
            filtros: filtros opcionales agrupados en PedidosFiltros (python:S107).
                Incluye, entre otros: solo_redistribucion (estado_id >= 4
                "CONFIRMADO POR EL RAYO", excluyendo CANCELADO (19), CANCELADO POR
                EL RAYO (20), CONFIRMADO POR PRODUCCION (23), PRODUCCION POSPUESTA
                (22) y RECHAZADO (24)); restringir_produccion_el_rayo (req. 1.8,
                perfil Producción El Rayo: solo NUEVO_PEDIDO y GESTIONAR_PEDIDO);
                excluir_estados_produccion_el_rayo (req. 1.8 segunda fase, perfil
                odcsap.view: esos 2 estados dejan de verse); y
                excluir_listo_para_redistribucion (excluye LISTO_PARA_REDISTRIBUCION
                (25); debe ser True salvo en la vista de Redistribución).
            limit, offset: paginación.
        """
        return self.cabecera_repo.get_pedidos_con_filtros(filtros, limit=limit, offset=offset)

    def get_pedidos_confirmados(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None,
        tipo_fecha: Optional[str] = None,
        proveedor_nombre: Optional[str] = None,
        numero_pedido: Optional[str] = None,
        creado_por: Optional[str] = None,
        modificado_por: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene pedidos en estado confirmado, ordenados por creado_en DESC.
        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_pedidos_confirmados(
            limit=limit,
            offset=offset,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            tipo_fecha=tipo_fecha,
            proveedor_nombre=proveedor_nombre,
            numero_pedido=numero_pedido,
            creado_por=creado_por,
            modificado_por=modificado_por,
        )

    def existe_numero_pedido(self, numero_pedido: str) -> bool:
        """
        Verifica si un número de pedido ya existe en el sistema.

        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.existe_numero_pedido(numero_pedido)

    def contar_hijos(self, pedido_padre_id: str) -> int:
        """
        Cantidad de pedidos "hijo" ya generados a partir de este pedido (req. 1.2).

        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.contar_hijos(pedido_padre_id)

    def get_ultimo_pedido(self, usuario_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el último pedido cargado por un usuario específico.
        
        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_ultimo_pedido(usuario_id)

    def get_ultimo_pedido_respuesta_proveedor_cargada(
        self, usuario_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene el último pedido con estado CONFIRMADO (id 4).
        Para pantalla Redistribución: al entrar en /redistribucion se carga el último pedido confirmado.
        
        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_ultimo_pedido_respuesta_proveedor_cargada(usuario_id)

    def tiene_pedidos(self) -> bool:
        """
        Verifica si existe al menos un pedido en la base de datos.

        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.tiene_pedidos()

    def get_creadores_distintos(self) -> List[str]:
        """
        Devuelve la lista de valores distintos de creado_por existentes.

        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_creadores_distintos()

    def get_modificadores_distintos(self) -> List[str]:
        """
        Devuelve la lista de valores distintos de modificado_por existentes.

        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_modificadores_distintos()

    def get_estados(
        self,
        solo_activos: bool = True,
        excluir_ids: Optional[List[int]] = None,
        solo_ids: Optional[List[int]] = None,
        solo_con_pedidos: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene la lista de estados de pedido para dropdowns de filtros.

        DELEGADO a PedidoCabeceraRepository.
        """
        return self.cabecera_repo.get_estados(
            solo_activos=solo_activos,
            excluir_ids=excluir_ids,
            solo_ids=solo_ids,
            solo_con_pedidos=solo_con_pedidos,
        )

    def get_respuestas_proveedor(
        self,
        pedido_id: str,
        *,
        top_one: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene respuestas del proveedor para un pedido.

        Args:
            pedido_id: UUID del pedido
            top_one: Si True, limita a la última respuesta

        Returns:
            Dict indexado por pedido_detalle_id
        """
        cursor = self.conn.cursor()
        top_clause = "TOP 1" if top_one else ""
        cursor.execute(
            f"""
            SELECT {top_clause}
                rpd.pedido_detalle_id,
                rpd.cantidad_solicitada_total,
                rpd.cantidad_confirmada_total
            FROM pedido_respuesta_proveedor_detalle rpd
            INNER JOIN pedido_respuesta_proveedor rp ON rpd.respuesta_id = rp.respuesta_id
            WHERE rp.pedido_id = ?
            ORDER BY rp.version DESC, rp.fecha_respuesta DESC
            """,
            (pedido_id,),
        )

        respuestas_proveedor: Dict[str, Dict[str, Any]] = {}
        for row in cursor.fetchall():
            # Normalizar a float para preservar decimales (ej. 0.5); evita truncado si el driver devuelve int/Decimal
            try:
                sol = float(row[1]) if row[1] is not None else 0.0
            except (TypeError, ValueError):
                sol = 0.0
            try:
                conf = float(row[2]) if row[2] is not None else 0.0
            except (TypeError, ValueError):
                conf = 0.0
            respuestas_proveedor[str(row[0])] = {
                "cantidad_solicitada_total": sol,
                "cantidad_confirmada_total": conf,
            }

        return respuestas_proveedor

    def _tiene_datos_asociados(self, cursor, pedido_id: str) -> bool:
        """Verifica si el pedido tiene registros en tablas que impedirían su eliminación."""
        for table, col in [
            ("pedido_respuesta_proveedor", "pedido_id"),
            ("distribucion_confirmada", "pedido_id"),
            ("orden_compra_cabecera", "pedido_id"),
        ]:
            try:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {col} = ?",
                    (pedido_id,),
                )
                row = cursor.fetchone()
                if row and (row[0] or 0) > 0:
                    return True
            except pyodbc.Error:
                pass
        return False

    def validar_puede_descartar(
        self, pedido_id: str, es_cancelar_pedido: bool = False
    ) -> Tuple[bool, str, str]:
        """
        Valida si un pedido puede eliminarse (Descartar o Cancelar Pedido).

        - Descartar (Cargar Plantilla): es_cancelar_pedido=False. Solo estados Borrador o Nuevo Pedido.
        - Cancelar Pedido (Redistribución): es_cancelar_pedido=True. Solo estados anteriores a Confirmado redistribución (estado_id < 10).

        En ambos casos no debe tener datos asociados (respuesta proveedor, redistribución confirmada, orden de compra)
        salvo que se implemente borrado en cascada para Cancelar Pedido.

        Returns:
            (ok, error_code, message): ok=True si puede eliminarse;
            si ok=False, error_code y message para la respuesta HTTP.
        """
        pedido = self.cabecera_repo.get_pedido_completo(pedido_id)
        if not pedido:
            return (False, "not_found", "No se encontró el pedido.")

        cabecera = pedido.get("cabecera", {})
        estado_id = cabecera.get("estado_id")
        if estado_id is None:
            estado_id = estado_id_desde_legacy(cabecera.get("estado"))
        try:
            estado_id = int(estado_id) if estado_id is not None else None
        except (TypeError, ValueError):
            estado_id = None

        if es_cancelar_pedido:
            # Cancelar Pedido: permitir solo estados anteriores a Confirmado redistribución (10)
            if estado_id is None or estado_id >= ESTADO_LIMITE_CANCELAR_PEDIDO:
                return (
                    False,
                    "estado_no_permitido",
                    "El pedido no puede cancelarse porque está en estado Confirmado redistribución o posterior.",
                )
        else:
            # Descartar: solo Borrador (1) o Nuevo Pedido (2)
            if estado_id not in ESTADOS_PUEDE_DESCARTAR:
                return (
                    False,
                    "estado_no_borrador",
                    "El pedido no puede descartarse porque no está en estado Borrador o Nuevo Pedido.",
                )

        cursor = self.conn.cursor()
        try:
            if self._tiene_datos_asociados(cursor, pedido_id):
                return (
                    False,
                    "tiene_datos_asociados",
                    "El pedido tiene información asociada (respuesta de proveedor, redistribución u orden de compra) y no puede descartarse.",
                )
            return (True, "", "")
        finally:
            cursor.close()

    def validar_puede_eliminar(self, pedido_id: str) -> tuple[bool, str, str]:
        """
        Valida si un pedido puede cancelarse con el botón "Cancelar Pedido" de EL RAYO (Detalle del Pedido).

        Solo permite cancelar si:
        - El pedido está en estado CONFIRMADO POR PRODUCCION (23)
        - No tiene respuesta de proveedor, redistribución confirmada u orden de compra

        Returns:
            Tupla: (puede_cancelar, codigo_error, mensaje_error)
        """
        pedido_completo = self.cabecera_repo.get_pedido_completo(pedido_id)
        if not pedido_completo:
            return (False, "not_found", "Pedido no encontrado.")

        # Obtener estado_id de la cabecera
        cabecera = pedido_completo.get("cabecera", {})
        estado_id = cabecera.get("estado_id")

        # Validar estado: solo CONFIRMADO POR PRODUCCION (23)
        if estado_id not in ESTADOS_PUEDE_CANCELAR_POR_EL_RAYO:
            return (
                False,
                "estado_no_permitido",
                "El pedido no puede cancelarse porque no está en estado Confirmado por Producción.",
            )
        
        # Validar que no tenga datos asociados
        cursor = self.conn.cursor()
        try:
            for table, col in [
                ("pedido_respuesta_proveedor", "pedido_id"),
                ("distribucion_confirmada", "pedido_id"),
                ("orden_compra_cabecera", "pedido_id"),
            ]:
                try:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {col} = ?",
                        (pedido_id,),
                    )
                    row = cursor.fetchone()
                    if row and (row[0] or 0) > 0:
                        return (
                            False,
                            "tiene_datos_asociados",
                            "El pedido tiene información asociada (respuesta de proveedor, redistribución u orden de compra) y no puede eliminarse.",
                        )
                except pyodbc.Error:
                    pass
            return (True, "", "")
        finally:
            cursor.close()

    def delete_pedido(
        self,
        pedido_id: str,
        audit_context: Optional["AuditContext"] = None,
    ) -> bool:
        """
        Elimina un pedido y sus detalles/distribuciones en una transacción.
        Solo debe llamarse después de validar con validar_puede_descartar.

        Orden: pedido_detalle_tienda → pedido_detalle → pedido.
        """
        cursor = self.conn.cursor()
        try:
            self.conn.autocommit = False
            self.tienda_repo.delete_distribuciones_by_pedido_id(pedido_id, cursor=cursor, audit_context=audit_context)
            self.detalle_repo.delete_by_pedido_id(pedido_id, cursor=cursor, audit_context=audit_context)
            ok = self.cabecera_repo.delete(pedido_id, cursor=cursor, audit_context=audit_context)
            self.conn.commit()
            if ok:
                logger.info(f"✅ Pedido {pedido_id} descartado (eliminado)")
            return ok
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al descartar pedido {pedido_id}: {e}", exc_info=True)
            raise
        finally:
            self.conn.autocommit = True
            cursor.close()

    # ========== Métodos de Detalle (delegados) ==========

    def insert_detalle(
        self,
        pedido_id: str,
        datos_detalle: Dict[str, Any],
        audit_context: Optional["AuditContext"] = None,
    ) -> str:
        """
        Inserta un registro en pedido_detalle (artículo).
        
        DELEGADO a PedidoDetalleRepository.
        """
        return self.detalle_repo.insert(pedido_id, datos_detalle, audit_context=audit_context)

    def update_costo_detalle(
        self,
        pedido_detalle_id: str,
        nuevo_costo: float,
        modificado_por: Optional[str] = None,
        audit_context: Optional["AuditContext"] = None
    ) -> Dict[str, Any]:
        """
        Actualiza el costo unitario de un detalle de pedido.

        DELEGADO a PedidoDetalleRepository.
        """
        return self.detalle_repo.update_costo(pedido_detalle_id, nuevo_costo, modificado_por, audit_context)

    def update_total_detalle(
        self,
        pedido_detalle_id: str,
        nuevo_total: float,
        modificado_por: Optional[str] = None,
        audit_context: Optional["AuditContext"] = None
    ) -> Dict[str, Any]:
        """
        Actualiza el total de un detalle de pedido.

        DELEGADO a PedidoDetalleRepository.
        """
        return self.detalle_repo.update_total(pedido_detalle_id, nuevo_total, modificado_por, audit_context)

    def update_comentario_detalle(
        self,
        pedido_detalle_id: str,
        nuevo_comentario: Optional[str],
        modificado_por: Optional[str] = None,
        audit_context: Optional["AuditContext"] = None
    ) -> Dict[str, Any]:
        """
        Actualiza el comentario de un detalle de pedido.

        DELEGADO a PedidoDetalleRepository.
        """
        return self.detalle_repo.update_comentario(pedido_detalle_id, nuevo_comentario, modificado_por, audit_context)

    def guardar_modificaciones_columnas(
        self,
        numero_pedido: str,
        modificaciones: List[Dict[str, str]],
        modificado_por: Optional[str] = None,
        rol_modificador: Optional[str] = None,
        audit_context: Optional["AuditContext"] = None
    ) -> Dict[str, Any]:
        """
        Guarda o actualiza modificaciones de columnas para un pedido.

        DELEGADO a PedidoDetalleRepository.
        """
        return self.detalle_repo.guardar_modificaciones_columnas(
            numero_pedido, modificaciones, modificado_por, rol_modificador, audit_context)

    def obtener_modificaciones_columnas(
        self,
        numero_pedido: str
    ) -> Dict[str, Any]:
        """
        Obtiene las modificaciones de columnas para un pedido.
        
        DELEGADO a PedidoDetalleRepository.
        """
        return self.detalle_repo.obtener_modificaciones_columnas(numero_pedido)

    # ========== Métodos de Tienda (delegados) ==========

    def insert_detalle_tiendas(
        self,
        pedido_detalle_id: str,
        distribuciones: List[Dict[str, Any]],
        audit_context: Optional["AuditContext"] = None,
    ) -> int:
        """
        Inserta distribuciones de un detalle por tiendas.
        
        DELEGADO a PedidoTiendaRepository.
        """
        return self.tienda_repo.insert_distribuciones(pedido_detalle_id, distribuciones, audit_context=audit_context)

    def get_or_create_tienda(
        self, 
        codigo: str, 
        nombre: Optional[str] = None, 
        consultar_sap: bool = True
    ) -> str:
        """
        Obtiene el ID de una tienda existente o la crea si no existe.
        
        DELEGADO a PedidoTiendaRepository.
        """
        return self.tienda_repo.get_or_create_tienda(codigo, nombre, consultar_sap)

    def validar_tiendas_existen(
        self,
        codigos_tiendas: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Valida si las tiendas existen y están activas.
        
        DELEGADO a PedidoTiendaRepository.
        """
        return self.tienda_repo.validar_tiendas_existen(codigos_tiendas)
