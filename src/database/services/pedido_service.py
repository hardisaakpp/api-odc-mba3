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
            
            # Paso 1: Extraer cabecera
            try:
                cabecera = self.parser.extraer_cabecera(df_raw, filename, usuario_id)
            except ValueError as e:
                # Error de validación (ej: numero_pedido no encontrado)
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
        bloquea_con_errores: bool = True
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
            
            tiene_cabecera_pedido = hoja_cabecera_encontrada is not None
            tiene_detalle_articulo = hoja_detalle_encontrada is not None
            
            if not tiene_cabecera_pedido:
                logger.warning(f"⚠️ No se encontró hoja de cabecera. Hojas disponibles: {excel_file.sheet_names}")
            if not tiene_detalle_articulo:
                logger.warning(f"⚠️ No se encontró hoja de detalle. Hojas disponibles: {excel_file.sheet_names}")
            
            # Formato con dos hojas (Template_Pedido_Inicial_v1.0.xlsx)
            if tiene_cabecera_pedido and tiene_detalle_articulo:
                resultado["formato_detectado"] = "dos_hojas"
                logger.info("📋 Formato DOS HOJAS detectado: CABECERA_PEDIDO + DETALLE_ARTICULO")
                
                # PASO 1: Parsear cabecera usando parsear_excel_pedido (solo para cabecera)
                excel_file_cabecera = pd.ExcelFile(io.BytesIO(file_content))
                df_cabecera = pd.read_excel(excel_file_cabecera, sheet_name=hoja_cabecera_encontrada, header=None)
                
                # Parsear cabecera manualmente (similar a parsear_excel_pedido pero solo cabecera)
                cabecera_parseada = {}
                if len(df_cabecera.columns) >= 2:
                    primera_fila = df_cabecera.iloc[0] if len(df_cabecera) > 0 else None
                    tiene_header = False
                    col_campo_idx = None
                    col_valor_idx = None
                    
                    if primera_fila is not None:
                        primera_fila_str = [str(v).upper().strip() if pd.notna(v) else "" for v in primera_fila.values]
                        if "CAMPO" in primera_fila_str or "VALOR" in primera_fila_str:
                            tiene_header = True
                            for idx, val in enumerate(primera_fila_str):
                                if "CAMPO" in val:
                                    col_campo_idx = idx
                                elif "VALOR" in val:
                                    col_valor_idx = idx
                            start_row = 1
                        else:
                            col_campo_idx = 0
                            col_valor_idx = 1
                            start_row = 0
                    else:
                        col_campo_idx = 0
                        col_valor_idx = 1
                        start_row = 0
                    
                    if col_campo_idx is None:
                        col_campo_idx = 0
                    if col_valor_idx is None:
                        col_valor_idx = 1
                    
                    mapeo_campos_cabecera = {
                        "CODIGO PEDIDO": "numero_pedido",
                        "CÓDIGO PEDIDO": "numero_pedido",
                        "FECHA PEDIDO": "fecha_pedido",
                        "FECHA ENTREGA": "fecha_entrega",
                        "FORMA PAGO": "forma_pago",
                        "FORMA DE PAGO": "forma_pago",
                        "ODC": "odc",
                        "NOMBRE PROVEEDOR": "proveedor_nombre",
                        "COMPRADOR NOMBRE": "comprador_nombre",
                        "COD COMPRADOR": "comprador_codigo",
                        "CÓD COMPRADOR": "comprador_codigo",
                        "CODIGO COMPRADOR": "comprador_codigo",
                        "ORIGEN TRASLADO": "origen_traslado",
                        "SERIE": "serie"
                    }
                    
                    for idx in range(start_row, len(df_cabecera)):
                        campo_raw = df_cabecera.iloc[idx, col_campo_idx] if col_campo_idx < len(df_cabecera.columns) else None
                        valor_raw = df_cabecera.iloc[idx, col_valor_idx] if col_valor_idx < len(df_cabecera.columns) else None
                        
                        if campo_raw is not None and not pd.isna(campo_raw):
                            campo = str(campo_raw).strip()
                            valor = str(valor_raw).strip() if valor_raw is not None and not pd.isna(valor_raw) else None
                            
                            if campo and valor:
                                cabecera_parseada[campo] = valor
                                campo_upper = campo.upper().strip()
                                if campo_upper in mapeo_campos_cabecera:
                                    cabecera_parseada[mapeo_campos_cabecera[campo_upper]] = valor
                
                # Convertir cabecera a formato BD
                cabecera = self._normalizar_cabecera_para_bd(
                    cabecera_parseada=cabecera_parseada,
                    filename=filename,
                    usuario_id=usuario_id
                )
                
                # PASO 2: Detectar formato de la hoja de detalle
                # Leer TODAS las columnas (no solo 5 filas) para detectar columnas ROLAND
                df_detalle_detection = pd.read_excel(
                    excel_file_cabecera, 
                    sheet_name=hoja_detalle_encontrada, 
                    header=0, 
                    nrows=1,
                    keep_default_na=False
                )
                df_detalle_detection.columns = [str(col).strip() if pd.notna(col) and str(col).strip() != "" else "" 
                                               for col in df_detalle_detection.columns]
                
                logger.info(f"🔍 Columnas encontradas en detalle (primeras 20): {list(df_detalle_detection.columns)[:20]}")
                logger.info(f"🔍 Total de columnas: {len(df_detalle_detection.columns)}")
                
                # Verificar si tiene columnas de tiendas (formato complejo)
                # Las columnas de tiendas contienen "ROLAND" (más flexible)
                columnas_tiendas = []
                for col in df_detalle_detection.columns:
                    col_upper = str(col).upper().strip()
                    # Buscar "ROLAND" en cualquier parte del nombre de la columna
                    if "ROLAND" in col_upper and col_upper != "ROLAND":  # Excluir solo "ROLAND" sin más texto
                        columnas_tiendas.append(col)
                
                logger.info(f"🔍 Todas las columnas (para debug): {list(df_detalle_detection.columns)}")
                
                has_columnas_tiendas = len(columnas_tiendas) > 0
                logger.info(f"🔍 Columnas ROLAND encontradas: {columnas_tiendas[:10]}")
                
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
                        hoja_cabecera=hoja_cabecera_encontrada,
                        hoja_detalle=hoja_detalle_encontrada
                    )
                    
                    # Consolidar usando el consolidator
                    detalles_con_tiendas = self.consolidator.consolidar_detalles_simple(
                        resultado_parsing.get("data", [])
                    )
                else:
                    # Formato complejo: usar _extraer_detalle_con_tiendas
                    logger.info("📋 Detalle en formato COMPLEJO (columnas de tiendas)")
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
                        # Resetear los nombres de columnas a índices numéricos
                        df_detalle_sin_header.columns = range(len(df_detalle_sin_header.columns))
                        
                        detalles_con_tiendas = self.parser.extraer_detalle_con_tiendas(df_detalle_sin_header)
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
                        hojas_disponibles = ", ".join(excel_file.sheet_names)
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
            
            # GUARDAR (solo si pasó validación o no se valida)
            with get_db_connection_context() as conn:
                repository = PedidoRepository(conn)
                pedido_id = repository.insert_cabecera(cabecera)
                resultado["pedido_id"] = pedido_id
                
                for detalle_data in detalles_con_tiendas:
                    try:
                        pedido_detalle_id = repository.insert_detalle(
                            pedido_id=pedido_id,
                            datos_detalle=detalle_data["detalle"]
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
                resultado_parsing = self.parsear_excel_pedido(file_content, hoja_cabecera, hoja_detalle)
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

