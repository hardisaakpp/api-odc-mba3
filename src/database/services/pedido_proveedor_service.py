"""
Servicio para manejar interfaz del proveedor: exportación e importación de respuestas.
FASE 3: Respuesta por producto consolidado + detalle por tienda opcional.
"""

import logging
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime
import io

from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.pedido_respuesta_repository import PedidoRespuestaRepository

logger = logging.getLogger(__name__)


class PedidoProveedorService:
    """Servicio para manejar interfaz del proveedor."""
    
    def validar_respuesta_proveedor(
        self,
        pedido: Dict[str, Any],
        respuestas_cantidades: List[Dict[str, Any]],
        respuestas_precios: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        VALIDA las respuestas del proveedor SIN guardar.
        Separado de la lógica de parsing/guardado.
        
        Reglas de validación:
        - cantidad_confirmada >= 0
        - cantidad_confirmada <= cantidad_solicitada (CRÍTICO)
        - precios ajustados >= 0
        
        Args:
            pedido: Pedido completo desde BD
            respuestas_cantidades: Lista de respuestas de cantidades
            respuestas_precios: Lista de respuestas de precios
            
        Returns:
            Dict con validaciones y errores
        """
        errores = []
        warnings = []
        
        # 1. Validar cantidades
        for respuesta in respuestas_cantidades:
            cantidad_solicitada = respuesta.get("cantidad_solicitada_total")
            cantidad_confirmada = respuesta.get("cantidad_confirmada_total")
            codigo_producto = respuesta.get("codigo_producto", "N/A")
            
            if cantidad_confirmada is None:
                errores.append({
                    "tipo": "ERROR",
                    "campo": "cantidad_confirmada_total",
                    "mensaje": f"Cantidad confirmada es obligatoria para producto: {codigo_producto}",
                    "producto": codigo_producto
                })
                continue
            
            if cantidad_confirmada < 0:
                errores.append({
                    "tipo": "ERROR",
                    "campo": "cantidad_confirmada_total",
                    "mensaje": f"Cantidad confirmada no puede ser negativa: {cantidad_confirmada}",
                    "producto": codigo_producto
                })
            
            # ✅ REGLA CRÍTICA: cantidad_confirmada ≤ solicitada
            if cantidad_solicitada is not None and cantidad_confirmada > cantidad_solicitada:
                errores.append({
                    "tipo": "ERROR",
                    "campo": "cantidad_confirmada_total",
                    "mensaje": f"Cantidad confirmada ({cantidad_confirmada}) no puede ser mayor que solicitada ({cantidad_solicitada})",
                    "producto": codigo_producto
                })
            
            # Warning si confirma menos del 80%
            if cantidad_solicitada is not None and cantidad_solicitada > 0 and cantidad_confirmada < (cantidad_solicitada * 0.8):
                warnings.append({
                    "tipo": "WARNING",
                    "campo": "cantidad_confirmada_total",
                    "mensaje": f"Proveedor confirma menos del 80% de lo solicitado: {cantidad_confirmada}/{cantidad_solicitada}",
                    "producto": codigo_producto
                })
        
        # 2. Validar precios
        for respuesta in respuestas_precios:
            costo_ajustado = respuesta.get("costo_doc_sin_iva_ajustado")
            codigo_producto = respuesta.get("codigo_producto", "N/A")
            
            if costo_ajustado is not None and costo_ajustado < 0:
                errores.append({
                    "tipo": "ERROR",
                    "campo": "costo_doc_sin_iva_ajustado",
                    "mensaje": f"Precio ajustado no puede ser negativo: {costo_ajustado}",
                    "producto": codigo_producto
                })
            
            # Warning si precio aumenta más del 10%
            costo_original = respuesta.get("costo_doc_sin_iva_original")
            if costo_original and costo_ajustado:
                incremento = ((costo_ajustado - costo_original) / costo_original) * 100
                if incremento > 10:
                    warnings.append({
                        "tipo": "WARNING",
                        "campo": "costo_doc_sin_iva_ajustado",
                        "mensaje": f"Precio aumenta más del 10%: {incremento:.2f}%",
                        "producto": codigo_producto
                    })
        
        # 3. Validar cobertura (warnings si faltan productos)
        productos_pedido = {d["codigo_interno"] for d in pedido["detalles"]}
        productos_respuesta = {r.get("codigo_producto") for r in respuestas_cantidades if r.get("codigo_producto")}
        productos_sin_respuesta = productos_pedido - productos_respuesta
        
        if productos_sin_respuesta:
            warnings.append({
                "tipo": "WARNING",
                "campo": "cobertura",
                "mensaje": f"Productos sin respuesta del proveedor: {', '.join(sorted(productos_sin_respuesta))}"
            })
        
        return {
            "valido": len(errores) == 0,
            "errores": errores,
            "warnings": warnings
        }
    
    def exportar_pedido_para_proveedor(self, pedido_id: str) -> bytes:
        """
        Exporta un pedido a Excel para que el proveedor lo complete.
        
        Formato exportado:
        - Hoja RESUMEN: Totales solicitados por producto (consolidado)
        - Hoja DETALLE_TIENDAS (opcional): Distribución por tienda si el proveedor quiere especificar
        - Hoja INSTRUCCIONES: Guía de uso
        
        Args:
            pedido_id: UUID del pedido
            
        Returns:
            Bytes del archivo Excel
        """
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = repo.get_pedido_completo(pedido_id)
            
            if not pedido:
                raise ValueError(f"Pedido no encontrado: {pedido_id}")
            
            cabecera = pedido["cabecera"]
            
            # Hoja 1: RESUMEN - Totales por producto
            resumen_data = []
            for detalle in pedido["detalles"]:
                total_cantidad = sum(t["cantidad"] for t in detalle["tiendas"])
                # Manejar valores None para que no aparezcan como celdas vacías
                costo_original = detalle.get("costo_doc_sin_iva")
                descuento_original = detalle.get("descuento_1")
                
                resumen_data.append({
                    "Código Producto": detalle["codigo_interno"],
                    "Descripción": detalle["descripcion_sap"],
                    "Marca": detalle.get("marca") or "",
                    "Cantidad Total Solicitada": total_cantidad,
                    "Cantidad Confirmada": "",  # Para que el proveedor complete
                    "Costo Unitario Original": costo_original if costo_original is not None else "",
                    "Costo Unitario Ajustado": "",  # Para que el proveedor complete
                    "Descuento % Original": descuento_original if descuento_original is not None else "",
                    "Descuento % Ajustado": "",  # Opcional
                    "Observaciones": "",  # Opcional
                })
            
            df_resumen = pd.DataFrame(resumen_data)
            
            # Hoja 2: DETALLE_TIENDAS - Solo si el proveedor quiere especificar por tienda
            detalle_data = []
            for detalle in pedido["detalles"]:
                for tienda in detalle["tiendas"]:
                    detalle_data.append({
                        "Código Producto": detalle["codigo_interno"],
                        "Descripción": detalle["descripcion_sap"],
                        "Tienda Código": tienda["codigo"],
                        "Tienda Nombre": tienda.get("nombre") or "",
                        "Cantidad Solicitada": tienda["cantidad"],
                        "Cantidad Confirmada": "",  # Opcional: solo si quiere especificar
                        "Observaciones": "",  # Opcional
                    })
            
            df_detalle = pd.DataFrame(detalle_data)
            
            # Hoja 3: INSTRUCCIONES
            instrucciones_data = [
                {"Instrucción": "1. Complete la hoja RESUMEN con las cantidades confirmadas por producto (consolidado)"},
                {"Instrucción": "2. Si necesita ajustar precios, complete las columnas 'Costo Unitario Ajustado' y 'Descuento % Ajustado'"},
                {"Instrucción": "3. La hoja DETALLE_TIENDAS es OPCIONAL: solo complétela si necesita especificar distribución por tienda"},
                {"Instrucción": "4. Si no completa DETALLE_TIENDAS, el sistema distribuirá proporcionalmente las cantidades confirmadas"},
                {"Instrucción": "5. Guarde el archivo y envíelo de vuelta al sistema"},
            ]
            df_instrucciones = pd.DataFrame(instrucciones_data)
            
            # Crear Excel en memoria
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_resumen.to_excel(writer, sheet_name="RESUMEN", index=False)
                df_detalle.to_excel(writer, sheet_name="DETALLE_TIENDAS", index=False)
                df_instrucciones.to_excel(writer, sheet_name="INSTRUCCIONES", index=False)
            
            output.seek(0)
            return output.read()
    
    def exportar_pedido_plano_mba(self, pedido_id: str, formato: str = "csv") -> bytes:
        """
        Exporta un pedido en formato plano (CSV o TXT) para subir en MBA.
        
        ⚠️ NOTA: Este es un formato temporal. Cuando se proporcione el formato real de MBA,
        este método debe ser actualizado para generar el formato exacto requerido.
        
        Formato temporal (CSV):
        - Separador: coma (,)
        - Encoding: UTF-8 con BOM para Excel
        - Columnas: Código Producto, Descripción, Cantidad Total, Costo Unitario, Marca
        
        Args:
            pedido_id: UUID del pedido
            formato: Formato de salida ("csv" o "txt"). Por defecto "csv"
            
        Returns:
            Bytes del archivo plano
        """
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = repo.get_pedido_completo(pedido_id)
            
            if not pedido:
                raise ValueError(f"Pedido no encontrado: {pedido_id}")
            
            cabecera = pedido["cabecera"]
            
            # ⚠️ FORMATO TEMPORAL - Ajustar cuando se proporcione el formato real de MBA
            # Por ahora generamos un CSV simple con los datos principales
            lines = []
            
            # Encabezado (opcional - comentar si MBA no requiere encabezado)
            if formato.lower() == "csv":
                lines.append("CODIGO_PRODUCTO,DESCRIPCION,CANTIDAD_TOTAL,COSTO_UNITARIO,MARCA")
            
            # Datos de cada producto
            for detalle in pedido["detalles"]:
                total_cantidad = sum(t["cantidad"] for t in detalle["tiendas"])
                codigo = detalle.get("codigo_interno", "").strip()
                descripcion = detalle.get("descripcion_sap", "").strip().replace(",", " ")  # Evitar comas en CSV
                marca = detalle.get("marca", "").strip().replace(",", " ")
                costo_unitario = detalle.get("costo_doc_sin_iva") or 0
                
                if formato.lower() == "csv":
                    # Formato CSV: valores separados por coma
                    line = f"{codigo},{descripcion},{total_cantidad},{costo_unitario},{marca}"
                else:
                    # Formato TXT: valores separados por pipe o tab
                    line = f"{codigo}|{descripcion}|{total_cantidad}|{costo_unitario}|{marca}"
                
                lines.append(line)
            
            # Unir todas las líneas
            content = "\n".join(lines)
            
            # Convertir a bytes con encoding UTF-8
            # Agregar BOM para Excel si es CSV
            if formato.lower() == "csv":
                content_bytes = ("\ufeff" + content).encode("utf-8-sig")
            else:
                content_bytes = content.encode("utf-8")
            
            return content_bytes
    
    def importar_respuesta_proveedor(
        self,
        pedido_id: str,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Importa la respuesta del proveedor desde un archivo Excel.
        
        FLUJO CORRECTO:
        1. Parsear Excel
        2. Validar formato
        3. Validar reglas de negocio (separado)
        4. Crear cabecera de respuesta
        5. Guardar detalles
        6. Actualizar estado del pedido a RESPUESTA_PROVEEDOR_CARGADA (NO CONFIRMADO)
        
        Args:
            pedido_id: UUID del pedido
            file_content: Contenido del archivo Excel
            filename: Nombre del archivo
            usuario_id: User ID del usuario que carga la respuesta
            
        Returns:
            Dict con resultado del procesamiento
        """
        try:
            # Leer Excel
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            
            # Validar que exista la hoja RESUMEN
            if "RESUMEN" not in excel_file.sheet_names:
                raise ValueError("Hoja requerida no encontrada: RESUMEN")
            
            # Obtener pedido completo para validar
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                pedido = repo.get_pedido_completo(pedido_id)
                
                if not pedido:
                    raise ValueError(f"Pedido no encontrado: {pedido_id}")
                
                # Leer hoja RESUMEN
                df_resumen = pd.read_excel(excel_file, sheet_name="RESUMEN")
                
                # Validar columnas requeridas
                columnas_requeridas = ["Código Producto", "Cantidad Total Solicitada"]
                for col in columnas_requeridas:
                    if col not in df_resumen.columns:
                        raise ValueError(f"Columna requerida no encontrada: {col}")
                
                # Crear mapa de pedido_detalle_id por código producto
                mapa_productos = {}
                for detalle in pedido["detalles"]:
                    codigo = detalle["codigo_interno"]
                    mapa_productos[codigo] = {
                        "pedido_detalle_id": detalle["pedido_detalle_id"],
                        "cantidad_solicitada_total": sum(t["cantidad"] for t in detalle["tiendas"]),
                        "costo_original": detalle.get("costo_doc_sin_iva"),
                        "descuento_original": detalle.get("descuento_1")
                    }
                
                # Procesar respuestas desde RESUMEN (modelo principal: producto consolidado)
                respuestas_cantidades = []
                respuestas_precios = []
                
                for idx, row in df_resumen.iterrows():
                    codigo_producto = str(row["Código Producto"]).strip()
                    
                    if codigo_producto not in mapa_productos:
                        continue  # Producto no encontrado en pedido
                    
                    producto_info = mapa_productos[codigo_producto]
                    
                    # Cantidad confirmada
                    cantidad_confirmada = row.get("Cantidad Confirmada", "")
                    if cantidad_confirmada == "" or pd.isna(cantidad_confirmada):
                        cantidad_confirmada = producto_info["cantidad_solicitada_total"]  # Por defecto, confirma todo
                    else:
                        try:
                            cantidad_confirmada = int(float(cantidad_confirmada))
                        except (ValueError, TypeError):
                            cantidad_confirmada = producto_info["cantidad_solicitada_total"]
                    
                    respuestas_cantidades.append({
                        "pedido_detalle_id": producto_info["pedido_detalle_id"],
                        "codigo_producto": codigo_producto,
                        "cantidad_solicitada_total": producto_info["cantidad_solicitada_total"],
                        "cantidad_confirmada_total": cantidad_confirmada,
                        "observaciones": str(row.get("Observaciones", "")) if not pd.isna(row.get("Observaciones", "")) else None
                    })
                    
                    # Precios ajustados (si se proporcionan)
                    costo_ajustado = row.get("Costo Unitario Ajustado", "")
                    descuento_ajustado = row.get("Descuento % Ajustado", "")
                    
                    if costo_ajustado != "" and not pd.isna(costo_ajustado):
                        try:
                            costo_ajustado = float(costo_ajustado)
                            if costo_ajustado >= 0:
                                respuestas_precios.append({
                                    "pedido_detalle_id": producto_info["pedido_detalle_id"],
                                    "codigo_producto": codigo_producto,
                                    "costo_doc_sin_iva_original": producto_info["costo_original"],
                                    "costo_doc_sin_iva_ajustado": costo_ajustado,
                                    "descuento_1_original": producto_info["descuento_original"],
                                    "descuento_1_ajustado": float(descuento_ajustado) if descuento_ajustado != "" and not pd.isna(descuento_ajustado) else None,
                                    "observaciones_precio": None
                                })
                        except (ValueError, TypeError):
                            pass  # Ignorar precios inválidos
                
                # ✅ Validar ANTES de guardar
                validacion = self.validar_respuesta_proveedor(
                    pedido=pedido,
                    respuestas_cantidades=respuestas_cantidades,
                    respuestas_precios=respuestas_precios
                )
                
                if not validacion["valido"]:
                    return {
                        "status": "validation_error",
                        "message": "La respuesta del proveedor contiene errores de validación",
                        "validacion": validacion,
                        "errores": validacion["errores"],
                        "warnings": validacion["warnings"]
                    }
                
                # Guardar respuesta con cabecera
                respuesta_repo = PedidoRespuestaRepository(conn)
                
                # Crear cabecera de respuesta
                respuesta_id = respuesta_repo.crear_respuesta_proveedor(
                    pedido_id=pedido_id,
                    usuario_id=usuario_id,
                    observaciones_generales=None
                )
                
                # Guardar detalles
                resultado_guardado = respuesta_repo.guardar_respuesta_detalles(
                    respuesta_id=respuesta_id,
                    respuestas_cantidades=respuestas_cantidades,
                    respuestas_precios=respuestas_precios
                )
                
                # ✅ Estado correcto: RESPUESTA_PROVEEDOR_CARGADA (no CONFIRMADO)
                repo.update_estado(pedido_id, "RESPUESTA_PROVEEDOR_CARGADA")
                
                return {
                    "status": "success",
                    "message": "Respuesta del proveedor cargada exitosamente",
                    "respuesta_id": respuesta_id,
                    "validacion": validacion,
                    "cantidades_guardadas": resultado_guardado["cantidades_guardadas"],
                    "precios_guardados": resultado_guardado["precios_guardados"],
                    "pedido_id": pedido_id
                }
                
        except ValueError as e:
            logger.error(f"❌ Error de validación al importar respuesta: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error al importar respuesta del proveedor: {e}", exc_info=True)
            raise

