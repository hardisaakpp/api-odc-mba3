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
from typing import Dict, Any, List, Optional
from datetime import datetime, date
import io

from src.config import ENABLE_SQL_SERVER_STORAGE
from src.exceptions import BusinessException
from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository
from .pedido_validator import PedidoValidator, ValidationSeverity
from .pedido_parser import PedidoParser
from .pedido_consolidator import PedidoConsolidator

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
            df_raw = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=None)
            
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
    
    def validar_y_procesar_archivo_excel(
        self,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str] = None,
        validar_antes_de_guardar: bool = True,
        tiendas_permitidas: Optional[List[str]] = None,
        bloquea_con_errores: bool = True,
        validar_sap: bool = True,
        sap_obligatorio: bool = True
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
            # Detectar formato: verificar hojas del Excel
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            
            # Buscar hojas con nombres similares (case-insensitive, tolerante a espacios)
            hoja_cabecera_encontrada = None
            hoja_detalle_encontrada = None
            hoja_movimiento_encontrada = None
            hoja_tiendas_encontrada = None
            
            logger.info(f"📄 Hojas encontradas en el Excel: {excel_file.sheet_names}")
            
            for sheet_name in excel_file.sheet_names:
                sheet_name_upper = str(sheet_name).upper().strip()
                # Buscar variaciones de CABECERA_PEDIDO
                if not hoja_cabecera_encontrada:
                    if ("CABECERA" in sheet_name_upper and "PEDIDO" in sheet_name_upper) or \
                       sheet_name_upper == "CABECERA_PEDIDO" or \
                       sheet_name_upper == "CABECERA PEDIDO":
                        hoja_cabecera_encontrada = sheet_name
                        logger.info(f"✅ Hoja de cabecera detectada: '{sheet_name}'")
                
                # Buscar variaciones de DETALLE_ARTICULO
                if not hoja_detalle_encontrada:
                    if ("DETALLE" in sheet_name_upper and "ARTICULO" in sheet_name_upper) or \
                       ("DETALLE" in sheet_name_upper and "ARTÍCULO" in sheet_name_upper) or \
                       sheet_name_upper == "DETALLE_ARTICULO" or \
                       sheet_name_upper == "DETALLE ARTICULO":
                        hoja_detalle_encontrada = sheet_name
                        logger.info(f"✅ Hoja de detalle detectada: '{sheet_name}'")
                
                # Buscar variaciones de MOVIMIENTO (nuevo formato v1.0)
                if not hoja_movimiento_encontrada:
                    if sheet_name_upper == "MOVIMIENTO":
                        hoja_movimiento_encontrada = sheet_name
                        logger.info(f"✅ Hoja de movimiento detectada: '{sheet_name}'")
                
                # Buscar variaciones de TIENDAS (nuevo formato v1.0)
                if not hoja_tiendas_encontrada:
                    if sheet_name_upper == "TIENDAS":
                        hoja_tiendas_encontrada = sheet_name
                        logger.info(f"✅ Hoja de tiendas detectada: '{sheet_name}'")
            
            
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
                return self._procesar_formato_v1_0(
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
                    sap_obligatorio=sap_obligatorio
                )
            
            # Formato con dos hojas (Template_Pedido_Inicial_v1.0.xlsx)
            if tiene_cabecera_pedido and tiene_detalle_articulo:
                resultado["formato_detectado"] = "dos_hojas"
                logger.info("📋 Formato DOS HOJAS detectado: CABECERA_PEDIDO + DETALLE_ARTICULO")
                
                # PASO 1: Parsear cabecera usando _parsear_cabecera (soporta formato horizontal y vertical)
                excel_file_cabecera = pd.ExcelFile(io.BytesIO(file_content))
                cabecera_parseada = self.parser._parsear_cabecera(excel_file_cabecera, str(hoja_cabecera_encontrada))
                
                # Convertir cabecera a formato BD
                cabecera = self._normalizar_cabecera_para_bd(
                    cabecera_parseada=cabecera_parseada,
                    filename=filename,
                    usuario_id=usuario_id
                )
                # Coerción de fechas desde texto si aplica
                try:
                    valor_fecha_pedido = cabecera.get("fecha_pedido", cabecera.get("fecha_de_pedido"))
                    if valor_fecha_pedido is not None:
                        cabecera["fecha_pedido"] = self._parsear_fecha_texto(valor_fecha_pedido)
                    valor_fecha_entrega = cabecera.get("fecha_entrega", cabecera.get("fecha_de_entrega"))
                    if valor_fecha_entrega is not None:
                        cabecera["fecha_entrega"] = self._parsear_fecha_texto(valor_fecha_entrega)
                except Exception:
                    # No bloquear por error de parseo de fecha; se mantiene valor original
                    pass
                
                # PASO 2: Detectar formato de la hoja de detalle
                # Leer TODAS las columnas (no solo 5 filas) para detectar columnas ROLAND
                df_detalle_detection = pd.read_excel(
                    excel_file_cabecera, 
                    sheet_name=str(hoja_detalle_encontrada), 
                    header=0, 
                    nrows=1,
                    keep_default_na=False
                )
                df_detalle_detection.columns = [str(col).strip() if pd.notna(col) and str(col).strip() != "" else "" 
                                               for col in df_detalle_detection.columns]
                
                logger.info(f"🔍 Columnas encontradas en detalle (primeras 20): {list(df_detalle_detection.columns)[:20]}")
                logger.info(f"🔍 Total de columnas: {len(df_detalle_detection.columns)}")
                
                # Verificar si tiene columnas de tiendas (formato complejo)
                # Soporta dos formatos:
                # 1. Formato antiguo: "ROLAND QUICENTRO NORTE", "ROLAND CC EL BOSQUE"
                # 2. Formato nuevo: "ROL01", "ROL02", etc. (códigos cortos)
                columnas_tiendas = []
                import re
                for col in df_detalle_detection.columns:
                    col_upper = str(col).upper().strip()
                    
                    # Formato nuevo: detectar códigos tipo ROL01, ROL02, etc.
                    # Patrón: 3 letras mayúsculas + 2 dígitos
                    es_codigo_tienda = bool(re.match(r'^[A-Z]{3}\d{2}$', col_upper))
                    
                    # Formato antiguo: buscar "ROLAND" en cualquier parte del nombre de la columna
                    es_formato_antiguo = "ROLAND" in col_upper and col_upper != "ROLAND"
                    
                    if es_codigo_tienda or es_formato_antiguo:
                        columnas_tiendas.append(col)
                
                logger.info(f"🔍 Todas las columnas (para debug): {list(df_detalle_detection.columns)}")
                
                has_columnas_tiendas = len(columnas_tiendas) > 0
                logger.info(f"🔍 Columnas de tiendas encontradas: {columnas_tiendas[:10]}")
                
                # Verificar si tiene formato simple (CodigoProducto, IdTienda, Cantidad)
                df_detalle_detection_lower = df_detalle_detection.copy()
                df_detalle_detection_lower.columns = [str(col).strip().lower() if pd.notna(col) else "" 
                                                      for col in df_detalle_detection_lower.columns]
                has_producto = any('codigoproducto' in col or 'codigo producto' in col for col in df_detalle_detection_lower.columns)
                has_idtienda = any('idtienda' in col or 'id tienda' in col for col in df_detalle_detection_lower.columns)
                has_cantidad = any('cantidad' in col for col in df_detalle_detection_lower.columns)
                
                # Si tiene columnas de tiendas, es formato complejo (prioridad)
                # Si no tiene columnas de tiendas pero tiene CodigoProducto, IdTienda, Cantidad, es simple
                is_detalle_simple = (has_producto and has_idtienda and has_cantidad) and not has_columnas_tiendas
                
                logger.info(f"🔍 Detección de formato detalle: has_columnas_tiendas={has_columnas_tiendas} ({len(columnas_tiendas)} columnas), has_producto={has_producto}, has_idtienda={has_idtienda}, has_cantidad={has_cantidad}, is_simple={is_detalle_simple}")
                if has_columnas_tiendas:
                    logger.info(f"   Columnas de tiendas encontradas: {columnas_tiendas[:5]}...")
                
                if is_detalle_simple:
                    # Formato simple: usar parsear_excel_pedido para el detalle
                    logger.info("📋 Detalle en formato SIMPLE (CodigoProducto, IdTienda, Cantidad)")
                    resultado_parsing = self.parsear_excel_pedido(
                        file_content=file_content,
                        hoja_cabecera=str(hoja_cabecera_encontrada),
                        hoja_detalle=str(hoja_detalle_encontrada)
                    )
                    
                    # Consolidar usando el consolidator
                    detalles_con_tiendas = self.consolidator.consolidar_detalles_simple(
                        resultado_parsing.get("data", [])
                    )
                else:
                    # Formato complejo: usar _extraer_detalle_con_tiendas
                    logger.info("📋 Detalle en formato COMPLEJO (columnas de tiendas)")
                    
                    # Leer hoja de tiendas si existe (nuevo formato v1.0)
                    catalogo_tiendas = self.parser.leer_hoja_tiendas(file_content)
                    if catalogo_tiendas:
                        logger.info(f"✅ Catálogo de tiendas cargado: {len(catalogo_tiendas)} tiendas")
                    
                    # Leer con header=0 porque la primera fila ya es el header
                    # Usar keep_default_na=False para no perder datos
                    try:
                        df_detalle = pd.read_excel(
                            excel_file_cabecera, 
                            sheet_name=hoja_detalle_encontrada, 
                            header=0,
                            keep_default_na=False
                        )
                        logger.info(f"📊 DataFrame detalle complejo leído: {len(df_detalle)} filas, {len(df_detalle.columns)} columnas")
                    except Exception as e:
                        logger.error(f"❌ Error al leer hoja de detalle: {e}")
                        # Intentar leer sin header y procesar manualmente
                        df_detalle_raw = pd.read_excel(
                            excel_file_cabecera, 
                            sheet_name=hoja_detalle_encontrada, 
                            header=None,
                            keep_default_na=False
                        )
                        logger.info(f"📊 Excel leído sin header: {len(df_detalle_raw)} filas totales")
                        if len(df_detalle_raw) > 0:
                            # Usar primera fila como header
                            df_detalle = df_detalle_raw.iloc[1:].copy()
                            df_detalle.columns = df_detalle_raw.iloc[0].values
                            df_detalle.columns = [str(col).strip() if pd.notna(col) and str(col).strip() != "" else f"col_{i}" 
                                                 for i, col in enumerate(df_detalle.columns)]
                            logger.info(f"📊 Después de procesar manualmente: {len(df_detalle)} filas")
                        else:
                            df_detalle = pd.DataFrame()
                    
                    if len(df_detalle) == 0:
                        logger.warning("⚠️ No se encontraron filas de datos en el formato complejo")
                        detalles_con_tiendas = []
                    else:
                        # Convertir a formato sin header para que _extraer_detalle_con_tiendas funcione
                        # Necesitamos que la primera fila sean los headers como valores
                        # Crear un nuevo DataFrame donde la primera fila son los nombres de columnas
                        df_detalle_sin_header = df_detalle.copy()
                        # Insertar los nombres de columnas como primera fila
                        # Convertir columns a list si no lo es ya
                        columnas_lista = list(df_detalle.columns) if not isinstance(df_detalle.columns, list) else df_detalle.columns
                        # Usar pd.Index para asegurar tipo correcto
                        columnas_index = pd.Index(columnas_lista) if not isinstance(df_detalle.columns, pd.Index) else df_detalle.columns
                        headers_row = pd.DataFrame([columnas_lista], columns=columnas_index)
                        df_detalle_sin_header = pd.concat([headers_row, df_detalle.reset_index(drop=True)], ignore_index=True)
                        # Resetear los nombres de columnas a índices numéricos (como strings)
                        df_detalle_sin_header.columns = [str(i) for i in range(len(df_detalle_sin_header.columns))]
                        
                        # Pasar catálogo de tiendas al parser
                        detalles_con_tiendas = self.parser.extraer_detalle_con_tiendas(
                            df_detalle_sin_header,
                            catalogo_tiendas=catalogo_tiendas
                        )
                        logger.info(f"✅ Detalles extraídos del formato complejo: {len(detalles_con_tiendas)} productos")
                
            else:
                # Detectar formato simple o complejo (legacy)
                df_detection = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=0, nrows=5)
                df_detection.columns = [str(col).strip().lower() if pd.notna(col) else "" 
                                       for col in df_detection.columns]
                
                # Detectar si es formato simple
                has_producto = any('codigoproducto' in col or 'producto' in col for col in df_detection.columns)
                has_idtienda = any('idtienda' in col or 'id tienda' in col for col in df_detection.columns)
                has_cantidad = any('cantidad' in col for col in df_detection.columns)
                
                is_formato_simple = has_producto and has_idtienda and has_cantidad
                
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
                        df_raw = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=None)
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
                    validator = PedidoValidator()
                    validacion_sap = validator.validar_productos_existen_en_sap(
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
                    
                    # 🔒 GUARDIA DURA: Si SAP es obligatorio y hay errores, NO persistir
                    if sap_obligatorio and not validacion_sap.get("todos_validos", False):
                        no_encontrados = validacion_sap.get("no_encontrados", [])
                        errores = validacion_sap.get("errores", [])
                        validos = validacion_sap.get("validos", [])
                        
                        # Construir mensaje legible (para logs y fallback)
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
                        
                        # Construir datos estructurados para el frontend
                        datos_estructurados = {
                            "validacion": {
                                "productos": {
                                    "no_encontrados": no_encontrados,
                                    "errores": errores,
                                    "total_validos": len(validos),
                                    "total_invalidos": len(no_encontrados) + len(errores)
                                }
                            },
                            "validacion_sap": {
                                "validos": len(validos),
                                "no_encontrados": len(no_encontrados),
                                "errores": len(errores),
                                "warnings": validacion_sap.get("warnings", 0),
                                "total_codigos": len(codigos_productos),
                                "todos_validos": False
                            }
                        }
                        
                        raise BusinessException(
                            message=mensaje_error,
                            error_code="PRODUCTOS_NO_VALIDOS_SAP",
                            data=datos_estructurados
                        )
                    
                    logger.info(
                        f"📊 Validación SAP: {len(validacion_sap.get('validos', []))} válidos, "
                        f"{len(validacion_sap.get('no_encontrados', []))} no encontrados"
                    )
            
            # GUARDAR (solo si pasó validación o no se valida)
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
                df_raw = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=None)
                cabecera = self.parser.extraer_cabecera(df_raw, filename, usuario_id)
                detalles_con_tiendas = self.parser.extraer_detalle_con_tiendas(df_raw)
                es_formato_simple = False
            
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
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Procesa el nuevo formato v1.0 con 4 hojas:
        1. Cabecera Pedido: Metadatos del pedido
        2. Detalle Articulos: Catálogo de productos
        3. Movimiento: Distribuciones por tienda (CodigoProducto, Tienda, Cantidad)
        4. Tiendas: Maestro de tiendas con validación

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
            # PASO 1: Leer y procesar hoja de Tiendas
            logger.info("📋 PASO 1: Procesando hoja de Tiendas")
            catalogo_tiendas = self.parser.leer_hoja_tiendas(file_content)
            if not catalogo_tiendas:
                resultado["warnings"].append("⚠️ No se encontró o está vacía la hoja 'Tiendas'")
                logger.warning("⚠️ Catálogo de tiendas vacío, continuando con validación")
            else:
                resultado["resumen"]["tiendas_validadas"] = len(catalogo_tiendas)
                resultado["resumen"]["hojas_procesadas"].append("Tiendas")
                logger.info(f"✅ Tiendas cargadas: {len(catalogo_tiendas)}")
            
            # PASO 2: Leer y procesar hoja de Cabecera Pedido
            logger.info("📋 PASO 2: Procesando hoja de Cabecera Pedido")
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            cabecera_parseada = self.parser._parsear_cabecera(excel_file, hoja_cabecera)
            
            cabecera = self._normalizar_cabecera_para_bd(
                cabecera_parseada=cabecera_parseada,
                filename=filename,
                usuario_id=usuario_id
            )
            # Coerción de fechas desde texto si aplica
            try:
                valor_fecha_pedido = cabecera.get("fecha_pedido", cabecera.get("fecha_de_pedido"))
                if valor_fecha_pedido is not None:
                    cabecera["fecha_pedido"] = self._parsear_fecha_texto(valor_fecha_pedido)
                valor_fecha_entrega = cabecera.get("fecha_entrega", cabecera.get("fecha_de_entrega"))
                if valor_fecha_entrega is not None:
                    cabecera["fecha_entrega"] = self._parsear_fecha_texto(valor_fecha_entrega)
            except Exception:
                # No bloquear por error de parseo de fecha; se mantiene valor original
                pass
            resultado["resumen"]["hojas_procesadas"].append("Cabecera Pedido")
            logger.info(f"✅ Cabecera parseada: {cabecera.get('numero_pedido', 'SIN NÚMERO')}")
            
            # PASO 3: Leer y procesar hoja de Detalle Articulos
            logger.info("📋 PASO 3: Procesando hoja de Detalle Articulos")
            df_detalle = pd.read_excel(
                excel_file,
                sheet_name=hoja_detalle,
                header=0,
                keep_default_na=False
            )
            
            # Normalizar columnas para búsqueda flexible
            df_detalle.columns = [str(col).strip() for col in df_detalle.columns]
            
            # Buscar columnas importantes
            col_codigo = None
            col_descripcion = None
            col_marca = None
            col_codigo_barras = None
            col_pack = None
            col_costo = None
            col_descuento = None
            col_pvp = None
            col_bodega = None
            
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
                return resultado
            
            logger.info(f"   Columnas detectadas: codigo='{col_codigo}', descripcion='{col_descripcion}', marca='{col_marca}'")
            
            # Cargar productos en un diccionario para referencia rápida
            productos_dict = {}
            for idx, row in df_detalle.iterrows():
                codigo = str(row.get(col_codigo, "")).strip()
                if not codigo:
                    continue
                
                productos_dict[codigo.upper()] = {
                    "codigo_interno": codigo.upper(),
                    "descripcion_sap": str(row.get(col_descripcion, "")).strip() if col_descripcion else None,
                    "marca": str(row.get(col_marca, "")).strip() if col_marca else None,
                    "codigo_barras": str(row.get(col_codigo_barras, "")).strip() if col_codigo_barras else None,
                    "pack": str(row.get(col_pack, "")).strip() if col_pack else None,
                    "costo_doc_sin_iva": self._convertir_a_decimal(row.get(col_costo)) if col_costo else None,
                    "descuento_1": self._convertir_a_decimal(row.get(col_descuento)) if col_descuento else None,
                    "pvp": self._convertir_a_decimal(row.get(col_pvp)) if col_pvp else None,
                    "bodega": self._convertir_a_entero(row.get(col_bodega)) if col_bodega else None,
                }
            
            resultado["resumen"]["productos_cargados"] = len(productos_dict)
            resultado["resumen"]["hojas_procesadas"].append("Detalle Articulos")
            logger.info(f"✅ Productos cargados en catálogo: {len(productos_dict)}")
            
            # PASO 4: Leer y procesar hoja de Movimiento
            logger.info("📋 PASO 4: Procesando hoja de Movimiento")
            movimiento_result = self.parser.leer_hoja_movimiento(file_content, catalogo_tiendas)
            
            if movimiento_result.get("errores"):
                resultado["errores"].extend(movimiento_result["errores"])
                resultado["status"] = "error"
                return resultado
            
            distribuciones_movimiento = movimiento_result.get("datos", [])
            resultado["resumen"]["distribuciones_totales"] = len(distribuciones_movimiento)
            resultado["resumen"]["hojas_procesadas"].append("Movimiento")
            
            logger.info(
                f"✅ Movimiento procesado: "
                f"{movimiento_result['resumen']['filas_validas']} filas válidas, "
                f"{movimiento_result['resumen']['productos_unicos']} productos únicos"
            )
            
            # PASO 5: Consolidar distribuciones por producto
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
            
            detalles_finales = [{"detalle": data["detalle"], "distribuciones": data["distribuciones"]} 
                               for data in detalles_consolidados.values()]
            
            logger.info(f"✅ Consolidación completa: {len(detalles_finales)} productos con distribuciones")
            
            # PASO 6: Validación antes de guardar
            if validar_antes_de_guardar:
                logger.info("📋 PASO 6: Validando pedido completo")
                validator = PedidoValidator()
                validacion_resultado = validator.validar_pedido_completo(cabecera, detalles_finales, es_formato_simple=False)
                # Serializar resultado de validación a estructuras JSON-safe
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
                
                if not validacion_resultado["valid"] and bloquea_con_errores:
                    resultado["status"] = "validation_error"
                    logger.error(f"❌ Errores de validación: {validacion_resultado['errors']}")
                    return resultado
            
            # PASO 7: Guardar en base de datos
            if ENABLE_SQL_SERVER_STORAGE:
                logger.info("📋 PASO 7: Guardando en base de datos")
                
                with get_db_connection_context() as conn:
                    repository = PedidoRepository(conn)
                    
                    # Insertar cabecera
                    pedido_id = repository.insert_cabecera(cabecera)
                    resultado["pedido_id"] = pedido_id
                    logger.info(f"✅ Cabecera guardada: {pedido_id}")
                    
                    # Procesar cada artículo con sus distribuciones
                    for detalle_data in detalles_finales:
                        try:
                            # Insertar detalle (artículo)
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
                                    fila_origen = dist.get("fila_origen")
                                    
                                    if tienda_codigo and cantidad and cantidad > 0:
                                        # Obtener o crear tienda
                                        tienda_id = repository.get_or_create_tienda(
                                            codigo=tienda_codigo,
                                            nombre=dist.get("tienda_nombre")
                                        )
                                        distribuciones.append({
                                            "tienda_id": tienda_id,
                                            "cantidad": cantidad,
                                            "fila_origen": fila_origen
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
                            resultado["warnings"].append(error_msg)
                            continue
                
                logger.info(
                    f"✅ Plantilla v1.0 procesada exitosamente: {filename} "
                    f"(pedido_id: {resultado['pedido_id']}, "
                    f"artículos: {resultado['articulos_cargados']}, "
                    f"distribuciones: {resultado['distribuciones_cargadas']})"
                )
            else:
                logger.info("⚠️ SQL Server storage deshabilitado, no se guardó en BD")
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al procesar formato v1.0: {e}", exc_info=True)
            resultado["status"] = "error"
            resultado["errores"].append(str(e))
            return resultado
    
    def _convertir_a_decimal(self, valor) -> Optional[float]:
        """Convierte un valor a decimal (float)."""
        if valor is None or pd.isna(valor):
            return None
        try:
            return float(valor)
        except (ValueError, TypeError):
            return None
    
    def _convertir_a_entero(self, valor) -> Optional[int]:
        """Convierte un valor a entero."""
        if valor is None or pd.isna(valor):
            return None
        try:
            return int(float(valor))
        except (ValueError, TypeError):
            return None

    def _parsear_fecha_texto(self, valor) -> Any:
        """Intenta convertir un valor de fecha en texto a date. Si no es reconocible, retorna el valor original (string)."""
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            return None
        try:
            from datetime import datetime, date
            # Manejar pd.Timestamp (devuelto por pandas al leer Date columns del Excel)
            if isinstance(valor, pd.Timestamp):
                return valor.date()
            if isinstance(valor, date):
                return valor
            if isinstance(valor, datetime):
                return valor.date()
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                # Podría ser serial de Excel; mantener el valor original para no introducir errores
                return valor
            if isinstance(valor, str):
                v = valor.strip()
                if v == "":
                    return None
                formatos = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]
                for fmt in formatos:
                    try:
                        dt = datetime.strptime(v, fmt)
                        return dt.date()
                    except ValueError:
                        continue
                # No coincide con formatos conocidos: devolver texto tal cual (p.ej. "INMEDIATO")
                return v
            return valor
        except Exception:
            # En caso de error, devolver el valor original para no bloquear el flujo
            return valor

