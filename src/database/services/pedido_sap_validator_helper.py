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
                "validas": 0,
                "no_encontradas": 0,
                "errores": 0,
                "warnings": 0,
                "todas_validas": True
            }
        
        logger.info("📋 Validación SAP: Verificando códigos de tienda contra SAP OWHS")
        
        validacion_tiendas_sap = self.validator.validar_tiendas_existen_en_sap(
            codigos_tiendas=codigos_tiendas,
            sap_obligatorio=sap_obligatorio
        )
        
        resultado["validacion_tiendas_sap"] = {
            "total_codigos": len(codigos_tiendas),
            "validas": len(validacion_tiendas_sap.get("validas", [])),
            "no_encontradas": len(validacion_tiendas_sap.get("no_encontradas", [])),
            "errores": len(validacion_tiendas_sap.get("errores", [])),
            "warnings": len(validacion_tiendas_sap.get("warnings", [])),
            "todas_validas": validacion_tiendas_sap.get("todas_validas", False)
        }
        
        # Si SAP es obligatorio y hay tiendas no encontradas, BLOQUEAR
        if sap_obligatorio and not validacion_tiendas_sap.get("todas_validas", False):
            no_encontradas = validacion_tiendas_sap.get("no_encontradas", [])
            errores_sap = validacion_tiendas_sap.get("errores", [])
            
            mensaje_error = "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP."
            if no_encontradas:
                mensaje_error += f" Tiendas no encontradas en SAP OWHS: {', '.join(no_encontradas[:5])}"
                if len(no_encontradas) > 5:
                    mensaje_error += f" y {len(no_encontradas) - 5} más"
            if errores_sap:
                mensaje_error += f" Errores al consultar SAP: {', '.join(errores_sap[:3])}"
                if len(errores_sap) > 3:
                    mensaje_error += f" y {len(errores_sap) - 3} más"
            
            resultado["status"] = "validation_error"
            resultado["errores"].append(mensaje_error)
            logger.error(f"❌ {mensaje_error}")
        
        logger.info(
            f"📊 Validación SAP (Tiendas): {len(validacion_tiendas_sap.get('validas', []))} válidas, "
            f"{len(validacion_tiendas_sap.get('no_encontradas', []))} no encontradas"
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
            validos = validacion_sap.get("validos", [])
            
            # Construir mensaje legible
            errores_lista = []
            if no_encontrados:
                errores_lista.append(f"Productos no encontrados en SAP: {', '.join(no_encontrados[:5])}")
                if len(no_encontrados) > 5:
                    errores_lista[-1] += f" y {len(no_encontrados) - 5} más"
            if errores:
                errores_lista.append(f"Errores al consultar SAP: {', '.join(errores[:3])}")
                if len(errores) > 3:
                    errores_lista[-1] += f" y {len(errores) - 3} más"
            
            mensaje_error = "No se puede persistir el pedido: existen productos no válidos en SAP. " + " ".join(errores_lista)
            
            resultado["status"] = "validation_error"
            resultado["errores"].append(mensaje_error)
            logger.error(f"❌ {mensaje_error}")
            
            return None  # Indicar que hay error y no se debe continuar
        
        logger.info(
            f"📊 Validación SAP: {len(validacion_sap.get('validos', []))} válidos, "
            f"{len(validacion_sap.get('no_encontrados', []))} no encontrados"
        )
        
        return validacion_sap
