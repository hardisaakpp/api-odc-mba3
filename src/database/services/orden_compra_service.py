"""
Servicio para copiar datos de despacho a orden de compra.
"""

import logging
from typing import Dict, Any, Optional

from ..repositories.despacho_repository import DespachoRepository
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..mappers.orden_compra_mapper import OrdenCompraMapper

logger = logging.getLogger(__name__)


def copy_despacho_to_orden_compra(
    despacho_repo: DespachoRepository,
    oc_repo: OrdenCompraRepository,
    despacho_id: str,
    skip_if_exists: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Copia datos de despacho_cabecera/detalle a orden_compra_cabecera/detalle.
    
    Proceso:
    1. Obtiene la cabecera de despacho
    2. Mapea empresa → proveedor (desde tabla cliente si es necesario)
    3. Crea orden_compra_cabecera
    4. Obtiene los detalles de despacho
    5. Crea orden_compra_detalle para cada detalle
    
    Args:
        despacho_repo: Repositorio de despachos
        oc_repo: Repositorio de órdenes de compra
        despacho_id: UUID del despacho a copiar
        skip_if_exists: Si True, no copia si ya existe una OC para este despacho
        
    Returns:
        Diccionario con información del resultado:
        {
            "oc_id": "uuid",
            "despacho_id": "uuid",
            "proveedor": "CardCode",
            "detalles_insertados": 5
        }
        O None si hubo error o ya existe
        
    Raises:
        Exception: Si falla la copia
    """
    try:
        # Verificar si ya existe una OC para este despacho
        if skip_if_exists:
            existing_oc_id = oc_repo.find_by_despacho_id(despacho_id)
            if existing_oc_id:
                logger.info(f"⏭️ Ya existe orden de compra para despacho {despacho_id}: {existing_oc_id}")
                return None
        
        # 1. Obtener cabecera de despacho
        despacho_cabecera = despacho_repo.get_existing_cabecera(despacho_id)
        if not despacho_cabecera:
            logger.error(f"❌ No se encontró despacho con ID: {despacho_id}")
            return None
        
        # Agregar despacho_id al diccionario
        despacho_cabecera["despacho_id"] = despacho_id
        
        # 2. Mapear empresa → proveedor
        empresa = despacho_cabecera.get("empresa")
        proveedor = oc_repo.get_proveedor_from_cliente(empresa)
        
        if not proveedor:
            logger.warning(f"⚠️ No se pudo obtener proveedor para empresa: {empresa}. Usando empresa como proveedor.")
            proveedor = empresa
        
        logger.debug(f"🔄 Mapeo empresa → proveedor: {empresa} → {proveedor}")
        
        # 3. Transformar cabecera
        oc_cabecera_data = OrdenCompraMapper.to_orden_compra_cabecera(
            despacho_cabecera,
            proveedor
        )
        
        # 4. Insertar cabecera de orden de compra
        oc_id = oc_repo.insert_cabecera(oc_cabecera_data)
        logger.info(f"✅ Orden de compra cabecera creada: {oc_id} para despacho {despacho_id}")
        
        # 5. Obtener detalles de despacho
        despacho_detalles = despacho_repo.get_detalles(despacho_id)
        
        if not despacho_detalles:
            logger.warning(f"⚠️ No se encontraron detalles para despacho {despacho_id}")
            return {
                "oc_id": oc_id,
                "despacho_id": despacho_id,
                "proveedor": proveedor,
                "detalles_insertados": 0
            }
        
        # 6. Transformar y insertar detalles
        oc_detalles = []
        for despacho_detalle in despacho_detalles:
            oc_detalle = OrdenCompraMapper.to_orden_compra_detalle(
                despacho_detalle,
                oc_id
            )
            # Solo agregar si tiene los campos mínimos requeridos
            if oc_detalle.get("sku_sap") and oc_detalle.get("cantidad_sap") is not None:
                oc_detalles.append(oc_detalle)
            else:
                logger.warning(
                    f"⚠️ Detalle omitido por falta de datos: "
                    f"SKU={oc_detalle.get('sku_sap')}, "
                    f"Cantidad={oc_detalle.get('cantidad_sap')}"
                )
        
        detalles_insertados = oc_repo.insert_detalles(oc_id, oc_detalles)
        
        logger.info(
            f"✅ Proceso completado: OC {oc_id} creada con {detalles_insertados} detalles "
            f"desde despacho {despacho_id}"
        )
        
        return {
            "oc_id": oc_id,
            "despacho_id": despacho_id,
            "proveedor": proveedor,
            "detalles_insertados": detalles_insertados
        }
        
    except Exception as e:
        logger.error(f"❌ Error al copiar despacho a orden de compra: {e}")
        logger.error(f"   Despacho ID: {despacho_id}")
        raise

