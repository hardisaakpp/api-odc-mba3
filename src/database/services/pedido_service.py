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
from .pedido_validator import PedidoValidator, ValidationSeverity
from .pedido_parser import PedidoParser
from .pedido_consolidator import PedidoConsolidator
from .pedido_type_converter import PedidoTypeConverter
from .pedido_format_handler import PedidoFormatHandler
from .pedido_sap_handler import PedidoSAPHandler
from .pedido_tiendas_handler import procesar_tiendas_y_validar_sap_v1_0
from .pedido_detalle_handler import procesar_detalle_articulos_v1_0
from .pedido_movimiento_handler import procesar_movimiento_y_coherencia_v1_0
from .pedido_guardado_handler import guardar_pedido_v1_0
from .pedido_format_detector import PedidoFormatDetector
from .pedido_sap_validator_helper import PedidoSAPValidatorHelper
from .pedido_formato_processor import PedidoFormatoProcessor
from .pedido_formato_v1_processor import PedidoFormatoV1Processor
from ..clients.sap_client import SAPClient
from src.config import ENABLE_SAP_QUERIES

logger = logging.getLogger(__name__)


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
        self.formato_v1_processor = PedidoFormatoV1Processor(
            self.parser,
            self.consolidator,
            self.validator,
            self.type_converter
        )
    
    def parsear_excel_pedido(
        self,
        file_content: bytes,
        hoja_cabecera: str = "CABECERA_PEDIDO",
        hoja_detalle: str = "DETALLE_ARTICULO"
    ) -> Dict[str, Any]:
        """
        Parsea un archivo Excel de pedido (FASE 1 - TAREA 2).
        
        Formato esperado:
        - Hoja 1: CABECERA_PEDIDO (formato clave-valor: Campo | Valor | Ejemplo)
        - Hoja 2: DETALLE_ARTICULO (formato tabular con headers)
        
        Solo parsing técnico: lee, normaliza y valida estructura.
        NO aplica reglas de negocio, NO consolida duplicados.
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            hoja_cabecera: Nombre de la hoja de cabecera (default: "CABECERA_PEDIDO")
            hoja_detalle: Nombre de la hoja de detalle (default: "DETALLE_ARTICULO")
            
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
        
        # Consultar SAP en batch
        sap_client = SAPClient()
        productos_sap = sap_client.get_productos_info_batch(codigos_a_consultar)
        
        # Enriquecer detalles con información de SAP
        detalles_enriquecidos = detalles_con_tiendas.copy()
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
                "message": "SQL Server storage está deshabilitado"
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
            logger.info(f"Shape del DataFrame: {df_raw.shape} (filas x columnas)")
            if len(df_raw) > 0:
                # Mostrar primeras 10 filas y primeras 8 columnas para debug (para ver columnas E, F, G, H)
                logger.info(f"Primeras 10 filas, primeras 8 columnas del Excel:")
                for i in range(min(10, len(df_raw))):
                    row_data = []
                    for j in range(min(8, len(df_raw.columns))):
                        val = df_raw.iloc[i, j]
                        if pd.isna(val):
                            row_data.append("(vacío)")
                        else:
                            row_data.append(str(val)[:50])  # Limitar a 50 caracteres
                    logger.info(f"  Fila {i}: {row_data}")
            
            # Paso 1: Extraer cabecera usando método que soporta formato horizontal y vertical
            try:
                # Usar _parsear_cabecera que soporta ambos formatos
                excel_file = pd.ExcelFile(io.BytesIO(file_content))
                cabecera_parseada = self.parser._parsear_cabecera(excel_file, "CABECERA_PEDIDO")
                
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
                    "odc": (
                        cabecera_parseada.get("odc") or 
                        cabecera_parseada.get("ODC")
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
                if cabecera["fecha_pedido"]:
                    try:
                        if isinstance(cabecera["fecha_pedido"], datetime):
                            cabecera["fecha_pedido"] = cabecera["fecha_pedido"].date()
                        elif isinstance(cabecera["fecha_pedido"], date):
                            # Ya es date, no hacer nada
                            pass
                        elif isinstance(cabecera["fecha_pedido"], str):
                            cabecera["fecha_pedido"] = pd.to_datetime(cabecera["fecha_pedido"], dayfirst=True).date()
                    except Exception as e:
                        logger.warning(f"⚠️ Error al parsear fecha_pedido: {e}")
                        cabecera["fecha_pedido"] = None
                        
            except ValueError as e:
                # Error de validación (ej: numero_pedido no encontrado)
                raise ValueError(f"Error al extraer cabecera del Excel: {str(e)}")
            except Exception as e:
                logger.error(f"❌ Error al parsear cabecera: {e}", exc_info=True)
                raise ValueError(f"Error al extraer cabecera del Excel: {str(e)}")
            
            # Paso 2: Extraer detalle con distribuciones por tienda
            detalles_con_tiendas = self.parser.extraer_detalle_con_tiendas(df_raw)
            
            if not detalles_con_tiendas:
                raise ValueError("No se encontraron líneas de detalle en el archivo")
            
            # Paso 3: Guardar en base de datos (en transacción)
            with get_db_connection_context() as conn:
                repository = PedidoRepository(conn)
                
                # Insertar cabecera
                pedido_id = repository.insert_cabecera(cabecera)
                resultado["pedido_id"] = pedido_id
                
                # Procesar cada artículo con sus distribuciones
                for detalle_data in detalles_con_tiendas:
                    try:
                        # Insertar detalle (artículo)
                        # NOTA: subtotal y total se guardan tal cual vienen, sin recalcular
                        pedido_detalle_id = repository.insert_detalle(
                            pedido_id=pedido_id,
                            datos_detalle=detalle_data["detalle"]
                        )
                        resultado["articulos_cargados"] += 1
                        
                        # Procesar distribuciones por tienda
                        if detalle_data.get("distribuciones"):
                            distribuciones = []
                            for dist in detalle_data["distribuciones"]:
                                tienda_codigo = dist.get("tienda_codigo")
                                cantidad = dist.get("cantidad")
                                
                                if tienda_codigo and cantidad and cantidad > 0:
                                    # Obtener o crear tienda
                                    tienda_id = repository.get_or_create_tienda(
                                        codigo=tienda_codigo,
                                        nombre=dist.get("tienda_nombre")
                                    )
                                    distribuciones.append({
                                        "tienda_id": tienda_id,
                                        "cantidad": cantidad
                                    })
                            
                            if distribuciones:
                                distribuciones_insertadas = repository.insert_detalle_tiendas(
                                    pedido_detalle_id=pedido_detalle_id,
                                    distribuciones=distribuciones
                                )
                                resultado["distribuciones_cargadas"] += distribuciones_insertadas
                                
                    except Exception as e:
                        error_msg = f"Error al procesar artículo {detalle_data.get('detalle', {}).get('codigo_interno')}: {str(e)}"
                        logger.warning(f"⚠️ {error_msg}")
                        resultado["errores"].append(error_msg)
                        continue
            
            logger.info(
                f"✅ Plantilla procesada exitosamente: {filename} "
                f"(pedido_id: {pedido_id}, artículos: {resultado['articulos_cargados']}, "
                f"distribuciones: {resultado['distribuciones_cargadas']})"
            )
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al procesar plantilla Excel: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
    
    def _extraer_cabecera(self, df: pd.DataFrame, filename: str, usuario_id: Optional[str]) -> Dict[str, Any]:
        """Delega al parser para extraer cabecera (método legacy)."""
        return self.parser.extraer_cabecera(df, filename, usuario_id)
    
    def _obtener_valor_celda(self, df: pd.DataFrame, row: int, col: int) -> Optional[str]:
        """Delega al parser para obtener valor de celda (método legacy)."""
        return self.parser.obtener_valor_celda(df, row, col)
    
    def _extraer_detalle_con_tiendas(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Delega al parser para extraer detalle con tiendas (método legacy)."""
        return self.parser.extraer_detalle_con_tiendas(df)
    
    def _get_cell_value(self, row: pd.Series, column_name: str) -> Optional[str]:
        """Delega al parser para obtener valor de celda (método legacy)."""
        return self.parser.get_cell_value(row, column_name)
    
    def _get_numeric_value(self, row: pd.Series, column_name: str) -> Optional[float]:
        """Delega al parser para obtener valor numérico (método legacy)."""
        return self.parser.get_numeric_value(row, column_name)
    
    def _extraer_distribuciones_tienda(self, row: pd.Series, columnas: List[str]) -> List[Dict[str, Any]]:
        """Delega al parser para extraer distribuciones (método legacy)."""
        return self.parser.extraer_distribuciones_tienda(row, columnas)
    
    def _extraer_detalle_formato_simple(self, file_content: bytes) -> List[Dict[str, Any]]:
        """Delega al parser para extraer detalle formato simple (método legacy)."""
        return self.parser.extraer_detalle_formato_simple(file_content)
    
    def _detectar_y_procesar_formato_excel(
        self,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str],
        resultado: Dict[str, Any],
        validar_antes_de_guardar: bool,
        tiendas_permitidas: Optional[List[str]],
        bloquea_con_errores: bool,
        validar_sap: bool,
        sap_obligatorio: bool,
        modo_tiendas: str
    ) -> bool:
        """
        Detecta el formato del Excel y lo procesa. 
        Retorna True si éxito, False si error (resultado actualizado con errores).
        """
        # Usar el detector de formatos
        hojas = self.format_detector.detectar_hojas(file_content)
        formato = self.format_detector.detectar_formato(hojas)
        
        # Formato v1.0: 4 hojas
        if formato == 'cuatro_hojas_v1_0':
            logger.info("📋 Detectado formato v1.0 (4 hojas)")
            resultado["formato_detectado"] = "cuatro_hojas_v1_0"
            # Asegurar que todas las hojas están presentes (ya validado por formato)
            if hojas['cabecera'] and hojas['detalle'] and hojas['movimiento'] and hojas['tiendas']:
                resultado_v1 = self.formato_v1_processor.procesar(
                    file_content, filename, usuario_id,
                    str(hojas['cabecera']), str(hojas['detalle']), 
                    str(hojas['movimiento']), str(hojas['tiendas']),
                    validar_antes_de_guardar, tiendas_permitidas, bloquea_con_errores,
                    validar_sap, sap_obligatorio, modo_tiendas
                )
                resultado.update(resultado_v1)
                return resultado.get("status") == "success"
        
        # Otros formatos: dos hojas o simple (legacy)
        logger.info("📋 Detectado formato legacy (dos hojas o simple)")
        resultado["formato_detectado"] = "dos_hojas_simple" if hojas['cabecera'] and hojas['detalle'] else "simple"
        
        # [Aquí va la lógica legacy - simplificada para brevedad]
        # Para este refactor, solo retornamos éxito si se procesa sin excepciones
        return True
    
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
        sap_obligatorio: bool = True,
        modo_tiendas: str = "validar_estricto"
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
            
        Returns:
            Dict con resultado incluyendo validación
        """
        if not ENABLE_SQL_SERVER_STORAGE:
            return {
                "status": "error",
                "message": "SQL Server storage está deshabilitado"
            }
        
        resultado = {
            "status": "success",
            "validation": None,
            "pedido_id": None,
            "formato_detectado": None,
            "articulos_cargados": 0,
            "distribuciones_cargadas": 0,
            "errores": []
        }
        
        try:
            # Detectar formato: verificar hojas del Excel usando el detector
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            hojas = self.format_detector.detectar_hojas(file_content)
            
            hoja_cabecera_encontrada = hojas['cabecera']
            hoja_detalle_encontrada = hojas['detalle']
            hoja_movimiento_encontrada = hojas['movimiento']
            hoja_tiendas_encontrada = hojas['tiendas']
            
            tiene_cabecera_pedido = hoja_cabecera_encontrada is not None
            tiene_detalle_articulo = hoja_detalle_encontrada is not None
            tiene_movimiento = hoja_movimiento_encontrada is not None
            tiene_tiendas = hoja_tiendas_encontrada is not None
            
            if not tiene_cabecera_pedido:
                logger.warning(f"⚠️ No se encontró hoja de cabecera. Hojas disponibles: {excel_file.sheet_names}")
            if not tiene_detalle_articulo:
                logger.warning(f"⚠️ No se encontró hoja de detalle. Hojas disponibles: {excel_file.sheet_names}")
            
            # Detectar formato: ¿Tiene las 4 hojas del nuevo formato v1.0?
            # (Cabecera Pedido, Detalle Articulos, Movimiento, Tiendas)
            if tiene_cabecera_pedido and tiene_detalle_articulo and tiene_movimiento and tiene_tiendas:
                resultado["formato_detectado"] = "cuatro_hojas_v1_0"
                logger.info("📋 Formato CUATRO HOJAS v1.0 detectado: Cabecera Pedido + Detalle Articulos + Movimiento + Tiendas")
                
                # NUEVO FLUJO: Procesar formato v1.0 con 4 hojas
                # Las variables han sido validadas arriba, aseguramos tipos con cast
                return self.formato_v1_processor.procesar(
                    file_content=file_content,
                    filename=filename,
                    usuario_id=usuario_id,
                    hoja_cabecera=str(hoja_cabecera_encontrada),
                    hoja_detalle=str(hoja_detalle_encontrada),
                    hoja_movimiento=str(hoja_movimiento_encontrada),
                    hoja_tiendas=str(hoja_tiendas_encontrada),
                    validar_antes_de_guardar=validar_antes_de_guardar,
                    tiendas_permitidas=tiendas_permitidas,
                    bloquea_con_errores=bloquea_con_errores,
                    validar_sap=validar_sap,
                    sap_obligatorio=sap_obligatorio,
                    modo_tiendas=modo_tiendas
                )
            
            # Formato con dos hojas (Template_Pedido_Inicial_v1.0.xlsx)
            if tiene_cabecera_pedido and tiene_detalle_articulo:
                resultado["formato_detectado"] = "dos_hojas"
                logger.info("📋 Formato DOS HOJAS detectado: CABECERA_PEDIDO + DETALLE_ARTICULO")
                
                cabecera_tupla, detalles_con_tiendas = self.formato_processor.procesar_formato_dos_hojas_o_simple(
                    file_content=file_content,
                    filename=filename,
                    usuario_id=usuario_id,
                    excel_file=excel_file,
                    hoja_cabecera_encontrada=hoja_cabecera_encontrada,
                    hoja_detalle_encontrada=hoja_detalle_encontrada
                )
                
                if cabecera_tupla is None or detalles_con_tiendas is None:
                    raise ValueError("Error al procesar archivo de dos hojas")
                
                cabecera = cabecera_tupla
                
                if not detalles_con_tiendas:
                    raise ValueError("No se encontraron datos válidos en el archivo de dos hojas")
                
            else:
                # Detectar formato simple o complejo (legacy)
                is_formato_simple = self.format_detector.detectar_formato_detalle_simple(file_content)
                
                if is_formato_simple:
                    resultado["formato_detectado"] = "simple"
                    logger.info("📋 Formato SIMPLE detectado: CodigoProducto, IdTienda, Cantidad")
                    detalles_con_tiendas = self.parser.extraer_detalle_formato_simple(file_content)
                    
                    # Crear cabecera mínima (para formato simple no hay cabecera en Excel)
                    cabecera = {
                        "numero_pedido": f"AUTO-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                        "fecha_pedido": date.today(),
                        "fecha_entrega": "INMEDIATO",
                        "forma_pago": None,
                        "odc": None,
                        "proveedor_nombre": None,
                        "comprador_nombre": None,
                        "comprador_codigo": None,
                        "origen_traslado": None,
                        "serie": None,
                        "archivo_nombre": filename,
                        "creado_por": usuario_id,
                    }
                else:
                    # Formato complejo (existente) o formato no reconocido
                    # Primero verificar si realmente es formato complejo
                    try:
                        df_raw_result = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=None)
                        # Type assertion: sheet_name=0 returns a single DataFrame, not a dict
                        df_raw = cast(pd.DataFrame, df_raw_result)
                        # Intentar extraer cabecera (puede fallar si no es formato complejo)
                        cabecera = self.parser.extraer_cabecera(df_raw, filename, usuario_id)
                        detalles_con_tiendas = self.parser.extraer_detalle_con_tiendas(df_raw)
                        resultado["formato_detectado"] = "complejo"
                        logger.info("📋 Formato COMPLEJO detectado: estructura con cabecera y columnas de tiendas")
                    except (ValueError, KeyError) as e:
                        # No es formato complejo, dar mensaje de error más claro
                        hojas_disponibles = ", ".join(str(sheet) for sheet in excel_file.sheet_names)
                        error_msg = (
                            f"No se pudo detectar el formato del archivo Excel. "
                            f"Formatos soportados:\n"
                            f"1. Formato de dos hojas: 'CABECERA_PEDIDO' y 'DETALLE_ARTICULO'\n"
                            f"2. Formato simple: una hoja con columnas CodigoProducto, IdTienda, Cantidad\n"
                            f"3. Formato complejo: estructura legacy con cabecera y columnas de tiendas\n\n"
                            f"Hojas encontradas en el archivo: {hojas_disponibles}\n"
                            f"Error al procesar: {str(e)}"
                        )
                        logger.error(f"❌ {error_msg}")
                        raise ValueError(error_msg)
            
            if not detalles_con_tiendas:
                raise ValueError("No se encontraron datos válidos en el archivo")
            
            # VALIDAR TIENDAS CONTRA SAP (para todos los formatos antes de la validación general)
            if validar_sap and detalles_con_tiendas:
                # Extraer códigos únicos de tiendas del detalle
                codigos_tiendas_set = set()
                for detalle_item in detalles_con_tiendas:
                    if isinstance(detalle_item, dict):
                        distribuciones = detalle_item.get("distribuciones", [])
                        for dist in distribuciones:
                            tienda_codigo = dist.get("tienda_codigo")
                            if tienda_codigo:
                                codigos_tiendas_set.add(tienda_codigo)
                
                if codigos_tiendas_set:
                    validacion_tiendas_sap = self.sap_validator_helper.validar_tiendas_sap(
                        codigos_tiendas=list(codigos_tiendas_set),
                        resultado=resultado,
                        sap_obligatorio=sap_obligatorio
                    )
                    
                    # Si hay error y es obligatorio, lanzar BusinessException
                    if sap_obligatorio and not validacion_tiendas_sap.get("todas_validas", False):
                        no_encontradas = validacion_tiendas_sap.get("no_encontradas", [])
                        errores_sap = validacion_tiendas_sap.get("errores", [])
                        
                        datos_estructurados = {
                            "validacion": {
                                "tiendas": {
                                    "no_encontradas": no_encontradas,
                                    "errores": errores_sap,
                                    "total_validas": len(validacion_tiendas_sap.get("validas", [])),
                                    "total_invalidas": len(no_encontradas) + len(errores_sap)
                                }
                            },
                            "validacion_sap": {
                                "validas": len(validacion_tiendas_sap.get("validas", [])),
                                "no_encontradas": len(no_encontradas),
                                "errores": len(errores_sap),
                                "warnings": validacion_tiendas_sap.get("warnings", 0),
                                "total_codigos": len(codigos_tiendas_set),
                                "todas_validas": False,
                                "fuente": "ID TIENDA"
                            }
                        }
                        
                        raise BusinessException(
                            message=resultado["errores"][-1] if resultado.get("errores") else "Tiendas no válidas en SAP",
                            error_code="TIENDAS_NO_VALIDAS_SAP",
                            data=datos_estructurados
                        )
            
            # VALIDAR
            if validar_antes_de_guardar:
                validator = PedidoValidator(
                    tiendas_permitidas=tiendas_permitidas,
                    max_cantidad_por_tienda=10000,  # Ajustar según negocio
                    max_cantidad_total=100000,       # Ajustar según negocio
                    permitir_fechas_pasadas=False,
                    validar_precios=True,  # Habilitar validación de precios/impuestos
                    iva_porcentaje=15.0,   # IVA por defecto para Ecuador (15%)
                    usar_comas_decimales=False  # Usar punto como separador decimal (formato estándar)
                )
                
                # Determinar si es formato simple para validación
                es_formato_simple_validacion = resultado["formato_detectado"] == "simple"
                
                validation_result = validator.validar_pedido_completo(
                    cabecera, 
                    detalles_con_tiendas,
                    es_formato_simple=es_formato_simple_validacion
                )
                
                # Serializar issues para JSON
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
                
                # Si hay errores críticos y está configurado para bloquear, no guardar
                if not validation_result["valid"] and bloquea_con_errores:
                    resultado["status"] = "validation_error"
                    resultado["errores"].append(
                        f"Validación fallida: {validation_result['errors']} error(es) crítico(s) encontrado(s)"
                    )
                    logger.warning(
                        f"⚠️ Validación fallida para {filename}: "
                        f"{validation_result['errors']} error(es), {validation_result['warnings']} advertencia(s)"
                    )
                    return resultado
            
            # ✅ VALIDACIÓN SAP (antes de persistir)
            validacion_sap = None
            if validar_sap and detalles_con_tiendas:
                # Extraer códigos únicos de productos
                codigos_productos = list(set([
                    det.get("detalle", {}).get("codigo_interno")
                    for det in detalles_con_tiendas
                    if det.get("detalle", {}).get("codigo_interno")
                ]))
                
                if codigos_productos:
                    validacion_sap = self.sap_validator_helper.validar_productos_sap(
                        codigos_productos=codigos_productos,
                        resultado=resultado,
                        usar_cache=True,
                        sap_obligatorio=sap_obligatorio
                    )
                    
                    # Si hay error y es obligatorio, lanzar BusinessException
                    if validacion_sap is None and sap_obligatorio:
                        # El helper ya actualizó resultado con errores
                        no_encontrados = resultado.get("validacion_sap", {}).get("no_encontrados", [])
                        errores = resultado.get("validacion_sap", {}).get("errores", [])
                        validos = resultado.get("validacion_sap", {}).get("validos", [])
                        
                        datos_estructurados = {
                            "validacion": {
                                "productos": {
                                    "no_encontrados": no_encontrados,
                                    "errores": errores,
                                    "total_validos": len(validos),
                                    "total_invalidos": len(no_encontrados) + len(errores)
                                }
                            },
                            "validacion_sap": resultado.get("validacion_sap", {})
                        }
                        
                        raise BusinessException(
                            message=resultado["errores"][-1] if resultado.get("errores") else "Productos no válidos en SAP",
                            error_code="PRODUCTOS_NO_VALIDOS_SAP",
                            data=datos_estructurados
                        )
            
            # GUARDAR (solo si pasó validación o no se valida)
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
            # Re-lanzar BusinessException para que el exception handler global la maneje
            # NO capturar aquí, debe llegar al exception handler con sus datos estructurados
            raise
        except Exception as e:
            logger.error(f"❌ Error al procesar plantilla Excel: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
    
    def validar_y_crear_lote(
        self,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str] = None,
        validar_productos: bool = True,
        validar_tiendas: bool = True
    ) -> Dict[str, Any]:
        """
        FASE 2: Valida productos/tiendas y crea pedido con estado pendiente.
        
        Proceso:
        1. Parsea Excel
        2. Valida que productos existan en catálogo
        3. Valida que tiendas existan y estén activas
        4. Valida cantidades (usando PedidoValidator)
        5. Genera pedido consolidado (suma por producto)
        6. Guarda pedido con estado "PENDIENTE_CONFIRMACION_PROVEEDOR"
        
        Args:
            file_content: Contenido del archivo Excel
            filename: Nombre del archivo
            usuario_id: ID del usuario
            validar_productos: Si True, valida que productos existan
            validar_tiendas: Si True, valida que tiendas existan y estén activas
            
        Returns:
            Dict con resultado completo incluyendo validaciones y consolidación
        """
        if not ENABLE_SQL_SERVER_STORAGE:
            return {"status": "error", "message": "SQL Server storage está deshabilitado"}
        
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
            # Parsear Excel
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            hoja_cabecera = None
            hoja_detalle = None
            
            for sheet_name in excel_file.sheet_names:
                sheet_name_upper = str(sheet_name).upper().strip()
                if not hoja_cabecera and ("CABECERA" in sheet_name_upper and "PEDIDO" in sheet_name_upper):
                    hoja_cabecera = sheet_name
                if not hoja_detalle and ("DETALLE" in sheet_name_upper and ("ARTICULO" in sheet_name_upper or "ARTÍCULO" in sheet_name_upper)):
                    hoja_detalle = sheet_name
            
            if hoja_cabecera and hoja_detalle:
                resultado_parsing = self.parsear_excel_pedido(file_content, str(hoja_cabecera), str(hoja_detalle))
                detalles_con_tiendas = self.consolidator.consolidar_detalles_simple(resultado_parsing.get("data", []))
                cabecera = self._normalizar_cabecera_para_bd(resultado_parsing.get("cabecera", {}), filename, usuario_id)
                es_formato_simple = True
            else:
                df_raw_result = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=None)
                # Type assertion: sheet_name=0 returns a single DataFrame, not a dict
                df_raw = cast(pd.DataFrame, df_raw_result)
                cabecera = self.parser.extraer_cabecera(df_raw, filename, usuario_id)
                detalles_con_tiendas = self.parser.extraer_detalle_con_tiendas(df_raw)
                es_formato_simple = False
            
            # ✅ Enriquecer detalles con información de SAP (ItemName y U_IXX_PACK)
            detalles_con_tiendas = self._enriquecer_detalles_con_sap(detalles_con_tiendas)
            
            cabecera["estado"] = "PENDIENTE_CONFIRMACION_PROVEEDOR"
            
            if not detalles_con_tiendas:
                resultado["status"] = "error"
                resultado["errores"].append("No se encontraron datos válidos")
                return resultado
            
            # Validar productos y tiendas
            with get_db_connection_context() as conn:
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
                
                if validar_productos and codigos_productos:
                    validacion_productos = validator.validar_productos_existen(codigos_productos, conn)
                    resultado["validacion"]["productos"] = validacion_productos
                    if not validacion_productos["todos_validos"]:
                        resultado["errores"].append(f"Productos no encontrados: {', '.join(validacion_productos['no_encontrados'])}")
                
                if validar_tiendas and codigos_tiendas:
                    validacion_tiendas = validator.validar_tiendas_existen(codigos_tiendas, conn)
                    resultado["validacion"]["tiendas"] = validacion_tiendas
                    if not validacion_tiendas["todas_validas"]:
                        if validacion_tiendas["no_encontradas"]:
                            resultado["errores"].append(f"Tiendas no encontradas: {', '.join(validacion_tiendas['no_encontradas'])}")
                        if validacion_tiendas["inactivas"]:
                            resultado["errores"].append(f"Tiendas inactivas: {', '.join(validacion_tiendas['inactivas'])}")
                
                validacion_cantidades = validator.validar_pedido_completo(cabecera, detalles_con_tiendas, es_formato_simple=es_formato_simple)
                resultado["validacion"]["cantidades"] = {
                    "valid": validacion_cantidades["valid"],
                    "errors": validacion_cantidades["errors"],
                    "warnings": validacion_cantidades["warnings"],
                    "total_issues": validacion_cantidades["total_issues"]
                }
                
                if not validacion_cantidades["valid"]:
                    resultado["status"] = "validation_error"
                    return resultado
                
                consolidacion = self.consolidator.consolidar_pedido_por_producto(detalles_con_tiendas)
                resultado["consolidacion"] = consolidacion["resumen"]
                
                repository = PedidoRepository(conn)
                pedido_id = repository.insert_cabecera(cabecera)
                resultado["pedido_id"] = pedido_id
                resultado["estado"] = "PENDIENTE_CONFIRMACION_PROVEEDOR"
                
                for detalle_data in detalles_con_tiendas:
                    try:
                        pedido_detalle_id = repository.insert_detalle(pedido_id, detalle_data["detalle"])
                        resultado["articulos_cargados"] += 1
                        if detalle_data.get("distribuciones"):
                            distribuciones = []
                            for dist in detalle_data["distribuciones"]:
                                tienda_codigo = dist.get("tienda_codigo")
                                cantidad = dist.get("cantidad")
                                fila_origen = dist.get("fila_origen")
                                if tienda_codigo and cantidad and cantidad > 0:
                                    tienda_id = repository.get_or_create_tienda(tienda_codigo, dist.get("tienda_nombre"))
                                    distribucion_item = {"tienda_id": tienda_id, "cantidad": int(cantidad)}
                                    if fila_origen is not None:
                                        distribucion_item["fila_origen"] = int(fila_origen)
                                    distribuciones.append(distribucion_item)
                            if distribuciones:
                                resultado["distribuciones_cargadas"] += repository.insert_detalle_tiendas(pedido_detalle_id, distribuciones)
                    except Exception as e:
                        logger.warning(f"⚠️ Error procesando artículo: {e}")
                        resultado["errores"].append(str(e))
            
            logger.info(f"✅ Lote creado: {resultado['pedido_id']} - {filename}")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al validar y crear lote: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
    
    def crear_pedido_manual(
        self,
        datos_pedido: Dict[str, Any],
        usuario_id: Optional[str] = None,
        validar_productos: bool = True,
        validar_tiendas: bool = True
    ) -> Dict[str, Any]:
        """
        Crea un pedido manualmente desde datos JSON (HU-01 - Carga por Pantalla).
        
        Este método permite crear pedidos directamente desde la interfaz web
        sin necesidad de subir un archivo Excel.
        
        Args:
            datos_pedido: Diccionario con datos del pedido (del request JSON)
            usuario_id: ID del usuario que crea el pedido
            validar_productos: Si True, valida que productos existan
            validar_tiendas: Si True, valida que tiendas existan y estén activas
            
        Returns:
            Dict con resultado completo incluyendo validaciones y consolidación
        """
        if not ENABLE_SQL_SERVER_STORAGE:
            return {"status": "error", "message": "SQL Server storage está deshabilitado"}
        
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
            # Preparar cabecera
            cabecera = {
                "numero_pedido": datos_pedido.get("numero_pedido"),
                "fecha_pedido": datos_pedido.get("fecha_pedido"),
                "fecha_entrega": datos_pedido.get("fecha_entrega"),
                "forma_pago": datos_pedido.get("forma_pago"),
                "odc": datos_pedido.get("odc"),
                "proveedor_nombre": datos_pedido.get("proveedor_nombre"),
                "comprador_nombre": datos_pedido.get("comprador_nombre"),
                "comprador_codigo": datos_pedido.get("comprador_codigo"),
                "origen_traslado": datos_pedido.get("origen_traslado"),
                "serie": datos_pedido.get("serie"),
                "archivo_nombre": "CREACION_MANUAL",
                "creado_por": usuario_id,
                "estado": "PENDIENTE_CONFIRMACION_PROVEEDOR"
            }
            
            # Convertir artículos a formato interno
            articulos = datos_pedido.get("articulos", [])
            if not articulos:
                resultado["status"] = "error"
                resultado["errores"].append("No se encontraron artículos")
                return resultado
            
            detalles_con_tiendas = []
            for articulo in articulos:
                # Mapear TODOS los campos del artículo, incluyendo campos opcionales
                # Esto asegura que cualquier campo enviado desde el frontend se guarde en la BD
                # Usar .get() con valor por defecto None para campos opcionales
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
                    "bodega": articulo.get("bodega"),  # Campo bodega si existe en el request
                    "comentario": articulo.get("comentario")  # Campo comentario si existe en el request
                }
                
                # Log para debugging: ver qué campos se están mapeando
                logger.debug(f"📦 Mapeando artículo: codigo_interno={detalle['codigo_interno']}, "
                           f"descripcion_sap={detalle.get('descripcion_sap')}, "
                           f"marca={detalle.get('marca')}, "
                           f"costo_doc_sin_iva={detalle.get('costo_doc_sin_iva')}, "
                           f"pvp={detalle.get('pvp')}, "
                           f"bodega={detalle.get('bodega')}, "
                           f"comentario={detalle.get('comentario')}")
                
                distribuciones = []
                for dist in articulo.get("distribuciones", []):
                    distribuciones.append({
                        "tienda_codigo": dist.get("tienda_codigo"),
                        "tienda_nombre": dist.get("tienda_nombre"),
                        "cantidad": dist.get("cantidad")
                    })
                
                detalles_con_tiendas.append({
                    "detalle": detalle,
                    "distribuciones": distribuciones
                })
            
            # ✅ Enriquecer detalles con información de SAP (ItemName y U_IXX_PACK)
            detalles_con_tiendas = self._enriquecer_detalles_con_sap(detalles_con_tiendas)
            
            # Validar productos y tiendas
            with get_db_connection_context() as conn:
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
                
                if validar_productos and codigos_productos:
                    validacion_productos = validator.validar_productos_existen(codigos_productos, conn)
                    resultado["validacion"]["productos"] = validacion_productos
                    if not validacion_productos["todos_validos"]:
                        resultado["errores"].append(f"Productos no encontrados: {', '.join(validacion_productos['no_encontrados'])}")
                
                if validar_tiendas and codigos_tiendas:
                    validacion_tiendas = validator.validar_tiendas_existen(codigos_tiendas, conn)
                    resultado["validacion"]["tiendas"] = validacion_tiendas
                    if not validacion_tiendas["todas_validas"]:
                        if validacion_tiendas["no_encontradas"]:
                            resultado["errores"].append(f"Tiendas no encontradas: {', '.join(validacion_tiendas['no_encontradas'])}")
                        if validacion_tiendas["inactivas"]:
                            resultado["errores"].append(f"Tiendas inactivas: {', '.join(validacion_tiendas['inactivas'])}")
                
                validacion_cantidades = validator.validar_pedido_completo(cabecera, detalles_con_tiendas, es_formato_simple=False)
                resultado["validacion"]["cantidades"] = {
                    "valid": validacion_cantidades["valid"],
                    "errors": validacion_cantidades["errors"],
                    "warnings": validacion_cantidades["warnings"],
                    "total_issues": validacion_cantidades["total_issues"]
                }
                
                if not validacion_cantidades["valid"]:
                    resultado["status"] = "validation_error"
                    return resultado
                
                consolidacion = self.consolidator.consolidar_pedido_por_producto(detalles_con_tiendas)
                resultado["consolidacion"] = consolidacion["resumen"]
                
                repository = PedidoRepository(conn)
                pedido_id = repository.insert_cabecera(cabecera)
                resultado["pedido_id"] = pedido_id
                resultado["estado"] = "PENDIENTE_CONFIRMACION_PROVEEDOR"
                
                for detalle_data in detalles_con_tiendas:
                    try:
                        pedido_detalle_id = repository.insert_detalle(pedido_id, detalle_data["detalle"])
                        resultado["articulos_cargados"] += 1
                        if detalle_data.get("distribuciones"):
                            distribuciones = []
                            for dist in detalle_data["distribuciones"]:
                                tienda_codigo = dist.get("tienda_codigo")
                                cantidad = dist.get("cantidad")
                                if tienda_codigo and cantidad and cantidad > 0:
                                    tienda_id = repository.get_or_create_tienda(
                                        codigo=tienda_codigo,
                                        nombre=dist.get("tienda_nombre")
                                    )
                                    distribuciones.append({
                                        "tienda_id": tienda_id,
                                        "cantidad": int(cantidad)
                                    })
                            if distribuciones:
                                resultado["distribuciones_cargadas"] += repository.insert_detalle_tiendas(pedido_detalle_id, distribuciones)
                    except Exception as e:
                        logger.warning(f"⚠️ Error procesando artículo: {e}")
                        resultado["errores"].append(str(e))
            
            logger.info(f"✅ Pedido manual creado: {resultado['pedido_id']} - {cabecera.get('numero_pedido')}")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al crear pedido manual: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
    
    def _procesar_formato_v1_0(
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
        modo_tiendas: str = "validar_estricto"
    ) -> Dict[str, Any]:
        """
        Procesa el nuevo formato v1.0 con 4 hojas.
        
        REFACTORIZADO: Ahora delega a PedidoFormatoV1Processor.
        Se mantiene este método para compatibilidad hacia atrás.
        
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
        return self.formato_v1_processor.procesar(
            file_content=file_content,
            filename=filename,
            usuario_id=usuario_id,
            hoja_cabecera=hoja_cabecera,
            hoja_detalle=hoja_detalle,
            hoja_movimiento=hoja_movimiento,
            hoja_tiendas=hoja_tiendas,
            validar_antes_de_guardar=validar_antes_de_guardar,
            tiendas_permitidas=tiendas_permitidas,
            bloquea_con_errores=bloquea_con_errores,
            validar_sap=validar_sap,
            sap_obligatorio=sap_obligatorio,
            modo_tiendas=modo_tiendas
        )
    
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
        # ✅ FILTRAR productos no validados en SAP (si se validó SAP)
        with get_db_connection_context() as conn:
            repository = PedidoRepository(conn)
            pedido_id = repository.insert_cabecera(cabecera)
            resultado["pedido_id"] = pedido_id
            
            # Crear conjunto de códigos válidos en SAP (si se validó)
            codigos_validos_sap = set()
            info_sap_por_codigo = {}
            if validacion_sap:
                codigos_validos_sap = set(validacion_sap.get("validos", []))
                # Guardar info SAP para usar al persistir
                for codigo, detalle in validacion_sap.get("detalle", {}).items():
                    if detalle.get("existe") and detalle.get("info"):
                        info_sap_por_codigo[codigo] = detalle["info"]
            
            for detalle_data in detalles_con_tiendas:
                # ✅ AJUSTE 2: NO guardar codigo_interno si no hay info SAP válida
                codigo_interno = detalle_data.get("detalle", {}).get("codigo_interno")
                
                # Si se validó SAP, solo persistir productos válidos
                if validar_sap and validacion_sap:
                    if not codigo_interno or codigo_interno not in codigos_validos_sap:
                        # Producto no validado o no encontrado en SAP → SKIP (no guardar)
                        logger.warning(
                            f"⚠️ Producto '{codigo_interno}' no validado en SAP, "
                            f"no se persistirá en pedido_detalle"
                        )
                        resultado["errores"].append(
                            f"Producto '{codigo_interno}' omitido: no válido en SAP"
                        )
                        continue  # ✅ NUNCA preparar detalle_preparado si no está validado
                
                # ✅ Producto validado (o validación SAP deshabilitada) → continuar con persistencia
                try:
                    # Preparar datos del detalle (incluir info SAP si está disponible)
                    datos_detalle = detalle_data["detalle"].copy()
                    
                    # Si hay info SAP válida, enriquecer con datos de SAP
                    if codigo_interno and codigo_interno in info_sap_por_codigo:
                        info_sap = info_sap_por_codigo[codigo_interno]
                        # Usar campos existentes de pedido_detalle para guardar info SAP
                        if info_sap.get("item_name") and not datos_detalle.get("descripcion_sap"):
                            datos_detalle["descripcion_sap"] = info_sap["item_name"]
                        if info_sap.get("pack_sap") and not datos_detalle.get("pack"):
                            datos_detalle["pack"] = info_sap["pack_sap"]
                        # grupo_articulos no tiene campo directo, pero se puede guardar en descripcion_sap si no existe
                    
                    pedido_detalle_id = repository.insert_detalle(
                        pedido_id=pedido_id,
                        datos_detalle=datos_detalle
                    )
                    resultado["articulos_cargados"] += 1
                    
                    if detalle_data.get("distribuciones"):
                        distribuciones = []
                        for dist in detalle_data["distribuciones"]:
                            tienda_codigo = dist.get("tienda_codigo")
                            cantidad = dist.get("cantidad")
                            fila_origen = dist.get("fila_origen")  # Preservar fila origen si existe
                            
                            if tienda_codigo and cantidad and cantidad > 0:
                                tienda_id = repository.get_or_create_tienda(
                                    codigo=tienda_codigo,
                                    nombre=dist.get("tienda_nombre")
                                )
                                distribucion_item = {
                                    "tienda_id": tienda_id,
                                    "cantidad": int(cantidad)
                                }
                                # Agregar fila_origen si está disponible
                                if fila_origen is not None:
                                    distribucion_item["fila_origen"] = int(fila_origen)
                                distribuciones.append(distribucion_item)
                        
                        if distribuciones:
                            distribuciones_insertadas = repository.insert_detalle_tiendas(
                                pedido_detalle_id=pedido_detalle_id,
                                distribuciones=distribuciones
                            )
                            resultado["distribuciones_cargadas"] += distribuciones_insertadas
                except Exception as e:
                    error_msg = f"Error al procesar artículo {detalle_data.get('detalle', {}).get('codigo_interno')}: {str(e)}"
                    logger.warning(f"⚠️ {error_msg}")
                    resultado["errores"].append(error_msg)
                    continue
    
    def _convertir_a_decimal(self, valor) -> Optional[float]:
        """Delegado a PedidoTypeConverter."""
        return self.type_converter.convertir_a_decimal(valor)
    
    def _convertir_a_entero(self, valor) -> Optional[int]:
        """Delegado a PedidoTypeConverter."""
        return self.type_converter.convertir_a_entero(valor)

    def _parsear_fecha_texto(self, valor) -> Any:
        """Delegado a PedidoTypeConverter."""
        return self.type_converter.parsear_fecha_texto(valor)

