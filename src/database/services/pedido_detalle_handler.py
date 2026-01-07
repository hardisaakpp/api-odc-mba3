import io
import logging
from typing import Dict, Any, Optional

import pandas as pd

from src.exceptions import BusinessException

logger = logging.getLogger(__name__)


def procesar_detalle_articulos_v1_0(
    service: Any,
    file_content: bytes,
    resultado: Dict[str, Any],
    validar_sap: bool,
    hoja_detalle: str,
) -> Optional[Dict[str, Dict]]:
    """Procesa hoja Detalle Articulos y valida contra SAP. Retorna productos_dict o None."""
    logger.info("📋 PASO 3: Procesando hoja de Detalle Articulos")
    excel_file = pd.ExcelFile(io.BytesIO(file_content))
    df_detalle = pd.read_excel(excel_file, sheet_name=hoja_detalle, header=0, keep_default_na=False)
    df_detalle.columns = [str(col).strip() for col in df_detalle.columns]

    col_codigo = col_descripcion = col_marca = col_codigo_barras = col_pack = None
    col_costo = col_descuento = col_pvp = col_bodega = None

    for col in df_detalle.columns:
        col_upper = str(col).upper().strip()
        if col_codigo is None and "CODIGO" in col_upper and "PRODUCTO" in col_upper:
            col_codigo = col
        elif col_descripcion is None and ("DESCRIPCION" in col_upper or "DESCRIPCIÓN" in col_upper) and "SAP" in col_upper:
            col_descripcion = col
        elif col_marca is None and "MARCA" in col_upper:
            col_marca = col
        elif col_codigo_barras is None and ("CODIGO" in col_upper or "CÓDIGO" in col_upper) and "BARRAS" in col_upper:
            col_codigo_barras = col
        elif col_pack is None and "PACK" in col_upper:
            col_pack = col
        elif col_costo is None and "COSTO" in col_upper and "SIN" in col_upper and "IVA" in col_upper:
            col_costo = col
        elif col_descuento is None and "DESCUENTO" in col_upper:
            col_descuento = col
        elif col_pvp is None and "PVP" in col_upper:
            col_pvp = col
        elif col_bodega is None and "BODEGA" in col_upper:
            col_bodega = col

    if not col_codigo:
        resultado["errores"].append("❌ No se encontró columna 'CODIGO PRODUCTO' en Detalle Articulos")
        resultado["status"] = "error"
        return None

    productos_dict: Dict[str, Dict[str, Any]] = {}
    for _, row in df_detalle.iterrows():
        codigo = str(row.get(col_codigo, "")).strip()
        if not codigo:
            continue

        productos_dict[codigo.upper()] = {
            "codigo_interno": codigo.upper(),
            "descripcion_sap": str(row.get(col_descripcion, "")).strip() if col_descripcion else None,
            "marca": str(row.get(col_marca, "")).strip() if col_marca else None,
            "codigo_barras": str(row.get(col_codigo_barras, "")).strip() if col_codigo_barras else None,
            "pack": str(row.get(col_pack, "")).strip() if col_pack else None,
            "costo_doc_sin_iva": service._convertir_a_decimal(row.get(col_costo)) if col_costo else None,
            "descuento_1": service._convertir_a_decimal(row.get(col_descuento)) if col_descuento else None,
            "pvp": service._convertir_a_decimal(row.get(col_pvp)) if col_pvp else None,
            "bodega": service._convertir_a_entero(row.get(col_bodega)) if col_bodega else None,
        }

    resultado["resumen"]["productos_cargados"] = len(productos_dict)
    resultado["resumen"]["hojas_procesadas"].append("Detalle Articulos")
    logger.info(f"✅ Productos cargados: {len(productos_dict)}")

    if validar_sap and productos_dict:
        logger.info("📋 Validando códigos de productos en Detalle Articulos contra SAP")
        codigos_detalle = list(productos_dict.keys())
        validacion_detalle_sap = service.validator.validar_productos_existen_en_sap(
            codigos_productos=codigos_detalle, usar_cache=True, sap_obligatorio=True
        )

        no_encontrados = validacion_detalle_sap.get("no_encontrados", [])
        errores = validacion_detalle_sap.get("errores", [])

        if no_encontrados or errores:
            errores_lista = []
            if no_encontrados:
                errores_lista.append(f"No encontrados en SAP: {', '.join(no_encontrados[:5])}")
                if len(no_encontrados) > 5:
                    errores_lista[-1] += f" y {len(no_encontrados) - 5} más"
            if errores:
                errores_lista.append(f"Errores SAP: {', '.join(errores[:3])}")
                if len(errores) > 3:
                    errores_lista[-1] += f" y {len(errores) - 3} más"

            mensaje_error = "No se puede procesar: productos no válidos en SAP (Detalle Articulos). " + " ".join(errores_lista)
            resultado["status"] = "validation_error"
            resultado["errores"].append(mensaje_error)
            logger.error(f"❌ {mensaje_error}")
            raise BusinessException(message=mensaje_error, error_code="PRODUCTOS_NO_VALIDOS_SAP_DETALLE_ARTICULOS")

        logger.info(f"✅ Validación SAP (Detalle): {len(validacion_detalle_sap.get('validos', []))} válidos")

    return productos_dict
