import logging
from typing import Dict, Any, Optional, List

from src.exceptions import BusinessException

logger = logging.getLogger(__name__)


def procesar_movimiento_y_coherencia_v1_0(
    service: Any,
    file_content: bytes,
    resultado: Dict[str, Any],
    catalogo_tiendas: Dict,
    productos_dict: Dict,
    validar_sap: bool,
    hoja_movimiento: str,
) -> Optional[List[Dict]]:
    """Procesa Movimiento, valida SAP y coherencia con Detalle. Retorna distribuciones o None."""
    logger.info("📋 PASO 4: Procesando hoja de Movimiento")
    movimiento_result = service.parser.leer_hoja_movimiento(file_content, catalogo_tiendas)

    if movimiento_result.get("errores"):
        resultado["errores"].extend(movimiento_result["errores"])
        resultado["status"] = "error"
        return None

    distribuciones_movimiento = movimiento_result.get("datos", [])
    resultado["resumen"]["distribuciones_totales"] = len(distribuciones_movimiento)
    resultado["resumen"]["hojas_procesadas"].append("Movimiento")
    logger.info(f"✅ Movimiento procesado: {movimiento_result['resumen']['filas_validas']} filas")

    if validar_sap:
        codigos_mov_sap = list({
            str(dist.get("codigo_producto")).strip().upper()
            for dist in distribuciones_movimiento
            if dist.get("codigo_producto")
        })
        if codigos_mov_sap:
            logger.info("📋 Validación SAP: verificando códigos Movimiento en SAP")
            validacion_mov_sap = service.validator.validar_productos_existen_en_sap(
                codigos_productos=codigos_mov_sap, usar_cache=True, sap_obligatorio=True
            )

            mov_no_encontrados = validacion_mov_sap.get("no_encontrados", [])
            mov_errores = validacion_mov_sap.get("errores", [])

            if mov_no_encontrados or mov_errores:
                errores_lista = []
                if mov_no_encontrados:
                    errores_lista.append(f"No encontrados: {', '.join(mov_no_encontrados[:5])}")
                if mov_errores:
                    errores_lista.append(f"Errores: {', '.join(mov_errores[:3])}")

                mensaje_error = "No se puede procesar: productos Movimiento no válidos en SAP. " + " ".join(errores_lista)
                resultado["status"] = "validation_error"
                resultado["errores"].append(mensaje_error)
                logger.error(f"❌ {mensaje_error}")
                raise BusinessException(message=mensaje_error, error_code="PRODUCTOS_NO_VALIDOS_SAP_MOVIMIENTO")

            logger.info(f"✅ Validación SAP (Movimiento): {len(validacion_mov_sap.get('validos', []))} válidos")

    logger.info("📋 Validación: Coherencia Movimiento vs Detalle Articulos")
    codigos_detalle = set(productos_dict.keys())
    codigos_movimiento = {str(d["codigo_producto"]).strip().upper() for d in distribuciones_movimiento if d.get("codigo_producto")}

    validacion_coherencia = service.validator.validar_coherencia_articulos(
        codigos_detalle=codigos_detalle, codigos_movimiento=codigos_movimiento
    )

    if not validacion_coherencia["coherente"]:
        logger.error(f"❌ Coherencia falló: {validacion_coherencia['resumen']}")
        resultado["status"] = "validation_error"
        resultado["errores"].append(validacion_coherencia["resumen"])
        resultado["validation"] = {
            "valid": False,
            "coherencia_articulos": {
                "coherente": False,
                "codigos_invalidos": validacion_coherencia["codigos_invalidos"],
                "cantidad_invalidos": len(validacion_coherencia["codigos_invalidos"]),
                "accion_recomendada": "Verifique que todos los códigos usados en Movimiento existan en Detalle Articulos",
                "detalle_errores": validacion_coherencia["errores"],
            },
        }
        return None

    logger.info(f"✅ {validacion_coherencia['resumen']}")
    return distribuciones_movimiento
