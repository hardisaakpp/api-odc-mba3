"""
Endpoints de exportación de pedidos.
"""

import logging
import uuid
from typing import Dict
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Path, Query
from fastapi.responses import Response

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)


def register_exportacion_endpoints(app: FastAPI):
    """Registra los endpoints de exportación de pedidos."""
    
    @app.get("/api/pedidos/{pedido_id}/exportar-para-proveedor", tags=["Pedidos - Proveedor"])
    async def exportar_pedido_para_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Exporta un pedido a Excel para que el proveedor lo complete.
        
        **Formato exportado:**
        - Hoja RESUMEN: Totales solicitados por producto (consolidado) - **OBLIGATORIO completar**
        - Hoja DETALLE_TIENDAS: Distribución por tienda - **OPCIONAL** (solo si el proveedor quiere especificar)
        - Hoja INSTRUCCIONES: Guía de uso
        
        **Modelo de respuesta:**
        - El proveedor responde principalmente por PRODUCTO (consolidado)
        - Puede opcionalmente especificar distribución por tienda
        - Si no especifica por tienda, el sistema distribuye proporcionalmente
        
        Returns:
            Archivo Excel descargable
        """
        try:
            from src.database.services.pedido_proveedor_service import PedidoProveedorService
            
            service = PedidoProveedorService()
            excel_bytes = service.exportar_pedido_para_proveedor(pedido_id)
            
            return Response(
                content=excel_bytes,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f'attachment; filename="pedido_proveedor_{pedido_id}_{datetime.now().strftime("%Y%m%d")}.xlsx"'
                }
            )
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al exportar pedido para proveedor: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al exportar pedido: {str(e)}"
            )
    
    @app.get("/api/pedidos/{pedido_id}/exportar-plano-mba", tags=["Pedidos - El Rayo"])
    async def exportar_pedido_plano_mba(
        pedido_id: str = Path(..., description="UUID del pedido o número de pedido"),
        codigo_cliente: str = Query("", description="Código de cliente MBA (ej: CLI0495)"),
        codigo_subcliente: str = Query("", description="Código de subcliente MBA (ej: GO05)"),
        moneda: str = Query("US", description="Código de moneda (ej: US, DOP)"),
        bodega: str = Query("", description="Código de bodega MBA (si vacío, usa origen_traslado del pedido)"),
        vendedor: str = Query("", description="Código de vendedor MBA (ej: JPC)"),
        numero_pedido_mba: int = Query(1, ge=1, description="Número de pedido temporal para agrupar líneas en MBA"),
        consolidado: bool = Query(False, description="Si True, consolida cantidades por producto; si False, genera una línea por tienda/sucursal"),
        incluir_encabezado: bool = Query(True, description="Incluir las 19 líneas de encabezado del formato MBA"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('odcsap.view'))
    ):
        """
        Exporta un pedido en formato plano (.txt) para importar en MBA.
        
        **HU-08**: Permite a usuarios de El Rayo descargar el pedido en archivo plano
        para subirlo en el sistema MBA.
        
        ## Formato de archivo
        
        Genera un archivo .txt compatible con el formato de importación de 
        **Pedidos de Clientes** de MBA (ENTERPRISE SOFTWARE SOLUTIONS):
        
        - **35 columnas** separadas por TAB
        - **19 líneas de encabezado** (se eliminan automáticamente al importar en MBA)
        - Una línea por cada combinación producto-tienda (o consolidado por producto)
        
        ## Parámetros de configuración
        
        Los siguientes campos deben configurarse según los datos del cliente en MBA:
        
        | Parámetro | Ejemplo | Descripción |
        |-----------|---------|-------------|
        | codigo_cliente | CLI0495 | Código del cliente en MBA |
        | codigo_subcliente | GO05 | Subcategoría del cliente (opcional) |
        | moneda | US | Código de moneda (US, DOP, etc.) |
        | bodega | BPT | Código de bodega en MBA |
        | vendedor | JPC | Código del vendedor |
        
        ## Modos de exportación
        
        - **consolidado=False** (predeterminado): Genera una línea por cada tienda/sucursal.
          Útil cuando el pedido tiene distribución por tiendas.
        - **consolidado=True**: Consolida las cantidades y genera una línea por producto.
          Útil cuando no se necesita distinguir por tienda.
        
        ## Ejemplo de línea generada
        
        ```
        91	3	CLI0495	GO05	29/10/2025	31/10/2025	US	BPT	JPC			CQ287341						TRUE	FALSE	PRI	R469.911.CCL	6	FALSE	6.16	TRUE								0	FALSE	91
        ```
        
        Returns:
            Archivo .txt descargable en formato MBA
        """
        try:
            from src.database.services.mba_pedido_exporter import MBAPedidoExporter, MBAExportConfig
            
            # Determinar si es UUID o numero_pedido
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                try:
                    # Si es un UUID válido, intentar obtener por pedido_id
                    uuid.UUID(pedido_id)
                    pedido = repo.get_pedido_completo(pedido_id)
                    if not pedido:
                        raise ValueError(f"Pedido no encontrado: {pedido_id}")
                    pedido_id_real = pedido_id
                    numero_pedido = pedido["cabecera"].get("numero_pedido", pedido_id[:8])
                except (ValueError, TypeError):
                    # No es UUID, intentar obtener por numero_pedido
                    pedido = repo.get_pedido_completo_por_numero(pedido_id)
                    if not pedido:
                        raise ValueError(f"Pedido no encontrado: {pedido_id}")
                    pedido_id_real = pedido["cabecera"]["pedido_id"]
                    numero_pedido = pedido_id
            
            # Configurar exportación
            config = MBAExportConfig(
                codigo_cliente=codigo_cliente,
                codigo_subcliente=codigo_subcliente,
                moneda=moneda,
                bodega=bodega,
                vendedor=vendedor,
                numero_pedido_temporal=numero_pedido_mba,
            )
            
            # Exportar según el modo seleccionado
            exporter = MBAPedidoExporter()
            
            if consolidado:
                file_bytes = exporter.exportar_pedido_formato_mba_consolidado(
                    pedido_id=pedido_id_real,
                    config=config,
                    incluir_encabezado=incluir_encabezado
                )
            else:
                file_bytes = exporter.exportar_pedido_formato_mba(
                    pedido_id=pedido_id_real,
                    config=config,
                    incluir_encabezado=incluir_encabezado
                )
            
            # Limpiar número de pedido para nombre de archivo
            numero_pedido_limpio = numero_pedido.replace(" ", "_").replace("-", "_").replace("/", "_")
            filename = f"pedido_mba_{numero_pedido_limpio}_{datetime.now().strftime('%Y%m%d')}.txt"
            
            logger.info(f"✅ Pedido {numero_pedido} exportado a formato MBA: {filename}")
            
            return Response(
                content=file_bytes,
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al exportar pedido plano para MBA: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al exportar pedido: {str(e)}"
            )
