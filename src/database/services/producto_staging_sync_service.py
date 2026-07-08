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

    @staticmethod
    def _get_campo(producto: Dict[str, Any], *claves: str, default: Any = "") -> Any:
        """Devuelve el primer valor truthy entre las claves indicadas, o `default`."""
        for clave in claves:
            valor = producto.get(clave)
            if valor:
                return valor
        return default

    @staticmethod
    def _str_strip(valor: Any) -> str:
        """Convierte a str y aplica strip; '' si el valor es falsy."""
        return str(valor).strip() if valor else ""

    def _ejecutar_lote_con_reintentos(self, ejecutar_lote, batch_number: int, max_retries: int = 3):
        """
        Ejecuta `ejecutar_lote()` con reintentos y backoff. Retorna (resultado, exito).
        Si se agotan los reintentos, retorna (None, False).
        """
        retry_count = 0
        while retry_count < max_retries:
            try:
                return ejecutar_lote(), True
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
                    return None, False
                wait_time = retry_count * 5
                logger.warning(
                    f"⚠️ Reintentando lote {batch_number} (intento {retry_count}/{max_retries}) "
                    f"después de {wait_time}s... Error: {str(e)[:100]}"
                )
                time.sleep(wait_time)
        return None, False

    @staticmethod
    def _manejar_lote_fallido(
        batch_number: int, lotes_fallidos_consecutivos: int,
        max_lotes_fallidos: int, max_retries: int = 3
    ):
        """Contabiliza un lote fallido. Retorna (lotes_fallidos_consecutivos, detener)."""
        lotes_fallidos_consecutivos += 1
        if lotes_fallidos_consecutivos >= max_lotes_fallidos:
            logger.error(
                f"❌ {max_lotes_fallidos} lotes consecutivos fallaron. "
                f"Deteniendo sincronización para evitar bucle infinito."
            )
            return lotes_fallidos_consecutivos, True
        logger.warning(
            f"⚠️ Lote {batch_number} falló después de {max_retries} intentos. "
            f"Lotes fallidos consecutivos: {lotes_fallidos_consecutivos}/{max_lotes_fallidos}. "
            f"Continuando con siguiente lote..."
        )
        return lotes_fallidos_consecutivos, False

    @staticmethod
    def _guardar_lote_staging(repo, productos_staging: List[Dict[str, Any]], batch_number: int):
        """
        Persiste el lote en staging. Retorna (insertados, actualizados, errores, procesados).
        Ante error de guardado, cuenta todo el lote como errores y 0 procesados.
        """
        try:
            stats = repo.bulk_insert_or_update(productos_staging)
            logger.info(
                f"✅ Lote {batch_number} completado: "
                f"{stats['insertados']} nuevos, {stats['actualizados']} actualizados, "
                f"{stats['errores']} errores"
            )
            return stats["insertados"], stats["actualizados"], stats["errores"], len(productos_staging)
        except Exception as e:
            logger.error(f"❌ Error guardando lote {batch_number}: {e}", exc_info=True)
            return 0, 0, len(productos_staging), 0

    @staticmethod
    def _log_progreso_acumulado(total_procesados, total_insertados, total_actualizados, total_errores):
        """Emite el log de progreso acumulado tras cada lote."""
        logger.info(
            f"📊 Progreso acumulado: {total_procesados} productos procesados | "
            f"Nuevos: {total_insertados} | "
            f"Actualizados: {total_actualizados} | "
            f"Errores: {total_errores}"
        )

    def _construir_query_mba3(
        self, query_base: str, last_product_id: Optional[str],
        lotes_repetidos_consecutivos: int, batch_size: int
    ) -> str:
        """Construye la query MBA3 del lote según el cursor y la estrategia de paginación."""
        if not last_product_id:
            return f"{query_base} LIMIT {batch_size}"
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
        return query

    def _evaluar_lote_repetido_mba3(
        self, productos: List[Dict[str, Any]], batch_number: int,
        primer_product_id_anterior: Optional[str], lotes_repetidos_consecutivos: int,
        max_lotes_repetidos: int, total_procesados: int
    ):
        """
        Detecta si MBA3 devuelve el mismo primer producto (no respeta paginación).
        Retorna (lotes_repetidos_consecutivos, primer_product_id_anterior, detener).
        """
        primer_product_id_actual = self._str_strip(
            self._get_campo(productos[0], "PRODUCT_ID", "product_id", "Product_ID")
        )
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
                return lotes_repetidos_consecutivos, primer_product_id_anterior, True
        else:
            lotes_repetidos_consecutivos = 0
            primer_product_id_anterior = primer_product_id_actual
        return lotes_repetidos_consecutivos, primer_product_id_anterior, False

    def _filtrar_primer_producto_cursor_mba3(
        self, productos: List[Dict[str, Any]], last_product_id: Optional[str], total_procesados: int
    ):
        """
        Si el primer producto del lote coincide con el cursor, lo descarta.
        Retorna (productos, detener).
        """
        if not (last_product_id and productos):
            return productos, False
        primer_product_id = self._str_strip(
            self._get_campo(productos[0], "PRODUCT_ID", "product_id", "Product_ID")
        )
        if primer_product_id == last_product_id:
            logger.info(f"⚠️ Primer producto del lote es igual al cursor ({last_product_id}), filtrándolo...")
            productos = productos[1:]
            if not productos:
                logger.info(f"✅ No hay más productos después de filtrar. Total procesado: {total_procesados}")
                return productos, True
            logger.info(f"   Productos restantes después de filtrar: {len(productos)}")
        return productos, False

    def _calcular_cursor_lote_mba3(
        self, productos: List[Dict[str, Any]], batch_number: int, last_product_id: Optional[str]
    ) -> Optional[str]:
        """Loguea diagnóstico del lote y retorna el último PRODUCT_ID válido (nuevo cursor) o None."""
        if not productos:
            return None
        primer_product_id = self._str_strip(
            self._get_campo(productos[0], "PRODUCT_ID", "product_id", "Product_ID")
        )
        ultimo_product_id_lote = self._str_strip(
            self._get_campo(productos[-1], "PRODUCT_ID", "product_id", "Product_ID")
        )
        if not ultimo_product_id_lote:
            return None
        logger.info(f"🔍 DIAGNÓSTICO Lote {batch_number}:")
        logger.info(f"   Cursor usado en query: {last_product_id if last_product_id else 'None (primer lote)'}")
        logger.info(f"   Primer producto recibido: {primer_product_id}")
        logger.info(f"   Último producto recibido: {ultimo_product_id_lote}")
        logger.info(f"   Total productos en lote: {len(productos)}")
        logger.debug(f"📍 Cursor preparado desde último producto del lote: {ultimo_product_id_lote}")
        return ultimo_product_id_lote

    def _construir_fila_staging_mba3(self, producto: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convierte un producto MBA3 crudo a una fila de staging, o None si no aplica/filtra."""
        product_id = self._str_strip(self._get_campo(producto, "PRODUCT_ID", "product_id", "Product_ID"))
        if not product_id:
            return None
        group_code = self._get_campo(producto, "GROUP_CODE", "group_code", "Group_Code")
        inactive = self._get_campo(producto, "INACTIVE", "inactive", "Inactive")
        tipo_origen = self._get_campo(producto, "Tipo_Origen", "tipo_origen")
        descontinuado = bool(self._get_campo(producto, "Descontinuado", "descontinuado", default=None))
        if (str(descontinuado).lower() == 'true' or
                str(inactive).lower() == 'true' or
                group_code != 'PTERM' or
                tipo_origen in ['ESPEC', 'EXPOR', 'MAPRO']):
            logger.debug(f"⚠️ Producto {product_id} no cumple filtros, omitiendo...")
            return None
        return {
            "product_id": product_id,
            "product_name": self._str_strip(self._get_campo(producto, "PRODUCT_NAME", "product_name", "Product_Name")),
            "corp": self._str_strip(self._get_campo(producto, "CORP", "corp", "Corp")),
            "grupo_prenda": self._str_strip(self._get_campo(producto, "GrupoPrenda", "grupoPrenda", "grupo_prenda")),
            "talla": self._str_strip(self._get_campo(producto, "Talla", "talla")),
            "presentacion": self._str_strip(self._get_campo(producto, "PRESENTACION", "presentacion", "Presentacion")),
            "descontinuado": descontinuado,
            "product_id_normalizado": normalizar_codigo(product_id)
        }

    def _extraer_productos_staging_mba3(
        self, productos: List[Dict[str, Any]], force_full_sync: bool, productos_encontrados: set
    ):
        """Convierte los productos crudos del lote a filas de staging. Retorna (staging, errores)."""
        productos_staging: List[Dict[str, Any]] = []
        errores = 0
        for producto in productos:
            try:
                fila = self._construir_fila_staging_mba3(producto)
                if fila is None:
                    continue
                productos_staging.append(fila)
                if force_full_sync:
                    productos_encontrados.add(fila["product_id"])
            except Exception as e:
                errores += 1
                logger.warning(f"⚠️ Error procesando producto MBA3: {e}")
                continue
        return productos_staging, errores

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
            query = self._construir_query_mba3(
                query_base, last_product_id, lotes_repetidos_consecutivos, batch_size
            )
            logger.info(f"📦 Lote {batch_number}: Consultando productos desde MBA3 API...")

            result, lote_exitoso = self._ejecutar_lote_con_reintentos(
                lambda q=query: self.mba3_service.execute_query(q), batch_number
            )

            if not lote_exitoso:
                total_errores += batch_size
                lotes_fallidos_consecutivos, detener = self._manejar_lote_fallido(
                    batch_number, lotes_fallidos_consecutivos, max_lotes_fallidos
                )
                if detener:
                    break
                continue

            lotes_fallidos_consecutivos = 0
            productos = self._normalizar_respuesta_mba3(result)
            if not productos:
                logger.info(f"✅ No hay más productos. Total procesado: {total_procesados}")
                break

            lotes_repetidos_consecutivos, primer_product_id_anterior, detener = self._evaluar_lote_repetido_mba3(
                productos, batch_number, primer_product_id_anterior,
                lotes_repetidos_consecutivos, max_lotes_repetidos, total_procesados
            )
            if detener:
                break

            productos, detener = self._filtrar_primer_producto_cursor_mba3(
                productos, last_product_id, total_procesados
            )
            if detener:
                break

            logger.info(f"📦 Lote {batch_number}: Procesando {len(productos)} productos...")
            ultimo_product_id_valido = self._calcular_cursor_lote_mba3(productos, batch_number, last_product_id)

            productos_staging, errores_lote = self._extraer_productos_staging_mba3(
                productos, force_full_sync, productos_encontrados
            )
            total_errores += errores_lote

            if ultimo_product_id_valido:
                last_product_id = ultimo_product_id_valido
                logger.info(f"📍 Cursor actualizado para siguiente lote: {last_product_id}")

            if productos_staging:
                logger.info(f"💾 Lote {batch_number}: Guardando {len(productos_staging)} productos en staging...")
                ins, act, err, proc = self._guardar_lote_staging(mba3_staging_repo, productos_staging, batch_number)
                total_insertados += ins
                total_actualizados += act
                total_errores += err
                total_procesados += proc

            if len(productos) < batch_size:
                logger.info(f"✅ Último lote procesado (menos de {batch_size} productos)")
                break

            self._log_progreso_acumulado(total_procesados, total_insertados, total_actualizados, total_errores)

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

    @staticmethod
    def _construir_query_sap(query_base: str, last_item_code: Optional[str], batch_size: int) -> str:
        """Construye la query SAP (OPENQUERY) del lote según el cursor de ItemCode."""
        if last_item_code:
            last_item_code_escaped = str(last_item_code).replace("'", "''")
            return f"{query_base} WHERE T0.\"ItemCode\" > '{last_item_code_escaped}' ORDER BY T0.\"ItemCode\" OFFSET 0 ROWS FETCH NEXT {batch_size} ROWS ONLY"
        return f"{query_base} ORDER BY T0.\"ItemCode\" OFFSET 0 ROWS FETCH NEXT {batch_size} ROWS ONLY"

    @staticmethod
    def _fetch_sap(sap_conn: Any, query: str):
        """Ejecuta la query en SAP vía cursor y retorna todas las filas."""
        cursor = sap_conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        return results

    @staticmethod
    def _col_opt_sap(row, idx: int) -> str:
        """Columna string opcional de una fila SAP: '' si el índice no existe o el valor es falsy."""
        return str(row[idx]).strip() if len(row) > idx and row[idx] else ""

    def _construir_fila_staging_sap(self, row) -> Optional[Dict[str, Any]]:
        """Convierte una fila cruda de SAP a una fila de staging, o None si no tiene ItemCode."""
        item_code = str(row[0]).strip() if row[0] else ""
        if not item_code:
            return None
        itms_grp_cod = row[6] if len(row) > 6 and row[6] else None
        valid_for_raw = row[7] if len(row) > 7 and row[7] is not None else 'N'
        valid_for = str(valid_for_raw).upper()
        invnt_item_raw = row[8] if len(row) > 8 and row[8] is not None else 'N'
        invnt_item = str(invnt_item_raw).upper() == 'Y'
        return {
            "item_code": item_code,
            "item_name": self._col_opt_sap(row, 1),
            "pack_sap": self._col_opt_sap(row, 2),
            "sal_unit_msr": self._col_opt_sap(row, 3),
            "code_bars": self._col_opt_sap(row, 4),
            "itms_grp_cod": itms_grp_cod,
            "itms_grp_nam": self._col_opt_sap(row, 5),
            "valid_for": valid_for,
            "activo": (valid_for == 'Y'),
            "invnt_item": invnt_item,
            "item_code_normalizado": normalizar_codigo(item_code)
        }

    def _extraer_productos_staging_sap(self, results, last_item_code: Optional[str]):
        """Convierte las filas del lote SAP a staging. Retorna (staging, errores, last_item_code)."""
        productos_staging: List[Dict[str, Any]] = []
        errores = 0
        for row in results:
            try:
                fila = self._construir_fila_staging_sap(row)
                if fila is None:
                    continue
                productos_staging.append(fila)
                last_item_code = fila["item_code"]
            except Exception as e:
                errores += 1
                logger.warning(f"⚠️ Error procesando producto SAP: {e}")
                continue
        return productos_staging, errores, last_item_code

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
            query = self._construir_query_sap(query_base, last_item_code, batch_size)

            logger.info(f"📦 Lote {batch_number}: Consultando productos desde SAP (OPENQUERY)...")
            if last_item_code:
                logger.info(f"   Cursor: ItemCode > '{last_item_code}'")
            logger.info(f"   Fetch: {batch_size}")

            results, lote_exitoso = self._ejecutar_lote_con_reintentos(
                lambda q=query: self._fetch_sap(sap_conn, q), batch_number
            )

            if not lote_exitoso:
                total_errores += batch_size
                lotes_fallidos_consecutivos, detener = self._manejar_lote_fallido(
                    batch_number, lotes_fallidos_consecutivos, max_lotes_fallidos
                )
                if detener:
                    break
                continue

            lotes_fallidos_consecutivos = 0
            if not results:
                logger.info(f"✅ No hay más productos. Total procesado: {total_procesados}")
                break

            logger.info(f"📦 Lote {batch_number}: Procesando {len(results)} productos...")
            productos_staging, errores_lote, last_item_code = self._extraer_productos_staging_sap(
                results, last_item_code
            )
            total_errores += errores_lote

            if productos_staging:
                logger.info(f"💾 Lote {batch_number}: Guardando {len(productos_staging)} productos en staging...")
                ins, act, err, proc = self._guardar_lote_staging(sap_staging_repo, productos_staging, batch_number)
                total_insertados += ins
                total_actualizados += act
                total_errores += err
                total_procesados += proc

            if len(results) < batch_size:
                logger.info(f"✅ Último lote procesado (menos de {batch_size} productos)")
                break

            self._log_progreso_acumulado(total_procesados, total_insertados, total_actualizados, total_errores)

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
