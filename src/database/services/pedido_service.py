"""
Servicio para procesar plantillas Excel de pedidos.
ENFOQUE: Solo ingesta y persistencia, sin cálculos ni validaciones de negocio.
Modelo: Pedido → PedidoDetalle → PedidoDetalleTienda

REFACTORIZADO (Fase 2): Separado en módulos especializados:
- pedido_parser.py: Parsing de Excel
- pedido_consolidator.py: Normalización y consolidación
- pedido_service.py: Orquestación y persistencia (este archivo)
"""

import logging
import pandas as pd
from typing import Dict, Any, List, Optional, cast
from datetime import datetime, date
import io

from src.config import ENABLE_SQL_SERVER_STORAGE
from src.exceptions import BusinessException
from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.producto_sap_repository import ProductoSAPRepository
from ..pedido_estados import ESTADO_BORRADOR, ESTADO_NUEVO_PEDIDO
from .pedido_validator import PedidoValidator
from .pedido_parser import PedidoParser
from .pedido_consolidator import PedidoConsolidator
from .pedido_type_converter import PedidoTypeConverter
from .pedido_format_handler import PedidoFormatHandler
from .pedido_sap_handler import PedidoSAPHandler
from .pedido_format_detector import PedidoFormatDetector
from .pedido_sap_validator_helper import PedidoSAPValidatorHelper
from src.utils.audit_context import AuditContext, ORIGEN_WEB
from .pedido_formato_processor import PedidoFormatoProcessor
from ..clients.sap_client import SAPClient
from ..clients.sap_service_layer_client import SAPServiceLayerClient
from src.config import ENABLE_SAP_QUERIES, SAP_USE_MIDDLEWARE

logger = logging.getLogger(__name__)

_MSG_STORAGE_DESHABILITADO = "SQL Server storage está deshabilitado"
_PATRON_NUM_PEDIDO = "número de pedido"
_PATRON_YA_EXISTE = "ya existe"

# Parámetros por defecto para validación de pedidos (Ecuador: IVA 15%, formato estándar)
DEFAULT_PEDIDO_VALIDATOR_KWARGS = {
    "max_cantidad_por_tienda": 10000,
    "max_cantidad_total": 100000,
    "permitir_fechas_pasadas": False,
    "validar_precios": True,
    "iva_porcentaje": 15.0,
    "usar_comas_decimales": False,
}


