"""
Helper para validaciones SAP repetidas en el procesamiento de pedidos.
Centraliza la lógica de validación SAP para productos y tiendas.
"""

import logging
from typing import Dict, Any, List, Optional

from .pedido_validator import PedidoValidator

logger = logging.getLogger(__name__)


class PedidoSAPValidatorHelper:
    """Helper para validaciones SAP en pedidos."""
    
    def __init__(self, validator: Optional[PedidoValidator] = None):
        """
        Inicializa el helper.
        
        Args:
            validator: Instancia de PedidoValidator (opcional, se crea una nueva si no se proporciona)
        """
        self.validator = validator or PedidoValidator()
    
    def validar_tiendas_sap(
        self,
        codigos_tiendas: List[str],
        resultado: Dict[str, Any],
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida códigos de tienda contra SAP OWHS.
        
        Args:
            codigos_tiendas: Lista de códigos de tiendas a validar
            resultado: Dict de resultado donde se agregará la validación
            sap_obligatorio: Si True, errores de SAP bloquean el proceso
            
        Returns:
            Dict con resultado de validación SAP de tiendas
        """
        if not codigos_tiendas:
            return {
                "total_codigos": 0,
                "validas": [],  # Lista vacía
                "no_encontradas": [],  # Lista vacía
                "errores": [],  # Lista vacía
                "warnings": [],  # Lista vacía
                "todas_validas": True,
                "total_validas": 0,
                "total_no_encontradas": 0,
                "total_errores": 0,
                "total_warnings": 0
            }
        
        logger.info("📋 Validación SAP: Verificando códigos de tienda contra SAP OWHS")
        
        validacion_tiendas_sap = self.validator.validar_tiendas_existen_en_sap(
            codigos_tiendas=codigos_tiendas,
            sap_obligatorio=sap_obligatorio
        )
        
        # Obtener listas originales para retornar
        validas_lista = validacion_tiendas_sap.get("validas", [])
        no_encontradas_lista = validacion_tiendas_sap.get("no_encontradas", [])
        errores_lista = validacion_tiendas_sap.get("errores", [])
        warnings_lista = validacion_tiendas_sap.get("warnings", [])
        
        resultado["validacion_tiendas_sap"] = {
            "total_codigos": len(codigos_tiendas),
            "validas": validas_lista,  # Lista de códigos válidos
            "no_encontradas": no_encontradas_lista,  # Lista de códigos no encontrados
            "errores": errores_lista,  # Lista de códigos con errores
            "warnings": warnings_lista,  # Lista de códigos con warnings
            "todas_validas": validacion_tiendas_sap.get("todas_validas", False),
            # Campos adicionales para compatibilidad (conteos)
            "total_validas": len(validas_lista),
            "total_no_encontradas": len(no_encontradas_lista),
            "total_errores": len(errores_lista),
            "total_warnings": len(warnings_lista)
        }
        
        # Si SAP es obligatorio y hay tiendas no encontradas, BLOQUEAR
        if sap_obligatorio and not validacion_tiendas_sap.get("todas_validas", False):
            # Mensaje simple - el frontend construirá el mensaje detallado
            mensaje_error = "Existen códigos de tienda/bodega no válidos en SAP"
            resultado["status"] = "validation_error"
            resultado["errores"].append(mensaje_error)
            
            # Log detallado para debugging (solo en backend)
            log_detalle = f"Códigos no encontrados ({len(no_encontradas_lista)}): {', '.join(no_encontradas_lista[:10])}"
            if len(no_encontradas_lista) > 10:
                log_detalle += f" y {len(no_encontradas_lista) - 10} más"
            if errores_lista:
                log_detalle += f" | Errores ({len(errores_lista)}): {', '.join(errores_lista[:5])}"
                if len(errores_lista) > 5:
                    log_detalle += f" y {len(errores_lista) - 5} más"
            logger.error(f"❌ Validación SAP tiendas falló: {log_detalle}")
        
        logger.info(
            f"📊 Validación SAP (Tiendas): {len(validas_lista)} válidas, "
            f"{len(no_encontradas_lista)} no encontradas"
        )
        
        return resultado["validacion_tiendas_sap"]
    
    def validar_productos_sap(
        self,
        codigos_productos: List[str],
        resultado: Dict[str, Any],
        usar_cache: bool = True,
        sap_obligatorio: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Valida códigos de producto contra SAP.
        
        Args:
            codigos_productos: Lista de códigos de productos a validar
            resultado: Dict de resultado donde se agregará la validación
            usar_cache: Si True, usa cache de SAP
            sap_obligatorio: Si True, errores de SAP bloquean el proceso
            
        Returns:
            Dict con resultado de validación SAP de productos, o None si hay error y es obligatorio
        """
        if not codigos_productos:
            return {
                "total_codigos": 0,
                "validos": 0,
                "no_encontrados": 0,
                "errores": 0,
                "warnings": 0,
                "todos_validos": True,
                "detalle": {}
            }
        
        logger.info("📋 Validación SAP: Verificando productos en SAP")
        
        validacion_sap = self.validator.validar_productos_existen_en_sap(
            codigos_productos=codigos_productos,
            usar_cache=usar_cache,
            sap_obligatorio=sap_obligatorio
        )
        
        resultado["validacion_sap"] = {
            "total_codigos": len(codigos_productos),
            "validos": len(validacion_sap.get("validos", [])),
            "no_encontrados": len(validacion_sap.get("no_encontrados", [])),
            "errores": len(validacion_sap.get("errores", [])),
            "warnings": len(validacion_sap.get("warnings", [])),
            "todos_validos": validacion_sap.get("todos_validos", False)
        }
        
        # Si SAP es obligatorio y hay errores, NO persistir
        if sap_obligatorio and not validacion_sap.get("todos_validos", False):
            no_encontrados = validacion_sap.get("no_encontrados", [])
            errores = validacion_sap.get("errores", [])
            
            # Mensaje simple - el frontend construirá el mensaje detallado
            mensaje_error = "Existen productos no válidos en SAP"
            
            resultado["status"] = "validation_error"
            resultado["errores"].append(mensaje_error)
            
            # Log detallado para debugging (solo en backend)
            log_detalle = f"Productos no encontrados ({len(no_encontrados)}): {', '.join(no_encontrados[:10])}"
            if len(no_encontrados) > 10:
                log_detalle += f" y {len(no_encontrados) - 10} más"
            if errores:
                log_detalle += f" | Errores ({len(errores)}): {', '.join(errores[:5])}"
                if len(errores) > 5:
                    log_detalle += f" y {len(errores) - 5} más"
            logger.error(f"❌ Validación SAP productos falló: {log_detalle}")
            
            return None  # Indicar que hay error y no se debe continuar
        
        logger.info(
            f"📊 Validación SAP: {len(validacion_sap.get('validos', []))} válidos, "
            f"{len(validacion_sap.get('no_encontrados', []))} no encontrados"
        )
        
        return validacion_sap
