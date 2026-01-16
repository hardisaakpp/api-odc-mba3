"""
Procesador especializado para el formato v1.0 de pedidos (4 hojas).
Extraído de pedido_service.py para mejorar separación de responsabilidades.
"""

import logging
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import date
import io

from src.config import ENABLE_SQL_SERVER_STORAGE, ENABLE_SAP_QUERIES
from src.exceptions import BusinessException
from .pedido_validator import PedidoValidator
from .pedido_tiendas_handler import procesar_tiendas_y_validar_sap_v1_0
from .pedido_detalle_handler import procesar_detalle_articulos_v1_0
from .pedido_movimiento_handler import procesar_movimiento_y_coherencia_v1_0
from .pedido_guardado_handler import guardar_pedido_v1_0
from ..clients.sap_client import SAPClient

logger = logging.getLogger(__name__)


class PedidoFormatoV1Processor:
    """
    Procesador especializado para el formato v1.0 con 4 hojas:
    1. Cabecera Pedido
    2. Detalle Articulos
    3. Movimiento
    4. Tiendas
    """
    
    def __init__(
        self,
        parser: Any,
        consolidator: Any,
        validator: PedidoValidator,
        type_converter: Any
    ):
        """
        Inicializa el procesador.
        
        Args:
            parser: Instancia de PedidoParser
            consolidator: Instancia de PedidoConsolidator
            validator: Instancia de PedidoValidator
            type_converter: Instancia de PedidoTypeConverter
        """
        self.parser = parser
        self.consolidator = consolidator
        self.validator = validator
        self.type_converter = type_converter
    
    def procesar(
        self,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str] = None,
        hoja_cabecera: str = "Cabecera Pedido",
        hoja_detalle: str = "Detalle Articulos",
        hoja_movimiento: str = "Movimiento",
        hoja_tiendas: str = "Tiendas",
        validar_antes_de_guardar: bool = True,
        tiendas_permitidas: Optional[List[str]] = None,
        bloquea_con_errores: bool = True,
        validar_sap: bool = True,
        sap_obligatorio: bool = True,
        modo_tiendas: str = "validar_estricto",
        correcciones_codigos: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Procesa el formato v1.0 completo.
        
        Args:
            file_content: Contenido del archivo Excel
            filename: Nombre del archivo
            usuario_id: ID del usuario
            hoja_cabecera: Nombre de la hoja de cabecera
            hoja_detalle: Nombre de la hoja de detalle
            hoja_movimiento: Nombre de la hoja de movimiento
            hoja_tiendas: Nombre de la hoja de tiendas
            validar_antes_de_guardar: Si True, valida antes de persistir
            tiendas_permitidas: Lista de tiendas permitidas
            bloquea_con_errores: Si True, no guarda si hay errores
            validar_sap: Si True, valida códigos contra SAP
            sap_obligatorio: Si True, errores de SAP bloquean persistencia
            
        Returns:
            Dict con resultado del procesamiento
        """
        resultado = {
            "status": "success",
            "formato_detectado": "cuatro_hojas_v1_0",
            "validation": None,
            "pedido_id": None,
            "articulos_cargados": 0,
            "distribuciones_cargadas": 0,
            "errores": [],
            "warnings": [],
            "resumen": {
                "hojas_procesadas": [],
                "tiendas_validadas": 0,
                "productos_cargados": 0,
                "distribuciones_totales": 0
            }
        }
        
        try:
            # PASO 1: Procesar Tiendas y validar SAP
            catalogo_tiendas = self._procesar_tiendas(
                file_content, resultado, sap_obligatorio, hoja_tiendas
            )
            if catalogo_tiendas is None:
                return resultado
            
            # PASO 2: Leer y procesar hoja de Cabecera Pedido
            cabecera = self._procesar_cabecera(
                file_content, filename, usuario_id, hoja_cabecera, resultado
            )
            if cabecera is None:
                return resultado
            
            # PASO 3 & 4: Procesar Detalle Articulos y Movimiento
            productos_dict, distribuciones_movimiento = self._procesar_detalle_y_movimiento(
                file_content, resultado, catalogo_tiendas, validar_sap,
                hoja_detalle, hoja_movimiento
            )
            if productos_dict is None or distribuciones_movimiento is None:
                return resultado
            
            # PASO 5: Consolidar distribuciones por producto
            detalles_finales = self._consolidar_distribuciones(
                distribuciones_movimiento, productos_dict, resultado, bloquea_con_errores
            )
            
            # ⭐ NUEVO: Aplicar correcciones de códigos si se proporcionan (antes de validación SAP)
            if correcciones_codigos:
                detalles_finales = self._aplicar_correcciones_codigos_v1_0(
                    detalles_finales, 
                    correcciones_codigos
                )
            
            # Validaciones SAP adicionales
            self._validar_sap_productos_y_bodegas(
                detalles_finales, resultado, validar_sap, sap_obligatorio, bloquea_con_errores
            )
            if resultado.get("status") != "success":
                return resultado
            
            # PASO 6: Validación antes de guardar
            if validar_antes_de_guardar:
                self._validar_pedido_completo(
                    cabecera, detalles_finales, resultado, tiendas_permitidas,
                    bloquea_con_errores, sap_obligatorio
                )
                if resultado.get("status") != "success":
                    return resultado
            
            # ✅ PASO 6.5: Enriquecer detalles con información de SAP (ItemName y U_IXX_PACK)
            detalles_finales = self._enriquecer_detalles_con_sap(detalles_finales)
            
            # PASO 7: Guardar en base de datos
            if ENABLE_SQL_SERVER_STORAGE:
                guardar_pedido_v1_0(resultado, resultado.get("pedido_id"), detalles_finales, cabecera)
            else:
                logger.info("⚠️ SQL Server storage deshabilitado, no se guardó en BD")
            
            return resultado
            
        except BusinessException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al procesar formato v1.0: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
    
    def _procesar_tiendas(
        self,
        file_content: bytes,
        resultado: Dict[str, Any],
        sap_obligatorio: bool,
        hoja_tiendas: str
    ) -> Optional[Dict[str, Any]]:
        """Procesa la hoja de Tiendas y valida contra SAP."""
        # Crear un objeto service-like para pasar a la función handler
        service_like = type('ServiceLike', (), {
            'parser': self.parser,
            'validator': self.validator
        })()
        
        catalogo_tiendas = procesar_tiendas_y_validar_sap_v1_0(
            service_like, file_content, resultado, sap_obligatorio, hoja_tiendas
        )
        
        if catalogo_tiendas is None and resultado.get("status") == "validation_error":
            return None
        if catalogo_tiendas is None:
            catalogo_tiendas = {}
        
        return catalogo_tiendas
    
    def _procesar_cabecera(
        self,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str],
        hoja_cabecera: str,
        resultado: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Procesa la hoja de Cabecera Pedido."""
        logger.info("📋 PASO 2: Procesando hoja de Cabecera Pedido")
        excel_file = pd.ExcelFile(io.BytesIO(file_content))
        cabecera_parseada = self.parser._parsear_cabecera(excel_file, hoja_cabecera)
        
        cabecera = self.consolidator.normalizar_cabecera_para_bd(
            cabecera_parseada=cabecera_parseada,
            filename=filename,
            usuario_id=usuario_id
        )
        
        # Coerción de fechas desde texto si aplica
        try:
            valor_fecha_pedido = cabecera.get("fecha_pedido", cabecera.get("fecha_de_pedido"))
            if valor_fecha_pedido is not None:
                cabecera["fecha_pedido"] = self.type_converter.parsear_fecha_texto(valor_fecha_pedido)
            valor_fecha_entrega = cabecera.get("fecha_entrega", cabecera.get("fecha_de_entrega"))
            if valor_fecha_entrega is not None:
                cabecera["fecha_entrega"] = self.type_converter.parsear_fecha_texto(valor_fecha_entrega)
        except Exception:
            # No bloquear por error de parseo de fecha; se mantiene valor original
            pass
        
        resultado["resumen"]["hojas_procesadas"].append("Cabecera Pedido")
        logger.info(f"✅ Cabecera parseada: {cabecera.get('numero_pedido', 'SIN NÚMERO')}")
        return cabecera
    
    def _procesar_detalle_y_movimiento(
        self,
        file_content: bytes,
        resultado: Dict[str, Any],
        catalogo_tiendas: Dict[str, Any],
        validar_sap: bool,
        hoja_detalle: str,
        hoja_movimiento: str
    ) -> tuple[Optional[Dict[str, Dict]], Optional[List[Dict]]]:
        """Procesa Detalle Articulos y Movimiento, valida coherencia."""
        try:
            # Crear un objeto service-like con conversores requeridos por los handlers
            class ServiceLike:
                def __init__(self, parser, validator, type_converter):
                    self.parser = parser
                    self.validator = validator
                    self.type_converter = type_converter

                def _convertir_a_decimal(self, valor):
                    # Limpia símbolos comunes antes de delegar
                    if isinstance(valor, str):
                        valor = valor.replace("$", "").replace("%", "").strip()
                    return self.type_converter.convertir_a_decimal(valor)

                def _convertir_a_entero(self, valor):
                    return self.type_converter.convertir_a_entero(valor)

            service_like = ServiceLike(
                parser=self.parser,
                validator=self.validator,
                type_converter=self.type_converter,
            )
            
            productos_dict = procesar_detalle_articulos_v1_0(
                service_like, file_content, resultado, validar_sap, hoja_detalle
            )
            if productos_dict is None:
                return None, None
            
            distribuciones_movimiento = procesar_movimiento_y_coherencia_v1_0(
                service_like, file_content, resultado, catalogo_tiendas,
                productos_dict, validar_sap, hoja_movimiento
            )
            if distribuciones_movimiento is None:
                return None, None
            
            return productos_dict, distribuciones_movimiento
            
        except BusinessException:
            raise
        except Exception as e:
            logger.error(f"❌ Error en procesamiento Detalle/Movimiento: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return None, None
    
    def _aplicar_correcciones_codigos_v1_0(
        self,
        detalles_finales: List[Dict[str, Any]],
        correcciones: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Aplica correcciones de códigos de producto en memoria (formato v1.0).
        
        Reemplaza los códigos originales del Excel por los códigos SAP corregidos
        antes de validar contra SAP.
        
        Args:
            detalles_finales: Lista de detalles con productos y distribuciones
            correcciones: Diccionario {codigo_original: codigo_sap_corregido}
            
        Returns:
            Lista de detalles con códigos corregidos aplicados
        """
        if not correcciones:
            return detalles_finales
        
        correcciones_aplicadas = 0
        
        for detalle_item in detalles_finales:
            if not isinstance(detalle_item, dict):
                continue
                
            detalle = detalle_item.get("detalle", {})
            codigo_original = detalle.get("codigo_interno")
            
            if codigo_original and codigo_original in correcciones:
                codigo_corregido = correcciones[codigo_original]
                
                # Reemplazar código original por código SAP corregido
                detalle["codigo_interno"] = codigo_corregido
                correcciones_aplicadas += 1
                
                logger.info(
                    f"✅ [CORRECCIÓN v1.0] Código reemplazado: "
                    f"{codigo_original} → {codigo_corregido}"
                )
                
                # Actualizar también en el detalle_item
                detalle_item["detalle"] = detalle
        
        logger.info(
            f"📋 [CORRECCIONES v1.0] Total de códigos corregidos: {correcciones_aplicadas} de {len(correcciones)}"
        )
        
        return detalles_finales
    
    def _consolidar_distribuciones(
        self,
        distribuciones_movimiento: List[Dict],
        productos_dict: Dict[str, Dict],
        resultado: Dict[str, Any],
        bloquea_con_errores: bool
    ) -> List[Dict[str, Any]]:
        """Consolida distribuciones por producto."""
        logger.info("📋 PASO 5: Consolidando distribuciones por producto")
        
        detalles_consolidados = {}
        for dist in distribuciones_movimiento:
            codigo_producto = dist["codigo_producto"]
            
            if codigo_producto not in detalles_consolidados:
                # Obtener info del producto del catálogo
                info_producto = productos_dict.get(codigo_producto, {
                    "codigo_interno": codigo_producto,
                    "descripcion_sap": None,
                    "marca": None,
                    "codigo_barras": None,
                    "pack": None,
                    "costo_doc_sin_iva": None,
                    "descuento_1": None,
                    "pvp": None,
                })
                
                detalles_consolidados[codigo_producto] = {
                    "detalle": info_producto,
                    "distribuciones": []
                }
            
            # Agregar distribución (validar que tienda sea válida)
            tienda_valida = dist["validacion"]["valida"]
            if not tienda_valida and bloquea_con_errores:
                # Si hay validaciones y están en error, registrar warning
                for error in dist["validacion"]["errores"]:
                    resultado["warnings"].append(f"⚠️ Fila {dist['fila_origen']}: {error}")
            else:
                detalles_consolidados[codigo_producto]["distribuciones"].append({
                    "tienda_codigo": dist["tienda_codigo"],
                    "tienda_nombre": dist["tienda_nombre"],
                    "cantidad": dist["cantidad"],
                    "fila_origen": dist["fila_origen"]
                })
        
        detalles_finales = [
            {"detalle": data["detalle"], "distribuciones": data["distribuciones"]}
            for data in detalles_consolidados.values()
        ]
        
        logger.info(f"✅ Consolidación completa: {len(detalles_finales)} productos con distribuciones")
        
        # Consolidador: resumen global
        try:
            consolidacion = self.consolidator.consolidar_pedido_por_producto(detalles_finales)
            resultado["consolidacion"] = consolidacion.get("resumen", {"total_productos": 0, "cantidad_total": 0})
        except Exception as e:
            logger.warning(f"⚠️ No se pudo calcular consolidación por producto: {e}")
            resultado["consolidacion"] = {"total_productos": len(detalles_finales), "cantidad_total": 0}
        
        return detalles_finales
    
    def _validar_sap_productos_y_bodegas(
        self,
        detalles_finales: List[Dict[str, Any]],
        resultado: Dict[str, Any],
        validar_sap: bool,
        sap_obligatorio: bool,
        bloquea_con_errores: bool
    ) -> None:
        """Valida productos y bodegas contra SAP."""
        if not validar_sap or not detalles_finales:
            return
        
        # Validar productos
        logger.info("📋 Validación SAP: Verificando productos en SAP")
        codigos_productos = list(set([
            det.get("detalle", {}).get("codigo_interno")
            for det in detalles_finales
            if det.get("detalle", {}).get("codigo_interno")
        ]))
        
        if codigos_productos:
            validacion_sap = self.validator.validar_productos_existen_en_sap(
                codigos_productos=codigos_productos,
                usar_cache=True,
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
                errores_sap = validacion_sap.get("errores", [])
                
                mensaje_error = "No se puede persistir el pedido: existen productos no válidos en SAP."
                if no_encontrados:
                    mensaje_error += f" Productos no encontrados en SAP: {', '.join(no_encontrados[:5])}"
                    if len(no_encontrados) > 5:
                        mensaje_error += f" y {len(no_encontrados) - 5} más"
                if errores_sap:
                    mensaje_error += f" Errores al consultar SAP: {', '.join(errores_sap[:3])}"
                    if len(errores_sap) > 3:
                        mensaje_error += f" y {len(errores_sap) - 3} más"
                
                resultado["status"] = "validation_error"
                resultado["errores"].append(mensaje_error)
                logger.error(f"❌ {mensaje_error}")
                return
            
            logger.info(
                f"✅ Validación SAP: {len(validacion_sap.get('validos', []))} válidos, "
                f"{len(validacion_sap.get('no_encontrados', []))} no encontrados"
            )
        
        # Validar bodegas (si no se validó al inicio)
        if resultado.get("tiendas_cargadas") and "validacion_bodegas" not in resultado:
            self._validar_bodegas_sap(resultado, sap_obligatorio)
    
    def _validar_bodegas_sap(
        self,
        resultado: Dict[str, Any],
        sap_obligatorio: bool
    ) -> None:
        """Valida bodegas contra SAP OWHS."""
        logger.info("📋 Validación de bodegas: Verificando bodegas contra SAP OWHS")
        
        # Extraer códigos de bodegas del catálogo
        codigos_bodegas_set: set[str] = set()
        tiendas_cargadas = resultado.get("tiendas_cargadas", {})
        if isinstance(tiendas_cargadas, dict):
            codigos_bodegas_set = set(tiendas_cargadas.keys())
        elif isinstance(tiendas_cargadas, list):
            for item in tiendas_cargadas:
                if isinstance(item, dict):
                    codigo = item.get("codigo")
                    if codigo:
                        codigos_bodegas_set.add(codigo)
                elif isinstance(item, str) and item.strip():
                    codigos_bodegas_set.add(item.strip())
        
        codigos_bodegas = list(codigos_bodegas_set)
        
        if codigos_bodegas:
            validacion_bodegas = self.validator.validar_bodegas_existen_en_sap(
                codigos_bodegas=codigos_bodegas,
                sap_obligatorio=sap_obligatorio
            )
            
            resultado["validacion_bodegas"] = {
                "total_codigos": len(codigos_bodegas),
                "validas": len(validacion_bodegas.get("validas", [])),
                "no_encontradas": len(validacion_bodegas.get("no_encontradas", [])),
                "errores": len(validacion_bodegas.get("errores", [])),
                "warnings": len(validacion_bodegas.get("warnings", [])),
                "todas_validas": validacion_bodegas.get("todas_validas", False)
            }
            
            # Si hay bodegas no encontradas, agregar warning o error
            if validacion_bodegas.get("no_encontradas"):
                no_encontradas = validacion_bodegas["no_encontradas"]
                mensaje = (
                    f"Bodegas no encontradas en SAP OWHS: "
                    f"{', '.join(no_encontradas[:5])}"
                )
                if len(no_encontradas) > 5:
                    mensaje += f" y {len(no_encontradas) - 5} más"
                
                if sap_obligatorio:
                    resultado["errores"].append(mensaje)
                    logger.error(f"❌ {mensaje}")
                else:
                    resultado["warnings"].append(mensaje)
                    logger.warning(f"⚠️ {mensaje}")
            
            # Si SAP es obligatorio y hay bodegas inválidas, retornar error
            if sap_obligatorio and not validacion_bodegas.get("todas_validas", False):
                resultado["status"] = "validation_error"
                logger.error(f"❌ Errores de validación de bodegas en SAP")
                return
            
            logger.info(
                f"📊 Validación bodegas: {len(validacion_bodegas.get('validas', []))} válidas, "
                f"{len(validacion_bodegas.get('no_encontradas', []))} no encontradas"
            )
    
    def _validar_pedido_completo(
        self,
        cabecera: Dict[str, Any],
        detalles_finales: List[Dict[str, Any]],
        resultado: Dict[str, Any],
        tiendas_permitidas: Optional[List[str]],
        bloquea_con_errores: bool,
        sap_obligatorio: bool
    ) -> None:
        """Valida el pedido completo antes de guardar."""
        logger.info("📋 PASO 6: Validando pedido completo")
        
        validator = PedidoValidator(
            tiendas_permitidas=tiendas_permitidas,
            max_cantidad_por_tienda=10000,
            max_cantidad_total=100000,
            permitir_fechas_pasadas=False,
            validar_precios=True,
            iva_porcentaje=15.0,
            usar_comas_decimales=False
        )
        
        validacion_resultado = validator.validar_pedido_completo(
            cabecera, detalles_finales, es_formato_simple=False
        )
        
        # Serializar resultado de validación
        resultado["validation"] = {
            "valid": validacion_resultado.get("valid", True),
            "total_issues": validacion_resultado.get("total_issues", 0),
            "errors": validacion_resultado.get("errors", 0),
            "warnings": validacion_resultado.get("warnings", 0),
            "issues_by_row": {
                str(row_num): [
                    {
                        "field": getattr(issue, "field", None),
                        "severity": getattr(getattr(issue, "severity", None), "value", str(getattr(issue, "severity", None))),
                        "message": getattr(issue, "message", None),
                        "value": (str(issue.value) if getattr(issue, "value", None) is not None else None)
                    }
                    for issue in issues
                ]
                for row_num, issues in validacion_resultado.get("issues_by_row", {}).items()
            }
        }
        
        # Validación de existencia en catálogos
        self._validar_existencia_catalogos(
            detalles_finales, resultado, bloquea_con_errores, sap_obligatorio
        )
        
        # Validación explícita de cantidades
        self._validar_cantidades(detalles_finales, resultado, bloquea_con_errores)
        
        # Verificar si hay errores que bloqueen
        if bloquea_con_errores and resultado.get("errores"):
            resultado["status"] = "validation_error"
            logger.error(f"❌ Errores de validación: {resultado['errores']}")
            return
        
        if not validacion_resultado["valid"] and bloquea_con_errores:
            resultado["status"] = "validation_error"
            logger.error(f"❌ Errores de validación: {validacion_resultado['errors']}")
            return
    
    def _validar_existencia_catalogos(
        self,
        detalles_finales: List[Dict[str, Any]],
        resultado: Dict[str, Any],
        bloquea_con_errores: bool,
        sap_obligatorio: bool
    ) -> None:
        """Valida existencia de productos y bodegas en catálogos SAP."""
        try:
            # Extraer códigos únicos de productos
            codigos_productos = list(set([
                det.get("detalle", {}).get("codigo_interno")
                for det in detalles_finales
                if det.get("detalle", {}).get("codigo_interno")
            ]))
            
            # Extraer códigos de bodegas/tiendas desde el catálogo cargado
            codigos_bodegas: List[str] = []
            tiendas_cargadas = resultado.get("tiendas_cargadas", {})
            if isinstance(tiendas_cargadas, dict):
                codigos_bodegas = list(tiendas_cargadas.keys())
            elif isinstance(tiendas_cargadas, list):
                for item in tiendas_cargadas:
                    if isinstance(item, dict):
                        codigo = item.get("codigo")
                        if codigo:
                            codigos_bodegas.append(codigo)
                    elif isinstance(item, str) and item.strip():
                        codigos_bodegas.append(item.strip())
                codigos_bodegas = list(set(codigos_bodegas))
            
            resultado.setdefault("validation", {})
            
            # Validar productos contra SAP
            if codigos_productos:
                vp = self.validator.validar_productos_existen_en_sap(
                    codigos_productos=codigos_productos,
                    usar_cache=True,
                    sap_obligatorio=sap_obligatorio
                )
                resultado["validation"]["productos"] = vp
                if bloquea_con_errores and not vp.get("todos_validos", True):
                    no_encontrados = vp.get("no_encontrados", [])
                    resultado["errores"].append(
                        f"Productos no encontrados en SAP: {', '.join(no_encontrados[:5])}" +
                        (f" y {len(no_encontrados)-5} más" if len(no_encontrados) > 5 else "")
                    )
            
            # Validar bodegas contra SAP OWHS
            if codigos_bodegas:
                vb = self.validator.validar_bodegas_existen_en_sap(
                    codigos_bodegas=codigos_bodegas,
                    sap_obligatorio=sap_obligatorio
                )
                resultado["validation"]["bodegas"] = vb
                if bloquea_con_errores and not vb.get("todas_validas", True):
                    if vb.get("no_encontradas"):
                        resultado["errores"].append(
                            f"Bodegas no encontradas en SAP: {', '.join(vb['no_encontradas'][:5])}" +
                            (f" y {len(vb['no_encontradas'])-5} más" if len(vb['no_encontradas']) > 5 else "")
                        )
        except Exception as e:
            logger.warning(f"⚠️ Error en validación de existencia contra SAP (productos/bodegas): {e}")
    
    def _validar_cantidades(
        self,
        detalles_finales: List[Dict[str, Any]],
        resultado: Dict[str, Any],
        bloquea_con_errores: bool
    ) -> None:
        """Valida que las cantidades sean enteras y > 0."""
        try:
            issues_cantidades = []
            for idx, det in enumerate(detalles_finales, start=1):
                for dist in det.get("distribuciones", []):
                    qty = dist.get("cantidad")
                    es_entero = isinstance(qty, int) or (isinstance(qty, str) and str(qty).isdigit())
                    if not es_entero:
                        issues_cantidades.append(
                            f"Fila {idx}: cantidad no entera '{qty}' en tienda {dist.get('tienda_codigo')}"
                        )
                    else:
                        if int(qty) <= 0:
                            issues_cantidades.append(
                                f"Fila {idx}: cantidad debe ser > 0 (recibido {qty}) en tienda {dist.get('tienda_codigo')}"
                            )
            
            if issues_cantidades:
                resultado.setdefault("validation", {})
                resultado["validation"]["cantidades"] = {
                    "validas": False,
                    "issues": issues_cantidades
                }
                if bloquea_con_errores:
                    resultado.setdefault("errores", [])
                    resultado["errores"].extend(issues_cantidades)
        except Exception as e:
            logger.warning(f"⚠️ Error en validación de cantidades: {e}")
    
    def _enriquecer_detalles_con_sap(
        self,
        detalles_finales: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enriquece los detalles del pedido con información de SAP (ItemName y U_IXX_PACK).
        
        Este método consulta SAP para obtener:
        - ItemName → descripcion_sap (solo si está vacío)
        - U_IXX_PACK → pack (solo si está vacío)
        
        Args:
            detalles_finales: Lista de detalles con estructura:
                [{
                    "detalle": {
                        "codigo_interno": str,
                        "descripcion_sap": Optional[str],
                        "pack": Optional[str],
                        ...
                    },
                    "distribuciones": [...]
                }, ...]
        
        Returns:
            Lista de detalles enriquecidos con información de SAP
        """
        if not ENABLE_SAP_QUERIES:
            logger.debug("⏭️ Consultas SAP deshabilitadas, omitiendo enriquecimiento")
            return detalles_finales
        
        # Extraer códigos de productos únicos que necesitan enriquecimiento
        codigos_a_consultar = []
        codigos_por_detalle = {}  # Mapeo: codigo_interno -> índices de detalles que lo usan
        
        for idx, detalle_data in enumerate(detalles_finales):
            detalle = detalle_data.get("detalle", {})
            codigo_interno = detalle.get("codigo_interno")
            
            if not codigo_interno:
                continue
            
            # Solo consultar si falta descripcion_sap o pack
            necesita_descripcion = not detalle.get("descripcion_sap")
            necesita_pack = not detalle.get("pack")
            
            if necesita_descripcion or necesita_pack:
                codigo_normalized = codigo_interno.strip().upper()
                if codigo_normalized not in codigos_por_detalle:
                    codigos_a_consultar.append(codigo_normalized)
                    codigos_por_detalle[codigo_normalized] = []
                codigos_por_detalle[codigo_normalized].append(idx)
        
        if not codigos_a_consultar:
            logger.debug("✅ Todos los detalles ya tienen descripcion_sap y pack, omitiendo consulta SAP")
            return detalles_finales
        
        logger.info(f"🔍 Consultando SAP para enriquecer {len(codigos_a_consultar)} productos únicos")
        
        # Consultar SAP en batch
        sap_client = SAPClient()
        productos_sap = sap_client.get_productos_info_batch(codigos_a_consultar)
        
        # Enriquecer detalles con información de SAP
        detalles_enriquecidos = detalles_finales.copy()
        productos_enriquecidos = 0
        
        for codigo_normalized, indices in codigos_por_detalle.items():
            sap_info = productos_sap.get(codigo_normalized)
            
            if not sap_info:
                logger.debug(f"⚠️ No se encontró información SAP para {codigo_normalized}")
                continue
            
            item_name = sap_info.get("ItemName")
            pack_sap = sap_info.get("U_IXX_PACK")
            
            # Enriquecer cada detalle que usa este código
            for idx in indices:
                detalle = detalles_enriquecidos[idx]["detalle"]
                
                # Solo rellenar si está vacío (no sobrescribir valores existentes)
                if item_name and not detalle.get("descripcion_sap"):
                    detalle["descripcion_sap"] = item_name
                    productos_enriquecidos += 1
                    logger.debug(f"✅ Enriquecido descripcion_sap para {codigo_normalized}: {item_name[:50]}")
                
                if pack_sap and not detalle.get("pack"):
                    detalle["pack"] = pack_sap
                    productos_enriquecidos += 1
                    logger.debug(f"✅ Enriquecido pack para {codigo_normalized}: {pack_sap}")
        
        logger.info(f"✅ Enriquecidos {productos_enriquecidos} campos desde SAP")
        return detalles_enriquecidos