class PedidoService:
    """
    Servicio para procesar plantillas Excel de pedidos.
    
    REFACTORIZADO: Ahora delega a módulos especializados:
    - PedidoParser: Parsing de Excel
    - PedidoConsolidator: Normalización y consolidación
    - PedidoValidator: Validación de reglas de negocio
    - PedidoRepository: Persistencia en BD
    
    Mantiene la misma interfaz pública para compatibilidad.
    """
    
    def __init__(self):
        """Inicializa el servicio con sus dependencias."""
        self.parser = PedidoParser()
        self.consolidator = PedidoConsolidator()
        self.validator = PedidoValidator()
        self.type_converter = PedidoTypeConverter()
        self.format_handler = PedidoFormatHandler()
        self.sap_handler = PedidoSAPHandler(self.validator)
        # Módulos auxiliares para refactorización
        self.format_detector = PedidoFormatDetector()
        self.sap_validator_helper = PedidoSAPValidatorHelper(self.validator)
        self.formato_processor = PedidoFormatoProcessor(
            self.parser,
            self.consolidator,
            self.type_converter
        )
    
    def parsear_excel_pedido(
        self,
        file_content: bytes,
        hoja_cabecera: str = "cabecera",
        hoja_detalle: str = "detalle",
    ) -> Dict[str, Any]:
        """
        Parsea un archivo Excel de pedido en formato v1.0.
        
        Formato esperado:
        - Hoja 1: "cabecera" (formato clave-valor: Campo | Valor | Ejemplo)
        - Hoja 2: "detalle" (formato tabular con columnas A-I producto, J-L bodegas, M+ tiendas)
        
        Solo parsing técnico: lee, normaliza y valida estructura.
        NO aplica reglas de negocio, NO consolida duplicados.
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            hoja_cabecera: Nombre de la hoja de cabecera (default: "cabecera")
            hoja_detalle: Nombre de la hoja de detalle (default: "detalle")

        Returns:
            Dict con estructura:
            {
                "cabecera": {
                    "numero_pedido": str,
                    "fecha_pedido": str,
                    ...
                },
                "resumen": {
                    "filasLeidas": int,
                    "filasValidas": int,
                    "filasInvalidas": int
                },
                "errores": [
                    {
                        "fila": int,
                        "campo": str,
                        "tipo": "ERROR",
                        "mensaje": str
                    }
                ],
                "data": [
                    {
                        "codigoProducto": str,
                        "idTienda": str,
                        "cantidad": int,
                        "filaOrigen": int
                    }
                ]
            }
        """
        # Delegar al parser
        # Solo se soporta el nuevo formato v1.0
        return self.parser.parsear_excel_pedido(
            file_content=file_content,
            hoja_cabecera=hoja_cabecera,
            hoja_detalle=hoja_detalle
        )
    
    def _normalizar_cabecera_para_bd(self, cabecera_parseada: Dict[str, Any], filename: str, usuario_id: Optional[str] = None) -> Dict[str, Any]:
        """Delega al consolidator para normalizar cabecera."""
        return self.consolidator.normalizar_cabecera_para_bd(
            cabecera_parseada=cabecera_parseada,
            filename=filename,
            usuario_id=usuario_id
        )
    
    @staticmethod
    def _enriquecer_detalles_codigo(
        detalles: List[Dict[str, Any]],
        indices: List[int],
        sap_info: Dict[str, Any],
        codigo: str,
    ) -> int:
        item_name = sap_info.get("ItemName")
        pack_sap = sap_info.get("U_IXX_PACK")
        enriquecidos = 0
        for idx in indices:
            detalle = detalles[idx]["detalle"]
            if item_name and not detalle.get("descripcion_sap"):
                detalle["descripcion_sap"] = item_name
                enriquecidos += 1
                logger.debug(f"✅ Enriquecido descripcion_sap para {codigo}: {item_name[:50]}")
            if pack_sap and not detalle.get("pack"):
                detalle["pack"] = pack_sap
                enriquecidos += 1
                logger.debug(f"✅ Enriquecido pack para {codigo}: {pack_sap}")
        return enriquecidos

    @staticmethod
    def _consultar_productos_via_middleware(
        codigos: List[str],
    ) -> tuple:
        """
        Consulta los códigos en una sola llamada batch al middleware
        (GET /api/v1/items/batch, en vez de N GET /api/v1/items/{code}).

        Returns:
            (resueltos, pendientes): `resueltos` con el mismo formato que
            get_productos_info_batch (los campos que consume el enriquecimiento);
            `pendientes` son los códigos que el middleware no pudo resolver
            (batch deshabilitado, chunk fallido/encolado, o error puntual) y
            deben consultarse por OPENQUERY. Un 404 confirmado NO es pendiente:
            es resolución definitiva (igual que OPENQUERY sin fila).
        """
        client = SAPServiceLayerClient()
        resueltos: Dict[str, Dict[str, Any]] = {}
        pendientes: List[str] = []

        items = client.get_items_batch(codigos)
        if items is None:
            # Middleware caído/deshabilitado: ningún código se pudo resolver
            return resueltos, list(codigos)

        for codigo in codigos:
            item = items.get(codigo)
            if item is None:
                # No vino en el batch (chunk fallido/encolado): fallback a OPENQUERY
                pendientes.append(codigo)
                continue
            if item.get("_error"):
                if item.get("_error_type") == "no_existe":
                    continue
                pendientes.append(codigo)
                continue
            resueltos[codigo] = {
                "ItemCode": item.get("ItemCode"),
                "ItemName": item.get("ItemName"),
                "U_IXX_PACK": item.get("U_IXX_PACK"),
            }
        return resueltos, pendientes

    def _consultar_productos_sap(self, codigos: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Consulta información de productos en SAP: middleware primero
        (SAP_USE_MIDDLEWARE), con fallback automático a OPENQUERY
        para los códigos que el middleware no pudo resolver.
        """
        pendientes = list(codigos)
        resultados: Dict[str, Dict[str, Any]] = {}

        if SAP_USE_MIDDLEWARE:
            resultados, pendientes = self._consultar_productos_via_middleware(codigos)
            if pendientes:
                logger.warning(
                    f"⚠️ Middleware no resolvió {len(pendientes)} SKUs; fallback a OPENQUERY"
                )

        if pendientes:
            resultados.update(SAPClient().get_productos_info_batch(pendientes))

        return resultados

    def _enriquecer_detalles_con_sap(
        self,
        detalles_con_tiendas: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enriquece los detalles del pedido con información de SAP (ItemName y U_IXX_PACK).
        
        Este método consulta SAP para obtener:
        - ItemName → descripcion_sap (solo si está vacío)
        - U_IXX_PACK → pack (solo si está vacío)
        
        Args:
            detalles_con_tiendas: Lista de detalles con estructura:
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
            return detalles_con_tiendas
        
        # Extraer códigos de productos únicos que necesitan enriquecimiento
        codigos_a_consultar = []
        codigos_por_detalle = {}  # Mapeo: codigo_interno -> índices de detalles que lo usan
        
        for idx, detalle_data in enumerate(detalles_con_tiendas):
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
            return detalles_con_tiendas
        
        logger.info(f"🔍 Consultando SAP para enriquecer {len(codigos_a_consultar)} productos únicos")

        # Consultar SAP: middleware primero, fallback a OPENQUERY
        productos_sap = self._consultar_productos_sap(codigos_a_consultar)
        
        # Enriquecer detalles con información de SAP
        detalles_enriquecidos = detalles_con_tiendas.copy()
        productos_enriquecidos = 0
        
        for codigo_normalized, indices in codigos_por_detalle.items():
            sap_info = productos_sap.get(codigo_normalized)
            
            if not sap_info:
                logger.debug(f"⚠️ No se encontró información SAP para {codigo_normalized}")
                continue
            
            productos_enriquecidos += self._enriquecer_detalles_codigo(
                detalles_enriquecidos, indices, sap_info, codigo_normalized
            )
        
        logger.info(f"✅ Enriquecidos {productos_enriquecidos} campos desde SAP")
        return detalles_enriquecidos
    
    @staticmethod
    def _log_debug_filas_excel(df: "pd.DataFrame") -> None:
        logger.info(f"Shape del DataFrame: {df.shape} (filas x columnas)")
        if len(df) == 0:
            return
        logger.info("Primeras 10 filas, primeras 8 columnas del Excel:")
        for i in range(min(10, len(df))):
            row_data = []
            for j in range(min(8, len(df.columns))):
                val = df.iloc[i, j]
                row_data.append("(vacío)" if pd.isna(val) else str(val)[:50])
            logger.info(f"  Fila {i}: {row_data}")

    @staticmethod
    def _normalizar_fecha_cabecera(fecha_raw: Any) -> Any:
        if not fecha_raw:
            return None
        try:
            if isinstance(fecha_raw, datetime):
                return fecha_raw.date()
            if isinstance(fecha_raw, date):
                return fecha_raw
            if isinstance(fecha_raw, str):
                return pd.to_datetime(fecha_raw, dayfirst=True).date()
        except Exception as e:
            logger.warning(f"⚠️ Error al parsear fecha_pedido: {e}")
        return None

    def procesar_archivo_excel(
        self,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Procesa un archivo Excel y guarda los datos en base de datos.
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            filename: Nombre del archivo
            usuario_id: ID del usuario que sube el archivo
            
        Returns:
            Dict con resultado del procesamiento:
            {
                "status": "success",
                "pedido_id": "...",
                "articulos_cargados": 128,
                "distribuciones_cargadas": 256,
                "errores": []
            }
        """
        if not ENABLE_SQL_SERVER_STORAGE:
            return {
                "status": "error",
                "message": _MSG_STORAGE_DESHABILITADO
            }
        
        resultado = {
            "status": "success",
            "pedido_id": None,
            "articulos_cargados": 0,
            "distribuciones_cargadas": 0,
            "errores": []
        }
        
        try:
            # Leer Excel sin headers (para poder buscar la cabecera)
            df_raw_result = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=None)
            # Type assertion: sheet_name=0 returns a single DataFrame, not a dict
            df_raw = cast(pd.DataFrame, df_raw_result)
            
            # Log para debug: mostrar primeras filas del Excel
            self._log_debug_filas_excel(df_raw)
            
            # Paso 1: Extraer cabecera usando método que soporta formato horizontal y vertical
            try:
                # Usar parsear_cabecera que soporta ambos formatos
                excel_file = pd.ExcelFile(io.BytesIO(file_content))
                cabecera_parseada = self.parser.parsear_cabecera(excel_file, "cabecera")
                
                # Convertir a formato BD (mapear campos del Excel a campos de BD)
                cabecera = {
                    "numero_pedido": (
                        cabecera_parseada.get("numero_pedido") or 
                        cabecera_parseada.get("CODIGO PEDIDO") or 
                        cabecera_parseada.get("CÓDIGO PEDIDO")
                    ),
                    "fecha_pedido": (
                        cabecera_parseada.get("fecha_pedido") or 
                        cabecera_parseada.get("FECHA PEDIDO")
                    ),
                    "fecha_entrega": (
                        cabecera_parseada.get("fecha_entrega") or 
                        cabecera_parseada.get("FECHA ENTREGA")
                    ),
                    "forma_pago": (
                        cabecera_parseada.get("forma_pago") or 
                        cabecera_parseada.get("FORMA PAGO") or 
                        cabecera_parseada.get("FORMA DE PAGO")
                    ),
                    "mensaje": (
                        cabecera_parseada.get("mensaje") or 
                        cabecera_parseada.get("MENSAJE")
                    ),
                    "proveedor_nombre": (
                        cabecera_parseada.get("proveedor_nombre") or 
                        cabecera_parseada.get("NOMBRE PROVEEDOR")
                    ),
                    "comprador_nombre": (
                        cabecera_parseada.get("comprador_nombre") or 
                        cabecera_parseada.get("COMPRADOR NOMBRE")
                    ),
                    "comprador_codigo": (
                        cabecera_parseada.get("comprador_codigo") or 
                        cabecera_parseada.get("COD COMPRADOR") or 
                        cabecera_parseada.get("CÓD COMPRADOR") or 
                        cabecera_parseada.get("CODIGO COMPRADOR")
                    ),
                    "origen_traslado": (
                        cabecera_parseada.get("origen_traslado") or 
                        cabecera_parseada.get("ORIGEN TRASLADO")
                    ),
                    "serie": (
                        cabecera_parseada.get("serie") or 
                        cabecera_parseada.get("SERIE")
                    ),
                    "archivo_nombre": filename,
                    "creado_por": usuario_id,
                }
                
                # Validar que numero_pedido existe
                if not cabecera["numero_pedido"]:
                    raise ValueError(
                        "No se pudo encontrar el campo 'CODIGO PEDIDO' en la cabecera del Excel. "
                        "Verifica que el archivo tenga la estructura correcta."
                    )
                
                # Convertir fecha_pedido a DATE si es posible
                cabecera["fecha_pedido"] = self._normalizar_fecha_cabecera(cabecera.get("fecha_pedido"))
                        
            except ValueError as e:
                # Error de validación (ej: numero_pedido no encontrado)
                raise ValueError(f"Error al extraer cabecera del Excel: {str(e)}")
            except Exception as e:
                logger.error(f"❌ Error al parsear cabecera: {e}", exc_info=True)
                raise ValueError(f"Error al extraer cabecera del Excel: {str(e)}")
            
            # Este método está deprecado. Usar validar_y_procesar_archivo_excel en su lugar.
            raise ValueError(
                "El método procesar_archivo_excel está deprecado. "
                "Use validar_y_procesar_archivo_excel en su lugar, que soporta el nuevo formato v1.0."
            )

        except Exception as e:
            logger.error(f"❌ Error al procesar plantilla Excel: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
    
    
    def _aplicar_correcciones_codigos(
        self,
        detalles_con_tiendas: List[Dict[str, Any]],
        correcciones: Dict[str, str]
    ) -> int:
        """
        Aplica correcciones de códigos de producto en memoria (mutación in-place).

        Args:
            detalles_con_tiendas: Lista de detalles con productos y distribuciones
            correcciones: Diccionario {codigo_original: codigo_sap_corregido}

        Returns:
            Número de correcciones aplicadas
        """
        if not correcciones:
            return 0
        
        correcciones_aplicadas = 0
        
        for detalle_item in detalles_con_tiendas:
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
                    f"✅ [CORRECCIÓN] Código reemplazado: "
                    f"{codigo_original} → {codigo_corregido}"
                )
                
                # Actualizar también en el detalle_item
                detalle_item["detalle"] = detalle
        
        logger.info(
            f"📋 [CORRECCIONES] Total de códigos corregidos: {correcciones_aplicadas} de {len(correcciones)}"
        )
        return correcciones_aplicadas

    def _detectar_y_procesar_formato_excel(
        self,
        file_content: bytes,
        resultado: Dict[str, Any],
    ) -> bool:
        """
        Detecta el formato del Excel y actualiza resultado["formato_detectado"].
        Retorna True si es formato v1.0, False si es formato legacy sin hojas requeridas.
        """
        hojas = self.format_detector.detectar_hojas(file_content)
        formato = self.format_detector.detectar_formato(hojas)

        if formato == 'dos_hojas_nuevo_v1_0':
            logger.info("📋 Detectado formato v1.0 (2 hojas)")
            resultado["formato_detectado"] = "dos_hojas_nuevo_v1_0"
            return True

        logger.info("📋 Detectado formato legacy (dos hojas o simple)")
        resultado["formato_detectado"] = "dos_hojas_simple" if hojas['cabecera'] and hojas['detalle'] else "simple"
        return hojas['cabecera'] is not None and hojas['detalle'] is not None
    
    def _procesar_formato_dos_hojas_o_simple(
        self,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str],
        excel_file: pd.ExcelFile,
        hoja_cabecera_encontrada: Optional[str],
        hoja_detalle_encontrada: Optional[str]
    ) -> tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
        """
        Procesa formato de dos hojas (CABECERA_PEDIDO + DETALLE_ARTICULO) o simple.
        Retorna (cabecera_dict, detalles_list) o (None, None) si error.
        
        NOTA: Este método delega al PedidoFormatoProcessor para mantener compatibilidad.
        """
        return self.formato_processor.procesar_formato_dos_hojas_o_simple(
            file_content=file_content,
            filename=filename,
            usuario_id=usuario_id,
            excel_file=excel_file,
            hoja_cabecera_encontrada=hoja_cabecera_encontrada,
            hoja_detalle_encontrada=hoja_detalle_encontrada
        )
    
    def validar_y_procesar_archivo_excel(
        self,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str] = None,
        validar_antes_de_guardar: bool = True,
        tiendas_permitidas: Optional[List[str]] = None,
        bloquea_con_errores: bool = True,
        validar_sap: bool = True,
        correcciones_codigos: Optional[Dict[str, str]] = None,
        correcciones_pack_pvp: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Valida y procesa un archivo Excel de pedido.

        Auto-detecta el formato (simple o complejo) basado en las columnas.

        Args:
            file_content: Contenido del archivo Excel
            filename: Nombre del archivo
            usuario_id: ID del usuario
            validar_antes_de_guardar: Si True, valida antes de guardar en BD
            tiendas_permitidas: Lista de códigos de tiendas permitidas
            bloquea_con_errores: Si True, no guarda si hay errores críticos
            validar_sap: Si True, valida que códigos de producto existan en SAP
            sap_obligatorio: Si True, errores de SAP bloquean la persistencia
            correcciones_pack_pvp: Mapa {codigo: {"pack": valor, "pvp": valor}} con el valor
                elegido por el usuario (SAP o Excel) para reintentar tras una discrepancia
                de Pack/PVP (RN-02). Si un campo viene presente, se usa ese valor y no se
                vuelve a comparar contra SAP.

        Returns:
            Dict con resultado incluyendo validación
        """
        if not ENABLE_SQL_SERVER_STORAGE:
            return {
                "status": "error",
                "message": _MSG_STORAGE_DESHABILITADO
            }

        resultado = {
            "status": "success",
            "validation": None,
            "pedido_id": None,
            "formato_detectado": None,
            "articulos_cargados": 0,
            "distribuciones_cargadas": 0,
            "errores": [],
            "correcciones_aplicadas": [
                {"codigo_original": k, "codigo_corregido": v}
                for k, v in (correcciones_codigos or {}).items()
            ]
        }

        try:
            hoja_cabecera, hoja_detalle = self._detectar_y_validar_formato(file_content)
            resultado["formato_detectado"] = "dos_hojas_nuevo_v1_0"
            cabecera, detalles_con_tiendas = self._procesar_formato_nuevo_v1_0(
                file_content, hoja_cabecera, hoja_detalle,
                filename, usuario_id, validar_sap, correcciones_codigos,
                correcciones_pack_pvp
            )
            if not detalles_con_tiendas:
                raise BusinessException(
                    message="El archivo Excel está vacío o no contiene datos válidos",
                    error_code="ARCHIVO_SIN_DATOS",
                    data={
                        "mensaje_detallado": "No se encontraron productos con distribuciones válidas en el archivo",
                        "validacion": {
                            "datos_archivo": {
                                "valido": False,
                                "mensaje": "El archivo debe contener al menos un producto con cantidades para tiendas o bodegas"
                            }
                        }
                    }
                )
            if validar_sap:
                self._validar_tiendas_bodegas_sap(cabecera, detalles_con_tiendas, resultado)
            if validar_antes_de_guardar:
                self._ejecutar_validacion_pedido(
                    cabecera, detalles_con_tiendas, resultado,
                    tiendas_permitidas, bloquea_con_errores, filename
                )
            validacion_sap = None
            if validar_sap:
                validacion_sap = self._preparar_validacion_sap_persistencia(detalles_con_tiendas, resultado)
            self._persistir_pedido(
                cabecera=cabecera,
                detalles_con_tiendas=detalles_con_tiendas,
                resultado=resultado,
                validar_sap=validar_sap,
                validacion_sap=validacion_sap
            )
            pedido_id = resultado.get("pedido_id")
            logger.info(
                f"✅ Pedido procesado: {filename} "
                f"(pedido_id: {pedido_id}, formato: {resultado['formato_detectado']}, "
                f"artículos: {resultado['articulos_cargados']}, "
                f"distribuciones: {resultado['distribuciones_cargadas']})"
            )
            return resultado

        except BusinessException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al procesar plantilla Excel: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado

    def _detectar_y_validar_formato(self, file_content: bytes) -> tuple:
        excel_file = pd.ExcelFile(io.BytesIO(file_content))
        hojas = self.format_detector.detectar_hojas(file_content)
        hoja_cabecera = hojas['cabecera']
        hoja_detalle = hojas['detalle']
        if hoja_cabecera is None:
            logger.warning(f"⚠️ No se encontró hoja de cabecera. Hojas disponibles: {excel_file.sheet_names}")
        if hoja_detalle is None:
            logger.warning(f"⚠️ No se encontró hoja de detalle. Hojas disponibles: {excel_file.sheet_names}")
        formato_detectado = self.format_detector.detectar_formato(hojas)
        if formato_detectado != 'dos_hojas_nuevo_v1_0':
            hojas_disponibles = ", ".join(str(sheet) for sheet in excel_file.sheet_names)
            hojas_disponibles_lista = [str(sheet) for sheet in excel_file.sheet_names]
            error_msg = (
                f"Formato de archivo no reconocido. "
                f"El sistema solo soporta el formato v1.0 con hojas 'cabecera' y 'detalle' (en minúsculas).\n\n"
                f"Hojas encontradas en el archivo: {hojas_disponibles}\n"
                f"Se esperaba: hoja 'cabecera' y hoja 'detalle'"
            )
            logger.error(f"❌ {error_msg}")
            raise BusinessException(
                message="El archivo Excel no tiene el formato correcto",
                error_code="FORMATO_EXCEL_INVALIDO",
                data={
                    "hojas_encontradas": hojas_disponibles_lista,
                    "hojas_esperadas": ["cabecera", "detalle"],
                    "mensaje_detallado": error_msg,
                    "validacion": {
                        "formato_archivo": {
                            "valido": False,
                            "mensaje": "El archivo debe contener dos hojas llamadas 'cabecera' y 'detalle' (en minúsculas)"
                        }
                    }
                }
            )
        return str(hoja_cabecera), str(hoja_detalle)

    def _validar_numero_pedido_duplicado(self, cabecera_parseada: Dict[str, Any]) -> None:
        numero_pedido_raw = (
            cabecera_parseada.get("numero_pedido") or
            cabecera_parseada.get("CODIGO PEDIDO") or
            cabecera_parseada.get("CÓDIGO PEDIDO")
        )
        if not numero_pedido_raw:
            return
        with get_db_connection_context() as conn_check:
            repo_check = PedidoRepository(conn_check)
            if repo_check.existe_numero_pedido(numero_pedido_raw):
                logger.warning(f"⚠️ [VALIDACIÓN TEMPRANA #1] Número de pedido duplicado detectado: '{numero_pedido_raw}'")
                raise BusinessException(
                    message=f"El número de pedido '{numero_pedido_raw}' ya existe en el sistema",
                    error_code="NUMERO_PEDIDO_DUPLICADO",
                    data={
                        "numero_pedido": numero_pedido_raw,
                        "validacion": {
                            "numero_pedido": {
                                "duplicado": True,
                                "mensaje": f"El número de pedido '{numero_pedido_raw}' ya fue utilizado anteriormente"
                            }
                        }
                    }
                )
            else:
                logger.info(f"✅ [VALIDACIÓN TEMPRANA #1] Número de pedido '{numero_pedido_raw}' disponible")

    @staticmethod
    def _norm_list(valor: Any) -> List:
        """Normaliza un valor a lista: si viene como int (o no-lista) lo convierte en []."""
        return [] if isinstance(valor, int) else valor

    @staticmethod
    def _construir_log_detalle_sap(etiqueta: str, no_encontradas: List, errores: List) -> str:
        """Construye el mensaje de log resumido para una validación SAP fallida."""
        log_detalle = f"{etiqueta} no encontradas ({len(no_encontradas)}): {', '.join(no_encontradas[:10])}"
        if len(no_encontradas) > 10:
            log_detalle += f" y {len(no_encontradas) - 10} más"
        if errores:
            log_detalle += f" | Errores ({len(errores)}): {', '.join(errores[:5])}"
            if len(errores) > 5:
                log_detalle += f" y {len(errores) - 5} más"
        return log_detalle

    @staticmethod
    def _recolectar_codigos_producto_parsing(
        datos_parsing: List[Dict],
        correcciones_codigos: Optional[Dict[str, str]]
    ) -> List[str]:
        """Extrae los códigos de producto únicos del parsing, aplicando correcciones si existen."""
        codigos_set: set = set()
        for item in datos_parsing:
            codigo = item.get("codigoProducto")
            if codigo is not None and isinstance(codigo, str):
                codigos_set.add(codigo)
        codigos_productos_parsing: List[str] = list(codigos_set)
        if correcciones_codigos:
            codigos_corregidos: List[str] = []
            for codigo in codigos_productos_parsing:
                codigo_corregido = correcciones_codigos.get(codigo, codigo)
                if codigo_corregido is not None and isinstance(codigo_corregido, str):
                    codigos_corregidos.append(codigo_corregido)
            codigos_productos_parsing = codigos_corregidos
        return codigos_productos_parsing

    def _validar_productos_sap_temprana(
        self,
        datos_parsing: List[Dict],
        correcciones_codigos: Optional[Dict[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Consulta la validación de productos contra SAP y la retorna siempre (válida o no) sin
        lanzar excepción — la decisión de bloquear es de _validar_sap_codigo_y_pack_pvp, que la
        combina con el resultado de Pack/PVP en una sola BusinessException.
        """
        codigos_productos_parsing = self._recolectar_codigos_producto_parsing(datos_parsing, correcciones_codigos)
        if not codigos_productos_parsing:
            return None
        codigos_sample = sorted(codigos_productos_parsing)[:20]
        logger.info(
            f"🔍 Validando {len(codigos_productos_parsing)} productos contra SAP (con sugerencias). "
            f"Códigos: {codigos_sample}{'...' if len(codigos_productos_parsing) > 20 else ''}"
        )
        validator = PedidoValidator()
        validacion_sap_productos = validator.validar_productos_existen_en_sap_con_sugerencias(
            codigos_productos=codigos_productos_parsing,
            usar_cache=False,
            sap_obligatorio=True,
            incluir_sugerencias=True,
            limite_sugerencias=20
        )
        if validacion_sap_productos is not None and validacion_sap_productos.get("todos_validos", False):
            logger.debug(f"✅ Validación SAP: {len(validacion_sap_productos.get('validos', []))} productos válidos")
        return validacion_sap_productos

    def _validar_sap_codigo_y_pack_pvp(
        self,
        datos_parsing: List[Dict],
        correcciones_codigos: Optional[Dict[str, str]],
        correcciones_pack_pvp: Optional[Dict[str, Dict[str, Any]]]
    ) -> None:
        """
        Ejecuta en una sola pasada las 3 validaciones contra SAP (código, pack, pvp) y, si alguna
        falla, lanza UNA sola BusinessException combinada — antes código bloqueaba de inmediato y
        pack/pvp solo se evaluaba en un reintento posterior; ahora el usuario ve y corrige todo en
        el mismo intento, sin importar cuál(es) de las 3 validaciones fallen.
        """
        validacion_sap_productos = self._validar_productos_sap_temprana(datos_parsing, correcciones_codigos)
        codigos_productos_parsing = self._recolectar_codigos_producto_parsing(datos_parsing, correcciones_codigos)
        codigo_invalido = bool(codigos_productos_parsing) and (
            validacion_sap_productos is None or not validacion_sap_productos.get("todos_validos", False)
        )

        pack_pvp_exc: Optional[BusinessException] = None
        try:
            self._validar_pack_pvp_temprana(
                datos_parsing, correcciones_codigos, validacion_sap_productos, correcciones_pack_pvp
            )
        except BusinessException as e:
            pack_pvp_exc = e

        if not codigo_invalido and pack_pvp_exc is None:
            self._resolver_costo_unitario_temprana(datos_parsing, correcciones_codigos)
            return
        self._raise_validacion_sap_combinada(
            codigo_invalido, validacion_sap_productos, codigos_productos_parsing, pack_pvp_exc,
            datos_parsing, correcciones_codigos
        )

    def _resolver_costo_unitario_temprana(
        self,
        datos_parsing: List[Dict],
        correcciones_codigos: Optional[Dict[str, str]],
    ) -> None:
        """
        Calcula costo_unitario = costo_doc_sin_iva / unidad_conversion para cada
        producto, usando el pack ya resuelto (SAP o Excel, según eligió el usuario
        en _evaluar_pack_producto). Reemplaza a costo_margen (columna "Costo" del
        Excel, manual) como insumo del Margen de Rentabilidad (req. 1.5).

        Bloquea la carga si el pack final no tiene una unidad de conversión
        configurada en pack_conversion (código inexistente, inactivo, o pack vacío).
        """
        codigo_a_info_productos = self._agrupar_info_productos_por_codigo(datos_parsing, correcciones_codigos)
        if not codigo_a_info_productos:
            return

        packs_invalidos: List[Dict[str, Any]] = []
        with get_db_connection_context() as conn:
            repo = ProductoSAPRepository(conn)
            for codigo, info_productos in codigo_a_info_productos.items():
                pack_final = next((ip.get("pack") for ip in info_productos if ip.get("pack")), None)
                unidad_conversion = repo.get_unidad_conversion_by_pack(pack_final) if pack_final else None
                if unidad_conversion is None:
                    packs_invalidos.append({"codigo": codigo, "pack": pack_final})
                    continue
                for info_producto in info_productos:
                    costo_doc_sin_iva = info_producto.get("costo_doc_sin_iva")
                    info_producto["costo_unitario"] = (
                        costo_doc_sin_iva / unidad_conversion if costo_doc_sin_iva is not None else None
                    )

        if packs_invalidos:
            self._raise_pack_sin_unidad_conversion(packs_invalidos)

    @staticmethod
    def _raise_pack_sin_unidad_conversion(packs_invalidos: List[Dict[str, Any]]) -> None:
        logger.error(f"❌ {len(packs_invalidos)} producto(s) con Pack sin unidad de conversión configurada")
        mensajes = [
            (
                f"El Pack '{m['pack']}' del producto '{m['codigo']}' no tiene una unidad de conversión "
                f"configurada en pack_conversion. Verifique el código de pack."
                if m["pack"]
                else f"El producto '{m['codigo']}' no tiene un Pack válido. Ingrese un código de pack (ej. X1, X2, X3)."
            )
            for m in packs_invalidos
        ]
        raise BusinessException(
            message=f"Existen {len(packs_invalidos)} producto(s) con Pack sin unidad de conversión válida",
            error_code="PACK_SIN_UNIDAD_CONVERSION",
            data={
                "validacion_pack_conversion": {
                    "packs_invalidos": packs_invalidos,
                    "mensajes": mensajes,
                }
            }
        )

    def _raise_validacion_sap_combinada(
        self,
        codigo_invalido: bool,
        validacion_sap_productos: Optional[Dict[str, Any]],
        codigos_productos_parsing: List[str],
        pack_pvp_exc: Optional[BusinessException],
        datos_parsing: List[Dict],
        correcciones_codigos: Optional[Dict[str, str]]
    ) -> None:
        """Combina el resultado de código inválido y/o de Pack/PVP en una sola BusinessException."""
        data: Dict[str, Any] = {}
        partes_mensaje: List[str] = []

        if codigo_invalido:
            no_encontrados = self._norm_list(validacion_sap_productos.get("no_encontrados", []) if validacion_sap_productos else [])
            errores = self._norm_list(validacion_sap_productos.get("errores", []) if validacion_sap_productos else [])
            validos = self._norm_list(validacion_sap_productos.get("validos", []) if validacion_sap_productos else [])
            detalle_validacion = validacion_sap_productos.get("detalle", {}) if validacion_sap_productos else {}
            no_encontrados_str = ', '.join(no_encontrados[:5])
            if len(no_encontrados) > 5:
                no_encontrados_str += f" (+{len(no_encontrados) - 5} más)"
            logger.error(f"❌ Validación SAP falló: {len(validos)}✓, {len(no_encontrados)}✗ [{no_encontrados_str}]")
            data["validacion"] = {
                "productos": {
                    "no_encontrados": no_encontrados,
                    "errores": errores,
                    "validos": validos,
                    "total_validos": len(validos),
                    "total_invalidos": len(no_encontrados) + len(errores)
                }
            }
            # codigo_a_info_productos: mismo agrupamiento (y misma convención de
            # "primer valor no nulo" ante filas duplicadas por código) que usa la
            # validación de Pack/PVP para códigos ya válidos — ver
            # _evaluar_pack_producto / _evaluar_pvp_producto. Se expone aquí el
            # Pack/PVP tal como vino en el Excel para que el frontend pueda
            # detectar el mismatch automáticamente apenas el usuario elige una
            # sugerencia SAP, sin esperar al reintento siguiente.
            codigo_a_info_productos = self._agrupar_info_productos_por_codigo(datos_parsing, correcciones_codigos)
            data["validacion_sap"] = {
                "total_codigos": len(codigos_productos_parsing),
                "validos": len(validos),
                "no_encontrados": len(no_encontrados),
                "errores": len(errores),
                "todos_validos": False,
                "detalle_validacion": {
                    codigo: {
                        "existe": info.get("existe"),
                        "severity": info.get("severity"),
                        "error": info.get("error"),
                        "mensaje": info.get("mensaje"),
                        "mba3": info.get("mba3"),
                        "sugerencias_sap": info.get("sugerencias_sap", []),
                        "pack_excel": next(
                            (ip.get("pack") for ip in codigo_a_info_productos.get(codigo, []) if ip.get("pack")),
                            None
                        ),
                        "pvp_excel": next(
                            (ip.get("pvp") for ip in codigo_a_info_productos.get(codigo, []) if ip.get("pvp")),
                            None
                        ),
                    }
                    for codigo, info in detalle_validacion.items()
                }
            }
            partes_mensaje.append("códigos de producto no válidos en SAP")

        if pack_pvp_exc is not None:
            data.update(pack_pvp_exc.data)
            validacion_pack_pvp = pack_pvp_exc.data["validacion_pack_pvp"]
            total_pack_pvp = len(validacion_pack_pvp["pack_mismatches"]) + len(validacion_pack_pvp["pvp_mismatches"])
            partes_mensaje.append(f"{total_pack_pvp} discrepancia(s) de Pack/PVP contra SAP")

        message = "Existen " + " y ".join(partes_mensaje)
        error_code = "PRODUCTOS_NO_VALIDOS_SAP" if codigo_invalido else "PACK_PVP_INVALIDOS_SAP"
        raise BusinessException(message=message, error_code=error_code, data=data)

    @staticmethod
    def _valores_numericos_difieren(valor_excel: Any, valor_sap: Any, tolerancia: float = 0.01) -> bool:
        """Compara dos valores monetarios redondeados a 2 decimales, con tolerancia por redondeo."""
        try:
            return abs(round(float(valor_excel), 2) - round(float(valor_sap), 2)) > tolerancia
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _agrupar_info_productos_por_codigo(
        datos_parsing: List[Dict],
        correcciones_codigos: Optional[Dict[str, str]]
    ) -> Dict[str, List[Dict]]:
        """Agrupa los info_producto del parsing por código (aplicando correcciones de código si existen)."""
        codigo_a_info_productos: Dict[str, List[Dict]] = {}
        for item in datos_parsing:
            codigo = item.get("codigoProducto")
            if not codigo:
                continue
            if correcciones_codigos and codigo in correcciones_codigos:
                codigo = correcciones_codigos[codigo]
            info_producto = item.get("info_producto")
            if info_producto is not None:
                codigo_a_info_productos.setdefault(codigo, []).append(info_producto)
        return codigo_a_info_productos

    @staticmethod
    def _aplicar_correccion_campo(
        info_productos: List[Dict],
        campo: str,
        valor_corregido: Any
    ) -> None:
        for info_producto in info_productos:
            info_producto[campo] = valor_corregido

    def _evaluar_pack_producto(
        self,
        codigo: str,
        info_productos: List[Dict],
        sap_info: Dict[str, Any],
        correccion: Dict[str, Any],
        mismatches_pack: List[Dict[str, Any]]
    ) -> None:
        pack_sap = sap_info.get("pack_sap")
        if "pack" in correccion:
            self._aplicar_correccion_campo(info_productos, "pack", correccion["pack"])
            return
        pack_excel = next((ip.get("pack") for ip in info_productos if ip.get("pack")), None)
        if pack_excel and pack_sap and pack_excel.strip().upper() != pack_sap.strip().upper():
            mismatches_pack.append({"codigo": codigo, "pack_excel": pack_excel, "pack_sap": pack_sap})

    def _evaluar_pvp_producto(
        self,
        codigo: str,
        info_productos: List[Dict],
        sap_info: Dict[str, Any],
        correccion: Dict[str, Any],
        mismatches_pvp: List[Dict[str, Any]]
    ) -> None:
        pvp_sap = sap_info.get("pvp_sap")
        if "pvp" in correccion:
            self._aplicar_correccion_campo(info_productos, "pvp", correccion["pvp"])
            return
        pvp_excel = next((ip.get("pvp") for ip in info_productos if ip.get("pvp")), None)
        if pvp_excel and pvp_sap and self._valores_numericos_difieren(pvp_excel, pvp_sap):
            mismatches_pvp.append({
                "codigo": codigo,
                "pvp_excel": float(pvp_excel),
                "pvp_sap": float(pvp_sap)
            })

    def _validar_pack_pvp_temprana(
        self,
        datos_parsing: List[Dict],
        correcciones_codigos: Optional[Dict[str, str]],
        validacion_sap_productos: Optional[Dict[str, Any]],
        correcciones_pack_pvp: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> None:
        """
        Valida Pack y PVP contra SAP (obligatorio por RN-02): bloquea la carga si difieren,
        a menos que `correcciones_pack_pvp` ya traiga el valor elegido por el usuario
        (re-intento tras elegir "usar SAP" o "usar Excel" en pantalla) para ese código/campo.

        También sincroniza codigo_barras/descripcion_sap desde SAP (fuente de verdad; el
        Excel es solo referencia visual para el usuario, esos dos campos no se validan).
        """
        if not validacion_sap_productos:
            return
        detalle = validacion_sap_productos.get("detalle", {})
        codigo_a_info_productos = self._agrupar_info_productos_por_codigo(datos_parsing, correcciones_codigos)

        mismatches_pack: List[Dict[str, Any]] = []
        mismatches_pvp: List[Dict[str, Any]] = []

        for codigo, info_productos in codigo_a_info_productos.items():
            sap_info = detalle.get(codigo, {}).get("info")
            if not sap_info:
                continue

            for info_producto in info_productos:
                if sap_info.get("codigo_barras"):
                    info_producto["codigo_barras"] = sap_info["codigo_barras"]
                if sap_info.get("item_name"):
                    info_producto["descripcion_sap"] = sap_info["item_name"]

            correccion = (correcciones_pack_pvp or {}).get(codigo, {})
            self._evaluar_pack_producto(codigo, info_productos, sap_info, correccion, mismatches_pack)
            self._evaluar_pvp_producto(codigo, info_productos, sap_info, correccion, mismatches_pvp)

        if mismatches_pack or mismatches_pvp:
            self._raise_pack_pvp_invalidos(mismatches_pack, mismatches_pvp)

    @staticmethod
    def _raise_pack_pvp_invalidos(mismatches_pack: List[Dict[str, Any]], mismatches_pvp: List[Dict[str, Any]]) -> None:
        total = len(mismatches_pack) + len(mismatches_pvp)
        logger.error(
            f"❌ Validación Pack/PVP contra SAP falló: {len(mismatches_pack)} Pack, {len(mismatches_pvp)} PVP"
        )
        mensajes = [
            f"El Pack '{m['pack_excel']}' del Excel no coincide con el Pack registrado en SAP "
            f"para '{m['codigo']}' ('{m['pack_sap']}'). Use '{m['pack_sap']}'."
            for m in mismatches_pack
        ] + [
            f"El PVP '{m['pvp_excel']:.2f}' del Excel no coincide con el PVP registrado en SAP "
            f"(Precio Minorista) para '{m['codigo']}' ('{m['pvp_sap']:.2f}'). Use '{m['pvp_sap']:.2f}'."
            for m in mismatches_pvp
        ]
        raise BusinessException(
            message=f"Existen {total} discrepancia(s) de Pack/PVP contra SAP",
            error_code="PACK_PVP_INVALIDOS_SAP",
            data={
                "validacion_pack_pvp": {
                    "pack_mismatches": mismatches_pack,
                    "pvp_mismatches": mismatches_pvp,
                    "mensajes": mensajes,
                }
            }
        )

    def _agrupar_datos_en_detalles(
        self,
        datos_parsing: List[Dict],
        correcciones_codigos: Optional[Dict[str, str]]
    ) -> List[Dict]:
        productos_agrupados: Dict = {}
        for item in datos_parsing:
            codigo_producto = item.get("codigoProducto")
            if not codigo_producto:
                continue
            if correcciones_codigos and codigo_producto in correcciones_codigos:
                codigo_producto = correcciones_codigos[codigo_producto]
                item["codigoProducto"] = codigo_producto
            info_producto = item.get("info_producto", {})
            if codigo_producto not in productos_agrupados:
                productos_agrupados[codigo_producto] = {
                    "detalle": {
                        "codigo_interno": codigo_producto,
                        "marca": info_producto.get("marca"),
                        "codigo_barras": info_producto.get("codigo_barras"),
                        "descripcion_sap": info_producto.get("descripcion_sap"),
                        "pack": info_producto.get("pack"),
                        "costo_doc_sin_iva": info_producto.get("costo_doc_sin_iva"),
                        "costo_margen": info_producto.get("costo_margen"),
                        "costo_unitario": info_producto.get("costo_unitario"),
                        "descuento_1": info_producto.get("descuento_1"),
                        "pvp": info_producto.get("pvp"),
                        "subtotal": info_producto.get("subtotal"),
                        "total": info_producto.get("total")
                    },
                    "distribuciones": []
                }
            productos_agrupados[codigo_producto]["distribuciones"].append({
                "tienda_codigo": item.get("idTienda"),
                "tienda_nombre": item.get("nombreTienda"),
                "cantidad": item.get("cantidad"),
                "fila_origen": item.get("filaOrigen"),
                "es_bodega": item.get("es_bodega", False)
            })
        return list(productos_agrupados.values())

    def _procesar_formato_nuevo_v1_0(
        self,
        file_content: bytes,
        hoja_cabecera: str,
        hoja_detalle: str,
        filename: str,
        usuario_id: Optional[str],
        validar_sap: bool,
        correcciones_codigos: Optional[Dict[str, str]],
        correcciones_pack_pvp: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> tuple:
        logger.info("📋 Formato DOS HOJAS NUEVO v1.0 detectado: 'cabecera' + 'detalle' (con bodegas centrales)")
        resultado_parsing = self.parser.parsear_excel_pedido(
            file_content=file_content,
            hoja_cabecera=hoja_cabecera,
            hoja_detalle=hoja_detalle
        )
        cabecera_parseada = resultado_parsing.get("cabecera", {})
        self._validar_numero_pedido_duplicado(cabecera_parseada)
        datos_parsing = resultado_parsing.get("data", [])
        if validar_sap and datos_parsing:
            self._validar_sap_codigo_y_pack_pvp(datos_parsing, correcciones_codigos, correcciones_pack_pvp)
        cabecera = self._normalizar_cabecera_para_bd(
            resultado_parsing.get("cabecera", {}), filename, usuario_id
        )
        detalles_con_tiendas = self._agrupar_datos_en_detalles(datos_parsing, correcciones_codigos)
        if not detalles_con_tiendas:
            raise BusinessException(
                message="El archivo Excel está vacío o no contiene datos válidos",
                error_code="ARCHIVO_SIN_DATOS",
                data={
                    "formato_detectado": "dos_hojas_nuevo_v1_0",
                    "mensaje_detallado": "No se encontraron productos con distribuciones válidas en las hojas 'cabecera' y 'detalle'",
                    "validacion": {
                        "datos_archivo": {
                            "valido": False,
                            "mensaje": "El archivo debe contener al menos un producto con cantidades para tiendas o bodegas"
                        }
                    }
                }
            )
        return cabecera, detalles_con_tiendas

    @staticmethod
    def _recolectar_codigos_tiendas_bodegas(
        cabecera: Dict[str, Any],
        detalles_con_tiendas: List[Dict]
    ) -> tuple:
        """Separa los códigos de tiendas y bodegas presentes en los detalles y la cabecera."""
        codigos_tiendas_set: set = set()
        codigos_bodegas_set: set = set()
        for detalle_item in detalles_con_tiendas:
            if not isinstance(detalle_item, dict):
                continue
            for dist in detalle_item.get("distribuciones", []):
                tienda_codigo = dist.get("tienda_codigo")
                if not tienda_codigo:
                    continue
                if dist.get("es_bodega", False):
                    codigos_bodegas_set.add(tienda_codigo.strip())
                else:
                    codigos_tiendas_set.add(tienda_codigo)
        origen_traslado = cabecera.get("origen_traslado")
        if origen_traslado and origen_traslado.strip():
            codigos_bodegas_set.add(origen_traslado.strip())
        return codigos_tiendas_set, codigos_bodegas_set

    def _validar_tiendas_sap_primero(self, codigos_tiendas_set: set, resultado: Dict[str, Any]) -> None:
        """Valida los códigos de tienda contra SAP y lanza BusinessException si hay inválidos."""
        logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_tiendas_set)} códigos de tienda contra SAP")
        validacion_tiendas_sap = self.sap_validator_helper.validar_tiendas_sap(
            codigos_tiendas=list(codigos_tiendas_set),
            resultado=resultado,
            sap_obligatorio=True
        )
        if validacion_tiendas_sap.get("todas_validas", False):
            return
        no_encontradas = self._norm_list(validacion_tiendas_sap.get("no_encontradas", []))
        errores_sap = self._norm_list(validacion_tiendas_sap.get("errores", []))
        validas = self._norm_list(validacion_tiendas_sap.get("validas", []))
        log_detalle = self._construir_log_detalle_sap("Tiendas", no_encontradas, errores_sap)
        logger.error(f"❌ Validación SAP tiendas falló: {log_detalle}")
        raise BusinessException(
            message="Existen códigos de tienda/bodega no válidos en SAP",
            error_code="TIENDAS_NO_VALIDAS_SAP",
            data={
                "validacion": {
                    "tiendas": {
                        "no_encontradas": no_encontradas,
                        "errores": errores_sap,
                        "validas": validas,
                        "total_validas": len(validas),
                        "total_invalidas": len(no_encontradas) + len(errores_sap)
                    }
                },
                "validacion_sap": {
                    "validas": validas,
                    "no_encontradas": no_encontradas,
                    "errores": errores_sap,
                    "warnings": validacion_tiendas_sap.get("warnings", []),
                    "total_codigos": len(codigos_tiendas_set),
                    "todas_validas": False,
                    "fuente": "ID TIENDA"
                }
            }
        )

    def _validar_bodegas_sap_primero(self, validator: Any, codigos_bodegas_set: set) -> None:
        """Valida los códigos de bodega contra SAP y lanza BusinessException si hay inválidos."""
        logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_bodegas_set)} códigos de bodega contra SAP")
        validacion_bodegas_sap = validator.validar_bodegas_existen_en_sap(
            codigos_bodegas=list(codigos_bodegas_set),
            sap_obligatorio=True
        )
        if validacion_bodegas_sap.get("todas_validas", False):
            return
        no_encontradas = self._norm_list(validacion_bodegas_sap.get("no_encontradas", []))
        errores = self._norm_list(validacion_bodegas_sap.get("errores", []))
        validas = self._norm_list(validacion_bodegas_sap.get("validas", []))
        log_detalle = self._construir_log_detalle_sap("Bodegas", no_encontradas, errores)
        logger.error(f"❌ Validación SAP bodegas falló: {log_detalle}")
        raise BusinessException(
            message="Existen códigos de bodega no válidos en SAP",
            error_code="BODEGAS_NO_VALIDAS_SAP",
            data={
                "validacion": {
                    "bodegas": {
                        "no_encontradas": no_encontradas,
                        "errores": errores,
                        "validas": validas,
                        "total_validas": len(validas),
                        "total_invalidas": len(no_encontradas) + len(errores)
                    }
                }
            }
        )

    def _validar_tiendas_bodegas_sap(
        self,
        cabecera: Dict[str, Any],
        detalles_con_tiendas: List[Dict],
        resultado: Dict[str, Any]
    ) -> None:
        validator = PedidoValidator()
        codigos_tiendas_set, codigos_bodegas_set = self._recolectar_codigos_tiendas_bodegas(
            cabecera, detalles_con_tiendas
        )
        if codigos_tiendas_set:
            self._validar_tiendas_sap_primero(codigos_tiendas_set, resultado)
        if codigos_bodegas_set:
            self._validar_bodegas_sap_primero(validator, codigos_bodegas_set)

    def _ejecutar_validacion_pedido(
        self,
        cabecera: Dict[str, Any],
        detalles_con_tiendas: List[Dict],
        resultado: Dict[str, Any],
        tiendas_permitidas: Optional[List[str]],
        bloquea_con_errores: bool,
        filename: str
    ) -> None:
        validator = PedidoValidator(
            tiendas_permitidas=tiendas_permitidas,
            **DEFAULT_PEDIDO_VALIDATOR_KWARGS
        )
        validation_result = validator.validar_pedido_completo(
            cabecera,
            detalles_con_tiendas,
            es_formato_simple=False
        )
        resultado["validation"] = {
            "valid": validation_result["valid"],
            "total_issues": validation_result["total_issues"],
            "errors": validation_result["errors"],
            "warnings": validation_result["warnings"],
            "issues_by_row": {
                str(row_num): [
                    {
                        "field": issue.field,
                        "severity": issue.severity.value,
                        "message": issue.message,
                        "value": str(issue.value) if issue.value is not None else None
                    }
                    for issue in issues
                ]
                for row_num, issues in validation_result["issues_by_row"].items()
            }
        }
        if not validation_result["valid"] and bloquea_con_errores:
            resultado["status"] = "validation_error"
            resultado["errores"].append(
                f"Validación fallida: {validation_result['errors']} error(es) crítico(s) encontrado(s)"
            )
            logger.warning(
                f"⚠️ Validación fallida para {filename}: "
                f"{validation_result['errors']} error(es), {validation_result['warnings']} advertencia(s). Se persistirá igual para mantener datos."
            )

    def _preparar_validacion_sap_persistencia(
        self,
        detalles_con_tiendas: List[Dict],
        resultado: Dict[str, Any]
    ) -> Optional[Any]:
        codigos_productos = list(set([
            det.get("detalle", {}).get("codigo_interno")
            for det in detalles_con_tiendas
            if det.get("detalle", {}).get("codigo_interno")
        ]))
        if not codigos_productos:
            return None
        return self.sap_validator_helper.validar_productos_sap(
            codigos_productos=codigos_productos,
            resultado=resultado,
            usar_cache=True,
            sap_obligatorio=True
        )

    def crear_pedido_manual(
        self,
        datos_pedido: Dict[str, Any],
        usuario_id: Optional[str] = None,
        validar_productos: bool = True,
        validar_tiendas: bool = True,
        audit_context: Optional["AuditContext"] = None,
    ) -> Dict[str, Any]:
        """
        Crea un pedido manualmente desde datos JSON (HU-01 - Carga por Pantalla).

        Args:
            datos_pedido: Diccionario con datos del pedido (del request JSON)
            usuario_id: ID del usuario que crea el pedido
            validar_productos: Si True, valida que productos existan
            validar_tiendas: Si True, valida que tiendas existan y estén activas

        Returns:
            Dict con resultado completo incluyendo validaciones y consolidación
        """
        if not ENABLE_SQL_SERVER_STORAGE:
            return {"status": "error", "message": _MSG_STORAGE_DESHABILITADO}

        resultado = {
            "status": "success",
            "pedido_id": None,
            "estado": None,
            "validacion": {
                "productos": {"validos": [], "no_encontrados": [], "todos_validos": False},
                "tiendas": {"validas": [], "no_encontradas": [], "inactivas": [], "todas_validas": False},
                "cantidades": {}
            },
            "consolidacion": {"total_productos": 0, "cantidad_total": 0},
            "articulos_cargados": 0,
            "distribuciones_cargadas": 0,
            "errores": []
        }

        try:
            cabecera = self._construir_cabecera_manual(datos_pedido, usuario_id)
            articulos = datos_pedido.get("articulos", [])
            if not articulos:
                resultado["status"] = "error"
                resultado["errores"].append("No se encontraron artículos")
                return resultado
            detalles_con_tiendas = self._construir_detalles_desde_articulos(articulos)
            detalles_con_tiendas = self._enriquecer_detalles_con_sap(detalles_con_tiendas)
            if self._es_numero_pedido_duplicado_manual(cabecera, resultado):
                return resultado
            with get_db_connection_context() as conn:
                if self._validar_todo_manual(conn, cabecera, detalles_con_tiendas, validar_productos, validar_tiendas, resultado):
                    return resultado
                consolidacion = self.consolidator.consolidar_pedido_por_producto(detalles_con_tiendas)
                resultado["consolidacion"] = consolidacion["resumen"]
                self._insertar_pedido_manual(conn, cabecera, detalles_con_tiendas, resultado, audit_context)
            logger.info(f"✅ Pedido manual creado: {resultado['pedido_id']} - {cabecera.get('numero_pedido')}")
            return resultado

        except ValueError as e:
            error_msg = str(e)
            if _PATRON_NUM_PEDIDO in error_msg.lower() and _PATRON_YA_EXISTE in error_msg.lower():
                numero_pedido = cabecera.get("numero_pedido")
                logger.warning(f"⚠️ Intento de crear pedido con número duplicado: {numero_pedido}")
                resultado["status"] = "error"
                resultado["errores"].append(f"El número de pedido '{numero_pedido}' ya existe en el sistema")
                resultado["error_tipo"] = "numero_pedido_duplicado"
                resultado["validacion_numero_pedido"] = {
                    "numero_pedido": numero_pedido,
                    "duplicado": True,
                    "mensaje": f"El número de pedido '{numero_pedido}' ya fue utilizado anteriormente"
                }
                return resultado
            logger.error(f"❌ Error de validación al crear pedido manual: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
        except Exception as e:
            logger.error(f"❌ Error al crear pedido manual: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado

    def _construir_cabecera_manual(self, datos_pedido: Dict[str, Any], usuario_id: Optional[str]) -> Dict[str, Any]:
        return {
            "numero_pedido": datos_pedido.get("numero_pedido"),
            "fecha_pedido": datos_pedido.get("fecha_pedido"),
            "fecha_entrega": datos_pedido.get("fecha_entrega"),
            "forma_pago": datos_pedido.get("forma_pago"),
            "mensaje": datos_pedido.get("mensaje"),
            "proveedor_nombre": datos_pedido.get("proveedor_nombre"),
            "comprador_nombre": datos_pedido.get("comprador_nombre"),
            "comprador_codigo": datos_pedido.get("comprador_codigo"),
            "origen_traslado": datos_pedido.get("origen_traslado"),
            "serie": datos_pedido.get("serie"),
            "archivo_nombre": "CREACION_MANUAL",
            "creado_por": usuario_id,
            "estado_id": 1
        }

    def _construir_detalles_desde_articulos(self, articulos: List[Dict]) -> List[Dict]:
        detalles_con_tiendas = []
        for articulo in articulos:
            detalle = {
                "codigo_interno": articulo.get("codigo_interno"),
                "descripcion_sap": articulo.get("descripcion_sap"),
                "marca": articulo.get("marca"),
                "codigo_barras": articulo.get("codigo_barras"),
                "pack": articulo.get("pack"),
                "costo_doc_sin_iva": articulo.get("costo_doc_sin_iva"),
                "descuento_1": articulo.get("descuento_1"),
                "pvp": articulo.get("pvp"),
                "subtotal": articulo.get("subtotal"),
                "total": articulo.get("total"),
                "comentario": articulo.get("comentario")
            }
            logger.debug(
                f"📦 Mapeando artículo: codigo_interno={detalle['codigo_interno']}, "
                f"descripcion_sap={detalle.get('descripcion_sap')}, "
                f"marca={detalle.get('marca')}, "
                f"costo_doc_sin_iva={detalle.get('costo_doc_sin_iva')}, "
                f"pvp={detalle.get('pvp')}, "
                f"comentario={detalle.get('comentario')}"
            )
            distribuciones = []
            for dist in articulo.get("distribuciones", []):
                distribuciones.append({
                    "tienda_codigo": dist.get("tienda_codigo"),
                    "tienda_nombre": dist.get("tienda_nombre"),
                    "cantidad": dist.get("cantidad")
                })
            detalles_con_tiendas.append({"detalle": detalle, "distribuciones": distribuciones})
        return detalles_con_tiendas

    def _es_numero_pedido_duplicado_manual(self, cabecera: Dict[str, Any], resultado: Dict[str, Any]) -> bool:
        numero_pedido = cabecera.get("numero_pedido")
        if not numero_pedido:
            return False
        with get_db_connection_context() as conn_check:
            repo_check = PedidoRepository(conn_check)
            if repo_check.existe_numero_pedido(numero_pedido):
                logger.warning(f"⚠️ [VALIDACIÓN TEMPRANA - MANUAL] Número de pedido duplicado detectado: '{numero_pedido}'")
                resultado["status"] = "error"
                resultado["errores"].append(f"El número de pedido '{numero_pedido}' ya existe en el sistema")
                resultado["error_tipo"] = "numero_pedido_duplicado"
                resultado["validacion_numero_pedido"] = {
                    "numero_pedido": numero_pedido,
                    "duplicado": True,
                    "mensaje": f"El número de pedido '{numero_pedido}' ya fue utilizado anteriormente"
                }
                return True
            else:
                logger.info(f"✅ [VALIDACIÓN TEMPRANA - MANUAL] Número de pedido '{numero_pedido}' disponible")
                return False

    def _validar_todo_manual(
        self,
        conn: Any,
        cabecera: Dict[str, Any],
        detalles_con_tiendas: List[Dict],
        validar_productos: bool,
        validar_tiendas: bool,
        resultado: Dict[str, Any]
    ) -> bool:
        validator = PedidoValidator()
        codigos_productos = list(set([
            det.get("detalle", {}).get("codigo_interno")
            for det in detalles_con_tiendas
            if det.get("detalle", {}).get("codigo_interno")
        ]))
        codigos_tiendas = list(set([
            dist.get("tienda_codigo")
            for det in detalles_con_tiendas
            for dist in det.get("distribuciones", [])
            if dist.get("tienda_codigo")
        ]))
        codigos_bodegas = self._extraer_codigos_bodegas_manual(cabecera, detalles_con_tiendas)
        if codigos_productos and self._validar_productos_sap_manual(codigos_productos, resultado):
            return True
        if codigos_tiendas and self._validar_tiendas_sap_manual(codigos_tiendas, resultado):
            return True
        if codigos_bodegas and self._validar_bodegas_sap_manual(codigos_bodegas, validator, resultado):
            return True
        if validar_productos and codigos_productos:
            resultado["validacion"]["productos"] = validator.validar_productos_existen(codigos_productos, conn)
        if validar_tiendas and codigos_tiendas:
            resultado["validacion"]["tiendas"] = validator.validar_tiendas_existen(codigos_tiendas, conn)
        validacion_cantidades = validator.validar_pedido_completo(cabecera, detalles_con_tiendas, es_formato_simple=False)
        resultado["validacion"]["cantidades"] = {
            "valid": validacion_cantidades["valid"],
            "errors": validacion_cantidades["errors"],
            "warnings": validacion_cantidades["warnings"],
            "total_issues": validacion_cantidades["total_issues"]
        }
        if not validacion_cantidades["valid"]:
            resultado["status"] = "validation_error"
            return True
        if resultado.get("errores") and len(resultado["errores"]) > 0:
            resultado["status"] = "validation_error"
            logger.warning(f"⚠️ Errores de validación detectados: {resultado['errores']}. No se creará el pedido.")
            return True
        return False

    def _extraer_codigos_bodegas_manual(
        self,
        cabecera: Dict[str, Any],
        detalles_con_tiendas: List[Dict]
    ) -> List[str]:
        codigos_bodegas_set: set = set()
        for det in detalles_con_tiendas:
            for dist in det.get("distribuciones", []):
                if dist.get("es_bodega", False):
                    tienda_codigo = dist.get("tienda_codigo")
                    if tienda_codigo:
                        codigos_bodegas_set.add(tienda_codigo.strip())
        origen_traslado = cabecera.get("origen_traslado")
        if origen_traslado and origen_traslado.strip():
            codigos_bodegas_set.add(origen_traslado.strip())
        return list(codigos_bodegas_set)

    def _validar_productos_sap_manual(self, codigos_productos: List[str], resultado: Dict[str, Any]) -> bool:
        logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_productos)} códigos de producto contra SAP")
        validacion_sap_productos = self.sap_validator_helper.validar_productos_sap(
            codigos_productos=codigos_productos,
            resultado=resultado,
            usar_cache=True,
            sap_obligatorio=True
        )
        if validacion_sap_productos is None or not validacion_sap_productos.get("todos_validos", False):
            no_encontrados = self._norm_list((validacion_sap_productos or {}).get("no_encontrados", []))
            errores = self._norm_list((validacion_sap_productos or {}).get("errores", []))
            log_detalle = self._construir_log_detalle_sap("Productos", no_encontrados, errores)
            logger.warning(f"⚠️ Validación SAP productos falló: {log_detalle}")
            resultado["status"] = "validation_error"
            resultado["errores"].append("Existen códigos de producto no válidos en SAP")
            resultado["validacion"]["productos"] = {
                "no_encontrados": no_encontrados,
                "errores": errores,
                "validos": (validacion_sap_productos or {}).get("validos", [])
            }
            return True
        resultado["validacion"]["productos_sap"] = {
            "validos": validacion_sap_productos.get("validos", []),
            "no_encontrados": validacion_sap_productos.get("no_encontrados", []),
            "errores": validacion_sap_productos.get("errores", []),
            "todos_validos": validacion_sap_productos.get("todos_validos", False)
        }
        return False

    def _validar_tiendas_sap_manual(self, codigos_tiendas: List[str], resultado: Dict[str, Any]) -> bool:
        logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_tiendas)} códigos de tienda contra SAP")
        validacion_tiendas_sap = self.sap_validator_helper.validar_tiendas_sap(
            codigos_tiendas=codigos_tiendas,
            resultado=resultado,
            sap_obligatorio=True
        )
        if not validacion_tiendas_sap.get("todas_validas", False):
            no_encontradas = (validacion_tiendas_sap or {}).get("no_encontradas", [])
            errores_sap = (validacion_tiendas_sap or {}).get("errores", [])
            if isinstance(no_encontradas, int):
                no_encontradas = []
            if isinstance(errores_sap, int):
                errores_sap = []
            log_detalle = f"Tiendas no encontradas ({len(no_encontradas)}): {', '.join(no_encontradas[:10])}"
            if len(no_encontradas) > 10:
                log_detalle += f" y {len(no_encontradas) - 10} más"
            if errores_sap:
                log_detalle += f" | Errores ({len(errores_sap)}): {', '.join(errores_sap[:5])}"
                if len(errores_sap) > 5:
                    log_detalle += f" y {len(errores_sap) - 5} más"
            logger.warning(f"⚠️ Validación SAP tiendas falló: {log_detalle}")
            resultado["status"] = "validation_error"
            resultado["errores"].append("Existen códigos de tienda/bodega no válidos en SAP")
            resultado["validacion"]["tiendas"] = {
                "no_encontradas": no_encontradas,
                "errores": errores_sap,
                "validas": validacion_tiendas_sap.get("validas", [])
            }
            return True
        resultado["validacion"]["tiendas_sap"] = {
            "validas": validacion_tiendas_sap.get("validas", []),
            "no_encontradas": validacion_tiendas_sap.get("no_encontradas", []),
            "errores": validacion_tiendas_sap.get("errores", []),
            "todas_validas": validacion_tiendas_sap.get("todas_validas", False)
        }
        return False

    def _validar_bodegas_sap_manual(
        self,
        codigos_bodegas: List[str],
        validator: Any,
        resultado: Dict[str, Any]
    ) -> bool:
        logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_bodegas)} códigos de bodega contra SAP")
        validacion_bodegas_sap = validator.validar_bodegas_existen_en_sap(
            codigos_bodegas=codigos_bodegas,
            sap_obligatorio=True
        )
        if not validacion_bodegas_sap.get("todas_validas", False):
            no_encontradas = (validacion_bodegas_sap or {}).get("no_encontradas", [])
            errores = (validacion_bodegas_sap or {}).get("errores", [])
            if isinstance(no_encontradas, int):
                no_encontradas = []
            if isinstance(errores, int):
                errores = []
            log_detalle = f"Bodegas no encontradas ({len(no_encontradas)}): {', '.join(no_encontradas[:10])}"
            if len(no_encontradas) > 10:
                log_detalle += f" y {len(no_encontradas) - 10} más"
            if errores:
                log_detalle += f" | Errores ({len(errores)}): {', '.join(errores[:5])}"
                if len(errores) > 5:
                    log_detalle += f" y {len(errores) - 5} más"
            logger.warning(f"⚠️ Validación SAP bodegas falló: {log_detalle}")
            resultado["status"] = "validation_error"
            resultado["errores"].append("Existen códigos de bodega no válidos en SAP")
            resultado["validacion"]["bodegas"] = {
                "no_encontradas": no_encontradas,
                "errores": errores,
                "validas": validacion_bodegas_sap.get("validas", [])
            }
            return True
        resultado["validacion"]["bodegas_sap"] = {
            "validas": validacion_bodegas_sap.get("validas", []),
            "no_encontradas": validacion_bodegas_sap.get("no_encontradas", []),
            "errores": validacion_bodegas_sap.get("errores", []),
            "todas_validas": validacion_bodegas_sap.get("todas_validas", False)
        }
        return False

    def _insertar_pedido_manual(
        self,
        conn: Any,
        cabecera: Dict[str, Any],
        detalles_con_tiendas: List[Dict],
        resultado: Dict[str, Any],
        audit_context: Optional["AuditContext"]
    ) -> None:
        from src.utils.audit_context import ensure_audit_context
        audit = ensure_audit_context(audit_context)
        repository = PedidoRepository(conn)
        pedido_id = repository.insert_cabecera(cabecera, audit_context=audit)
        resultado["pedido_id"] = pedido_id
        resultado["numero_pedido"] = cabecera.get("numero_pedido")
        resultado["estado_id"] = 1
        resultado["estado_nombre"] = "BORRADOR"
        resultado["estado"] = "BORRADOR"
        for orden_linea, detalle_data in enumerate(detalles_con_tiendas):
            self._insertar_un_detalle_manual(repository, pedido_id, orden_linea, detalle_data, resultado, audit)

    def _insertar_un_detalle_manual(
        self,
        repository: Any,
        pedido_id: Any,
        orden_linea: int,
        detalle_data: Dict,
        resultado: Dict[str, Any],
        audit: Any
    ) -> None:
        try:
            detalle_data["detalle"]["orden_linea"] = orden_linea
            pedido_detalle_id = repository.insert_detalle(pedido_id, detalle_data["detalle"], audit_context=audit)
            resultado["articulos_cargados"] += 1
            if detalle_data.get("distribuciones"):
                distribuciones = self._construir_distribuciones_manual_lista(
                    repository, detalle_data["distribuciones"]
                )
                if distribuciones:
                    resultado["distribuciones_cargadas"] += repository.insert_detalle_tiendas(
                        pedido_detalle_id, distribuciones, audit_context=audit
                    )
        except Exception as e:
            logger.warning(f"⚠️ Error procesando artículo: {e}")
            resultado["errores"].append(str(e))

    def _construir_distribuciones_manual_lista(self, repository: Any, distribuciones_raw: List[Dict]) -> List[Dict]:
        distribuciones = []
        for dist in distribuciones_raw:
            tienda_codigo = dist.get("tienda_codigo")
            cantidad = dist.get("cantidad")
            if tienda_codigo and cantidad is not None and cantidad >= 0:
                tienda_id = repository.get_or_create_tienda(
                    codigo=tienda_codigo,
                    nombre=dist.get("tienda_nombre")
                )
                distribuciones.append({
                    "tienda_id": tienda_id,
                    "cantidad": float(cantidad),
                    "es_bodega": dist.get("es_bodega", False)
                })
        return distribuciones

    def _persistir_pedido(
        self,
        cabecera: Dict[str, Any],
        detalles_con_tiendas: List[Dict[str, Any]],
        resultado: Dict[str, Any],
        validar_sap: bool,
        validacion_sap: Optional[Dict[str, Any]]
    ) -> None:
        """
        Persiste un pedido en la base de datos.

        Args:
            cabecera: Datos de cabecera del pedido
            detalles_con_tiendas: Lista de detalles con distribuciones
            resultado: Dict de resultado donde se actualizará el estado
            validar_sap: Si True, filtra productos no validados en SAP
            validacion_sap: Resultado de validación SAP (opcional)
        """
        with get_db_connection_context() as conn:
            repository = PedidoRepository(conn)
            pedido_id = self._insertar_cabecera_verificando_duplicado(repository, cabecera)
            resultado["pedido_id"] = pedido_id
            resultado["numero_pedido"] = cabecera.get("numero_pedido")
            codigos_validos_sap, info_sap_por_codigo = self._construir_info_sap_por_codigo(validacion_sap)
            for orden_linea, detalle_data in enumerate(detalles_con_tiendas):
                detalle_data["detalle"]["orden_linea"] = orden_linea
                codigo_interno = detalle_data.get("detalle", {}).get("codigo_interno")
                if self._debe_omitir_detalle_sap(validar_sap, validacion_sap, codigo_interno, codigos_validos_sap):
                    logger.warning(
                        f"⚠️ Producto '{codigo_interno}' no validado en SAP, "
                        f"no se persistirá en pedido_detalle"
                    )
                    resultado["errores"].append(f"Producto '{codigo_interno}' omitido: no válido en SAP")
                    continue
                self._persistir_un_detalle(repository, pedido_id, detalle_data, codigo_interno, info_sap_por_codigo, resultado)

    def _insertar_cabecera_verificando_duplicado(self, repository: Any, cabecera: Dict[str, Any]) -> Any:
        try:
            return repository.insert_cabecera(cabecera)
        except ValueError as e:
            error_msg = str(e)
            if _PATRON_NUM_PEDIDO in error_msg.lower() and _PATRON_YA_EXISTE in error_msg.lower():
                numero_pedido = cabecera.get("numero_pedido")
                logger.warning(f"⚠️ Intento de crear pedido con número duplicado: {numero_pedido}")
                raise BusinessException(
                    message=f"El número de pedido '{numero_pedido}' ya existe en el sistema",
                    error_code="NUMERO_PEDIDO_DUPLICADO",
                    data={
                        "numero_pedido": numero_pedido,
                        "validacion": {
                            "numero_pedido": {
                                "duplicado": True,
                                "mensaje": f"El número de pedido '{numero_pedido}' ya fue utilizado anteriormente"
                            }
                        }
                    }
                )
            raise

    def _construir_info_sap_por_codigo(self, validacion_sap: Optional[Dict[str, Any]]) -> tuple:
        codigos_validos_sap: set = set()
        info_sap_por_codigo: Dict = {}
        if not validacion_sap:
            return codigos_validos_sap, info_sap_por_codigo
        codigos_validos_sap = set(validacion_sap.get("validos", []))
        for codigo, detalle in validacion_sap.get("detalle", {}).items():
            if detalle.get("existe") and detalle.get("info"):
                info_sap_por_codigo[codigo] = detalle["info"]
        return codigos_validos_sap, info_sap_por_codigo

    def _debe_omitir_detalle_sap(
        self,
        validar_sap: bool,
        validacion_sap: Optional[Dict[str, Any]],
        codigo_interno: Optional[str],
        codigos_validos_sap: set
    ) -> bool:
        if not (validar_sap and validacion_sap):
            return False
        return not codigo_interno or codigo_interno not in codigos_validos_sap

    def _enriquecer_detalle_con_sap_info(
        self,
        datos_detalle: Dict[str, Any],
        codigo_interno: Optional[str],
        info_sap_por_codigo: Dict
    ) -> Dict[str, Any]:
        if not (codigo_interno and codigo_interno in info_sap_por_codigo):
            return datos_detalle
        info_sap = info_sap_por_codigo[codigo_interno]
        if info_sap.get("item_name") and not datos_detalle.get("descripcion_sap"):
            datos_detalle["descripcion_sap"] = info_sap["item_name"]
        if info_sap.get("pack_sap") and not datos_detalle.get("pack"):
            datos_detalle["pack"] = info_sap["pack_sap"]
        return datos_detalle

    def _persistir_un_detalle(
        self,
        repository: Any,
        pedido_id: Any,
        detalle_data: Dict,
        codigo_interno: Optional[str],
        info_sap_por_codigo: Dict,
        resultado: Dict[str, Any]
    ) -> None:
        try:
            datos_detalle = self._enriquecer_detalle_con_sap_info(
                detalle_data["detalle"].copy(), codigo_interno, info_sap_por_codigo
            )
            pedido_detalle_id = repository.insert_detalle(pedido_id=pedido_id, datos_detalle=datos_detalle)
            resultado["articulos_cargados"] += 1
            if detalle_data.get("distribuciones"):
                distribuciones = self._construir_distribuciones_persistir(
                    repository, detalle_data["distribuciones"], detalle_data
                )
                if distribuciones:
                    resultado["distribuciones_cargadas"] += repository.insert_detalle_tiendas(
                        pedido_detalle_id=pedido_detalle_id,
                        distribuciones=distribuciones
                    )
        except Exception as e:
            error_msg = f"Error al procesar artículo {detalle_data.get('detalle', {}).get('codigo_interno')}: {str(e)}"
            logger.warning(f"⚠️ {error_msg}")
            resultado["errores"].append(error_msg)

    def _construir_distribuciones_persistir(
        self,
        repository: Any,
        distribuciones_raw: List[Dict],
        detalle_data: Dict
    ) -> List[Dict]:
        distribuciones = []
        for dist in distribuciones_raw:
            tienda_codigo = dist.get("tienda_codigo")
            cantidad = dist.get("cantidad")
            fila_origen = dist.get("fila_origen")
            es_bodega = dist.get("es_bodega", False)
            if tienda_codigo and cantidad is not None and cantidad >= 0:
                if es_bodega:
                    logger.info(
                        f"📦 Procesando bodega: {tienda_codigo}, cantidad: {cantidad}, "
                        f"producto: {detalle_data.get('detalle', {}).get('codigo_interno')}"
                    )
                tienda_id = repository.get_or_create_tienda(
                    codigo=tienda_codigo,
                    nombre=dist.get("tienda_nombre")
                )
                distribucion_item = {
                    "tienda_id": tienda_id,
                    "cantidad": float(cantidad),
                    "es_bodega": es_bodega
                }
                if fila_origen is not None:
                    distribucion_item["fila_origen"] = int(fila_origen)
                distribuciones.append(distribucion_item)
        return distribuciones

    def enviar_pedido(self, pedido_id: str, usuario_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Acción de negocio "Enviar": valida que el pedido esté en BORRADOR, intenta enviar correo a EL RAYO
        y cambia el estado a NUEVO_PEDIDO. Si el correo falla (ej. IP en Spamhaus), el pedido se marca
        como enviado igualmente y la respuesta incluye email_enviado=False.

        Raises:
            BusinessException: not_found, estado_no_borrador, sin_detalles
        """
        if not ENABLE_SQL_SERVER_STORAGE:
            raise BusinessException(
                "SQL Server storage está deshabilitado.",
                error_code="storage_disabled"
            )
        with get_db_connection_context() as conn:
            repository = PedidoRepository(conn)
            pedido = repository.get_pedido_completo(pedido_id)
            if not pedido:
                raise BusinessException(
                    "No se encontró el pedido.",
                    error_code="not_found"
                )
            cabecera = pedido.get("cabecera", {})
            estado_id = cabecera.get("estado_id")
            if estado_id != ESTADO_BORRADOR:
                raise BusinessException(
                    "El pedido no se puede enviar en su estado actual.",
                    error_code="estado_no_borrador"
                )
            detalles = pedido.get("detalles", [])
            if not detalles:
                raise BusinessException(
                    "El pedido no tiene detalles. Debe tener al menos un artículo.",
                    error_code="sin_detalles"
                )
            numero_pedido = cabecera.get("numero_pedido") or "N/A"
            articulos_cargados = len(detalles)
            distribuciones_cargadas = sum(len(d.get("tiendas", [])) for d in detalles)

        # Enviar correo a EL RAYO (best-effort: si falla, el pedido se envía igual y se avisa)
        email_enviado = False
        try:
            from src.utils.email_notifier import send_plantilla_upload_notification
            email_enviado = send_plantilla_upload_notification(
                pedido_id=pedido_id,
                numero_pedido=numero_pedido,
                filename=None,
                usuario_id=usuario_id,
                articulos_cargados=articulos_cargados,
                distribuciones_cargadas=distribuciones_cargadas,
                formato_detectado="Enviado desde pantalla"
            )
            if not email_enviado:
                logger.warning(
                    "⚠️ No se pudo enviar la notificación por correo (pedido se marcará como enviado igualmente)"
                )
        except Exception as e:
            logger.warning(
                f"⚠️ Error al enviar correo en enviar_pedido (pedido se marcará como enviado igualmente): {e}",
                exc_info=True,
            )

        # Copiar snapshot original ANTES de cambiar estado (los datos aún están intactos)
        try:
            from ..repositories.pedido_original_repository import PedidoOriginalRepository
            with get_db_connection_context() as conn:
                original_repo = PedidoOriginalRepository(conn)
                original_repo.copiar_pedido_original(
                    pedido_id=pedido_id,
                    cabecera=cabecera,
                    detalles=detalles,
                    copiado_por=usuario_id,
                )
        except Exception as e:
            # No bloquear el envío si falla la copia del snapshot
            logger.warning(
                f"⚠️ No se pudo crear snapshot original para pedido {pedido_id}: {e}",
                exc_info=True,
            )

        # Cambiar estado a NUEVO_PEDIDO
        audit = AuditContext(usuario=usuario_id, origen=ORIGEN_WEB)
        with get_db_connection_context() as conn:
            repository = PedidoRepository(conn)
            repository.update_estado(pedido_id, ESTADO_NUEVO_PEDIDO, audit_context=audit)

        logger.info(
            f"✅ Pedido {pedido_id} ({numero_pedido}) enviado a EL RAYO por usuario {usuario_id or 'N/A'}"
        )
        return {
            "status": "success",
            "message": "Pedido enviado",
            "pedido_id": pedido_id,
            "numero_pedido": numero_pedido,
            "estado_id": ESTADO_NUEVO_PEDIDO,
            "estado_nombre": "NUEVO_PEDIDO",
            "email_enviado": email_enviado,
        }

    def _convertir_a_decimal(self, valor) -> Optional[float]:
        """Delegado a PedidoTypeConverter."""
        return self.type_converter.convertir_a_decimal(valor)
    
    def _convertir_a_entero(self, valor) -> Optional[int]:
        """Delegado a PedidoTypeConverter."""
        return self.type_converter.convertir_a_entero(valor)

    def _parsear_fecha_texto(self, valor) -> Any:
        """Delegado a PedidoTypeConverter."""
        return self.type_converter.parsear_fecha_texto(valor)

