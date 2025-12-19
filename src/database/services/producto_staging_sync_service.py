"""
Servicio para sincronizar maestros de productos desde ERPs a staging.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.database.connection import get_db_connection, get_sap_db_connection
from src.database.repositories.producto_mba3_staging_repository import ProductoMBA3StagingRepository
from src.database.repositories.producto_sap_staging_repository import ProductoSAPStagingRepository
from src.database.repositories.sync_control_repository import SyncControlRepository
from src.services.mba3_service import MBA3Service
from src.config import SAP_LINKED_SERVER, SAP_DATABASE

logger = logging.getLogger(__name__)


def normalizar_codigo(codigo: str) -> str:
    """
    Normaliza código de producto para comparación.
    
    Regla: Eliminar puntos, guiones, espacios, convertir a mayúsculas.
    
    Args:
        codigo: Código a normalizar
        
    Returns:
        Código normalizado
    """
    if not codigo:
        return ""
    return re.sub(r'[.\-\s]', '', codigo.strip().upper())


class ProductoStagingSyncService:
    """
    Servicio para sincronizar maestros de productos desde ERPs a staging.
    """
    
    def __init__(self):
        """Inicializa el servicio."""
        self.mba3_service = MBA3Service()
    
    def sync_mba3_products(self) -> Dict[str, Any]:
        """
        Sincroniza productos MBA3 desde API a staging.
        
        Returns:
            Diccionario con estadísticas de sincronización
        """
        conn = None
        sync_control_id = None
        start_time = datetime.now()
        
        try:
            logger.info("🔄 Iniciando sincronización de productos MBA3...")
            
            # Obtener conexión y repositorios
            conn = get_db_connection()
            sync_control_repo = SyncControlRepository(conn)
            mba3_staging_repo = ProductoMBA3StagingRepository(conn)
            
            # Iniciar registro en sync_control
            sync_control_id = sync_control_repo.iniciar_sync('MBA3', 'BACKEND')
            
            # Consultar productos desde MBA3 API
            query = (
                "SELECT "
                "PRODUCT_ID, "
                "PRODUCT_NAME, "
                "CORP, "
                "GrupoPrenda, "
                "Talla, "
                "PRESENTACION, "
                "Descontinuado "
                "FROM INVT_FICHA_PRINCIPAL "
                "WHERE PRODUCT_ID IS NOT NULL "
                "LIMIT 500"
            )
            
            logger.info("🔍 Consultando productos desde MBA3 API...")
            result = self.mba3_service.execute_query(query)
            
            # Normalizar estructura de respuesta
            productos = []
            if isinstance(result, list):
                productos = result
            elif isinstance(result, dict):
                for key, value in result.items():
                    if isinstance(value, list):
                        productos = value
                        break
                if not productos and result:
                    productos = [result]
            
            logger.info(f"📦 Procesando {len(productos)} productos desde MBA3...")
            
            # Preparar productos para staging
            productos_staging = []
            for producto in productos:
                try:
                    product_id = str(producto.get("PRODUCT_ID") or producto.get("product_id") or producto.get("Product_ID", "")).strip()
                    if not product_id:
                        continue
                    
                    # CORRECCIÓN: Normalizar en sync, no en cruce
                    product_id_normalizado = normalizar_codigo(product_id)
                    
                    # Extraer datos
                    product_name = producto.get("PRODUCT_NAME") or producto.get("product_name") or producto.get("Product_Name", "")
                    corp = producto.get("CORP") or producto.get("corp") or producto.get("Corp", "")
                    grupo_prenda = producto.get("GrupoPrenda") or producto.get("grupoPrenda") or producto.get("grupo_prenda", "")
                    talla = producto.get("Talla") or producto.get("talla", "")
                    presentacion = producto.get("PRESENTACION") or producto.get("presentacion") or producto.get("Presentacion", "")
                    descontinuado = bool(producto.get("Descontinuado") or producto.get("descontinuado") or False)
                    
                    productos_staging.append({
                        "product_id": product_id,
                        "product_name": str(product_name).strip() if product_name else "",
                        "corp": str(corp).strip() if corp else "",
                        "grupo_prenda": str(grupo_prenda).strip() if grupo_prenda else "",
                        "talla": str(talla).strip() if talla else "",
                        "presentacion": str(presentacion).strip() if presentacion else "",
                        "descontinuado": descontinuado,
                        "product_id_normalizado": product_id_normalizado
                    })
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando producto MBA3: {e}")
                    continue
            
            # Sincronizar a staging (UPSERT)
            logger.info(f"💾 Guardando {len(productos_staging)} productos en staging...")
            stats = mba3_staging_repo.bulk_insert_or_update(productos_staging)
            
            # Calcular duración
            end_time = datetime.now()
            duracion_segundos = int((end_time - start_time).total_seconds())
            
            # Finalizar sync_control
            sync_control_repo.finalizar_sync(
                sync_control_id,
                'EXITOSA',
                stats["total"],
                stats["insertados"],
                stats["actualizados"],
                None,
                duracion_segundos
            )
            
            logger.info(
                f"✅ Sync MBA3 completado: {stats['total']} procesados, "
                f"{stats['insertados']} nuevos, {stats['actualizados']} actualizados "
                f"({duracion_segundos}s)"
            )
            
            return {
                "status": "success",
                "entidad": "MBA3",
                "registros_procesados": stats["total"],
                "registros_nuevos": stats["insertados"],
                "registros_actualizados": stats["actualizados"],
                "registros_con_error": stats["errores"],
                "duracion_segundos": duracion_segundos,
                "timestamp": end_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error crítico en sync MBA3: {e}", exc_info=True)
            
            # Marcar sync_control como ERROR
            if conn and sync_control_id:
                try:
                    sync_control_repo = SyncControlRepository(conn)
                    end_time = datetime.now()
                    duracion_segundos = int((end_time - start_time).total_seconds())
                    sync_control_repo.finalizar_sync(
                        sync_control_id,
                        'ERROR',
                        0, 0, 0,
                        str(e),
                        duracion_segundos
                    )
                except:
                    pass
            
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def sync_sap_products(self) -> Dict[str, Any]:
        """
        Sincroniza productos SAP desde OPENQUERY a staging.
        
        Returns:
            Diccionario con estadísticas de sincronización
        """
        conn = None
        sap_conn = None
        sync_control_id = None
        start_time = datetime.now()
        
        try:
            logger.info("🔄 Iniciando sincronización de productos SAP...")
            
            # Obtener conexiones y repositorios
            conn = get_db_connection()
            sap_conn = get_sap_db_connection()
            sync_control_repo = SyncControlRepository(conn)
            sap_staging_repo = ProductoSAPStagingRepository(conn)
            
            # Iniciar registro en sync_control
            sync_control_id = sync_control_repo.iniciar_sync('SAP', 'BACKEND')
            
            # Consultar productos desde SAP via OPENQUERY
            query = f"""
            SELECT 
                T0."ItemCode",
                T0."ItemName",
                T0."U_IXX_PACK",
                T0."ItmsGrpCod",
                T0."validFor",
                T0."ItmsGrpNam"
            FROM OPENQUERY([{SAP_LINKED_SERVER}], '
                SELECT TOP 500
                    OITM."ItemCode",
                    OITM."ItemName",
                    OITM."U_IXX_PACK",
                    OITM."ItmsGrpCod",
                    OITM."validFor",
                    OITB."ItmsGrpNam"
                FROM "{SAP_DATABASE}"."OITM" OITM
                INNER JOIN "{SAP_DATABASE}"."OITB" OITB 
                    ON OITM."ItmsGrpCod" = OITB."ItmsGrpCod"
                WHERE OITM."ItemCode" IS NOT NULL
                  AND OITB."ItmsGrpNam" IN (''R-MEDIAS'', ''RD-INDUM MEDIAS'')
            ') T0;
            """
            
            logger.info("🔍 Consultando productos desde SAP (OPENQUERY)...")
            cursor = sap_conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            
            logger.info(f"📦 Procesando {len(results)} productos desde SAP...")
            
            # Preparar productos para staging
            productos_staging = []
            for row in results:
                try:
                    item_code = row[0] if row[0] else ""
                    if not item_code:
                        continue
                    
                    item_code = str(item_code).strip()
                    
                    # CORRECCIÓN: Normalizar en sync
                    item_code_normalizado = normalizar_codigo(item_code)
                    
                    # Extraer datos
                    item_name = row[1] if row[1] else ""
                    pack_sap = row[2] if row[2] else ""
                    itms_grp_cod = row[3] if row[3] else None
                    valid_for_raw = row[4] if row[4] is not None else 'N'
                    valid_for = str(valid_for_raw).upper()
                    itms_grp_nam = row[5] if row[5] else ""
                    
                    # CORRECCIÓN: activo es derivado, no editable
                    activo = (valid_for == 'Y')
                    
                    productos_staging.append({
                        "item_code": item_code,
                        "item_name": str(item_name).strip() if item_name else "",
                        "pack_sap": str(pack_sap).strip() if pack_sap else "",
                        "itms_grp_cod": itms_grp_cod,
                        "itms_grp_nam": str(itms_grp_nam).strip() if itms_grp_nam else "",
                        "valid_for": valid_for,
                        "activo": activo,
                        "item_code_normalizado": item_code_normalizado
                    })
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando producto SAP: {e}")
                    continue
            
            # Sincronizar a staging (UPSERT)
            logger.info(f"💾 Guardando {len(productos_staging)} productos en staging...")
            stats = sap_staging_repo.bulk_insert_or_update(productos_staging)
            
            # Calcular duración
            end_time = datetime.now()
            duracion_segundos = int((end_time - start_time).total_seconds())
            
            # Finalizar sync_control
            sync_control_repo.finalizar_sync(
                sync_control_id,
                'EXITOSA',
                stats["total"],
                stats["insertados"],
                stats["actualizados"],
                None,
                duracion_segundos
            )
            
            logger.info(
                f"✅ Sync SAP completado: {stats['total']} procesados, "
                f"{stats['insertados']} nuevos, {stats['actualizados']} actualizados "
                f"({duracion_segundos}s)"
            )
            
            return {
                "status": "success",
                "entidad": "SAP",
                "registros_procesados": stats["total"],
                "registros_nuevos": stats["insertados"],
                "registros_actualizados": stats["actualizados"],
                "registros_con_error": stats["errores"],
                "duracion_segundos": duracion_segundos,
                "timestamp": end_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error crítico en sync SAP: {e}", exc_info=True)
            
            # Marcar sync_control como ERROR
            if conn and sync_control_id:
                try:
                    sync_control_repo = SyncControlRepository(conn)
                    end_time = datetime.now()
                    duracion_segundos = int((end_time - start_time).total_seconds())
                    sync_control_repo.finalizar_sync(
                        sync_control_id,
                        'ERROR',
                        0, 0, 0,
                        str(e),
                        duracion_segundos
                    )
                except:
                    pass
            
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
            if sap_conn:
                try:
                    sap_conn.close()
                except:
                    pass
    
    def sync_all(self) -> Dict[str, Any]:
        """
        Sincroniza ambos maestros (MBA3 y SAP).
        
        Returns:
            Diccionario con estadísticas combinadas
        """
        logger.info("🔄 Iniciando sincronización completa de maestros...")
        
        mba3_result = self.sync_mba3_products()
        sap_result = self.sync_sap_products()
        
        return {
            "status": "success",
            "mba3": mba3_result,
            "sap": sap_result,
            "timestamp": datetime.now().isoformat()
        }


