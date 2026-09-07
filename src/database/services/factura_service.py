"""
Servicio para guardar facturas de MBA3 en SQL Server.
"""

import logging
from typing import Dict, Any, List, Optional

from ..connection import get_db_connection_context
from ..repositories.despacho_repository import DespachoRepository
from ..mappers.factura_mapper import FacturaMapper
from ..services.sap_service import SAPService

logger = logging.getLogger(__name__)

# Tipos de arrays que pueden existir en ObjDatosFactura
TIPOS_LINEAS = [
    "GrabarLineasProd",
    "Lineas",
    "CtrlEliminados1",
    "CtrlEliminados2",
    "CtrlEliminados3",
    "CtrlEliminados4",
    "CtrlEliminados5",
    "CtrlEliminados6",
    "CtrlEliminados7",
    "CtrlEliminados8",
    "CtrlEliminadosA",
    "CtrlEliminadosB",
]


def _manejar_error_sap(
    codigo: str,
    sap_info: Dict[str, Any],
    homologacion_service: Optional[Any]
) -> None:
    """Registra y notifica un error retornado por SAP (sap_info con _error=True)."""
    tipo_problema = sap_info.get("_error_type", "no_existe")
    item_code_sap = sap_info.get("_item_code_sap")
    if homologacion_service:
        info_adicional = {"item_code_sap": item_code_sap} if item_code_sap else None
        homologacion_service.detectar_producto_no_homologado(
            codigo,
            tipo_problema=tipo_problema,
            info_adicional=info_adicional
        )
    if tipo_problema == "mismatch":
        logger.warning(f"   ⚠️ MISMATCH: SKU MBA3='{codigo}' no coincide con ItemCode SAP='{item_code_sap}'")
    elif tipo_problema == "no_existe":
        logger.debug(f"   ⚠️ Producto no encontrado en SAP: {codigo}")
    else:
        logger.warning(f"   ⚠️ Error al consultar SAP para {codigo}")


def _consultar_sap_para_linea(
    codigo: Optional[str],
    sap_service: Any,
    homologacion_service: Optional[Any]
) -> Optional[Dict[str, Any]]:
    """Consulta SAP para un SKU y retorna sap_info válido, o None si no existe/error."""
    if not codigo:
        return None
    try:
        sap_info = sap_service.get_or_fetch_producto_info(codigo)
        if not sap_info:
            if homologacion_service:
                homologacion_service.detectar_producto_no_homologado(codigo, tipo_problema="no_existe")
            logger.debug(f"   ⚠️ Producto no encontrado en SAP: {codigo}")
            return None
        if sap_info.get("_error"):
            _manejar_error_sap(codigo, sap_info, homologacion_service)
            return None
        logger.debug(
            f"   → SAP info para {codigo}: "
            f"Pack={sap_info.get('pack_sap')}, Unidad={sap_info.get('unidad_conversion')}"
        )
        return sap_info
    except Exception as sap_error:
        logger.warning(f"   ⚠️ Error al consultar SAP para {codigo}: {sap_error}")
        if homologacion_service:
            homologacion_service.detectar_producto_no_homologado(
                codigo,
                tipo_problema="error",
                info_adicional={"error_message": str(sap_error)}
            )
        return None


def _procesar_lineas_tipo(
    tipo_linea: str,
    lineas: List[Dict[str, Any]],
    despacho_id: Any,
    repository: DespachoRepository,
    sap_service: Any,
    homologacion_service: Optional[Any],
    result: Dict[str, Any]
) -> None:
    """Transforma e inserta las líneas de un tipo (GrabarLineasProd, Lineas, CtrlEliminados*)."""
    try:
        detalles = []
        for linea in lineas:
            codigo = linea.get("Codigo")
            sap_info = _consultar_sap_para_linea(codigo, sap_service, homologacion_service)
            detalle = FacturaMapper.to_despacho_detalle(linea, tipo_linea, sap_info=sap_info)
            if detalle:
                if detalle.get("cantidad_sap"):
                    logger.info(
                        f"   ✅ Conversión aplicada para {codigo}: "
                        f"{detalle['cantidad']} docenas → {detalle['cantidad_sap']:.2f} packs "
                        f"({detalle.get('unidad_sap')})"
                    )
                detalles.append(detalle)
        if detalles:
            count = repository.insert_detalles(despacho_id, detalles)
            result["detalles_insertados"] += count
    except Exception as e:
        error_msg = f"Error al insertar {tipo_linea}: {str(e)}"
        logger.error(f"❌ {error_msg}")
        result["errors"].append(error_msg)


