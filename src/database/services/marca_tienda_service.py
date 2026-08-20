"""
Servicio de solo lectura para resolver la marca de una tienda/bodega desde sc_maestros.
"""

import logging
from typing import Optional

from ..connection import get_maestros_db_connection_context

logger = logging.getLogger(__name__)

# Mapeo fijo marca (sc_maestros.almacenes_local.u_marca) -> código de bodega/CD.
MARCA_A_BODEGA = {
    "ROLAND": "RL-CD",
    "REGIONS": "RG-CD",
    "DESCUENTON": "OUT-CD",
}


class MarcaTiendaService:
    """Consulta sc_maestros.dbo.almacenes_local (servidor de producción, SOLO LECTURA)."""

    def buscar_marca(self, codigo: str) -> Optional[str]:
        """
        Busca la marca (ROLAND/REGIONS/DESCUENTON) de un código de tienda
        en sc_maestros.dbo.almacenes_local (u_bod_tra -> u_marca).

        whs_code en esta tabla es el código del Centro de Distribución (RL-CD,
        RG-CD, OUT-CD), NO el código de tienda del Excel — el código de tienda
        vive en u_bod_tra (confirmado 20/08/2026 contra datos reales).

        No bloqueante: cualquier error de conexión o de datos se loguea como
        warning y retorna None en vez de propagar la excepción, para no afectar
        el flujo de creación/lectura de la tienda.
        """
        if not codigo or not codigo.strip():
            return None
        codigo_normalizado = codigo.strip().upper()
        try:
            with get_maestros_db_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT u_marca FROM almacenes_local WHERE u_bod_tra = ?",
                    (codigo_normalizado,),
                )
                row = cursor.fetchone()
                cursor.close()
                if not row or not row[0]:
                    return None
                marca = row[0].strip().upper()
                if marca not in MARCA_A_BODEGA:
                    logger.warning(
                        f"⚠️ Marca desconocida '{marca}' para tienda {codigo_normalizado} en sc_maestros"
                    )
                    return None
                return marca
        except Exception as e:
            logger.warning(
                f"⚠️ No se pudo obtener marca de sc_maestros para {codigo_normalizado}: {e}"
            )
            return None
