import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def procesar_tiendas_y_validar_sap_v1_0(
    service: Any,
    file_content: bytes,
    resultado: Dict[str, Any],
    sap_obligatorio: bool,
    hoja_tiendas: str,
) -> Optional[Dict[str, Any]]:
    """Procesa hoja Tiendas y valida SIEMPRE contra SAP. Retorna catálogo."""
    logger.info("📋 PASO 1: Procesando hoja de Tiendas")
    try:
        catalogo_tiendas = service.parser.leer_hoja_tiendas(file_content)
    except ValueError as e:
        # Normalizar a error de validación para bloquear la carga
        resultado["status"] = "validation_error"
        resultado["errores"].append(str(e))
        logger.error(f"❌ Validación Tiendas: {e}")
        return None
    except Exception as e:
        resultado["status"] = "error"
        resultado["errores"].append(f"Error al procesar hoja 'Tiendas': {str(e)}")
        logger.error(f"❌ Error inesperado en Tiendas: {e}")
        return None

    resultado["tiendas_cargadas"] = catalogo_tiendas if catalogo_tiendas else []

    if not catalogo_tiendas:
        mensaje_error = "Hoja 'Tiendas' incompleta o vacía: las columnas ID TIENDA, NOMBRE TIENDA y ACTIVO son obligatorias y no pueden tener celdas vacías."
        resultado["status"] = "validation_error"
        resultado["errores"].append(mensaje_error)
        logger.error(f"❌ {mensaje_error}")
        return None

    # Validación de celdas vacías en columnas obligatorias
    logger.info("📋 Validando que todas las celdas obligatorias contengan información")
    celdas_vacias = []
    for id_tienda, tienda_info in catalogo_tiendas.items():
        if not id_tienda or str(id_tienda).strip() == "":
            celdas_vacias.append(f"ID TIENDA vacío en fila")
        if not tienda_info.get("nombre") or str(tienda_info.get("nombre", "")).strip() == "":
            celdas_vacias.append(f"NOMBRE TIENDA vacío para ID: {id_tienda}")
        if tienda_info.get("activo") is None or str(tienda_info.get("activo", "")).strip() == "":
            celdas_vacias.append(f"ACTIVO vacío para ID: {id_tienda}")

    if celdas_vacias:
        mensaje_error = "Validación fallida: existen celdas vacías en columnas obligatorias (ID TIENDA, NOMBRE TIENDA, ACTIVO). No se puede procesar el archivo."
        resultado["status"] = "validation_error"
        resultado["errores"].append(mensaje_error)
        resultado["errores"].extend(celdas_vacias[:10])  # Mostrar primeros 10 errores
        if len(celdas_vacias) > 10:
            resultado["errores"].append(f"... y {len(celdas_vacias) - 10} celdas vacías más")
        logger.error(f"❌ {mensaje_error}")
        return None

    logger.info("✅ Todas las celdas obligatorias contienen información")

    resultado["resumen"]["tiendas_validadas"] = len(catalogo_tiendas)
    resultado["resumen"]["hojas_procesadas"].append("Tiendas")
    logger.info(f"✅ Tiendas cargadas: {len(catalogo_tiendas)}")

    # Validación SAP SIEMPRE obligatoria para ID TIENDA
    logger.info("📋 Validación SAP (Tiendas): Verificando ID TIENDA contra SAP OWHS")
    codigos_bodegas = list(catalogo_tiendas.keys())
    try:
        validacion_bodegas = service.validator.validar_bodegas_existen_en_sap(
            codigos_bodegas=codigos_bodegas,
            sap_obligatorio=sap_obligatorio,
        )
        resultado["validacion_bodegas"] = {
            "total_codigos": len(codigos_bodegas),
            "validas": len(validacion_bodegas.get("validas", [])),
            "no_encontradas": len(validacion_bodegas.get("no_encontradas", [])),
            "errores": len(validacion_bodegas.get("errores", [])),
            "warnings": len(validacion_bodegas.get("warnings", [])),
            "todas_validas": validacion_bodegas.get("todas_validas", False),
        }

        if sap_obligatorio and not validacion_bodegas.get("todas_validas", False):
            no_encontradas = validacion_bodegas.get("no_encontradas", [])
            errores_sap = validacion_bodegas.get("errores", [])
            mensaje_error = "No se puede procesar: existen ID TIENDA que no existen en SAP (OWHS)."
            if no_encontradas:
                mensaje_error += f" No encontrados: {', '.join(no_encontradas[:5])}"
                if len(no_encontradas) > 5:
                    mensaje_error += f" y {len(no_encontradas) - 5} más"
            if errores_sap:
                mensaje_error += f" Errores SAP: {', '.join(errores_sap[:3])}"
                if len(errores_sap) > 3:
                    mensaje_error += f" y {len(errores_sap) - 3} más"
            resultado["status"] = "validation_error"
            resultado["errores"].append(mensaje_error)
            logger.error(f"❌ {mensaje_error}")
            return None

        logger.info(
            f"✅ Validación SAP (ID TIENDA): {len(validacion_bodegas.get('validas', []))} válidas"
        )
    except Exception as e:
        logger.error(f"❌ Error en validación SAP de tiendas: {e}")
        if sap_obligatorio:
            resultado["status"] = "validation_error"
            resultado["errores"].append(f"Error validando Tiendas contra SAP: {str(e)}")
            return None

    return catalogo_tiendas
