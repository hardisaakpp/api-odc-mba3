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
    upsert: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Copia datos de despacho_cabecera/detalle a orden_compra_cabecera/detalle.
    
    Implementa lógica UPSERT igual que despacho:
    - Si existe OC para el despacho: actualiza cabecera y reemplaza todos los detalles
    - Si no existe: inserta nueva cabecera y detalles
    
    Proceso:
    1. Verifica si ya existe una OC para este despacho
    2. Obtiene la cabecera de despacho
    3. Mapea empresa → proveedor (desde tabla cliente si es necesario)
    4. Si existe OC: actualiza cabecera, elimina detalles antiguos, inserta nuevos
    5. Si no existe: crea nueva cabecera y detalles
    
    Args:
        despacho_repo: Repositorio de despachos
        oc_repo: Repositorio de órdenes de compra
        despacho_id: UUID del despacho a copiar
        upsert: Si True, actualiza si existe; si False, inserta siempre
        
    Returns:
        Diccionario con información del resultado:
        {
            "oc_id": "uuid",
            "despacho_id": "uuid",
            "proveedor": "CardCode",
            "detalles_insertados": 5,
            "cabecera_insertada": False,
            "cabecera_actualizada": True
        }
        O None si hubo error
        
    Raises:
        Exception: Si falla la copia
    """
    result = {
        "oc_id": None,
        "despacho_id": despacho_id,
        "proveedor": None,
        "detalles_insertados": 0,
        "cabecera_insertada": False,
        "cabecera_actualizada": False
    }
    
    try:
        # 1. Verificar si ya existe una OC para este despacho (para upsert)
        existing_oc_id = None
        if upsert:
            existing_oc_id = oc_repo.find_by_despacho_id(despacho_id)
        
        # 2. Obtener cabecera de despacho
        despacho_cabecera = despacho_repo.get_existing_cabecera(despacho_id)
        if not despacho_cabecera:
            logger.error(f"❌ No se encontró despacho con ID: {despacho_id}")
            return None
        
        # Agregar despacho_id al diccionario
        despacho_cabecera["despacho_id"] = despacho_id
        
        # 3. Mapear empresa → proveedor
        empresa = despacho_cabecera.get("empresa")
        if empresa is None:
            logger.error(f"❌ No se encontró 'empresa' en despacho_cabecera para despacho {despacho_id}")
            return None
        
        proveedor = oc_repo.get_proveedor_from_cliente(empresa)
        
        if not proveedor:
            logger.warning(f"⚠️ No se pudo obtener proveedor para empresa: {empresa}. Usando empresa como proveedor.")
            proveedor = empresa
        
        if proveedor is None:
            logger.error(f"❌ No se pudo determinar proveedor para despacho {despacho_id}")
            return None
        
        logger.debug(f"🔄 Mapeo empresa → proveedor: {empresa} → {proveedor}")
        result["proveedor"] = proveedor
        
        # 4. Transformar cabecera
        oc_cabecera_data = OrdenCompraMapper.to_orden_compra_cabecera(
            despacho_cabecera,
            proveedor
        )
        
        if existing_oc_id:
            # ACTUALIZAR OC existente (UPSERT)
            logger.info(f"🔄 OC ya existe para despacho {despacho_id} (oc_id: {existing_oc_id}) - Actualizando...")
            
            # Actualizar cabecera
            oc_repo.update_cabecera(existing_oc_id, oc_cabecera_data)
            result["oc_id"] = existing_oc_id
            result["cabecera_insertada"] = False
            result["cabecera_actualizada"] = True
            
            # Eliminar detalles antiguos
            detalles_eliminados = oc_repo.delete_detalles(existing_oc_id)
            logger.debug(f"   → {detalles_eliminados} detalles antiguos eliminados")
            
            oc_id = existing_oc_id
        else:
            # INSERTAR nueva OC
            oc_id = oc_repo.insert_cabecera(oc_cabecera_data)
            result["oc_id"] = oc_id
            result["cabecera_insertada"] = True
            result["cabecera_actualizada"] = False
            logger.info(f"✅ Orden de compra cabecera creada: {oc_id} para despacho {despacho_id}")
        
        # 5. Obtener detalles de despacho
        despacho_detalles = despacho_repo.get_detalles(despacho_id)
        
        if not despacho_detalles:
            logger.warning(f"⚠️ No se encontraron detalles para despacho {despacho_id}")
            return result
        
        # 6. Transformar y preparar detalles
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
        
        # 7. Insertar detalles (tanto para INSERT como UPDATE)
        detalles_insertados = oc_repo.insert_detalles(oc_id, oc_detalles)
        result["detalles_insertados"] = detalles_insertados
        
        accion = "actualizada" if result.get("cabecera_actualizada") else "creada"
        logger.info(
            f"✅ OC {accion}: {oc_id} para despacho {despacho_id} "
            f"(detalles: {detalles_insertados})"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error al copiar despacho a orden de compra: {e}")
        logger.error(f"   Despacho ID: {despacho_id}")
        raise

