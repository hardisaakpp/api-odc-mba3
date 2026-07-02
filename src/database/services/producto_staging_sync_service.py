"""
Servicio para sincronizar maestros de productos desde ERPs a staging.
"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple

from src.utils.timezone import ahora_naive

from src.database.connection import get_db_connection, get_sap_db_connection
from src.database.repositories.producto_mba3_staging_repository import ProductoMBA3StagingRepository
from src.database.repositories.producto_sap_staging_repository import ProductoSAPStagingRepository
from src.database.repositories.sync_control_repository import SyncControlRepository
from src.services.mba3_service import MBA3Service
from src.config import SAP_LINKED_SERVER, SAP_DATABASE

logger = logging.getLogger(__name__)


def normalizar_codigo(codigo: str) -> str:
    """
    Normaliza código de producto para comparación (wrapper para compatibilidad).

    IMPORTANTE: Ahora usa función centralizada que incluye TODOS los separadores:
    ., -, /, _, espacio

    DEPRECATED: Usar normalizar_codigo_producto de src.utils directamente.
    Este wrapper se mantiene por compatibilidad con código existente.

    Args:
        codigo: Código a normalizar

    Returns:
        Código normalizado
    """
    from src.utils import normalizar_codigo_producto
    return normalizar_codigo_producto(codigo)


class ProductoStagingSyncService:
    """
    Servicio para sincronizar maestros de productos desde ERPs a staging.
    """

    def __init__(self):
        """Inicializa el servicio."""
        self.mba3_service = MBA3Service()

    def _normalizar_respuesta_mba3(self, result: Any) -> List[Dict[str, Any]]:
        """
        Normaliza la estructura de respuesta del API de MBA3.

        Args:
            result: Resultado de la consulta al API

        Returns:
            Lista de productos normalizados
        """
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
        return productos

    @staticmethod
    def _determinar_estrategia_sync(
        force_full_sync: bool,
        ultimo_id: Optional[str],
        total_en_staging: int,
    ) -> Tuple[str, Optional[str]]:
        """Determina modo de sincronización. Retorna (modo_sync, cursor_inicial)."""
        if force_full_sync:
            logger.info("🔄 Sincronización completa forzada (desde el inicio)")
            return "completa", None
        if ultimo_id is None or total_en_staging == 0:
            logger.info("🔄 Tabla vacía, sincronización completa desde el inicio")
            return "completa", None
        if total_en_staging < 100:
            logger.info(f"🔄 Pocos productos en staging ({total_en_staging}), sincronización completa para asegurar consistencia")
            return "completa", None
        logger.info(f"🔄 Sincronización incremental desde: {ultimo_id} (total en staging: {total_en_staging})")
        return "incremental", ultimo_id

    def _limpiar_obsoletos_mba3(
        self,
        mba3_staging_repo: ProductoMBA3StagingRepository,
        force_full_sync: bool,
        productos_encontrados: set,
    ) -> int:
        """Elimina productos obsoletos de staging tras sincronización completa."""
        if not force_full_sync or not productos_encontrados:
            return 0
        logger.info("🗑️ Eliminando productos que ya no existen en MBA3...")
        logger.info(f"   Productos encontrados en MBA3: {len(productos_encontrados)}")
        try:
            total_eliminados = mba3_staging_repo.delete_products_not_in_list(list(productos_encontrados))
            logger.info(f"✅ Eliminados {total_eliminados} productos obsoletos")
            return total_eliminados
        except Exception as e:
            logger.error(f"❌ Error al eliminar productos obsoletos: {e}", exc_info=True)
            return 0

    def _registrar_error_sync_mba3(
        self,
        conn: Any,
        sync_control_id: Optional[int],
        start_time: Any,
        error: Exception,
    ) -> None:
        """Registra error crítico y marca sync_control como ERROR."""
        logger.error(f"❌ Error crítico en sync MBA3: {error}", exc_info=True)
        if not conn or not sync_control_id:
            return
        try:
            sync_control_repo = SyncControlRepository(conn)
            end_time = ahora_naive()
            duracion_segundos = int((end_time - start_time).total_seconds())
            sync_control_repo.finalizar_sync(
                sync_control_id, 'ERROR', 0, 0, 0, str(error), duracion_segundos
            )
        except Exception:
            pass

    def _bucle_paginacion_mba3(
        self,
        mba3_staging_repo: ProductoMBA3StagingRepository,
        query_base: str,
        batch_size: int,
        force_full_sync: bool,
    ) -> Dict[str, Any]:
        """Ejecuta el bucle de paginación por lotes para MBA3."""
        total_insertados = 0
        total_actualizados = 0
        total_errores = 0
        total_procesados = 0
        productos_encontrados: set = set()
        last_product_id = None
        batch_number = 0
        lotes_fallidos_consecutivos = 0
        max_lotes_fallidos = 3
        primer_product_id_anterior = None
        lotes_repetidos_consecutivos = 0
        max_lotes_repetidos = 2

        while True:
            batch_number += 1

            if last_product_id:
                last_product_id_escaped = str(last_product_id).replace("'", "''")
                if lotes_repetidos_consecutivos > 0:
                    logger.warning(
                        "⚠️ Intentando estrategia alternativa de paginación (usando solo >) "
                        "debido a productos repetidos..."
                    )
                    query = f"{query_base} AND PRODUCT_ID > '{last_product_id_escaped}' LIMIT {batch_size}"
                    logger.info(f"   Cursor alternativo: PRODUCT_ID > '{last_product_id}'")
                else:
                    query = f"{query_base} AND PRODUCT_ID >= '{last_product_id_escaped}' AND PRODUCT_ID != '{last_product_id_escaped}' LIMIT {batch_size}"
                    logger.info(f"   Cursor: PRODUCT_ID >= '{last_product_id}' AND PRODUCT_ID != '{last_product_id}'")
            else:
                query = f"{query_base} LIMIT {batch_size}"

            logger.info(f"📦 Lote {batch_number}: Consultando productos desde MBA3 API...")

            max_retries = 3
            retry_count = 0
            result = None
            lote_exitoso = False

            while retry_count < max_retries:
                try:
                    result = self.mba3_service.execute_query(query)
                    lote_exitoso = True
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.error(
                            f"❌ Error en consulta del lote {batch_number} después de {max_retries} intentos: {e}",
                            exc_info=True
                        )
                        logger.warning(
                            f"⚠️ Saltando lote {batch_number} y continuando con el siguiente..."
                        )
                        break
                    else:
                        wait_time = retry_count * 5
                        logger.warning(
                            f"⚠️ Reintentando lote {batch_number} (intento {retry_count}/{max_retries}) "
                            f"después de {wait_time}s... Error: {str(e)[:100]}"
                        )
                        time.sleep(wait_time)

            if not lote_exitoso:
                total_errores += batch_size
                lotes_fallidos_consecutivos += 1
                if lotes_fallidos_consecutivos >= max_lotes_fallidos:
                    logger.error(
                        f"❌ {max_lotes_fallidos} lotes consecutivos fallaron. "
                        f"Deteniendo sincronización para evitar bucle infinito."
                    )
                    break
                logger.warning(
                    f"⚠️ Lote {batch_number} falló después de {max_retries} intentos. "
                    f"Lotes fallidos consecutivos: {lotes_fallidos_consecutivos}/{max_lotes_fallidos}. "
                    f"Continuando con siguiente lote..."
                )
                continue

            lotes_fallidos_consecutivos = 0
            productos = self._normalizar_respuesta_mba3(result)

            if not productos:
                logger.info(f"✅ No hay más productos. Total procesado: {total_procesados}")
                break

            primer_producto_actual = productos[0]
            primer_product_id_actual = str(
                primer_producto_actual.get("PRODUCT_ID") or
                primer_producto_actual.get("product_id") or
                primer_producto_actual.get("Product_ID", "")
            ).strip()

            if primer_product_id_anterior and primer_product_id_actual == primer_product_id_anterior:
                lotes_repetidos_consecutivos += 1
                logger.warning(
                    f"⚠️ Lote {batch_number}: Primer producto repetido ({primer_product_id_actual}). "
                    f"MBA3 no está respetando la paginación. Lotes repetidos consecutivos: {lotes_repetidos_consecutivos}/{max_lotes_repetidos}"
                )
                if lotes_repetidos_consecutivos >= max_lotes_repetidos:
                    logger.error(
                        f"❌ {max_lotes_repetidos} lotes consecutivos con el mismo primer producto. "
                        f"MBA3 no está respetando la condición de paginación. Deteniendo sincronización para evitar bucle infinito."
                    )
                    logger.info(f"✅ Sincronización detenida. Total procesado: {total_procesados}")
                    break
            else:
                lotes_repetidos_consecutivos = 0
                primer_product_id_anterior = primer_product_id_actual

            if last_product_id and productos:
                primer_producto = productos[0]
                primer_product_id = str(
                    primer_producto.get("PRODUCT_ID") or
                    primer_producto.get("product_id") or
                    primer_producto.get("Product_ID", "")
                ).strip()
                if primer_product_id == last_product_id:
                    logger.info(f"⚠️ Primer producto del lote es igual al cursor ({last_product_id}), filtrándolo...")
                    productos = productos[1:]
                    if not productos:
                        logger.info(f"✅ No hay más productos después de filtrar. Total procesado: {total_procesados}")
                        break
                    logger.info(f"   Productos restantes después de filtrar: {len(productos)}")

            logger.info(f"📦 Lote {batch_number}: Procesando {len(productos)} productos...")

            productos_staging = []
            ultimo_product_id_valido = None

            if productos:
                primer_producto = productos[0]
                ultimo_producto_lote = productos[-1]
                primer_product_id = str(
                    primer_producto.get("PRODUCT_ID") or
                    primer_producto.get("product_id") or
                    primer_producto.get("Product_ID", "")
                ).strip()
                ultimo_product_id_lote = str(
                    ultimo_producto_lote.get("PRODUCT_ID") or
                    ultimo_producto_lote.get("product_id") or
                    ultimo_producto_lote.get("Product_ID", "")
                ).strip()
                if ultimo_product_id_lote:
                    ultimo_product_id_valido = ultimo_product_id_lote
                    logger.info(f"🔍 DIAGNÓSTICO Lote {batch_number}:")
                    logger.info(f"   Cursor usado en query: {last_product_id if last_product_id else 'None (primer lote)'}")
                    logger.info(f"   Primer producto recibido: {primer_product_id}")
                    logger.info(f"   Último producto recibido: {ultimo_product_id_valido}")
                    logger.info(f"   Total productos en lote: {len(productos)}")
                    logger.debug(f"📍 Cursor preparado desde último producto del lote: {ultimo_product_id_valido}")

            for producto in productos:
                try:
                    product_id = str(producto.get("PRODUCT_ID") or producto.get("product_id") or producto.get("Product_ID", "")).strip()
                    if not product_id:
                        continue
                    product_id_normalizado = normalizar_codigo(product_id)
                    product_name = producto.get("PRODUCT_NAME") or producto.get("product_name") or producto.get("Product_Name", "")
                    corp = producto.get("CORP") or producto.get("corp") or producto.get("Corp", "")
                    grupo_prenda = producto.get("GrupoPrenda") or producto.get("grupoPrenda") or producto.get("grupo_prenda", "")
                    talla = producto.get("Talla") or producto.get("talla", "")
                    presentacion = producto.get("PRESENTACION") or producto.get("presentacion") or producto.get("Presentacion", "")
                    descontinuado_raw = producto.get("Descontinuado") or producto.get("descontinuado")
                    descontinuado = bool(descontinuado_raw) if descontinuado_raw else False
                    group_code = producto.get("GROUP_CODE") or producto.get("group_code") or producto.get("Group_Code", "")
                    inactive = producto.get("INACTIVE") or producto.get("inactive") or producto.get("Inactive", "")
                    tipo_origen = producto.get("Tipo_Origen") or producto.get("tipo_origen") or producto.get("Tipo_Origen", "")
                    if (str(descontinuado).lower() == 'true' or
                            str(inactive).lower() == 'true' or
                            group_code != 'PTERM' or
                            tipo_origen in ['ESPEC', 'EXPOR', 'MAPRO']):
                        logger.debug(f"⚠️ Producto {product_id} no cumple filtros, omitiendo...")
                        continue
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
                    if force_full_sync:
                        productos_encontrados.add(product_id)
                except Exception as e:
                    total_errores += 1
                    logger.warning(f"⚠️ Error procesando producto MBA3: {e}")
                    continue

            if ultimo_product_id_valido:
                last_product_id = ultimo_product_id_valido
                logger.info(f"📍 Cursor actualizado para siguiente lote: {last_product_id}")

            if productos_staging:
                logger.info(f"💾 Lote {batch_number}: Guardando {len(productos_staging)} productos en staging...")
                try:
                    stats = mba3_staging_repo.bulk_insert_or_update(productos_staging)
                    total_insertados += stats["insertados"]
                    total_actualizados += stats["actualizados"]
                    total_errores += stats["errores"]
                    total_procesados += len(productos_staging)
                    logger.info(
                        f"✅ Lote {batch_number} completado: "
                        f"{stats['insertados']} nuevos, {stats['actualizados']} actualizados, "
                        f"{stats['errores']} errores"
                    )
                except Exception as e:
                    logger.error(f"❌ Error guardando lote {batch_number}: {e}", exc_info=True)
                    total_errores += len(productos_staging)

            if len(productos) < batch_size:
                logger.info(f"✅ Último lote procesado (menos de {batch_size} productos)")
                break

            logger.info(
                f"📊 Progreso acumulado: {total_procesados} productos procesados | "
                f"Nuevos: {total_insertados} | "
                f"Actualizados: {total_actualizados} | "
                f"Errores: {total_errores}"
            )

        return {
            'total_insertados': total_insertados,
            'total_actualizados': total_actualizados,
            'total_errores': total_errores,
            'total_procesados': total_procesados,
            'productos_encontrados': productos_encontrados,
            'batch_number': batch_number,
        }

    def sync_mba3_products(self, batch_size: int = 1000, force_full_sync: bool = False) -> Dict[str, Any]:
        """
        Sincroniza productos MBA3 desde API a staging con paginación por lotes.

        Usa cursor basado en PRODUCT_ID para paginación eficiente.
        Query corregida con filtros de negocio alineados con el cruce de productos.

        Soporta sincronización incremental (desde último producto) o completa (desde inicio).
        Por defecto usa incremental si hay productos en staging, completa si está vacío.

        Args:
            batch_size: Tamaño de cada lote (default: 1000)
            force_full_sync: Si True, fuerza sincronización completa desde el inicio (default: False)

        Returns:
            Diccionario con estadísticas de sincronización
        """
        conn = None
        sync_control_id = None
        start_time = ahora_naive()
        try:
            logger.info("🔄 Iniciando sincronización de productos MBA3 con paginación...")
            logger.info(f"📊 Configuración: batch_size={batch_size}, force_full_sync={force_full_sync}")

            conn = get_db_connection()
            sync_control_repo = SyncControlRepository(conn)
            mba3_staging_repo = ProductoMBA3StagingRepository(conn)

            modo_sync, _ = self._determinar_estrategia_sync(
                force_full_sync,
                mba3_staging_repo.get_last_product_id(),
                mba3_staging_repo.count_all()
            )
            sync_control_id = sync_control_repo.iniciar_sync('MBA3', 'BACKEND')

            query_base = (
                "SELECT "
                "PRODUCT_NAME, "
                "PRODUCT_ID, "
                "GrupoPrenda, "
                "CORP, "
                "Talla, "
                "PRESENTACION, "
                "Descontinuado, "
                "GROUP_CODE, "
                "INACTIVE, "
                "Tipo_Origen, "
                "SELL, "
                "CODE_PROV_O_ALT, "
                "CATEGORY, "
                "Familia, "
                "Codigo_Marca, "
                "PRODUCT_NAME_2, "
                "Fecha_Ultima_Venta, "
                "FechaUltimoMovimiento "
                "FROM INVT_FICHA_PRINCIPAL "
                "WHERE PRODUCT_ID IS NOT NULL "
                "AND GrupoPrenda IS NOT NULL "
                "AND Descontinuado = 'false' "
                "AND GROUP_CODE = 'PTERM' "
                "AND INACTIVE = 'false' "
                "AND Tipo_Origen != 'ESPEC' "
                "AND Tipo_Origen != 'EXPOR' "
                "AND Tipo_Origen != 'MAPRO' "
                "AND PRODUCT_NAME IS NOT NULL "
                "AND SELL > 0 "
                "ORDER BY PRODUCT_ID"
            )

            loop_stats = self._bucle_paginacion_mba3(mba3_staging_repo, query_base, batch_size, force_full_sync)
            total_eliminados = self._limpiar_obsoletos_mba3(
                mba3_staging_repo, force_full_sync, loop_stats['productos_encontrados']
            )

            end_time = ahora_naive()
            duracion_segundos = int((end_time - start_time).total_seconds())
            sync_control_repo.finalizar_sync(
                sync_control_id, 'EXITOSA',
                loop_stats['total_procesados'], loop_stats['total_insertados'],
                loop_stats['total_actualizados'], None, duracion_segundos
            )
            logger.info(
                f"✅ Sync MBA3 completado: {loop_stats['total_procesados']} procesados, "
                f"{loop_stats['total_insertados']} nuevos, {loop_stats['total_actualizados']} actualizados, "
                f"{total_eliminados} eliminados, {loop_stats['total_errores']} errores ({duracion_segundos}s)"
            )
            return {
                "status": "success",
                "entidad": "MBA3",
                "modo_sincronizacion": modo_sync,
                "registros_procesados": loop_stats['total_procesados'],
                "registros_nuevos": loop_stats['total_insertados'],
                "registros_actualizados": loop_stats['total_actualizados'],
                "registros_eliminados": total_eliminados,
                "registros_con_error": loop_stats['total_errores'],
                "duracion_segundos": duracion_segundos,
                "lotes_procesados": loop_stats['batch_number'],
                "timestamp": end_time.isoformat()
            }
        except Exception as e:
            self._registrar_error_sync_mba3(conn, sync_control_id, start_time, e)
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _registrar_error_sync_sap(
        self,
        conn: Any,
        sync_control_id: Optional[int],
        start_time: Any,
        error: Exception,
    ) -> None:
        """Registra error crítico y marca sync_control como ERROR."""
        logger.error(f"❌ Error crítico en sync SAP: {error}", exc_info=True)
        if not conn or not sync_control_id:
            return
        try:
            sync_control_repo = SyncControlRepository(conn)
            end_time = ahora_naive()
            duracion_segundos = int((end_time - start_time).total_seconds())
            sync_control_repo.finalizar_sync(
                sync_control_id, 'ERROR', 0, 0, 0, str(error), duracion_segundos
            )
        except Exception:
            pass

    def _bucle_paginacion_sap(
        self,
        sap_conn: Any,
        sap_staging_repo: ProductoSAPStagingRepository,
        query_base: str,
        batch_size: int,
        last_item_code: Optional[str],
    ) -> Dict[str, Any]:
        """Ejecuta el bucle de paginación por lotes para SAP."""
        total_insertados = 0
        total_actualizados = 0
        total_errores = 0
        total_procesados = 0
        batch_number = 0
        lotes_fallidos_consecutivos = 0
        max_lotes_fallidos = 3

        while True:
            batch_number += 1

            if last_item_code:
                last_item_code_escaped = str(last_item_code).replace("'", "''")
                query = f"{query_base} WHERE T0.\"ItemCode\" > '{last_item_code_escaped}' ORDER BY T0.\"ItemCode\" OFFSET 0 ROWS FETCH NEXT {batch_size} ROWS ONLY"
            else:
                query = f"{query_base} ORDER BY T0.\"ItemCode\" OFFSET 0 ROWS FETCH NEXT {batch_size} ROWS ONLY"

            logger.info(f"📦 Lote {batch_number}: Consultando productos desde SAP (OPENQUERY)...")
            if last_item_code:
                logger.info(f"   Cursor: ItemCode > '{last_item_code}'")
            logger.info(f"   Fetch: {batch_size}")

            max_retries = 3
            retry_count = 0
            results = None
            lote_exitoso = False

            while retry_count < max_retries:
                try:
                    cursor = sap_conn.cursor()
                    cursor.execute(query)
                    results = cursor.fetchall()
                    cursor.close()
                    lote_exitoso = True
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.error(
                            f"❌ Error en consulta del lote {batch_number} después de {max_retries} intentos: {e}",
                            exc_info=True
                        )
                        logger.warning(
                            f"⚠️ Saltando lote {batch_number} y continuando con el siguiente..."
                        )
                        break
                    else:
                        wait_time = retry_count * 5
                        logger.warning(
                            f"⚠️ Reintentando lote {batch_number} (intento {retry_count}/{max_retries}) "
                            f"después de {wait_time}s... Error: {str(e)[:100]}"
                        )
                        time.sleep(wait_time)

            if not lote_exitoso:
                total_errores += batch_size
                lotes_fallidos_consecutivos += 1
                if lotes_fallidos_consecutivos >= max_lotes_fallidos:
                    logger.error(
                        f"❌ {max_lotes_fallidos} lotes consecutivos fallaron. "
                        f"Deteniendo sincronización para evitar bucle infinito."
                    )
                    break
                logger.warning(
                    f"⚠️ Lote {batch_number} falló después de {max_retries} intentos. "
                    f"Lotes fallidos consecutivos: {lotes_fallidos_consecutivos}/{max_lotes_fallidos}. "
                    f"Continuando con siguiente lote..."
                )
                continue

            lotes_fallidos_consecutivos = 0

            if not results:
                logger.info(f"✅ No hay más productos. Total procesado: {total_procesados}")
                break

            logger.info(f"📦 Lote {batch_number}: Procesando {len(results)} productos...")

            productos_staging = []
            for row in results:
                try:
                    item_code = row[0] if row[0] else ""
                    if not item_code:
                        continue
                    item_code = str(item_code).strip()
                    item_code_normalizado = normalizar_codigo(item_code)
                    item_name = row[1] if row[1] else ""
                    pack_sap = row[2] if row[2] else ""
                    sal_unit_msr = row[3] if len(row) > 3 and row[3] else ""
                    code_bars = row[4] if len(row) > 4 and row[4] else ""
                    itms_grp_nam = row[5] if len(row) > 5 and row[5] else ""
                    itms_grp_cod = row[6] if len(row) > 6 and row[6] else None
                    valid_for_raw = row[7] if len(row) > 7 and row[7] is not None else 'N'
                    valid_for = str(valid_for_raw).upper()
                    invnt_item_raw = row[8] if len(row) > 8 and row[8] is not None else 'N'
                    invnt_item = str(invnt_item_raw).upper() == 'Y'
                    activo = (valid_for == 'Y')
                    productos_staging.append({
                        "item_code": item_code,
                        "item_name": str(item_name).strip() if item_name else "",
                        "pack_sap": str(pack_sap).strip() if pack_sap else "",
                        "sal_unit_msr": str(sal_unit_msr).strip() if sal_unit_msr else "",
                        "code_bars": str(code_bars).strip() if code_bars else "",
                        "itms_grp_cod": itms_grp_cod,
                        "itms_grp_nam": str(itms_grp_nam).strip() if itms_grp_nam else "",
                        "valid_for": valid_for,
                        "activo": activo,
                        "invnt_item": invnt_item,
                        "item_code_normalizado": item_code_normalizado
                    })
                    last_item_code = item_code
                except Exception as e:
                    total_errores += 1
                    logger.warning(f"⚠️ Error procesando producto SAP: {e}")
                    continue

            if productos_staging:
                logger.info(f"💾 Lote {batch_number}: Guardando {len(productos_staging)} productos en staging...")
                try:
                    stats = sap_staging_repo.bulk_insert_or_update(productos_staging)
                    total_insertados += stats["insertados"]
                    total_actualizados += stats["actualizados"]
                    total_errores += stats["errores"]
                    total_procesados += len(productos_staging)
                    logger.info(
                        f"✅ Lote {batch_number} completado: "
                        f"{stats['insertados']} nuevos, {stats['actualizados']} actualizados, "
                        f"{stats['errores']} errores"
                    )
                except Exception as e:
                    logger.error(f"❌ Error guardando lote {batch_number}: {e}", exc_info=True)
                    total_errores += len(productos_staging)

            if len(results) < batch_size:
                logger.info(f"✅ Último lote procesado (menos de {batch_size} productos)")
                break

            logger.info(
                f"📊 Progreso acumulado: {total_procesados} productos procesados | "
                f"Nuevos: {total_insertados} | "
                f"Actualizados: {total_actualizados} | "
                f"Errores: {total_errores}"
            )

        return {
            'total_insertados': total_insertados,
            'total_actualizados': total_actualizados,
            'total_errores': total_errores,
            'total_procesados': total_procesados,
            'batch_number': batch_number,
        }

    def sync_sap_products(self, batch_size: int = 1000, force_full_sync: bool = False) -> Dict[str, Any]:
        """
        Sincroniza productos SAP desde OPENQUERY a staging con paginación por lotes.

        Usa cursor basado en ItemCode para paginación eficiente.

        Soporta sincronización incremental (desde último producto) o completa (desde inicio).
        Por defecto usa incremental si hay productos en staging, completa si está vacío.

        Args:
            batch_size: Tamaño de cada lote (default: 1000)
            force_full_sync: Si True, fuerza sincronización completa desde el inicio (default: False)

        Returns:
            Diccionario con estadísticas de sincronización
        """
        conn = None
        sap_conn = None
        sync_control_id = None
        start_time = ahora_naive()
        try:
            logger.info("🔄 Iniciando sincronización de productos SAP con paginación...")
            logger.info(f"📊 Configuración: batch_size={batch_size}, force_full_sync={force_full_sync}")

            conn = get_db_connection()
            sap_conn = get_sap_db_connection()
            sync_control_repo = SyncControlRepository(conn)
            sap_staging_repo = ProductoSAPStagingRepository(conn)

            modo_sync, initial_cursor = self._determinar_estrategia_sync(
                force_full_sync,
                sap_staging_repo.get_last_item_code(),
                sap_staging_repo.count_all()
            )
            sync_control_id = sync_control_repo.iniciar_sync('SAP', 'BACKEND')

            query_base = f"""
            SELECT
                T0."ItemCode",
                T0."ItemName",
                T0."U_IXX_PACK",
                T0."SalUnitMsr",
                T0."CodeBars",
                T0."ItmsGrpNam",
                T0."ItmsGrpCod",
                T0."validFor",
                T0."InvntItem"
            FROM OPENQUERY([{SAP_LINKED_SERVER}], '
                SELECT
                    OITM."ItemCode",
                    OITM."ItemName",
                    OITM."U_IXX_PACK",
                    OITM."SalUnitMsr",
                    OITM."CodeBars",
                    OITB."ItmsGrpNam",
                    OITM."ItmsGrpCod",
                    OITM."validFor",
                    OITM."InvntItem"
                FROM "{SAP_DATABASE}"."OITM" OITM
                INNER JOIN "{SAP_DATABASE}"."OITB" OITB
                    ON OITM."ItmsGrpCod" = OITB."ItmsGrpCod"
                WHERE OITM."ItemCode" IS NOT NULL
                  AND OITM."ItemName" IS NOT NULL
                  AND OITM."validFor" = ''Y''
                  AND OITM."SellItem" = ''Y''
                  AND OITB."ItmsGrpNam" IN (''R-MEDIAS'', ''RD-INDUM MEDIAS'')
                  AND EXISTS (
                      SELECT 1
                      FROM "{SAP_DATABASE}"."INV1" INV1
                      INNER JOIN "{SAP_DATABASE}"."OINV" OINV
                          ON INV1."DocEntry" = OINV."DocEntry"
                      WHERE INV1."ItemCode" = OITM."ItemCode"
                        AND OINV."DocDate" >= ADD_DAYS(CURRENT_DATE, -365)
                  )
                ORDER BY OITM."ItemCode"
            ') T0
            """

            loop_stats = self._bucle_paginacion_sap(sap_conn, sap_staging_repo, query_base, batch_size, initial_cursor)

            end_time = ahora_naive()
            duracion_segundos = int((end_time - start_time).total_seconds())
            sync_control_repo.finalizar_sync(
                sync_control_id, 'EXITOSA',
                loop_stats['total_procesados'], loop_stats['total_insertados'],
                loop_stats['total_actualizados'], None, duracion_segundos
            )
            logger.info(
                f"✅ Sync SAP completado: {loop_stats['total_procesados']} procesados, "
                f"{loop_stats['total_insertados']} nuevos, {loop_stats['total_actualizados']} actualizados, "
                f"{loop_stats['total_errores']} errores ({duracion_segundos}s)"
            )
            return {
                "status": "success",
                "entidad": "SAP",
                "modo_sincronizacion": modo_sync,
                "registros_procesados": loop_stats['total_procesados'],
                "registros_nuevos": loop_stats['total_insertados'],
                "registros_actualizados": loop_stats['total_actualizados'],
                "registros_con_error": loop_stats['total_errores'],
                "duracion_segundos": duracion_segundos,
                "lotes_procesados": loop_stats['batch_number'],
                "timestamp": end_time.isoformat()
            }
        except Exception as e:
            self._registrar_error_sync_sap(conn, sync_control_id, start_time, e)
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            if sap_conn:
                try:
                    sap_conn.close()
                except Exception:
                    pass

    def sync_all(self, force_full_sync: bool = False) -> Dict[str, Any]:
        """
        Sincroniza ambos maestros (MBA3 y SAP).

        Args:
            force_full_sync: Si True, fuerza sincronización completa desde el inicio (default: False)

        Returns:
            Diccionario con estadísticas combinadas
        """
        logger.info("🔄 Iniciando sincronización completa de maestros...")
        if force_full_sync:
            logger.info("⚠️ Modo: Sincronización completa forzada")

        mba3_result = self.sync_mba3_products(force_full_sync=force_full_sync)
        sap_result = self.sync_sap_products(force_full_sync=force_full_sync)

        return {
            "status": "success",
            "mba3": mba3_result,
            "sap": sap_result,
            "timestamp": ahora_naive().isoformat()
        }
