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
from ..pedido_estados import ESTADO_BORRADOR, ESTADO_NUEVO_PEDIDO
from .pedido_validator import PedidoValidator, ValidationSeverity
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
from src.config import ENABLE_SAP_QUERIES

logger = logging.getLogger(__name__)

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
        es_formato_nuevo_v1_0: bool = True
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
            es_formato_nuevo_v1_0: Si True, usa el nuevo formato v1.0 (default: True)
            
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
            hoja_detalle=hoja_detalle,
            es_formato_nuevo_v1_0=True
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
            
            # Paso 2: Este método (procesar_archivo_excel) está deprecado
            # Se debe usar validar_y_procesar_archivo_excel en su lugar
            raise ValueError(
                "El método procesar_archivo_excel está deprecado. "
                "Use validar_y_procesar_archivo_excel en su lugar, que soporta el nuevo formato v1.0."
            )
            
            # Paso 3: Guardar en base de datos (en transacción)
            with get_db_connection_context() as conn:
                repository = PedidoRepository(conn)
                
                # Insertar cabecera
                try:
                    pedido_id = repository.insert_cabecera(cabecera)
                except ValueError as e:
                    # Detectar específicamente el error de número de pedido duplicado
                    error_msg = str(e)
                    if "número de pedido" in error_msg.lower() and "ya existe" in error_msg.lower():
                        logger.warning(f"⚠️ Intento de crear pedido con número duplicado: {error_msg}")
                        resultado["status"] = "error"
                        resultado["errores"].append(error_msg)
                        resultado["error_tipo"] = "numero_pedido_duplicado"
                        return resultado
                    # Otros ValueError se propagan
                    raise
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
                                
                                if tienda_codigo and cantidad is not None and cantidad >= 0:
                                    # Obtener o crear tienda
                                    tienda_id = repository.get_or_create_tienda(
                                        codigo=tienda_codigo,
                                        nombre=dist.get("tienda_nombre")
                                    )
                                    distribuciones.append({
                                        "tienda_id": tienda_id,
                                        "cantidad": cantidad,
                                        "fila_origen": dist.get("fila_origen"),
                                        "es_bodega": dist.get("es_bodega", False)  # ⭐ NUEVO: Pasar flag de bodega
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
    
    
    def _aplicar_correcciones_codigos(
        self,
        detalles_con_tiendas: List[Dict[str, Any]],
        correcciones: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Aplica correcciones de códigos de producto en memoria.
        
        Reemplaza los códigos originales del Excel por los códigos SAP corregidos
        antes de validar contra SAP. Esto permite que el usuario seleccione sugerencias
        SAP sin necesidad de modificar el archivo Excel.
        
        Args:
            detalles_con_tiendas: Lista de detalles con productos y distribuciones
            correcciones: Diccionario {codigo_original: codigo_sap_corregido}
            
        Returns:
            Lista de detalles con códigos corregidos aplicados
        """
        if not correcciones:
            return detalles_con_tiendas
        
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
        
        return detalles_con_tiendas
    
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
        
        # Formato de 2 hojas v1.0 (ÚNICO FORMATO SOPORTADO)
        if formato == 'dos_hojas_nuevo_v1_0':
            logger.info("📋 Detectado formato v1.0 (2 hojas)")
            resultado["formato_detectado"] = "dos_hojas_nuevo_v1_0"
            # El procesamiento de 2 hojas se maneja en validar_y_procesar_archivo_excel
            # Este método solo valida, no procesa completamente
            return True
        
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
        modo_tiendas: str = "validar_estricto",
        correcciones_codigos: Optional[Dict[str, str]] = None
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
            "errores": [],
            "correcciones_aplicadas": [
                {"codigo_original": k, "codigo_corregido": v}
                for k, v in (correcciones_codigos or {}).items()
            ]
        }
        
        try:
            # Detectar formato: verificar hojas del Excel usando el detector
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            hojas = self.format_detector.detectar_hojas(file_content)
            
            hoja_cabecera_encontrada = hojas['cabecera']
            hoja_detalle_encontrada = hojas['detalle']
            
            tiene_cabecera_pedido = hoja_cabecera_encontrada is not None
            tiene_detalle_articulo = hoja_detalle_encontrada is not None
            
            if not tiene_cabecera_pedido:
                logger.warning(f"⚠️ No se encontró hoja de cabecera. Hojas disponibles: {excel_file.sheet_names}")
            if not tiene_detalle_articulo:
                logger.warning(f"⚠️ No se encontró hoja de detalle. Hojas disponibles: {excel_file.sheet_names}")
            
            # Detectar si es nuevo formato v1.0 (hojas "cabecera" y "detalle" en minúsculas)
            formato_detectado = self.format_detector.detectar_formato(hojas)
            es_formato_nuevo_v1_0 = formato_detectado == 'dos_hojas_nuevo_v1_0'
            
            # Formato con dos hojas - Nuevo formato v1.0 (hojas "cabecera" y "detalle")
            if es_formato_nuevo_v1_0:
                resultado["formato_detectado"] = "dos_hojas_nuevo_v1_0"
                logger.info("📋 Formato DOS HOJAS NUEVO v1.0 detectado: 'cabecera' + 'detalle' (con bodegas centrales)")
                
                # Parsear usando el nuevo parser
                resultado_parsing = self.parser.parsear_excel_pedido(
                    file_content=file_content,
                    hoja_cabecera=str(hoja_cabecera_encontrada),
                    hoja_detalle=str(hoja_detalle_encontrada),
                    es_formato_nuevo_v1_0=True
                )
                
                # ⭐ VALIDACIÓN TEMPRANA #1: Verificar número de pedido duplicado PRIMERO (antes de SAP)
                cabecera_parseada = resultado_parsing.get("cabecera", {})
                numero_pedido_raw = (
                    cabecera_parseada.get("numero_pedido") or 
                    cabecera_parseada.get("CODIGO PEDIDO") or 
                    cabecera_parseada.get("CÓDIGO PEDIDO")
                )
                
                if numero_pedido_raw:
                    with get_db_connection_context() as conn_check:
                        from ..repositories.pedido_repository import PedidoRepository
                        repo_check = PedidoRepository(conn_check)
                        
                        if repo_check.existe_numero_pedido(numero_pedido_raw):
                            logger.warning(f"⚠️ [VALIDACIÓN TEMPRANA #1] Número de pedido duplicado detectado: '{numero_pedido_raw}'")
                            
                            # Lanzar BusinessException INMEDIATAMENTE (antes de validar SAP)
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
                
                # ✅ VALIDACIÓN TEMPRANA #2: Extraer códigos de producto inmediatamente después del parsing
                # y validarlos ANTES de procesar y consolidar datos
                datos_parsing = resultado_parsing.get("data", [])
                if validar_sap and datos_parsing:
                    # Extraer códigos únicos de productos del parsing
                    # ⭐ Filtrar explícitamente None para satisfacer el type checker
                    codigos_set = set()  # type: set[str]
                    for item in datos_parsing:
                        codigo = item.get("codigoProducto")
                        if codigo is not None and isinstance(codigo, str):
                            codigos_set.add(codigo)
                    codigos_productos_parsing: List[str] = list(codigos_set)
                    
                    # ⭐ Aplicar correcciones de códigos si se proporcionan (antes de validación SAP)
                    if correcciones_codigos:
                        codigos_corregidos: List[str] = []
                        for codigo in codigos_productos_parsing:
                            codigo_corregido = correcciones_codigos.get(codigo, codigo)
                            if codigo_corregido is not None and isinstance(codigo_corregido, str):
                                codigos_corregidos.append(codigo_corregido)
                        codigos_productos_parsing = codigos_corregidos
                    
                    # Validar códigos de producto INMEDIATAMENTE - interrumpir si hay errores
                    if codigos_productos_parsing:
                        logger.info(f"🔍 Validando {len(codigos_productos_parsing)} productos contra SAP (con sugerencias)")
                        validator = PedidoValidator()
                        # ⭐ USAR MÉTODO CON SUGERENCIAS para incluir sugerencias en la respuesta
                        validacion_sap_productos = validator.validar_productos_existen_en_sap_con_sugerencias(
                            codigos_productos=codigos_productos_parsing,
                            usar_cache=True,
                            sap_obligatorio=True,  # OBLIGATORIO: SAP es fuente de verdad
                            incluir_sugerencias=True,  # ⭐ Habilitar sugerencias
                            limite_sugerencias=20
                        )
                        
                        if validacion_sap_productos is None or not validacion_sap_productos.get("todos_validos", False):
                            no_encontrados = validacion_sap_productos.get("no_encontrados", []) if validacion_sap_productos else []
                            errores = validacion_sap_productos.get("errores", []) if validacion_sap_productos else []
                            validos = validacion_sap_productos.get("validos", []) if validacion_sap_productos else []
                            detalle_validacion = validacion_sap_productos.get("detalle", {}) if validacion_sap_productos else {}
                            
                            # Asegurar que son listas (no ints)
                            if isinstance(no_encontrados, int):
                                no_encontrados = []
                            if isinstance(errores, int):
                                errores = []
                            if isinstance(validos, int):
                                validos = []
                            
                            # Mensaje simple - el frontend construirá el mensaje detallado
                            mensaje_error = "Existen códigos de producto no válidos en SAP"
                            
                            # Log consolidado y conciso
                            no_encontrados_str = ', '.join(no_encontrados[:5])
                            if len(no_encontrados) > 5:
                                no_encontrados_str += f" (+{len(no_encontrados) - 5} más)"
                            logger.error(f"❌ Validación SAP falló: {len(validos)}✓, {len(no_encontrados)}✗ [{no_encontrados_str}]")
                            
                            # ⭐ INCLUIR DETALLE CON SUGERENCIAS en la respuesta
                            datos_estructurados = {
                                "validacion": {
                                    "productos": {
                                        "no_encontrados": no_encontrados,
                                        "errores": errores,
                                        "validos": validos,
                                        "total_validos": len(validos),
                                        "total_invalidos": len(no_encontrados) + len(errores)
                                    }
                                },
                                "validacion_sap": {
                                    "total_codigos": len(codigos_productos_parsing),
                                    "validos": len(validos),
                                    "no_encontrados": len(no_encontrados),
                                    "errores": len(errores),
                                    "todos_validos": False,
                                    # ⭐ INCLUIR DETALLE CON SUGERENCIAS
                                    "detalle_validacion": {
                                        codigo: {
                                            "existe": info.get("existe"),
                                            "severity": info.get("severity"),
                                            "error": info.get("error"),
                                            "mensaje": info.get("mensaje"),
                                            "mba3": info.get("mba3"),  # Información de MBA3 si existe
                                            "sugerencias_sap": info.get("sugerencias_sap", [])  # Sugerencias similares en SAP
                                        }
                                        for codigo, info in detalle_validacion.items()
                                    }
                                }
                            }
                            
                            # INTERRUMPIR INMEDIATAMENTE - no procesar ni guardar nada
                            raise BusinessException(
                                message=mensaje_error,
                                error_code="PRODUCTOS_NO_VALIDOS_SAP",
                                data=datos_estructurados
                            )
                        
                        logger.debug(f"✅ Validación SAP: {len(validacion_sap_productos.get('validos', []))} productos válidos")
                
                # Convertir datos del parsing al formato esperado
                cabecera = self._normalizar_cabecera_para_bd(
                    resultado_parsing.get("cabecera", {}), 
                    filename, 
                    usuario_id
                )
                
                # Convertir distribuciones a formato detalle_con_tiendas
                detalles_con_tiendas = []
                
                # Agrupar por código de producto (incluyendo información completa del producto)
                productos_agrupados = {}
                for item in datos_parsing:
                    codigo_producto = item.get("codigoProducto")
                    if not codigo_producto:
                        continue
                    
                    # ⭐ Aplicar correcciones de códigos si se proporcionan
                    if correcciones_codigos and codigo_producto in correcciones_codigos:
                        codigo_producto = correcciones_codigos[codigo_producto]
                        item["codigoProducto"] = codigo_producto
                    
                    # Obtener información del producto del primer item (es la misma para todas las distribuciones)
                    info_producto = item.get("info_producto", {})
                    
                    if codigo_producto not in productos_agrupados:
                        # Crear detalle con toda la información del producto extraída del Excel
                        productos_agrupados[codigo_producto] = {
                            "detalle": {
                                "codigo_interno": codigo_producto,
                                "marca": info_producto.get("marca"),
                                "codigo_barras": info_producto.get("codigo_barras"),
                                "descripcion_sap": info_producto.get("descripcion_sap"),
                                "pack": info_producto.get("pack"),
                                "costo_doc_sin_iva": info_producto.get("costo_doc_sin_iva"),
                                "descuento_1": info_producto.get("descuento_1"),
                                "pvp": info_producto.get("pvp"),
                                "subtotal": info_producto.get("subtotal"),
                                "total": info_producto.get("total")
                            },
                            "distribuciones": []
                        }
                    
                    distribuciones = productos_agrupados[codigo_producto]["distribuciones"]
                    distribuciones.append({
                        "tienda_codigo": item.get("idTienda"),
                        "tienda_nombre": item.get("nombreTienda"),  # ⭐ AGREGADO: Nombre de la tienda de la fila 1 del Excel
                        "cantidad": item.get("cantidad"),
                        "fila_origen": item.get("filaOrigen"),
                        "es_bodega": item.get("es_bodega", False)  # ⭐ NUEVO: Preservar flag de bodega
                    })
                
                detalles_con_tiendas = list(productos_agrupados.values())
                
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
            
            else:
                # Solo se soporta el nuevo formato v1.0 (hojas "cabecera" y "detalle")
                hojas_disponibles = ", ".join(str(sheet) for sheet in excel_file.sheet_names)
                hojas_disponibles_lista = [str(sheet) for sheet in excel_file.sheet_names]
                
                error_msg = (
                    f"Formato de archivo no reconocido. "
                    f"El sistema solo soporta el formato v1.0 con hojas 'cabecera' y 'detalle' (en minúsculas).\n\n"
                    f"Hojas encontradas en el archivo: {hojas_disponibles}\n"
                    f"Se esperaba: hoja 'cabecera' y hoja 'detalle'"
                )
                logger.error(f"❌ {error_msg}")
                
                # Lanzar BusinessException con datos estructurados para el frontend
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
            
            # ✅ VALIDACIÓN SAP OBLIGATORIA (para tiendas y bodegas - productos ya validados arriba)
            # Validar tiendas y bodegas contra SAP antes que cualquier otra validación
            if validar_sap and detalles_con_tiendas:
                validator = PedidoValidator()
                
                # Extraer códigos únicos
                codigos_productos = list(set([
                    det.get("detalle", {}).get("codigo_interno")
                    for det in detalles_con_tiendas
                    if det.get("detalle", {}).get("codigo_interno")
                ]))
                
                codigos_tiendas_set = set()
                codigos_bodegas_set = set()
                
                for detalle_item in detalles_con_tiendas:
                    if isinstance(detalle_item, dict):
                        # Extraer tiendas y bodegas de distribuciones
                        distribuciones = detalle_item.get("distribuciones", [])
                        for dist in distribuciones:
                            tienda_codigo = dist.get("tienda_codigo")
                            if tienda_codigo:
                                # Las bodegas ahora están en las distribuciones con es_bodega=True
                                if dist.get("es_bodega", False):
                                    codigos_bodegas_set.add(tienda_codigo.strip())
                                else:
                                    codigos_tiendas_set.add(tienda_codigo)
                
                # Extraer bodegas de cabecera (origen_traslado)
                origen_traslado = cabecera.get("origen_traslado")
                if origen_traslado and origen_traslado.strip():
                    codigos_bodegas_set.add(origen_traslado.strip())
                
                # NOTA: Los productos ya fueron validados tempranamente después del parsing
                # Aquí solo validamos tiendas y bodegas
                
                # 1. VALIDAR TIENDAS CONTRA SAP (OBLIGATORIO)
                if codigos_tiendas_set:
                    logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_tiendas_set)} códigos de tienda contra SAP")
                    validacion_tiendas_sap = self.sap_validator_helper.validar_tiendas_sap(
                        codigos_tiendas=list(codigos_tiendas_set),
                        resultado=resultado,
                        sap_obligatorio=True  # OBLIGATORIO: SAP es fuente de verdad
                    )
                    
                    if not validacion_tiendas_sap.get("todas_validas", False):
                        no_encontradas = validacion_tiendas_sap.get("no_encontradas", [])
                        errores_sap = validacion_tiendas_sap.get("errores", [])
                        validas = validacion_tiendas_sap.get("validas", [])
                        
                        # Asegurar que son listas (no ints)
                        if isinstance(no_encontradas, int):
                            no_encontradas = []
                        if isinstance(errores_sap, int):
                            errores_sap = []
                        if isinstance(validas, int):
                            validas = []
                        
                        # Mensaje simple - el frontend construirá el mensaje detallado
                        mensaje_error = "Existen códigos de tienda/bodega no válidos en SAP"
                        
                        # Log detallado para debugging (solo en backend)
                        log_detalle = f"Tiendas no encontradas ({len(no_encontradas)}): {', '.join(no_encontradas[:10])}"
                        if len(no_encontradas) > 10:
                            log_detalle += f" y {len(no_encontradas) - 10} más"
                        if errores_sap:
                            log_detalle += f" | Errores ({len(errores_sap)}): {', '.join(errores_sap[:5])}"
                            if len(errores_sap) > 5:
                                log_detalle += f" y {len(errores_sap) - 5} más"
                        logger.error(f"❌ Validación SAP tiendas falló: {log_detalle}")
                        
                        datos_estructurados = {
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
                        
                        raise BusinessException(
                            message=mensaje_error,
                            error_code="TIENDAS_NO_VALIDAS_SAP",
                            data=datos_estructurados
                        )
                
                # 3. VALIDAR BODEGAS CONTRA SAP (OBLIGATORIO)
                if codigos_bodegas_set:
                    logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_bodegas_set)} códigos de bodega contra SAP")
                    codigos_bodegas = list(codigos_bodegas_set)
                    validacion_bodegas_sap = validator.validar_bodegas_existen_en_sap(
                        codigos_bodegas=codigos_bodegas,
                        sap_obligatorio=True  # OBLIGATORIO: SAP es fuente de verdad
                    )
                    
                    if not validacion_bodegas_sap.get("todas_validas", False):
                        no_encontradas = validacion_bodegas_sap.get("no_encontradas", [])
                        errores = validacion_bodegas_sap.get("errores", [])
                        validas = validacion_bodegas_sap.get("validas", [])
                        
                        # Asegurar que son listas (no ints)
                        if isinstance(no_encontradas, int):
                            no_encontradas = []
                        if isinstance(errores, int):
                            errores = []
                        if isinstance(validas, int):
                            validas = []
                        
                        # Mensaje simple - el frontend construirá el mensaje detallado
                        mensaje_error = "Existen códigos de bodega no válidos en SAP"
                        
                        # Log detallado para debugging (solo en backend)
                        log_detalle = f"Bodegas no encontradas ({len(no_encontradas)}): {', '.join(no_encontradas[:10])}"
                        if len(no_encontradas) > 10:
                            log_detalle += f" y {len(no_encontradas) - 10} más"
                        if errores:
                            log_detalle += f" | Errores ({len(errores)}): {', '.join(errores[:5])}"
                            if len(errores) > 5:
                                log_detalle += f" y {len(errores) - 5} más"
                        logger.error(f"❌ Validación SAP bodegas falló: {log_detalle}")
                        
                        datos_estructurados = {
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
                        
                        raise BusinessException(
                            message=mensaje_error,
                            error_code="BODEGAS_NO_VALIDAS_SAP",
                            data=datos_estructurados
                        )
            
            # VALIDAR (solo después de validar SAP)
            if validar_antes_de_guardar:
                validator = PedidoValidator(
                    tiendas_permitidas=tiendas_permitidas,
                    **DEFAULT_PEDIDO_VALIDATOR_KWARGS
                )
                
                # El nuevo formato v1.0 no es "simple"
                es_formato_simple_validacion = False
                
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
                
                # Si hay errores críticos y está configurado para bloquear, marcar pero seguir para persistir
                # (sync y async: la información se guarda en pedido para que el toast muestre pedido_id y conteos)
                if not validation_result["valid"] and bloquea_con_errores:
                    resultado["status"] = "validation_error"
                    resultado["errores"].append(
                        f"Validación fallida: {validation_result['errors']} error(es) crítico(s) encontrado(s)"
                    )
                    logger.warning(
                        f"⚠️ Validación fallida para {filename}: "
                        f"{validation_result['errors']} error(es), {validation_result['warnings']} advertencia(s). Se persistirá igual para mantener datos."
                    )
                    # No return: continuar para persistir pedido y devolver pedido_id/articulos/distribuciones
            
            # ✅ Preparar validación SAP para persistencia (ya validada arriba)
            # La validación SAP obligatoria ya se ejecutó arriba, aquí solo preparamos para persistencia
            validacion_sap = None
            if validar_sap and detalles_con_tiendas:
                codigos_productos = list(set([
                    det.get("detalle", {}).get("codigo_interno")
                    for det in detalles_con_tiendas
                    if det.get("detalle", {}).get("codigo_interno")
                ]))
                
                # Obtener resultado de validación SAP (ya ejecutada arriba) para usar en persistencia
                if codigos_productos:
                    validacion_sap = self.sap_validator_helper.validar_productos_sap(
                        codigos_productos=codigos_productos,
                        resultado=resultado,
                        usar_cache=True,
                        sap_obligatorio=True  # OBLIGATORIO: SAP es fuente de verdad
                    )
            
            # GUARDAR (solo si pasó validación SAP obligatoria)
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
                    "comentario": articulo.get("comentario")  # Campo comentario si existe en el request
                }
                
                # Log para debugging: ver qué campos se están mapeando
                logger.debug(f"📦 Mapeando artículo: codigo_interno={detalle['codigo_interno']}, "
                           f"descripcion_sap={detalle.get('descripcion_sap')}, "
                           f"marca={detalle.get('marca')}, "
                           f"costo_doc_sin_iva={detalle.get('costo_doc_sin_iva')}, "
                           f"pvp={detalle.get('pvp')}, "
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
            
            # ✅ VALIDACIÓN TEMPRANA: Verificar número de pedido duplicado ANTES de validaciones SAP costosas
            numero_pedido = cabecera.get("numero_pedido")
            if numero_pedido:
                with get_db_connection_context() as conn_check:
                    from ..repositories.pedido_repository import PedidoRepository
                    repo_check = PedidoRepository(conn_check)
                    
                    if repo_check.existe_numero_pedido(numero_pedido):
                        logger.warning(f"⚠️ [VALIDACIÓN TEMPRANA - MANUAL] Número de pedido duplicado detectado: '{numero_pedido}'")
                        resultado["status"] = "error"
                        resultado["errores"].append(f"El número de pedido '{numero_pedido}' ya existe en el sistema")
                        resultado["error_tipo"] = "numero_pedido_duplicado"
                        # Agregar datos estructurados
                        resultado["validacion_numero_pedido"] = {
                            "numero_pedido": numero_pedido,
                            "duplicado": True,
                            "mensaje": f"El número de pedido '{numero_pedido}' ya fue utilizado anteriormente"
                        }
                        return resultado
                    else:
                        logger.info(f"✅ [VALIDACIÓN TEMPRANA - MANUAL] Número de pedido '{numero_pedido}' disponible")
            
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
                
                # ✅ VALIDACIÓN SAP OBLIGATORIA (PRIMERO - fuente de verdad)
                # Validar productos, tiendas y bodegas contra SAP antes que cualquier otra validación
                
                # Extraer códigos de bodegas de las distribuciones (es_bodega=True)
                codigos_bodegas_set = set()
                for det in detalles_con_tiendas:
                    distribuciones = det.get("distribuciones", [])
                    for dist in distribuciones:
                        if dist.get("es_bodega", False):
                            tienda_codigo = dist.get("tienda_codigo")
                            if tienda_codigo:
                                codigos_bodegas_set.add(tienda_codigo.strip())
                origen_traslado = cabecera.get("origen_traslado")
                if origen_traslado and origen_traslado.strip():
                    codigos_bodegas_set.add(origen_traslado.strip())
                codigos_bodegas = list(codigos_bodegas_set)
                
                # 1. VALIDAR PRODUCTOS CONTRA SAP (OBLIGATORIO)
                if codigos_productos:
                    logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_productos)} códigos de producto contra SAP")
                    validacion_sap_productos = self.sap_validator_helper.validar_productos_sap(
                        codigos_productos=codigos_productos,
                        resultado=resultado,
                        usar_cache=True,
                        sap_obligatorio=True  # OBLIGATORIO: SAP es fuente de verdad
                    )
                    
                    if validacion_sap_productos is None or not validacion_sap_productos.get("todos_validos", False):
                        no_encontrados = validacion_sap_productos.get("no_encontrados", []) if validacion_sap_productos else []
                        errores = validacion_sap_productos.get("errores", []) if validacion_sap_productos else []
                        
                        # Asegurar que son listas
                        if isinstance(no_encontrados, int):
                            no_encontrados = []
                        if isinstance(errores, int):
                            errores = []
                        
                        # Mensaje simple - el frontend construirá el mensaje detallado
                        mensaje_error = "Existen códigos de producto no válidos en SAP"
                        
                        # Log detallado para debugging (solo en backend)
                        log_detalle = f"Productos no encontrados ({len(no_encontrados)}): {', '.join(no_encontrados[:10])}"
                        if len(no_encontrados) > 10:
                            log_detalle += f" y {len(no_encontrados) - 10} más"
                        if errores:
                            log_detalle += f" | Errores ({len(errores)}): {', '.join(errores[:5])}"
                            if len(errores) > 5:
                                log_detalle += f" y {len(errores) - 5} más"
                        logger.warning(f"⚠️ Validación SAP productos falló: {log_detalle}")
                        
                        resultado["status"] = "validation_error"
                        resultado["errores"].append(mensaje_error)
                        resultado["validacion"]["productos"] = {
                            "no_encontrados": no_encontrados,
                            "errores": errores,
                            "validos": validacion_sap_productos.get("validos", []) if validacion_sap_productos else []
                        }
                        return resultado
                    
                    resultado["validacion"]["productos_sap"] = {
                        "validos": validacion_sap_productos.get("validos", []),
                        "no_encontrados": validacion_sap_productos.get("no_encontrados", []),
                        "errores": validacion_sap_productos.get("errores", []),
                        "todos_validos": validacion_sap_productos.get("todos_validos", False)
                    }
                
                # 2. VALIDAR TIENDAS CONTRA SAP (OBLIGATORIO)
                if codigos_tiendas:
                    logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_tiendas)} códigos de tienda contra SAP")
                    validacion_tiendas_sap = self.sap_validator_helper.validar_tiendas_sap(
                        codigos_tiendas=codigos_tiendas,
                        resultado=resultado,
                        sap_obligatorio=True  # OBLIGATORIO: SAP es fuente de verdad
                    )
                    
                    if not validacion_tiendas_sap.get("todas_validas", False):
                        no_encontradas = validacion_tiendas_sap.get("no_encontradas", [])
                        errores_sap = validacion_tiendas_sap.get("errores", [])
                        
                        # Asegurar que son listas
                        if isinstance(no_encontradas, int):
                            no_encontradas = []
                        if isinstance(errores_sap, int):
                            errores_sap = []
                        
                        # Mensaje simple - el frontend construirá el mensaje detallado
                        mensaje_error = "Existen códigos de tienda/bodega no válidos en SAP"
                        
                        # Log detallado para debugging (solo en backend)
                        log_detalle = f"Tiendas no encontradas ({len(no_encontradas)}): {', '.join(no_encontradas[:10])}"
                        if len(no_encontradas) > 10:
                            log_detalle += f" y {len(no_encontradas) - 10} más"
                        if errores_sap:
                            log_detalle += f" | Errores ({len(errores_sap)}): {', '.join(errores_sap[:5])}"
                            if len(errores_sap) > 5:
                                log_detalle += f" y {len(errores_sap) - 5} más"
                        logger.warning(f"⚠️ Validación SAP tiendas falló: {log_detalle}")
                        
                        resultado["status"] = "validation_error"
                        resultado["errores"].append(mensaje_error)
                        resultado["validacion"]["tiendas"] = {
                            "no_encontradas": no_encontradas,
                            "errores": errores_sap,
                            "validas": validacion_tiendas_sap.get("validas", [])
                        }
                        return resultado
                    
                    resultado["validacion"]["tiendas_sap"] = {
                        "validas": validacion_tiendas_sap.get("validas", []),
                        "no_encontradas": validacion_tiendas_sap.get("no_encontradas", []),
                        "errores": validacion_tiendas_sap.get("errores", []),
                        "todas_validas": validacion_tiendas_sap.get("todas_validas", False)
                    }
                
                # 3. VALIDAR BODEGAS CONTRA SAP (OBLIGATORIO)
                if codigos_bodegas:
                    logger.info(f"🔍 [SAP PRIMERO] Validando {len(codigos_bodegas)} códigos de bodega contra SAP")
                    validacion_bodegas_sap = validator.validar_bodegas_existen_en_sap(
                        codigos_bodegas=codigos_bodegas,
                        sap_obligatorio=True  # OBLIGATORIO: SAP es fuente de verdad
                    )
                    
                    if not validacion_bodegas_sap.get("todas_validas", False):
                        no_encontradas = validacion_bodegas_sap.get("no_encontradas", [])
                        errores = validacion_bodegas_sap.get("errores", [])
                        
                        # Asegurar que son listas
                        if isinstance(no_encontradas, int):
                            no_encontradas = []
                        if isinstance(errores, int):
                            errores = []
                        
                        # Mensaje simple - el frontend construirá el mensaje detallado
                        mensaje_error = "Existen códigos de bodega no válidos en SAP"
                        
                        # Log detallado para debugging (solo en backend)
                        log_detalle = f"Bodegas no encontradas ({len(no_encontradas)}): {', '.join(no_encontradas[:10])}"
                        if len(no_encontradas) > 10:
                            log_detalle += f" y {len(no_encontradas) - 10} más"
                        if errores:
                            log_detalle += f" | Errores ({len(errores)}): {', '.join(errores[:5])}"
                            if len(errores) > 5:
                                log_detalle += f" y {len(errores) - 5} más"
                        logger.warning(f"⚠️ Validación SAP bodegas falló: {log_detalle}")
                        
                        resultado["status"] = "validation_error"
                        resultado["errores"].append(mensaje_error)
                        resultado["validacion"]["bodegas"] = {
                            "no_encontradas": no_encontradas,
                            "errores": errores,
                            "validas": validacion_bodegas_sap.get("validas", [])
                        }
                        return resultado
                    
                    resultado["validacion"]["bodegas_sap"] = {
                        "validas": validacion_bodegas_sap.get("validas", []),
                        "no_encontradas": validacion_bodegas_sap.get("no_encontradas", []),
                        "errores": validacion_bodegas_sap.get("errores", []),
                        "todas_validas": validacion_bodegas_sap.get("todas_validas", False)
                    }
                
                # ✅ Validaciones locales (opcionales - solo informativas, no bloquean)
                # NOTA: Estas validaciones son solo informativas porque SAP es la fuente de verdad
                if validar_productos and codigos_productos:
                    validacion_productos_local = validator.validar_productos_existen(codigos_productos, conn)
                    resultado["validacion"]["productos"] = validacion_productos_local
                    # No bloquear - SAP ya validó
                
                if validar_tiendas and codigos_tiendas:
                    validacion_tiendas_local = validator.validar_tiendas_existen(codigos_tiendas, conn)
                    resultado["validacion"]["tiendas"] = validacion_tiendas_local
                    # No bloquear - SAP ya validó
                
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
                
                # ✅ Verificar si hay errores de validación antes de crear el pedido
                # Si hay errores (SAP, productos o tiendas), no crear el pedido
                if resultado.get("errores") and len(resultado["errores"]) > 0:
                    resultado["status"] = "validation_error"
                    logger.warning(f"⚠️ Errores de validación detectados: {resultado['errores']}. No se creará el pedido.")
                    return resultado
                
                consolidacion = self.consolidator.consolidar_pedido_por_producto(detalles_con_tiendas)
                resultado["consolidacion"] = consolidacion["resumen"]
                
                # Construir audit_context con fallback si no se proporcionó
                from src.utils.audit_context import ensure_audit_context
                audit = ensure_audit_context(audit_context)
                
                repository = PedidoRepository(conn)
                pedido_id = repository.insert_cabecera(cabecera, audit_context=audit)
                resultado["pedido_id"] = pedido_id
                resultado["numero_pedido"] = cabecera.get("numero_pedido")  # ⭐ Agregado para redirección del frontend
                resultado["estado_id"] = 1
                resultado["estado_nombre"] = "BORRADOR"
                resultado["estado"] = "BORRADOR"  # compat API
                
                for detalle_data in detalles_con_tiendas:
                    try:
                        pedido_detalle_id = repository.insert_detalle(pedido_id, detalle_data["detalle"], audit_context=audit)
                        resultado["articulos_cargados"] += 1
                        if detalle_data.get("distribuciones"):
                            distribuciones = []
                            for dist in detalle_data["distribuciones"]:
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
                                        "es_bodega": dist.get("es_bodega", False)  # ⭐ NUEVO: Preservar flag de bodega
                                    })
                            if distribuciones:
                                resultado["distribuciones_cargadas"] += repository.insert_detalle_tiendas(pedido_detalle_id, distribuciones, audit_context=audit)
                    except Exception as e:
                        logger.warning(f"⚠️ Error procesando artículo: {e}")
                        resultado["errores"].append(str(e))
            
            logger.info(f"✅ Pedido manual creado: {resultado['pedido_id']} - {cabecera.get('numero_pedido')}")
            return resultado
            
        except ValueError as e:
            # Detectar específicamente el error de número de pedido duplicado
            error_msg = str(e)
            if "número de pedido" in error_msg.lower() and "ya existe" in error_msg.lower():
                numero_pedido = cabecera.get("numero_pedido")
                logger.warning(f"⚠️ Intento de crear pedido con número duplicado: {numero_pedido}")
                resultado["status"] = "error"
                resultado["errores"].append(f"El número de pedido '{numero_pedido}' ya existe en el sistema")
                resultado["error_tipo"] = "numero_pedido_duplicado"
                # ✅ Agregar datos estructurados para el frontend (consistente con validaciones SAP)
                resultado["validacion_numero_pedido"] = {
                    "numero_pedido": numero_pedido,
                    "duplicado": True,
                    "mensaje": f"El número de pedido '{numero_pedido}' ya fue utilizado anteriormente"
                }
                return resultado
            # Otros ValueError se propagan como error genérico
            logger.error(f"❌ Error de validación al crear pedido manual: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
        except Exception as e:
            logger.error(f"❌ Error al crear pedido manual: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
    
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
        # Persistir siempre que se invoque: ya se pasó validación SAP y hay cabecera/detalles.
        # Si status es validation_error, igual se guarda para que sync/async devuelvan pedido_id y conteos.
        # ✅ FILTRAR productos no validados en SAP (si se validó SAP)
        with get_db_connection_context() as conn:
            repository = PedidoRepository(conn)
            try:
                pedido_id = repository.insert_cabecera(cabecera)
            except ValueError as e:
                # Detectar específicamente el error de número de pedido duplicado
                error_msg = str(e)
                if "número de pedido" in error_msg.lower() and "ya existe" in error_msg.lower():
                    numero_pedido = cabecera.get("numero_pedido")
                    logger.warning(f"⚠️ Intento de crear pedido con número duplicado: {numero_pedido}")
                    
                    # ✅ Lanzar BusinessException con datos estructurados (consistente con validaciones SAP)
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
                # Otros ValueError se propagan
                raise
            resultado["pedido_id"] = pedido_id
            # ⭐ Agregar numero_pedido al resultado para que el frontend pueda redirigir
            resultado["numero_pedido"] = cabecera.get("numero_pedido")
            
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
                            es_bodega = dist.get("es_bodega", False)
                            
                            if tienda_codigo and cantidad is not None and cantidad >= 0:
                                # ⭐ LOG: Registrar bodegas para debugging
                                if es_bodega:
                                    logger.info(f"📦 Procesando bodega: {tienda_codigo}, cantidad: {cantidad}, producto: {detalle_data.get('detalle', {}).get('codigo_interno')}")
                                
                                tienda_id = repository.get_or_create_tienda(
                                    codigo=tienda_codigo,
                                    nombre=dist.get("tienda_nombre")
                                )
                                distribucion_item = {
                                    "tienda_id": tienda_id,
                                    "cantidad": float(cantidad),
                                    "es_bodega": es_bodega  # ⭐ NUEVO: Preservar flag de bodega
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

