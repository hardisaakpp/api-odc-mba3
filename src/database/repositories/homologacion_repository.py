"""
Repositorio para operaciones relacionadas con homologación de productos.

Este repositorio actúa como fachada que delega a repositorios especializados
internos para mantener una interfaz pública unificada y compatible.
"""

import logging
import pyodbc
from typing import List, Dict, Any, Optional, Tuple

# Importar utilidades y repositorios internos
from .homologacion import (
    serialize_date,
    serialize_decimal,
    NotificacionRepository,
    ConsultaRepository,
    SkuRepository,
    EstadisticasRepository
)

logger = logging.getLogger(__name__)


class HomologacionRepository:
    """
    Repositorio para consultar productos no homologados.
    
    Este repositorio actúa como fachada que delega a repositorios especializados:
    - NotificacionRepository: Gestión de notificaciones
    - ConsultaRepository: Consultas de productos no homologados
    - SkuRepository: CRUD de homologaciones SKU
    - EstadisticasRepository: Estadísticas de homologación
    """
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
        # Inicializar repositorios internos mediante composición
        self._notificacion = NotificacionRepository(conn)
        self._consulta = ConsultaRepository(conn)
        self._sku = SkuRepository(conn)
        self._estadisticas = EstadisticasRepository(conn)
    
    # =========================================================================
    # MÉTODOS DE CONSULTA (delegados a ConsultaRepository)
    # =========================================================================
    
    def get_productos_no_homologados(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los productos de MBA3 que NO están homologados en SAP.
        
        Un producto NO está homologado si:
        - Existe en despacho_detalle (viene de MBA3)
        - NO existe en producto_sap_cache (nunca se consultó en SAP o no existe)
        
        Returns:
            Lista de diccionarios con información de productos no homologados
        """
        return self._consulta.get_productos_no_homologados()
    
    def get_skus_no_homologados(self) -> List[str]:
        """
        Obtiene una lista simple de SKUs no homologados.
        
        Returns:
            Lista de SKUs (strings)
        """
        return self._consulta.get_skus_no_homologados()
    
    def get_productos_no_homologados_por_empresa(self) -> List[Dict[str, Any]]:
        """
        Obtiene productos no homologados agrupados por empresa.
        
        Returns:
            Lista de diccionarios con información agrupada por empresa
        """
        return self._consulta.get_productos_no_homologados_por_empresa()
    
    # =========================================================================
    # MÉTODOS DE NOTIFICACIÓN (delegados a NotificacionRepository)
    # =========================================================================
    
    def is_sku_ya_notificado(self, sku: str) -> bool:
        """
        Verifica si un SKU ya fue notificado anteriormente.
        
        Args:
            sku: SKU del producto a verificar
            
        Returns:
            True si ya fue notificado, False en caso contrario
        """
        return self._notificacion.is_sku_ya_notificado(sku)
    
    def get_skus_ya_notificados(self) -> set:
        """
        Obtiene el conjunto de SKUs que ya fueron notificados.
        
        Returns:
            Set de SKUs ya notificados
        """
        return self._notificacion.get_skus_ya_notificados()
    
    def registrar_producto_notificado(self, sku: str) -> bool:
        """
        Registra un producto como notificado (o actualiza si ya existe).
        
        Args:
            sku: SKU del producto notificado
            
        Returns:
            True si se registró correctamente, False en caso contrario
        """
        return self._notificacion.registrar_producto_notificado(sku)
    
    def registrar_productos_notificados(self, skus: List[str]) -> int:
        """
        Registra múltiples productos como notificados.
        
        Args:
            skus: Lista de SKUs a registrar
            
        Returns:
            Número de productos registrados exitosamente
        """
        return self._notificacion.registrar_productos_notificados(skus)
    
    # =========================================================================
    # MÉTODOS DE GESTIÓN SKU (delegados a SkuRepository)
    # =========================================================================
    
    def get_homologaciones_sku(
        self, 
        page: int = 1, 
        page_size: int = 10,
        estado: Optional[str] = None,
        tiene_diferencias: Optional[bool] = None,
        tiene_datos_sap: Optional[bool] = None,
        sku: Optional[str] = None,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Obtiene lista de homologaciones SKU con filtros y paginación.
        
        Args:
            page: Número de página (empezando en 1)
            page_size: Cantidad de registros por página
            estado: Filtro por estado (PENDIENTE, HOMOLOGADO, ERROR)
            tiene_diferencias: Filtro por diferencias MBA3 vs SAP
            tiene_datos_sap: Filtro por presencia de datos SAP
            sku: Búsqueda por SKU (MBA3 o SAP)
            search: Búsqueda general en SKU y nombres de producto (MBA3 y SAP)
            
        Returns:
            Tupla (lista_homologaciones, total_registros)
        """
        return self._sku.get_homologaciones_sku(
            page, page_size, estado, tiene_diferencias, 
            tiene_datos_sap, sku, search
        )
    
    def get_homologacion_by_id(self, homologacion_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene una homologación por ID.
        
        Args:
            homologacion_id: UUID de la homologación
            
        Returns:
            Diccionario con la homologación o None si no existe
        """
        return self._sku.get_homologacion_by_id(homologacion_id)
    
    def create_homologacion_sku(
        self,
        data: Dict[str, Any],
        modificado_por: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Crea una nueva homologación SKU.
        
        Args:
            data: Diccionario con datos de la homologación
            modificado_por: Usuario que crea la homologación
            
        Returns:
            Diccionario con la homologación creada o None si hubo error
        """
        return self._sku.create_homologacion_sku(data, modificado_por)
    
    def update_homologacion_sku(
        self, 
        homologacion_id: str, 
        data: Dict[str, Any],
        modificado_por: Optional[str] = None
    ) -> bool:
        """
        Actualiza una homologación SKU.
        
        Args:
            homologacion_id: UUID de la homologación
            data: Diccionario con campos a actualizar
            modificado_por: Usuario que realiza la modificación
            
        Returns:
            True si se actualizó, False si no existe
        """
        return self._sku.update_homologacion_sku(homologacion_id, data, modificado_por)
    
    def bulk_update_homologaciones(
        self, 
        updates: List[Dict[str, Any]],
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza múltiples homologaciones en lote.
        
        Args:
            updates: Lista de diccionarios con homologacion_id y data
            modificado_por: Usuario que realiza la modificación
            
        Returns:
            Diccionario con resultados: {actualizadas, errores, detalles}
        """
        return self._sku.bulk_update_homologaciones(updates, modificado_por)
    
    def sincronizar_homologaciones_desde_despachos(self) -> Dict[str, Any]:
        """
        Sincroniza homologaciones desde los despachos.
        Detecta SKUs que existen en despacho_detalle y busca diferencias con SAP.
        
        Returns:
            Diccionario con estadísticas de sincronización
        """
        return self._sku.sincronizar_homologaciones_desde_despachos()
    
    # =========================================================================
    # MÉTODOS DE ESTADÍSTICAS (delegados a EstadisticasRepository)
    # =========================================================================
    
    def get_estadisticas_homologacion(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas generales de homologación.
        
        Returns:
            Diccionario con estadísticas:
            {
                "total_productos_mba3": 150,
                "productos_homologados": 145,
                "productos_no_homologados": 5,
                "porcentaje_homologacion": 96.67
            }
        """
        return self._estadisticas.get_estadisticas_homologacion()
    
    def get_estadisticas_homologaciones_sku(self) -> Dict[str, int]:
        """
        Obtiene estadísticas de homologaciones por estado.
        
        Returns:
            Diccionario con conteos por estado
        """
        return self._estadisticas.get_estadisticas_homologaciones_sku()