def save_mba3_factura(
    repository: DespachoRepository,
    factura: Dict[str, Any],
    upsert: bool = False,
    homologacion_service: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Guarda una factura completa de MBA3 en SQL Server (cabecera + detalles).

    Args:
        repository: Repositorio de despacho
        factura: Diccionario con datos de factura de MBA3
        upsert: Si True, actualiza si existe; si False, inserta siempre

    Returns:
        Dict con estadísticas de la operación
    """
    result = {
        "status": "success",
        "despacho_id": None,
        "cabecera_insertada": False,
        "cabecera_actualizada": False,
        "detalles_insertados": 0,
        "errors": []
    }

    try:
        codigo_factura = factura.get("CODIGO_FACTURA")
        datos_cabecera = FacturaMapper.to_despacho_cabecera(factura)

        existing_id = None
        if upsert and codigo_factura:
            existing_id = repository.find_by_codigo_factura(codigo_factura)

        if existing_id:
            logger.info(f"🔄 Factura ya existe: {codigo_factura} (despacho_id: {existing_id}) - Actualizando...")
            repository.update_cabecera(existing_id, datos_cabecera)
            result["despacho_id"] = existing_id
            result["cabecera_insertada"] = False
            result["cabecera_actualizada"] = True
            detalles_eliminados = repository.delete_detalles(existing_id)
            logger.debug(f"   → {detalles_eliminados} detalles antiguos eliminados")
            despacho_id = existing_id
        else:
            despacho_id = repository.insert_cabecera(datos_cabecera)
            result["despacho_id"] = despacho_id
            result["cabecera_insertada"] = True
            result["cabecera_actualizada"] = False

        obj_datos = factura.get("ObjDatosFactura")
        if obj_datos:
            sap_service = SAPService()
            for tipo_linea in TIPOS_LINEAS:
                if tipo_linea in obj_datos and obj_datos[tipo_linea]:
                    _procesar_lineas_tipo(
                        tipo_linea, obj_datos[tipo_linea],
                        despacho_id, repository, sap_service, homologacion_service, result
                    )

        accion = "actualizada" if result.get("cabecera_actualizada") else "guardada"
        logger.info(
            f"✅ Factura {accion}: {codigo_factura} "
            f"(despacho_id: {despacho_id}, detalles: {result['detalles_insertados']})"
        )

    except Exception as e:
        error_msg = f"Error al guardar factura {factura.get('CODIGO_FACTURA')}: {str(e)}"
        logger.error(f"❌ {error_msg}")
        result["status"] = "error"
        result["errors"].append(error_msg)

    return result


def _convertir_a_lista_facturas(mba3_json_result: Any) -> Optional[List[Dict[str, Any]]]:
    """Convierte el resultado de MBA3 a lista de facturas, o None si el formato no es soportado."""
    if isinstance(mba3_json_result, list):
        return mba3_json_result
    if isinstance(mba3_json_result, dict):
        return [mba3_json_result]
    logger.error(f"❌ Formato de resultado no soportado: {type(mba3_json_result)}")
    return None


def _actualizar_stats_factura(result: Dict[str, Any], stats: Dict[str, Any]) -> bool:
    """
    Acumula el resultado de una factura en stats.

    Retorna True si ocurrió un error (para que el caller decida si detener el proceso).
    """
    if result["status"] == "success":
        if result.get("cabecera_actualizada"):
            stats["facturas_actualizadas"] += 1
        else:
            stats["facturas_guardadas"] += 1
        stats["total_detalles"] += result["detalles_insertados"]
        return False
    if result["status"] == "exists":
        # Este caso ya no debería ocurrir con upsert=True, pero se mantiene por compatibilidad
        stats["facturas_existentes"] += 1
        return False
    # status == "error"
    stats["facturas_error"] += 1
    stats["errors"].extend(result["errors"])
    return True


def _procesar_facturas_en_lote(
    facturas: List[Dict[str, Any]],
    repository: DespachoRepository,
    upsert: bool,
    homologacion_service: Optional[Any],
    stats: Dict[str, Any],
    continue_on_error: bool
) -> None:
    """Procesa cada factura de la lista y acumula estadísticas en stats."""
    for idx, factura in enumerate(facturas, 1):
        try:
            result = save_mba3_factura(
                repository, factura, upsert=upsert, homologacion_service=homologacion_service
            )
            debe_parar = _actualizar_stats_factura(result, stats)
            if debe_parar and not continue_on_error:
                raise RuntimeError(f"Error al guardar factura: {result['errors']}")
        except Exception as e:
            error_msg = f"Error al procesar factura {idx}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            stats["facturas_error"] += 1
            stats["errors"].append(error_msg)
            if not continue_on_error:
                raise


def save_mba3_data_to_sql_server(
    mba3_json_result: Any,
    upsert: bool = False,
    continue_on_error: bool = True,
    homologacion_service: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Guarda el resultado JSON de MBA3 en SQL Server.

    Esta función es el punto de entrada principal para guardar datos de MBA3.

    ⚠️ ACTUALIZACIÓN: Usa context manager para garantizar cierre de conexión.
    Esto previene conexiones huérfanas que causan bloqueos en SQL Server.

    Args:
        mba3_json_result: Resultado JSON de MBA3 (puede ser list o dict)
        upsert: Si True, actualiza si existe; si False, inserta siempre
        continue_on_error: Si True, continúa procesando aunque falle una factura
        homologacion_service: Servicio de homologación para detectar productos no homologados

    Returns:
        Dict con estadísticas de la operación
    """
    stats = {
        "status": "success",
        "total_facturas": 0,
        "facturas_guardadas": 0,
        "facturas_actualizadas": 0,
        "facturas_existentes": 0,  # Deprecated: usar facturas_actualizadas
        "facturas_error": 0,
        "total_detalles": 0,
        "errors": []
    }

    try:
        # CRÍTICO: Usar context manager para garantizar cierre de conexión
        with get_db_connection_context() as conn:
            repository = DespachoRepository(conn)

            facturas = _convertir_a_lista_facturas(mba3_json_result)
            if facturas is None:
                return {"status": "error", "message": f"Formato no soportado: {type(mba3_json_result)}"}

            stats["total_facturas"] = len(facturas)
            logger.info(f"📦 Procesando {stats['total_facturas']} factura(s)...")

            _procesar_facturas_en_lote(facturas, repository, upsert, homologacion_service, stats, continue_on_error)

            if stats["facturas_error"] == 0:
                stats["status"] = "success"
            elif stats["facturas_guardadas"] > 0:
                stats["status"] = "partial"
            else:
                stats["status"] = "error"

            logger.info(
                f"✅ Proceso completado: {stats['facturas_guardadas']} guardadas, "
                f"{stats['facturas_actualizadas']} actualizadas, "
                f"{stats['facturas_error']} errores de {stats['total_facturas']} totales"
            )
            logger.info(f"   Total detalles: {stats['total_detalles']}")
            logger.info("=" * 70)

    except Exception as e:
        logger.error(f"❌ Error crítico al guardar en SQL Server: {e}", exc_info=True)
        stats["status"] = "error"
        stats["errors"].append(f"Error crítico: {str(e)}")
        return {
            "status": "error",
            "message": f"Error de conexión a SQL Server: {str(e)}",
            "total_facturas": 0,
            "facturas_guardadas": 0,
            "facturas_actualizadas": 0,
            "facturas_error": 0,
            "total_detalles": 0,
            "errors": [f"Error de conexión: {str(e)}"]
        }

    return stats
