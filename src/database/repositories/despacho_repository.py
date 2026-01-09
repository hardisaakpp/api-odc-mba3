"""
Repositorio para operaciones CRUD de despachos en SQL Server.

REFACTORIZADO: Ahora delega a repositorios especializados:
- DespachoCabeceraRepository: Operaciones de cabecera
- DespachoDetalleRepository: Operaciones de detalle
- DespachoQueryRepository: Consultas complejas

Mantiene la misma interfaz pública para compatibilidad hacia atrás.

CHANGELOG:
- 2026-01-08: Refactorizado como facade que delega a repositorios especializados
- 2026-01-08: Movidas utilidades de serialización a common.serialization
"""

import logging
import pyodbc
from typing import Optional, Dict, Any, List

# Importar repositorios especializados
from .despacho.despacho_cabecera_repository import DespachoCabeceraRepository
from .despacho.despacho_detalle_repository import DespachoDetalleRepository
from .despacho.despacho_query_repository import DespachoQueryRepository

# Re-exportar utilidades para compatibilidad hacia atrás
from .common.serialization import serialize_date, serialize_decimal

logger = logging.getLogger(__name__)


class DespachoRepository:
    """
    Repositorio para operaciones de despacho_cabecera y despacho_detalle.

    REFACTORIZADO: Facade que delega a repositorios especializados.
    """

    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
        # Inicializar repositorios especializados
        self.cabecera_repo = DespachoCabeceraRepository(conn)
        self.detalle_repo = DespachoDetalleRepository(conn)
        self.query_repo = DespachoQueryRepository(conn)

    # ========== Métodos de Cabecera (delegados) ==========

    def find_by_codigo_factura(self, codigo_factura: str) -> Optional[str]:
        """
        Busca un despacho por código de factura.
        
        DELEGADO a DespachoCabeceraRepository.
        """
        return self.cabecera_repo.find_by_codigo_factura(codigo_factura)

    def get_existing_cabecera(self, despacho_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos existentes de una cabecera de despacho.
        
        DELEGADO a DespachoCabeceraRepository.
        """
        return self.cabecera_repo.get_by_id(despacho_id)

    def insert_cabecera(self, datos_cabecera: Dict[str, Any]) -> str:
        """
        Inserta un registro en despacho_cabecera.
        
        DELEGADO a DespachoCabeceraRepository.
        """
        return self.cabecera_repo.insert(datos_cabecera)

    def update_cabecera(self, despacho_id: str, datos_cabecera: Dict[str, Any]) -> bool:
        """
        Actualiza un registro existente en despacho_cabecera.

        DELEGADO a DespachoCabeceraRepository.
        """
        return self.cabecera_repo.update(despacho_id, datos_cabecera)

    # ========== Métodos de Detalle (delegados) ==========

    def insert_detalles(self, despacho_id: str, detalles: List[Dict[str, Any]]) -> int:
        """
        Inserta múltiples líneas de detalle en despacho_detalle.

        DELEGADO a DespachoDetalleRepository.
        """
        return self.detalle_repo.insert_many(despacho_id, detalles)

    def get_detalles(self, despacho_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los detalles de un despacho.

        DELEGADO a DespachoDetalleRepository.
        """
        return self.detalle_repo.get_by_despacho_id(despacho_id)

    def delete_detalles(self, despacho_id: str) -> int:
        """
        Elimina todos los detalles de un despacho.

        DELEGADO a DespachoDetalleRepository.
        """
        return self.detalle_repo.delete_by_despacho_id(despacho_id)

    # ========== Métodos de Consulta (delegados) ==========

    def get_despachos_sin_oc(self) -> List[str]:
        """
        Obtiene todos los despacho_id que no tienen una orden de compra asociada.

        DELEGADO a DespachoQueryRepository.
        """
        return self.query_repo.get_despachos_sin_oc()

    def count_despachos_sin_oc(self) -> int:
        """
        Cuenta los despachos que no tienen una orden de compra asociada.

        DELEGADO a DespachoQueryRepository.
        """
        return self.query_repo.count_despachos_sin_oc()

    def get_despachos_con_info_oc(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Obtiene información detallada de despachos junto con sus órdenes de compra asociadas.

        DELEGADO a DespachoQueryRepository.
        """
        return self.query_repo.get_despachos_con_info_oc(limit)
