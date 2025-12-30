"""
Endpoints para gestión de plantillas Excel.
"""

import logging
import base64
from typing import Dict, Optional
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from src.security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)

# Exportar función principal para el linter
__all__ = ["register_plantillas_endpoints"]

# Constantes
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {'.xlsx', '.xls'}
ALLOWED_MIME_TYPES = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.ms-excel'  # .xls
}


def validate_excel_file(file: UploadFile) -> None:
    """
    Valida que el archivo sea un Excel válido.
    
    Args:
        file: Archivo subido
        
    Raises:
        HTTPException: Si el archivo no es válido
    """
    # Validar extensión
    file_name = file.filename.lower() if file.filename else ""
    if not any(file_name.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Formato de archivo no permitido. Solo se permiten archivos Excel (.xlsx, .xls)"
        )
    
    # Validar tipo MIME (opcional, algunos navegadores no lo envían correctamente)
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        logger.warning(f"⚠️ Tipo MIME no reconocido: {file.content_type}, pero continuando con validación de extensión")


def register_plantillas_endpoints(app: FastAPI):
    """
    Registra los endpoints de plantillas Excel en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.post("/api/plantillas/upload", tags=["Plantillas"])
    async def upload_plantilla(
        file: UploadFile = File(..., description="Archivo Excel (.xlsx o .xls)"),
        validar: bool = Query(True, description="Validar datos antes de guardar"),
        bloquea_con_errores: bool = Query(True, description="Bloquear guardado si hay errores críticos"),
        exportar_log: bool = Query(False, description="Incluir log de validación en respuesta (base64)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Sube y valida una plantilla Excel para procesamiento.
        
        **Nuevo:** Incluye validación pre-negocio antes de guardar.
        
        **Formatos soportados:**
        1. **Formato Simple:** CodigoProducto, IdTienda, Cantidad (consolida productos)
        2. **Formato Complejo:** Estructura con cabecera y columnas de tiendas
        
        **Validaciones realizadas:**
        - Catálogo: códigos de producto no vacíos, caracteres válidos
        - Tiendas: IdTienda corresponde a sucursal/almacén permitido
        - Unidades: enteros, máximos razonables por tienda y total
        - Fechas: formato correcto, no pasadas (si aplica)
        - Duplicados: detección de combinaciones producto+tienda duplicadas
        
        **Query Parameters:**
        - `validar` (bool, default: true): Validar datos antes de guardar
        - `bloquea_con_errores` (bool, default: true): Bloquear guardado si hay errores críticos
        - `exportar_log` (bool, default: false): Incluir log de validación en respuesta (Excel en base64)
        
        **Respuesta exitosa:**
        ```json
        {
            "status": "success",
            "message": "Plantilla procesada y guardada exitosamente",
            "pedido_id": "...",
            "formato_detectado": "simple",
            "articulos_cargados": 5,
            "distribuciones_cargadas": 10,
            "validation": {
                "valid": true,
                "total_issues": 0,
                "errors": 0,
                "warnings": 0,
                "issues_by_row": {}
            },
            "file_info": {...},
            "metadata": {...}
        }
        ```
        
        **Respuesta con errores de validación:**
        ```json
        {
            "status": "validation_error",
            "message": "Validación fallida: 2 error(es) crítico(s) encontrado(s)",
            "validation": {
                "valid": false,
                "errors": 2,
                "warnings": 1,
                "issues_by_row": {
                    "2": [
                        {
                            "field": "CodigoProducto",
                            "severity": "ERROR",
                            "message": "El código interno contiene caracteres no permitidos",
                            "value": "PROD#123"
                        }
                    ]
                }
            }
        }
        ```
        
        Returns:
            JSON con resultado del procesamiento incluyendo validación
        """
        try:
            # Validar archivo
            validate_excel_file(file)
            
            # Leer contenido del archivo
            content = await file.read()
            file_size = len(content)
            
            # Validar tamaño
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"El archivo es demasiado grande. Tamaño máximo: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
                )
            
            if file_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail="El archivo está vacío"
                )
            
            # Obtener ID del usuario
            user_id = user.get('id') or user.get('username', 'unknown')
            
            # Procesar el archivo Excel con validación
            from src.database.services.pedido_service import PedidoService
            
            service = PedidoService()
            
            # TODO: Obtener tiendas permitidas desde BD si es necesario
            # from src.database.connection import get_db_connection
            # with get_db_connection() as conn:
            #     repo = PedidoRepository(conn)
            #     tiendas_permitidas = repo.get_tiendas_activas()
            
            resultado = service.validar_y_procesar_archivo_excel(
                file_content=content,
                filename=file.filename or "sin_nombre.xlsx",
                usuario_id=user_id,
                validar_antes_de_guardar=validar,
                bloquea_con_errores=bloquea_con_errores,
                tiendas_permitidas=None  # None = todas permitidas
            )
            
            # Construir respuesta
            response_data = {
                "status": resultado["status"],
                "message": (
                    "Plantilla procesada y guardada exitosamente" if resultado["status"] == "success"
                    else "Plantilla validada pero tiene errores críticos" if resultado["status"] == "validation_error"
                    else "Error al procesar plantilla"
                ),
                "pedido_id": resultado.get("pedido_id"),
                "formato_detectado": resultado.get("formato_detectado"),
                "articulos_cargados": resultado.get("articulos_cargados", 0),
                "distribuciones_cargadas": resultado.get("distribuciones_cargadas", 0),
                "validation": resultado.get("validation"),
                "file_info": {
                    "filename": file.filename,
                    "size_mb": round(file_size / (1024 * 1024), 2)
                },
                "metadata": {
                    "uploaded_by": user_id,
                    "uploaded_at": datetime.now().isoformat()
                }
            }
            
            # Si se solicita, incluir log de validación en base64
            if exportar_log and resultado.get("validation"):
                from src.database.services.pedido_validation_exporter import PedidoValidationExporter
                
                excel_bytes = PedidoValidationExporter.export_to_excel_bytes(resultado["validation"])
                response_data["validation_log_excel_base64"] = base64.b64encode(excel_bytes).decode('utf-8')
                response_data["validation_log_filename"] = f"validation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            # Si hay errores de validación, retornar 400 pero con detalles
            if resultado["status"] == "validation_error":
                return JSONResponse(
                    status_code=400,
                    content=response_data
                )
            
            # Si hay error general
            if resultado["status"] == "error":
                raise HTTPException(
                    status_code=400,
                    detail=f"Error al procesar plantilla: {resultado.get('errores', ['Error desconocido'])}"
                )
            
            return JSONResponse(status_code=200, content=response_data)
            
        except HTTPException:
            # Re-lanzar excepciones HTTP
            raise
        except Exception as e:
            logger.error(f"❌ Error al procesar plantilla: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al procesar la plantilla: {str(e)}"
            )
    
    @app.get("/api/plantillas/{pedido_id}", tags=["Plantillas"])
    async def get_pedido(
        pedido_id: str = Path(..., description="UUID del pedido"),
        incluir_respuesta: bool = Query(False, description="Incluir respuesta del proveedor si existe"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene un pedido completo con cabecera, detalles y distribuciones por tienda.
        Opcionalmente incluye la respuesta del proveedor.
        
        **Query Parameters:**
        - `incluir_respuesta` (bool, default: false): Si true, incluye respuesta del proveedor si existe
        
        **Respuesta exitosa:**
        ```json
        {
            "cabecera": {
                "pedido_id": "...",
                "numero_pedido": "...",
                "fecha_pedido": "...",
                ...
            },
            "detalles": [
                {
                    "pedido_detalle_id": "...",
                    "codigo_interno": "...",
                    "descripcion_sap": "...",
                    "tiendas": [
                        {
                            "tienda_id": "...",
                            "codigo": "RECREO",
                            "nombre": "...",
                            "cantidad": 10
                        }
                    ]
                }
            ],
            "respuesta_proveedor": {
                "cabecera": {...},
                "detalles": [...]
            }
        }
        ```
        
        Returns:
            JSON con pedido completo
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository
            
            with get_db_connection_context() as conn:
                repository = PedidoRepository(conn)
                pedido = repository.get_pedido_completo(pedido_id)
                
                if not pedido:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Pedido no encontrado: {pedido_id}"
                    )
                
                # Agregar respuesta si se solicita y existe
                if incluir_respuesta:
                    respuesta_repo = PedidoRespuestaRepository(conn)
                    respuesta = respuesta_repo.obtener_respuesta_activa(pedido_id)
                    if respuesta:
                        pedido["respuesta_proveedor"] = respuesta
                
                return JSONResponse(status_code=200, content=pedido)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener pedido: {str(e)}"
            )
    
    @app.post("/pedidos/importar-excel", tags=["Pedidos"])
    async def importar_excel_pedido(
        file: UploadFile = File(..., description="Archivo Excel (.xlsx) con hojas 'CABECERA_PEDIDO' y 'DETALLE_ARTICULO'"),
        hoja_cabecera: str = Query("CABECERA_PEDIDO", description="Nombre de la hoja de cabecera"),
        hoja_detalle: str = Query("DETALLE_ARTICULO", description="Nombre de la hoja de detalle"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Importa y parsea un archivo Excel de pedido (FASE 1 - TAREA 2).
        
        **Formato esperado (Template_Pedido_Inicial_v1.0.xlsx):**
        - **Hoja 1: CABECERA_PEDIDO** - Formato clave-valor (Campo | Valor | Ejemplo)
        - **Hoja 2: DETALLE_ARTICULO** - Formato tabular con headers
        
        **Solo parsing técnico:** lee, normaliza y valida estructura.
        NO aplica reglas de negocio, NO consolida duplicados.
        
        **Validaciones técnicas:**
        - Extensión: .xlsx
        - Tamaño máximo: 10 MB
        - Hojas obligatorias: "CABECERA_PEDIDO" y "DETALLE_ARTICULO"
        - Columnas obligatorias en detalle: CodigoProducto, IdTienda, Cantidad
        - Duplicados (CodigoProducto + IdTienda) = ERROR
        
        **Estructura de respuesta:**
        ```json
        {
            "cabecera": {
                "Número de pedido": "P-12.48",
                "Fecha de pedido": "2025-01-21",
                ...
            },
            "resumen": {
                "filasLeidas": 120,
                "filasValidas": 115,
                "filasInvalidas": 5
            },
            "errores": [
                {
                    "fila": 18,
                    "campo": "Cantidad",
                    "tipo": "ERROR",
                    "mensaje": "Cantidad no es un entero válido"
                },
                {
                    "fila": 23,
                    "campo": "CodigoProducto, IdTienda",
                    "tipo": "ERROR",
                    "mensaje": "Registro duplicado (SKU + Tienda). Ya existe en fila 2"
                }
            ],
            "data": [
                {
                    "codigoProducto": "R225.1012.BCO",
                    "idTienda": "T001",
                    "cantidad": 10,
                    "filaOrigen": 2
                }
            ]
        }
        ```
        
        Returns:
            JSON con resultado del parsing técnico incluyendo cabecera y detalle
        """
        try:
            # Validar archivo
            file_name = file.filename.lower() if file.filename else ""
            if not file_name.endswith('.xlsx'):
                raise HTTPException(
                    status_code=400,
                    detail="Formato de archivo no permitido. Solo se permiten archivos .xlsx"
                )
            
            # Leer contenido del archivo
            content = await file.read()
            file_size = len(content)
            
            # Validar tamaño
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"El archivo es demasiado grande. Tamaño máximo: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
                )
            
            if file_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail="El archivo está vacío"
                )
            
            # Parsear Excel (solo parsing técnico)
            from src.database.services.pedido_service import PedidoService
            
            service = PedidoService()
            resultado = service.parsear_excel_pedido(
                file_content=content,
                hoja_cabecera=hoja_cabecera,
                hoja_detalle=hoja_detalle
            )
            
            # Retornar resultado del parsing
            return JSONResponse(
                status_code=200,
                content=resultado
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al importar Excel: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al importar el archivo: {str(e)}"
            )
    
    @app.post("/api/pedidos/validar-y-crear-lote", tags=["Pedidos"])
    async def validar_y_crear_lote(
        file: UploadFile = File(..., description="Archivo Excel (.xlsx) con hojas 'CABECERA_PEDIDO' y 'DETALLE_ARTICULO'"),
        validar_productos: bool = Query(True, description="Validar que productos existan en catálogo"),
        validar_tiendas: bool = Query(True, description="Validar que tiendas existan y estén activas"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        FASE 2: Valida productos/tiendas y crea pedido con estado pendiente.
        
        **Proceso:**
        1. Parsea Excel
        2. Valida que productos existan en catálogo (producto_mba3_staging)
        3. Valida que tiendas existan y estén activas
        4. Valida cantidades correctas
        5. Genera pedido consolidado (sumatoria por producto)
        6. Guarda pedido con estado "PENDIENTE_CONFIRMACION_PROVEEDOR"
        
        **Formatos soportados:**
        - Formato de dos hojas: 'CABECERA_PEDIDO' y 'DETALLE_ARTICULO'
        - Formato simple: CodigoProducto, IdTienda, Cantidad
        
        **Respuesta exitosa:**
        ```json
        {
            "status": "success",
            "pedido_id": "uuid-del-pedido",
            "estado": "PENDIENTE_CONFIRMACION_PROVEEDOR",
            "validacion": {
                "productos": {
                    "validos": ["R225.1012.BCO", ...],
                    "no_encontrados": [],
                    "todos_validos": true
                },
                "tiendas": {
                    "validas": ["T001", "T002", ...],
                    "no_encontradas": [],
                    "inactivas": [],
                    "todas_validas": true
                },
                "cantidades": {
                    "valid": true,
                    "errors": 0,
                    "warnings": 0
                }
            },
            "consolidacion": {
                "total_productos": 10,
                "cantidad_total": 250
            },
            "articulos_cargados": 10,
            "distribuciones_cargadas": 25,
            "errores": []
        }
        ```
        
        **Respuesta con errores:**
        ```json
        {
            "status": "validation_error",
            "validacion": {
                "productos": {
                    "no_encontrados": ["PROD999", "PROD888"]
                },
                "tiendas": {
                    "no_encontradas": ["T999"]
                }
            },
            "errores": [
                "Productos no encontrados: PROD999, PROD888",
                "Tiendas no encontradas: T999"
            ]
        }
        ```
        
        Returns:
            JSON con resultado completo de validación y creación del lote
        """
        try:
            # Validar archivo
            validate_excel_file(file)
            
            # Leer contenido
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"El archivo excede el tamaño máximo permitido de {MAX_FILE_SIZE / 1024 / 1024} MB"
                )
            
            # Procesar con servicio
            from src.database.services.pedido_service import PedidoService
            
            service = PedidoService()
            usuario_id = user.get("sub") or user.get("user_id")
            
            resultado = service.validar_y_crear_lote(
                file_content=content,
                filename=file.filename or "pedido.xlsx",
                usuario_id=usuario_id,
                validar_productos=validar_productos,
                validar_tiendas=validar_tiendas
            )
            
            # Determinar código de estado HTTP
            status_code = 200
            if resultado["status"] == "validation_error":
                status_code = 400
            elif resultado["status"] == "error":
                status_code = 500
            
            return JSONResponse(
                status_code=status_code,
                content=resultado
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al validar y crear lote: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al procesar el archivo: {str(e)}"
            )
    
    # ============================================================================
    # ENDPOINTS FASE 3: Interfaz para Proveedor
    # ============================================================================
    
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
            from fastapi.responses import Response
            
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
    
    @app.post("/api/pedidos/{pedido_id}/cargar-respuesta-proveedor", tags=["Pedidos - Proveedor"])
    async def cargar_respuesta_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        file: UploadFile = File(..., description="Archivo Excel con respuesta del proveedor"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Carga la respuesta del proveedor desde un archivo Excel.
        
        **Formato esperado:**
        - Hoja RESUMEN (obligatoria): Con columna "Cantidad Confirmada" completada
        - Hoja DETALLE_TIENDAS (opcional): Si el proveedor especificó distribución por tienda
        - Precios ajustados en columnas "Costo Unitario Ajustado" y "Descuento % Ajustado"
        
        **Validaciones:**
        - ✅ Cantidad confirmada >= 0
        - ✅ Cantidad confirmada <= cantidad solicitada (CRÍTICO)
        - ✅ Precios ajustados >= 0
        - ⚠️ Warning si confirma menos del 80%
        - ⚠️ Warning si precio aumenta más del 10%
        
        **Estado del pedido:**
        - Se actualiza a `RESPUESTA_PROVEEDOR_CARGADA` (pendiente de revisión)
        - NO se marca como `CONFIRMADO_PROVEEDOR` automáticamente
        
        **Respuesta exitosa:**
        ```json
        {
            "status": "success",
            "message": "Respuesta del proveedor cargada exitosamente",
            "respuesta_id": "...",
            "validacion": {
                "valido": true,
                "errores": [],
                "warnings": [...]
            },
            "cantidades_guardadas": 10,
            "precios_guardados": 5,
            "pedido_id": "..."
        }
        ```
        
        Returns:
            JSON con resultado del procesamiento
        """
        try:
            validate_excel_file(file)
            
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"El archivo excede el tamaño máximo permitido de {MAX_FILE_SIZE / 1024 / 1024} MB"
                )
            
            from src.database.services.pedido_proveedor_service import PedidoProveedorService
            
            service = PedidoProveedorService()
            usuario_id = user.get('id') or user.get('username', 'unknown')
            
            resultado = service.importar_respuesta_proveedor(
                pedido_id=pedido_id,
                file_content=content,
                filename=file.filename or "respuesta.xlsx",
                usuario_id=usuario_id
            )
            
            status_code = 200
            if resultado["status"] == "validation_error":
                status_code = 400
            
            return JSONResponse(status_code=status_code, content=resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al cargar respuesta del proveedor: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al procesar respuesta: {str(e)}"
            )
    
    @app.get("/api/pedidos/{pedido_id}/respuesta-proveedor", tags=["Pedidos - Proveedor"])
    async def obtener_respuesta_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene la respuesta más reciente del proveedor para un pedido (si existe).
        
        **Respuesta exitosa:**
        ```json
        {
            "cabecera": {
                "respuesta_id": "...",
                "version": 1,
                "estado": "PENDIENTE_REVISION",
                "fecha_respuesta": "2025-01-21T10:00:00",
                "creado_por": "...",
                "observaciones_generales": "..."
            },
            "detalles": [
                {
                    "codigo_producto": "R225.1012.BCO",
                    "cantidad_solicitada_total": 100,
                    "cantidad_confirmada_total": 80,
                    "costo_doc_sin_iva_original": 100.50,
                    "costo_doc_sin_iva_ajustado": 95.00,
                    "observaciones": "Stock limitado"
                }
            ]
        }
        ```
        
        Returns:
            JSON con respuesta del proveedor o 404 si no existe
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository
            
            with get_db_connection_context() as conn:
                repo = PedidoRespuestaRepository(conn)
                respuesta = repo.obtener_respuesta_activa(pedido_id)
                
                if not respuesta:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No existe respuesta del proveedor para este pedido"
                    )
                
                return JSONResponse(status_code=200, content=respuesta)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener respuesta del proveedor: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno: {str(e)}"
            )

