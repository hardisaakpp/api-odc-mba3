"""
Manejador de lógica de validación contra SAP.
Centraliza todo lo relacionado con validaciones contra el sistema SAP.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PedidoSAPHandler:
    """Maneja validaciones y operaciones contra SAP."""
    
    def __init__(self, validator: Optional[Any] = None):
        """
        Inicializa el manejador SAP.
        
        Args:
            validator: Instancia de PedidoValidator (inyección de dependencia)
        """
        self.validator = validator
    
    def validar_tiendas_contra_sap(
        self,
        codigos_tiendas: List[str],
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de tienda existan en SAP OWHS.
        
        Args:
            codigos_tiendas: Lista de códigos de tienda a validar
            sap_obligatorio: Si True, errores bloquean persistencia
            
        Returns:
            Dict con resultado de validación
        """
        if not self.validator or not codigos_tiendas:
            return {
                'todas_validas': True,
                'validas': [],
                'no_encontradas': [],
                'errores': [],
                'warnings': []
            }
        
        resultado = self.validator.validar_tiendas_existen_en_sap(
            codigos_tiendas=codigos_tiendas,
            sap_obligatorio=sap_obligatorio
        )
        
        logger.info(
            f"Validación SAP tiendas: {len(resultado.get('validas', []))} válidas, "
            f"{len(resultado.get('no_encontradas', []))} no encontradas"
        )
        
        return resultado
    
    def validar_productos_contra_sap(
        self,
        codigos_productos: List[str],
        validar_sap: bool = True,
        sap_obligatorio: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Valida que los códigos de producto existan en SAP ITEMS.

        Args:
            codigos_productos: Lista de códigos a validar
            validar_sap: Si False, retorna None sin validar
            sap_obligatorio: Si True, errores bloquean persistencia
            
        Returns:
            Dict con resultado o None si validar_sap=False
        """
        if not validar_sap or not self.validator or not codigos_productos:
            return None
        
        resultado = self.validator.validar_productos_existen_en_sap(
            codigos_productos=codigos_productos,
            sap_obligatorio=sap_obligatorio
        )
        
        logger.info(
            f"Validación SAP productos: {len(resultado.get('validos', []))} válidos, "
            f"{len(resultado.get('no_encontrados', []))} no encontrados"
        )
        
        return resultado
    
    def construir_mensaje_error_tiendas_invalidas(
        self,
        validacion_sap: Dict[str, Any]
    ) -> str:
        """
        Construye un mensaje de error amigable para tiendas inválidas.
        """
        no_encontradas = validacion_sap.get("no_encontradas", [])
        errores = validacion_sap.get("errores", [])
        
        mensaje = "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP."
        
        if no_encontradas:
            mensaje += f" Tiendas no encontradas: {', '.join(no_encontradas[:5])}"
            if len(no_encontradas) > 5:
                mensaje += f" y {len(no_encontradas) - 5} más"
        
        if errores:
            mensaje += f" Errores al consultar SAP: {', '.join(errores[:3])}"
            if len(errores) > 3:
                mensaje += f" y {len(errores) - 3} más"
        
        return mensaje
    
    def construir_mensaje_error_productos_invalidos(
        self,
        validacion_sap: Dict[str, Any]
    ) -> str:
        """
        Construye un mensaje de error amigable para productos inválidos.
        """
        no_encontrados = validacion_sap.get("no_encontrados", [])
        errores = validacion_sap.get("errores", [])
        
        mensaje = "No se puede persistir el pedido: existen productos no válidos en SAP."
        
        if no_encontrados:
            mensaje += f" Productos no encontrados: {', '.join(no_encontrados[:5])}"
            if len(no_encontrados) > 5:
                mensaje += f" y {len(no_encontrados) - 5} más"
        
        if errores:
            mensaje += f" Errores: {', '.join(errores[:3])}"
            if len(errores) > 3:
                mensaje += f" y {len(errores) - 3} más"
        
        return mensaje
    
    def construir_datos_validacion_error(
        self,
        error_type: str,
        validacion_sap: Dict[str, Any],
        total_codigos: int
    ) -> Dict[str, Any]:
        """
        Construye la estructura de datos para retornar en caso de error de validación.
        
        Args:
            error_type: 'tiendas' o 'productos'
            validacion_sap: Resultado de validación SAP
            total_codigos: Total de códigos validados
        """
        if error_type == 'tiendas':
            no_encontrados = validacion_sap.get("no_encontradas", [])
            errores = validacion_sap.get("errores", [])
            fuente = "ID TIENDA"
        else:  # productos
            no_encontrados = validacion_sap.get("no_encontrados", [])
            errores = validacion_sap.get("errores", [])
            fuente = "CODIGO PRODUCTO"
        
        return {
            "validacion": {
                error_type: {
                    "no_encontrados": no_encontrados,
                    "errores": errores,
                    "total_validos": len(validacion_sap.get("validas", validacion_sap.get("validos", []))),
                    "total_invalidos": len(no_encontrados) + len(errores)
                }
            },
            "validacion_sap": {
                "validos": len(validacion_sap.get("validas", validacion_sap.get("validos", []))),
                "no_encontrados": len(no_encontrados),
                "errores": len(errores),
                "warnings": len(validacion_sap.get("warnings", [])),
                "total_codigos": total_codigos,
                "todos_validos": validacion_sap.get("todas_validas", validacion_sap.get("todos_validos", False)),
                "fuente": fuente
            }
        }
