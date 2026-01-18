"""
Endpoints de exportación de pedidos.
"""

import logging
from typing import Dict
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Path, Query
from fastapi.responses import Response

from src.security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)


def register_exportacion_endpoints(app: FastAPI):
    """Registra los endpoints de exportación de pedidos."""
    
    @app.get("/api/pedidos/{pedido_id}/exportar-para-proveedor", tags=["Pedidos - Proveedor"])
    async def exportar_pedido_para_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
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
        formato: str = Query("csv", description="Formato de salida: 'csv' o 'txt'"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Exporta un pedido en formato plano (CSV o TXT) para subir en MBA.
        
        **HU-08**: Permite a usuarios de El Rayo descargar el pedido en archivo plano
        para subirlo en el sistema MBA.
        
        ⚠️ **NOTA IMPORTANTE**: Este es un formato temporal. Cuando se proporcione 
        el formato exacto requerido por MBA, este endpoint debe ser actualizado.
        
        **Formato temporal:**
        - CSV: Separado por comas, con encabezado
        - TXT: Separado por pipes (|), sin encabezado
        
        **Columnas incluidas:**
        - Código Producto
        - Descripción
        - Cantidad Total
        - Costo Unitario
        - Marca
        
        Returns:
            Archivo plano descargable (CSV o TXT)
        """
        try:
            from src.database.services.pedido_proveedor_service import PedidoProveedorService
            from src.database.repositories.pedido_repository import PedidoRepository
            from src.database.connection import get_db_connection_context
            import uuid
            
            if formato.lower() not in ["csv", "txt"]:
                raise HTTPException(
                    status_code=400,
                    detail="Formato no válido. Use 'csv' o 'txt'"
                )
            
            # Determinar si es UUID o numero_pedido
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Intentar determinar si es UUID o numero_pedido
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
                    numero_pedido = pedido_id  # El parámetro ya es el numero_pedido
            
            service = PedidoProveedorService()
            file_bytes = service.exportar_pedido_plano_mba(pedido_id_real, formato)
            
            # Determinar media type y extensión
            if formato.lower() == "csv":
                media_type = "text/csv; charset=utf-8"
                extension = "csv"
            else:
                media_type = "text/plain; charset=utf-8"
                extension = "txt"
            
            # Limpiar número de pedido para nombre de archivo
            numero_pedido_limpio = numero_pedido.replace(" ", "_").replace("-", "_").replace("/", "_")
            
            return Response(
                content=file_bytes,
                media_type=media_type,
                headers={
                    "Content-Disposition": f'attachment; filename="pedido_mba_{numero_pedido_limpio}_{datetime.now().strftime("%Y%m%d")}.{extension}"'
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
