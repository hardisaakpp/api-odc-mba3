"""
Endpoints para gestión de plantillas Excel.
"""

import logging
import base64
from typing import Dict, Optional
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Path, Query, Body, status
from fastapi.responses import JSONResponse

from src.security.jwt_auth import verify_jwt_token, require_permission
from src.exceptions import BusinessException
from src.models import (
    RespuestaProveedorRequest,
    FormularioProveedorResponse,
    RespuestaProveedorResponse,
    ActualizarCostoRequest,
    ActualizarTotalRequest,
    ActualizarComentarioRequest,
    NotificarConfirmacionRequest,
    RedistribuirPedidoRequest,
    DistribucionPedidoResponse,
    ConfirmarRedistribucionRequest,
    ConfirmarRedistribucionResponse,
    ReporteDiferenciasResponse,
    RedistribucionConfirmarRequest,
    ConfirmarRedistribucionResponseFrontend,
    GuardarBorradorRequest,
    GuardarBorradorResponse,
    BorradorResponse,
    AjusteDetalle,
    ResumenConfirmacion,
    GuardarModificacionesColumnasRequest,
    GuardarModificacionesColumnasResponse,
    ObtenerModificacionesColumnasResponse,
    ConfirmacionRayoListResponse,
    ConfirmacionRayoDetailResponse,
    ConfirmacionRayoItem
)

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


def get_user_id(user: Dict) -> str:
    """
    Normaliza y obtiene el ID del usuario del JWT.
    
    Usa el mismo identificador que se usa al guardar pedidos (creado_por).
    Esto asegura consistencia entre creación y consulta.
    
    Args:
        user: Diccionario del JWT decodificado
        
    Returns:
        ID del usuario normalizado
        
    Raises:
        HTTPException: Si el usuario no tiene ID válido
    """
    user_id = user.get('id') or user.get('username')
    
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Usuario inválido: no se pudo obtener el ID del usuario"
        )
    
    return user_id


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
        modo_tiendas: str = Query(
            "validar_estricto",
            description="Modo de validación de tiendas: 'validar_estricto' (recomendado) | 'crear_si_no_existe' (legacy) | 'sincronizar_maestro' (admin)",
            regex="^(validar_estricto|crear_si_no_existe|sincronizar_maestro)$"
        ),
        confirmar_sincronizacion: bool = Query(
            False,
            description="⚠️ REQUERIDO si modo_tiendas='sincronizar_maestro'. Confirma que deseas DESACTIVAR tiendas no presentes en Excel"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Sube y valida una plantilla Excel para procesamiento.
        
        **Nuevo:** Incluye validación pre-negocio antes de guardar.
        
        **⏱️ IMPORTANTE:** El procesamiento puede tardar hasta 2 minutos para archivos grandes.
        El servidor está configurado con timeout de 120 segundos.
        
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
            # ✅ VALIDACIÓN EXPLÍCITA PARA SINCRONIZAR (AJUSTE 3)
            if modo_tiendas == "sincronizar_maestro":
                if not confirmar_sincronizacion:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "confirmation_required",
                            "message": (
                                "El modo 'sincronizar_maestro' requiere confirmación explícita. "
                                "Esta operación va a DESACTIVAR tiendas no presentes en el Excel. "
                                "Envía el parámetro ?confirmar_sincronizacion=true si estás seguro."
                            ),
                            "modo_tiendas": "sincronizar_maestro",
                            "accion_recomendada": "Revisar Excel antes de confirmar"
                        }
                    )
                
                logger.warning(
                    f"⚠️⚠️⚠️ OPERACIÓN DESTRUCTIVA CONFIRMADA ⚠️⚠️⚠️ - "
                    f"Usuario {get_user_id(user)} activó modo SINCRONIZAR_MAESTRO con confirmación. "
                    f"Se va a actualizar el maestro de tiendas (puede desactivar existentes)."
                )
            
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
            
            # Obtener ID del usuario (normalizado)
            user_id = get_user_id(user)
            
            # Log informativo sobre el procesamiento
            logger.info(
                f"⏱️ Iniciando procesamiento de plantilla '{file.filename}' "
                f"(tamaño: {file_size / 1024:.1f} KB). Esto puede tomar hasta 2 minutos."
            )
            
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
            
            # Construir mensaje de respuesta
            # Si hay errores en el resultado, usar el primer error como mensaje principal
            mensaje_respuesta = "Plantilla procesada y guardada exitosamente"
            if resultado["status"] == "validation_error":
                # Usar el primer error de la lista de errores si existe
                errores = resultado.get("errores", [])
                if errores:
                    mensaje_respuesta = errores[0]  # Mensaje específico del error
                else:
                    mensaje_respuesta = "Plantilla validada pero tiene errores críticos"
            elif resultado["status"] == "error":
                mensaje_respuesta = resultado.get("message", "Error al procesar plantilla")
            
            # Construir respuesta
            response_data = {
                "status": resultado["status"],
                "message": mensaje_respuesta,
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
        except BusinessException:
            # BusinessException se maneja en el exception handler global
            raise
        except Exception as e:
            logger.error(f"❌ Error al procesar plantilla: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al procesar la plantilla: {str(e)}"
            )
    
    @app.get("/api/plantillas/ultimo", tags=["Plantillas"])
    async def get_ultimo_pedido(
        incluir_respuesta: bool = Query(False, description="Incluir respuesta del proveedor si existe"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene el último pedido cargado por el usuario autenticado.
        
        **Características:**
        - ✅ Filtrado por usuario (cada usuario ve solo sus pedidos)
        - ✅ Devuelve el mismo formato que GET /api/plantillas/{identificador}
        - ✅ Útil para mostrar automáticamente el último Excel en la página de cargar plantillas
        
        **Query Parameters:**
        - `incluir_respuesta` (bool, default: false): Si true, incluye respuesta del proveedor si existe
        
        **Respuesta exitosa:**
        Mismo formato que GET /api/plantillas/{identificador}:
        ```json
        {
            "cabecera": {
                "pedido_id": "...",
                "numero_pedido": "...",
                "fecha_pedido": "...",
                ...
            },
            "detalles": [...],
            "respuesta_proveedor": {...}  // Solo si incluir_respuesta=true
        }
        ```
        
        **Respuesta si no hay pedidos:**
        ```json
        {
            "status": "not_found",
            "message": "No hay pedidos cargados para este usuario"
        }
        ```
        
        Returns:
            JSON con pedido completo (mismo formato que GET /api/plantillas/{identificador})
            O 404 si el usuario no tiene pedidos
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository
            
            # Obtener ID del usuario (normalizado, mismo que al subir Excel)
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Obtener el último pedido DEL USUARIO
                ultimo_pedido = repo.get_ultimo_pedido(user_id)
                
                if not ultimo_pedido:
                    # Retornar 200 OK con respuesta clara (no es un error, es un estado válido)
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "success",
                            "hay_datos": False,
                            "data": None,
                            "mensaje": "No hay pedidos cargados para este usuario"
                        }
                    )
                
                # Obtener pedido completo (mismo método que GET /api/plantillas/{identificador})
                pedido_completo = repo.get_pedido_completo(ultimo_pedido["pedido_id"])
                
                if not pedido_completo:
                    raise HTTPException(
                        status_code=500,
                        detail="Error al obtener detalles del último pedido"
                    )
                
                # Agregar respuesta si se solicita (mismo comportamiento que el endpoint existente)
                if incluir_respuesta:
                    respuesta_repo = PedidoRespuestaRepository(conn)
                    pedido_id = pedido_completo["cabecera"]["pedido_id"]
                    respuesta = respuesta_repo.obtener_respuesta_activa(pedido_id)
                    if respuesta:
                        pedido_completo["respuesta_proveedor"] = respuesta
                
                # Retornar con estructura consistente (200 OK, con hay_datos=True)
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "hay_datos": True,
                        "data": pedido_completo,
                        "mensaje": "Último pedido recuperado exitosamente"
                    }
                )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener último pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener último pedido: {str(e)}"
            )
    
    @app.get("/api/plantillas/{identificador}", tags=["Plantillas"])
    async def get_pedido(
        identificador: str = Path(..., description="Número de pedido (ej: 'P-12.48 - 12 - 2025') o UUID del pedido (para compatibilidad)"),
        incluir_respuesta: bool = Query(False, description="Incluir respuesta del proveedor si existe"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene un pedido completo con cabecera, detalles y distribuciones por tienda.
        Acepta número de pedido (recomendado) o UUID (para compatibilidad).
        Opcionalmente incluye la respuesta del proveedor.
        
        **Path Parameters:**
        - `identificador` (string, requerido) - Puede ser:
          - Número de pedido (business key, ej: 'P-12.48 - 12 - 2025') ⭐ RECOMENDADO
          - UUID del pedido (ej: 'AEDEC52D-D007-416F-8A09-9F0D31282EEE') ⚠️ Compatibilidad
        
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
            import re
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository
            
            # Detectar si es UUID (formato: 8-4-4-4-12 caracteres hexadecimales)
            uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            es_uuid = uuid_pattern.match(identificador.strip()) is not None
            
            with get_db_connection_context() as conn:
                repository = PedidoRepository(conn)
                
                # Usar método apropiado según el formato detectado
                if es_uuid:
                    logger.info(f"🔍 Detectado UUID: {identificador}, usando get_pedido_completo")
                    pedido = repository.get_pedido_completo(identificador)
                    if not pedido:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Pedido no encontrado con UUID: {identificador}"
                        )
                else:
                    logger.info(f"🔍 Detectado numero_pedido: {identificador}, usando get_pedido_completo_por_numero")
                    pedido = repository.get_pedido_completo_por_numero(identificador)
                    if not pedido:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Pedido no encontrado con número: {identificador}"
                        )
                
                # Agregar respuesta si se solicita y existe (usando pedido_id de la cabecera)
                if incluir_respuesta:
                    respuesta_repo = PedidoRespuestaRepository(conn)
                    pedido_id = pedido["cabecera"]["pedido_id"]
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
        validar_sap: bool = Query(True, description="Validar códigos de producto contra SAP"),
        sap_obligatorio: bool = Query(True, description="Si True, errores de SAP bloquean la importación. Si False, solo genera warnings"),
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
            
            # ✅ VALIDACIÓN SAP POST-PARSING (si está habilitada)
            if validar_sap and resultado.get("data"):
                from src.database.services.pedido_validator import PedidoValidator
                
                # Extraer códigos únicos de productos (performance: validar una vez por código)
                codigos_productos = list(set([
                    item.get("codigoProducto")
                    for item in resultado.get("data", [])
                    if item.get("codigoProducto")
                ]))
                
                if codigos_productos:
                    validator = PedidoValidator()
                    validacion_sap = validator.validar_productos_existen_en_sap(
                        codigos_productos=codigos_productos,
                        usar_cache=True,
                        sap_obligatorio=sap_obligatorio
                    )
                    
                    # Mapear códigos a filas para reportar errores por fila
                    # Crear mapa código -> lista de filas que lo usan
                    codigo_a_filas = {}
                    for item in resultado.get("data", []):
                        codigo = item.get("codigoProducto")
                        fila = item.get("filaOrigen")
                        if codigo and fila:
                            if codigo not in codigo_a_filas:
                                codigo_a_filas[codigo] = []
                            codigo_a_filas[codigo].append(fila)
                    
                    # Agregar errores y warnings por fila
                    codigos_no_encontrados = set(validacion_sap.get("no_encontrados", []))
                    codigos_errores = set(validacion_sap.get("errores", []))
                    codigos_warnings = set(validacion_sap.get("warnings", []))
                    
                    # Errores: códigos no encontrados o errores críticos
                    for codigo in (codigos_no_encontrados | codigos_errores):
                        detalle_codigo = validacion_sap.get("detalle", {}).get(codigo, {})
                        mensaje = detalle_codigo.get("mensaje") or f"El código de producto '{codigo}' no es válido en SAP"
                        
                        # Agregar error a todas las filas que usan este código
                        for fila in codigo_a_filas.get(codigo, []):
                            resultado["errores"].append({
                                "fila": fila,
                                "campo": "CodigoProducto",
                                "tipo": "ERROR",
                                "mensaje": mensaje
                            })
                    
                    # Warnings: errores de SAP pero no es obligatorio
                    for codigo in codigos_warnings:
                        detalle_codigo = validacion_sap.get("detalle", {}).get(codigo, {})
                        mensaje = detalle_codigo.get("mensaje") or f"No se pudo validar el código '{codigo}' en SAP"
                        
                        # Agregar warning a todas las filas que usan este código
                        for fila in codigo_a_filas.get(codigo, []):
                            resultado["errores"].append({
                                "fila": fila,
                                "campo": "CodigoProducto",
                                "tipo": "WARNING",
                                "mensaje": mensaje
                            })
                    
                    # ✅ RECALCULAR filasValidas/filasInvalidas (no modificar directamente)
                    # Contar filas con errores críticos (ERROR, no WARNING)
                    filas_con_errores_criticos = set()
                    for error in resultado.get("errores", []):
                        if error.get("tipo") == "ERROR":
                            fila = error.get("fila")
                            if fila and fila > 0:  # Fila válida (> 0)
                                filas_con_errores_criticos.add(fila)
                    
                    # Recalcular contadores
                    filas_leidas = resultado["resumen"].get("filasLeidas", 0)
                    filas_invalidas_originales = resultado["resumen"].get("filasInvalidas", 0)
                    
                    # Filas inválidas = errores originales del parsing + filas con errores SAP
                    # Pero solo contar una vez por fila
                    filas_invalidas_finales = max(
                        filas_invalidas_originales,
                        len(filas_con_errores_criticos)
                    )
                    
                    resultado["resumen"]["filasInvalidas"] = filas_invalidas_finales
                    resultado["resumen"]["filasValidas"] = max(
                        0,
                        filas_leidas - filas_invalidas_finales
                    )
                    
                    # Agregar resumen de validación SAP al resultado
                    resultado["validacion_sap"] = {
                        "total_codigos": len(codigos_productos),
                        "validos": len(validacion_sap.get("validos", [])),
                        "no_encontrados": len(codigos_no_encontrados),
                        "errores": len(codigos_errores),
                        "warnings": len(codigos_warnings),
                        "todos_validos": validacion_sap.get("todos_validos", False),
                        "detalle_validacion": {
                            codigo: {
                                "existe": info.get("existe"),
                                "severity": info.get("severity"),
                                "error": info.get("error"),
                                "mensaje": info.get("mensaje")
                            }
                            for codigo, info in validacion_sap.get("detalle", {}).items()
                        }
                    }
                    
                    logger.info(
                        f"📊 Validación SAP: {len(validacion_sap.get('validos', []))} válidos, "
                        f"{len(codigos_no_encontrados)} no encontrados, "
                        f"{len(codigos_errores)} errores, {len(codigos_warnings)} warnings"
                    )
            
            # Retornar resultado del parsing con validación SAP
            return JSONResponse(
                status_code=200,
                content=resultado
            )
            
        except HTTPException:
            raise
        except BusinessException:
            # BusinessException se maneja en el exception handler global
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
            usuario_id = get_user_id(user)
            
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
    

    @app.get("/api/pedidos/{pedido_id}/reporte-diferencias", tags=["Pedidos - Reportes"])
    async def obtener_reporte_diferencias(
        pedido_id: str = Path(..., description="UUID del pedido"),
        formato: str = Query("json", description="Formato del reporte: json, excel, csv"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Genera un reporte de diferencias entre solicitado y confirmado.
        
        **Útil para:**
        - Revisar qué productos fueron confirmados parcialmente
        - Analizar cambios de precio
        - Auditoría de confirmaciones
        
        Returns:
            Reporte en el formato solicitado
        """
        try:
            from src.database.services.pedido_ajuste_service import PedidoAjusteService
            
            service = PedidoAjusteService()
            reporte = service.generar_reporte_diferencias(
                pedido_id=pedido_id,
                formato=formato
            )
            
            if formato == "json":
                return reporte
            else:
                # Para Excel/CSV, retornar archivo
                raise NotImplementedError(f"Formato {formato} pendiente de implementar")
                
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "message": str(e)
                }
            )
        except NotImplementedError as e:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail={
                    "error": "not_implemented",
                    "message": str(e)
                }
            )
        except Exception as e:
            logger.error(f"❌ Error al generar reporte: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": "Error interno al generar reporte"
                }
            )
    
    @app.post("/api/pedidos/{pedido_id}/crear-orden-compra", tags=["Pedidos - ODC"])
    async def crear_orden_compra_desde_pedido(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Crea una orden de compra desde un pedido confirmado.
        
        **FASE 5: Generación de ODC desde cantidades confirmadas**
        
        **Flujo:**
        1. Valida que el pedido tenga respuesta aprobada
        2. Obtiene cantidades confirmadas (cantidad_confirmada_total > 0)
        3. Convierte unidades (docenas → packs SAP)
        4. Obtiene SKU SAP desde homologación/cache
        5. Crea OC con pedido_id asociado
        6. Estado inicial: PENDIENTE (lista para enviar a SAP)
        
        **Diferencia con /procesar-oc:**
        - Este endpoint es para **PEDIDOS confirmados** (flujo nuevo)
        - `/procesar-oc` es para **DESPACHOS legacy** (flujo antiguo)
        
        **Validaciones:**
        - ✅ Pedido debe existir
        - ✅ Debe tener respuesta del proveedor en estado APROBADA
        - ✅ Debe haber productos con cantidad_confirmada_total > 0
        - ✅ Todos los productos deben tener SKU SAP homologado
        - ✅ Todos los productos deben tener unidad de conversión
        
        **Respuesta exitosa:**
        ```json
        {
            "status": "success",
            "message": "Orden de compra creada exitosamente",
            "oc_id": "uuid-de-la-oc",
            "pedido_id": "uuid-del-pedido",
            "proveedor": "P1790389219001",
            "estado": "PENDIENTE",
            "detalles_insertados": 10,
            "total_lineas": 10,
            "warnings": []
        }
        ```
        
        **Próximo paso:**
        Después de crear la OC, usar `POST /integrar-sap` para enviarla a SAP.
        
        Returns:
            JSON con resultado de la creación de la OC
        """
        try:
            from src.database.services.pedido_oc_service import PedidoOCService
            
            user_id = user.get("sub") or user.get("user_id")
            
            service = PedidoOCService()
            resultado = service.crear_oc_desde_pedido_confirmado(
                pedido_id=pedido_id,
                usuario_id=user_id
            )
            
            return {
                "status": "success",
                "message": "Orden de compra creada exitosamente",
                **resultado
            }
            
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "message": str(e)
                }
            )
        except Exception as e:
            logger.error(f"❌ Error al crear orden de compra: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al crear orden de compra: {str(e)}"
                }
            )
    
    @app.patch("/api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/costo", tags=["Pedidos - Edición"])
    async def actualizar_costo_detalle(
        numero_pedido: str = Path(..., description="Número del pedido"),
        pedido_detalle_id: str = Path(..., description="UUID del detalle del pedido"),
        request_body: ActualizarCostoRequest = Body(..., description="Datos del costo a actualizar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Actualiza el costo unitario de una línea de detalle del pedido.
        
        **Funcionalidad:**
        - Permite edición inline del costo unitario desde la UI
        - Actualiza directamente en la tabla pedido_detalle
        - Recalcula totales automáticamente
        
        **Validaciones:**
        - ✅ El detalle debe existir
        - ✅ El nuevo costo debe ser un número válido ≥ 0
        - ✅ Solo usuarios con permiso 'mba3-consultas.proceso.execute' pueden actualizar
        
        **Request:**
        ```
        PATCH /api/pedidos/176120/detalle/550e8400-e29b-41d4-a716-446655440000/costo
        {
            "costo_doc_sin_iva": 25.50
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Costo actualizado correctamente",
            "pedido_detalle_id": "550e8400-e29b-41d4-a716-446655440000",
            "costo_anterior": 20.00,
            "costo_nuevo": 25.50,
            "total_actualizado": 510.00
        }
        ```
        """
        cursor = None
        try:
            # Importar aquí para evitar circular imports
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            
            # Extraer el costo del request body
            nuevo_costo = request_body.costo_doc_sin_iva
            
            # Obtener usuario que realiza la modificación
            user_id = get_user_id(user)
            
            # Conectar a BD
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Actualizar costo con información de auditoría
                resultado = repo.update_costo_detalle(pedido_detalle_id, nuevo_costo, modificado_por=user_id)
            
            if resultado["success"]:
                logger.info(f"✅ Costo actualizado para detalle {pedido_detalle_id} por usuario {user.get('username', 'UNKNOWN')}")
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "status": "success",
                        "message": resultado["mensaje"],
                        "pedido_detalle_id": resultado["pedido_detalle_id"],
                        "costo_anterior": resultado["costo_anterior"],
                        "costo_nuevo": resultado["costo_nuevo"]
                    }
                )
            else:
                logger.warning(f"⚠️ {resultado['mensaje']}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "detalle_not_found",
                        "message": resultado["mensaje"]
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al actualizar costo: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al actualizar costo: {str(e)}"
                }
            )
    
    @app.patch("/api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/total", tags=["Pedidos - Edición"])
    async def actualizar_total_detalle(
        numero_pedido: str = Path(..., description="Número del pedido"),
        pedido_detalle_id: str = Path(..., description="UUID del detalle del pedido"),
        request_body: ActualizarTotalRequest = Body(..., description="Datos del total a actualizar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Actualiza el total de una línea de detalle del pedido y recalcula el costo unitario.
        
        **Funcionalidad:**
        - Permite edición inline del total desde la UI
        - Actualiza directamente en la tabla pedido_detalle
        - Recalcula el costo unitario automáticamente (total / cantidad)
        
        **Validaciones:**
        - ✅ El detalle debe existir
        - ✅ El nuevo total debe ser un número válido ≥ 0
        - ✅ Solo usuarios con permiso 'mba3-consultas.proceso.execute' pueden actualizar
        
        **Request:**
        ```
        PATCH /api/pedidos/176120/detalle/550e8400-e29b-41d4-a716-446655440000/total
        {
            "total": 510.00
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Total actualizado correctamente. Nuevo costo unitario: 25.50",
            "pedido_detalle_id": "550e8400-e29b-41d4-a716-446655440000",
            "total_anterior": 500.00,
            "total_nuevo": 510.00,
            "costo_actualizado": 25.50
        }
        ```
        """
        cursor = None
        try:
            # Importar aquí para evitar circular imports
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            
            # Extraer el total del request body
            nuevo_total = request_body.total
            
            # Obtener usuario que realiza la modificación
            user_id = get_user_id(user)
            
            # Conectar a BD
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Actualizar total con información de auditoría
                resultado = repo.update_total_detalle(pedido_detalle_id, nuevo_total, modificado_por=user_id)
            
            if resultado["success"]:
                logger.info(f"✅ Total actualizado para detalle {pedido_detalle_id} por usuario {user.get('username', 'UNKNOWN')}")
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "status": "success",
                        "message": resultado["mensaje"],
                        "pedido_detalle_id": resultado["pedido_detalle_id"],
                        "total_anterior": resultado["total_anterior"],
                        "total_nuevo": resultado["total_nuevo"],
                        "costo_actualizado": resultado["costo_actualizado"]
                    }
                )
            else:
                logger.warning(f"⚠️ {resultado['mensaje']}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "detalle_not_found",
                        "message": resultado["mensaje"]
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al actualizar total: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al actualizar total: {str(e)}"
                }
            )
    
    @app.patch("/api/pedidos/{numero_pedido}/detalle/{pedido_detalle_id}/comentario", tags=["Pedidos - Edición"])
    async def actualizar_comentario_detalle(
        numero_pedido: str = Path(..., description="Número del pedido"),
        pedido_detalle_id: str = Path(..., description="UUID del detalle del pedido"),
        request_body: ActualizarComentarioRequest = Body(..., description="Datos del comentario a actualizar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Actualiza el comentario de una línea de detalle del pedido.
        
        **Funcionalidad:**
        - Permite edición inline del comentario desde la UI
        - Actualiza directamente en la tabla pedido_detalle
        - Permite limpiar el comentario enviando null o string vacío
        
        **Validaciones:**
        - ✅ El detalle debe existir
        - ✅ El comentario puede ser null o string (máximo 2000 caracteres)
        - ✅ Solo usuarios con permiso 'mba3-consultas.proceso.execute' pueden actualizar
        
        **Request:**
        ```
        PATCH /api/pedidos/176120/detalle/550e8400-e29b-41d4-a716-446655440000/comentario
        {
            "comentario": "Producto con descuento especial"
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Comentario actualizado correctamente",
            "pedido_detalle_id": "550e8400-e29b-41d4-a716-446655440000",
            "comentario_anterior": null,
            "comentario_nuevo": "Producto con descuento especial"
        }
        ```
        """
        cursor = None
        try:
            # Importar aquí para evitar circular imports
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            
            # Extraer el comentario del request body
            nuevo_comentario = request_body.comentario
            
            # Obtener usuario que realiza la modificación
            user_id = get_user_id(user)
            
            # Conectar a BD
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Actualizar comentario con información de auditoría
                resultado = repo.update_comentario_detalle(pedido_detalle_id, nuevo_comentario, modificado_por=user_id)
            
            if resultado["success"]:
                logger.info(f"✅ Comentario actualizado para detalle {pedido_detalle_id} por usuario {user.get('username', 'UNKNOWN')}")
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "status": "success",
                        "message": resultado["mensaje"],
                        "pedido_detalle_id": resultado["pedido_detalle_id"],
                        "comentario_anterior": resultado["comentario_anterior"],
                        "comentario_nuevo": resultado["comentario_nuevo"],
                        "costo_nuevo": None,  # No aplica para comentario
                        "total_actualizado": None  # No aplica para comentario
                    }
                )
            else:
                logger.warning(f"⚠️ {resultado['mensaje']}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "detalle_not_found",
                        "message": resultado["mensaje"]
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al actualizar comentario: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al actualizar comentario: {str(e)}"
                }
            )
    
    @app.post("/api/pedidos/{numero_pedido}/modificaciones-columnas",
              response_model=GuardarModificacionesColumnasResponse,
              tags=["Pedidos - Modificaciones"])
    async def guardar_modificaciones_columnas(
            numero_pedido: str = Path(..., description="Número del pedido"),
            request_body: GuardarModificacionesColumnasRequest = Body(..., description="Datos de las modificaciones"),
            user: Dict = Depends(verify_jwt_token),
            _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Guarda o actualiza las modificaciones de columnas para un pedido.
        
        **Funcionalidad:**
        - Almacena qué columnas (costo_doc_sin_iva, total, comentario) fueron modificadas manualmente
        - Permite al frontend persistir el estado de resaltado de celdas modificadas
        - Incluye información de auditoría (usuario, fecha)
        
        **Validaciones:**
        - ✅ El pedido debe existir
        - ✅ Los detalles deben pertenecer al pedido
        - ✅ Solo columnas válidas: costo_doc_sin_iva, total, comentario
        - ✅ Solo usuarios con permiso 'mba3-consultas.proceso.execute' pueden guardar
        
        **Request:**
        ```json
        {
            "numero_pedido": "P-12.48 - 12 - 2025",
            "modificaciones": [
                {
                    "pedido_detalle_id": "uuid-del-detalle",
                    "columna_key": "costo_doc_sin_iva"
                },
                {
                    "pedido_detalle_id": "uuid-del-detalle-2",
                    "columna_key": "total"
                }
            ]
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Se guardaron 2 modificaciones correctamente",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "modificaciones_guardadas": 2
        }
        ```
        """
        try:
            # Importar aquí para evitar circular imports
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            
            # Validar que el numero_pedido coincida
            if request_body.numero_pedido != numero_pedido:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "numero_pedido_mismatch",
                        "message": f"El número de pedido en la URL ({numero_pedido}) no coincide con el del body ({request_body.numero_pedido})"
                    }
                )
            
            # Convertir modificaciones a lista de diccionarios
            modificaciones_list = [
                {
                    "pedido_detalle_id": mod.pedido_detalle_id,
                    "columna_key": mod.columna_key
                }
                for mod in request_body.modificaciones
            ]
            
            # Obtener usuario que realiza la modificación
            user_id = get_user_id(user)
            
            # Conectar a BD
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Guardar modificaciones
                resultado = repo.guardar_modificaciones_columnas(
                    numero_pedido=numero_pedido,
                    modificaciones=modificaciones_list,
                    modificado_por=user_id
                )
            
            if resultado["success"]:
                logger.info(f"✅ Modificaciones guardadas para pedido {numero_pedido} por usuario {user.get('username', 'UNKNOWN')}")
                return GuardarModificacionesColumnasResponse(
                    status="success",
                    message=resultado["mensaje"],
                    numero_pedido=numero_pedido,
                    modificaciones_guardadas=resultado["modificaciones_guardadas"]
                )
            else:
                logger.warning(f"⚠️ {resultado['mensaje']}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "pedido_not_found",
                        "message": resultado["mensaje"]
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al guardar modificaciones de columnas: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al guardar modificaciones: {str(e)}"
                }
            )
    
    @app.get("/api/pedidos/{numero_pedido}/modificaciones-columnas",
             response_model=ObtenerModificacionesColumnasResponse,
             tags=["Pedidos - Modificaciones"])
    async def obtener_modificaciones_columnas(
            numero_pedido: str = Path(..., description="Número del pedido"),
            user: Dict = Depends(verify_jwt_token),
            _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene las modificaciones de columnas para un pedido.
        
        **Funcionalidad:**
        - Retorna qué columnas fueron modificadas manualmente para cada detalle
        - Incluye información de auditoría (usuario, fecha)
        - Permite al frontend restaurar el estado de resaltado
        
        **Validaciones:**
        - ✅ El pedido debe existir
        - ✅ Solo usuarios con permiso 'mba3-consultas.facturas.view' pueden obtener
        
        **Response exitosa:**
        ```json
        {
            "status": "success",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "modificaciones": [
                {
                    "pedido_detalle_id": "uuid-del-detalle",
                    "columna_key": "costo_doc_sin_iva",
                    "modificado_por": "usuario@ejemplo.com",
                    "fecha_modificacion": "2025-01-15T10:30:00Z"
                }
            ]
        }
        ```
        
        **Response sin modificaciones:**
        ```json
        {
            "status": "success",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "modificaciones": []
        }
        ```
        """
        try:
            # Importar aquí para evitar circular imports
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            
            # Conectar a BD
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Obtener modificaciones
                resultado = repo.obtener_modificaciones_columnas(numero_pedido=numero_pedido)
            
            if not resultado["success"]:
                logger.warning(f"⚠️ {resultado['mensaje']}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "pedido_not_found",
                        "message": resultado["mensaje"]
                    }
                )
            
            # Convertir modificaciones a objetos ModificacionColumnaItem
            from src.models import ModificacionColumnaItem
            
            modificaciones_items = [
                ModificacionColumnaItem(
                    pedido_detalle_id=mod["pedido_detalle_id"],
                    columna_key=mod["columna_key"],
                    modificado_por=mod["modificado_por"],
                    fecha_modificacion=mod["fecha_modificacion"]
                )
                for mod in resultado["modificaciones"]
            ]
            
            logger.info(f"✅ Modificaciones obtenidas para pedido {numero_pedido} por usuario {user.get('username', 'UNKNOWN')}")
            return ObtenerModificacionesColumnasResponse(
                status="success",
                numero_pedido=numero_pedido,
                modificaciones=modificaciones_items
            )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener modificaciones de columnas: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener modificaciones: {str(e)}"
                }
            )
    
    @app.post("/api/pedidos/{numero_pedido}/notificar-confirmacion", tags=["Pedidos - Notificaciones"])
    async def notificar_confirmacion_pedido(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: NotificarConfirmacionRequest = Body(..., description="Datos de la notificación"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Envía un correo electrónico a MABEL TRADING notificando que se requiere confirmación de un pedido.
        
        **Funcionalidad:**
        - Obtiene los datos del pedido desde la base de datos
        - Construye un correo HTML con información del pedido
        - Incluye un link directo para confirmar el pedido
        - Envía el correo usando la configuración SMTP existente
        
        **Request:**
        ```json
        {
            "usuario_origen": "EL RAYO",
            "usuario_destino": "MABEL TRADING",
            "url_confirmacion": "https://tu-dominio.com/mba3-consultas/pedidos/P-12.48%20-%2012%20-%202025?modo=confirmacion&usuario=mabel-trading"
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Notificación enviada exitosamente a MABEL TRADING",
            "data": {
                "numero_pedido": "P-12.48 - 12 - 2025",
                "email_enviado_a": "mabel.trading@example.com",
                "fecha_envio": "2025-01-15T10:30:00Z"
            }
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            from src.utils.email_notifier_pedido import send_pedido_confirmacion_notification
            from datetime import datetime
            
            # Obtener datos del request
            usuario_origen = request_body.usuario_origen
            usuario_destino = request_body.usuario_destino
            email_destino = request_body.email_destino  # Opcional
            url_confirmacion = request_body.url_confirmacion  # Opcional
            
            # Obtener pedido desde la base de datos
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Intentar obtener por número de pedido primero
                pedido_data = repo.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
            
            # Enviar correo
            fecha_envio = datetime.now()
            email_enviado = send_pedido_confirmacion_notification(
                pedido_data=pedido_data,
                numero_pedido=numero_pedido,
                usuario_origen=usuario_origen,
                usuario_destino=usuario_destino,
                email_destino=email_destino,
                url_confirmacion=url_confirmacion,
                fecha_ejecucion=fecha_envio
            )
            
            if email_enviado:
                logger.info(f"✅ Notificación de confirmación enviada para pedido {numero_pedido} por usuario {user.get('username', 'UNKNOWN')}")
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "status": "success",
                        "message": f"Notificación enviada exitosamente a {usuario_destino}",
                        "data": {
                            "numero_pedido": numero_pedido,
                            "email_enviado_a": email_destino or "MABEL TRADING (configurado)",
                            "fecha_envio": fecha_envio.isoformat()
                        }
                    }
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": "email_send_failed",
                        "message": "No se pudo enviar el correo electrónico. Verifique la configuración SMTP."
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al notificar confirmación de pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al enviar notificación: {str(e)}"
                }
            )
    
    # ============================================================================
    # ENDPOINTS FASE 3: Interfaz Web para Proveedor (NUEVO)
    # ============================================================================
    
    @app.get("/api/pedidos/{pedido_id}/formulario-proveedor", 
             response_model=FormularioProveedorResponse,
             tags=["Pedidos - Proveedor"])
    async def obtener_formulario_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene los datos del pedido formateados para el formulario web del proveedor.
        
        **Características:**
        - ✅ Idempotente: muestra respuesta existente si ya respondió
        - ✅ Indica si puede responder (no está cerrado/bloqueado)
        - ✅ Incluye datos de respuesta previa si existe
        - ✅ Muestra estado claro del pedido
        
        **Estados que bloquean respuesta:**
        - `CONFIRMADO_PROVEEDOR`
        - `ORDEN_COMPRA_CREADA`
        - `ENVIADA_SAP`
        - `CERRADO`
        - `CANCELADO`
        
        **Respuesta exitosa:**
        ```json
        {
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "fecha_pedido": "2025-01-21",
            "proveedor_nombre": "Proveedor XYZ",
            "estado_pedido": "PENDIENTE_CONFIRMACION_PROVEEDOR",
            "puede_responder": true,
            "tiene_respuesta": false,
            "productos": [
                {
                    "pedido_detalle_id": "...",
                    "codigo_producto": "PROD001",
                    "descripcion": "Producto ejemplo",
                    "cantidad_total_solicitada": 100,
                    "costo_unitario_original": 50.00,
                    "tiendas": [...]
                }
            ]
        }
        ```
        
        Returns:
            JSON con datos formateados para formulario
        """
        try:
            from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
            
            service = PedidoProveedorWebService()
            formulario = service.obtener_formulario_proveedor(pedido_id)
            
            return JSONResponse(status_code=200, content=formulario)
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al obtener formulario proveedor: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener formulario: {str(e)}"
            )
    
    @app.post("/api/pedidos/{pedido_id}/enviar-respuesta-proveedor",
              response_model=RespuestaProveedorResponse,
              tags=["Pedidos - Proveedor"])
    async def enviar_respuesta_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        respuesta: RespuestaProveedorRequest = Body(...),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Recibe la respuesta del proveedor desde el formulario web.
        
        **Características:**
        - ✅ Reutiliza validaciones de PedidoProveedorService
        - ✅ Soporta guardar como borrador o confirmado
        - ✅ Validación estricta solo si es confirmado
        - ✅ Borradores pueden tener errores (se guardan con warnings)
        
        **Estados de respuesta:**
        - `borrador`: Guarda sin validación estricta, estado `BORRADOR`
        - `confirmado`: Valida estrictamente, estado `PENDIENTE_REVISION`, actualiza pedido
        
        **Validaciones aplicadas:**
        - ✅ Cantidad confirmada >= 0
        - ✅ Cantidad confirmada <= cantidad solicitada (CRÍTICO)
        - ✅ Precios ajustados >= 0
        - ⚠️ Warning si confirma menos del 80%
        - ⚠️ Warning si precio aumenta más del 10%
        
        **Request:**
        ```json
        {
            "productos": [
                {
                    "pedido_detalle_id": "...",
                    "codigo_producto": "PROD001",
                    "cantidad_confirmada_total": 100,
                    "costo_unitario_ajustado": 50.00,
                    "descuento_ajustado": 5.0,
                    "observaciones": "Disponible",
                    "distribucion_tiendas": [
                        {"tienda_id": "...", "cantidad_confirmada": 60}
                    ]
                }
            ],
            "observaciones_generales": "Todos disponibles",
            "estado": "confirmado"
        }
        ```
        
        **Respuesta exitosa:**
        ```json
        {
            "status": "success",
            "message": "Respuesta del proveedor guardada como confirmado",
            "respuesta_id": "...",
            "validacion": {
                "valido": true,
                "errores": [],
                "warnings": [...]
            },
            "cantidades_guardadas": 10,
            "precios_guardados": 5,
            "pedido_id": "...",
            "estado_guardado": "PENDIENTE_REVISION"
        }
        ```
        
        **Respuesta con errores (solo si es confirmado):**
        ```json
        {
            "status": "validation_error",
            "message": "La respuesta contiene errores de validación y no puede ser confirmada",
            "validacion": {
                "valido": false,
                "errores": [...],
                "warnings": [...]
            },
            "pedido_id": "..."
        }
        ```
        
        Returns:
            JSON con resultado del procesamiento
        """
        try:
            from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
            
            service = PedidoProveedorWebService()
            usuario_id = get_user_id(user)
            
            # Convertir productos a formato dict
            productos_dict = [producto.model_dump() for producto in respuesta.productos]
            
            resultado = service.procesar_respuesta_proveedor_web(
                pedido_id=pedido_id,
                productos=productos_dict,
                observaciones_generales=respuesta.observaciones_generales,
                estado=respuesta.estado,
                usuario_id=usuario_id
            )
            
            status_code = 200
            if resultado["status"] == "validation_error":
                status_code = 400
            
            return JSONResponse(status_code=status_code, content=resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al enviar respuesta del proveedor: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al procesar respuesta: {str(e)}"
            )
    
    @app.post("/api/pedidos/{pedido_id}/crear-respuesta-desde-pedido",
              response_model=RespuestaProveedorResponse,
              tags=["Pedidos - Proveedor"])
    async def crear_respuesta_desde_pedido(
            pedido_id: str = Path(..., description="UUID del pedido"),
            user: Dict = Depends(verify_jwt_token),
            _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
        ):
        """
        Guarda los cambios realizados por EL RAYO y crea la respuesta del proveedor.
        
        **FASE 3: Confirmación por EL RAYO**
        
        Este endpoint se usa cuando EL RAYO ha editado directamente los campos del pedido
        (costo_doc_sin_iva, total, comentario) y hace clic en "Confirmar".
        
        **Características:**
        - ✅ Guarda los cambios realizados por EL RAYO (costo, total, comentario)
        - ✅ Crea respuesta automáticamente desde los cambios en pedido.detalles
        - ✅ Usa el campo `total` como cantidad confirmada
        - ✅ Usa el campo `costo_doc_sin_iva` como costo ajustado (sin recalcular)
        - ✅ Valida la respuesta antes de guardarla
        - ✅ Actualiza el estado del pedido a RESPUESTA_PROVEEDOR_CARGADA
        - ❌ NO procesa la confirmación automáticamente
        - ❌ NO ajusta cantidades por tienda
        - ❌ NO recalcula costos
        - ❌ NO genera reporte de diferencias
        
        **Flujo:**
        1. EL RAYO edita `costo_doc_sin_iva`, `total` y/o `comentario` en la tabla
        2. Al hacer clic en "Confirmar", se llama a este endpoint
        3. Se guardan los cambios en la base de datos
        4. Se crea la respuesta automáticamente desde los cambios guardados
        5. El estado del pedido se actualiza a RESPUESTA_PROVEEDOR_CARGADA
        6. El frontend navega a la interfaz de redistribución (Fase 4)
        
        **Próximo paso (Fase 4):**
        MABEL TRADING debe redistribuir manualmente las cantidades por tienda
        desde el total confirmado. Los costos unitarios permanecen como los guardó EL RAYO.
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Cambios guardados y respuesta creada exitosamente",
            "respuesta_id": "...",
            "pedido_id": "...",
            "validacion": {...},
            "cantidades_guardadas": 10,
            "precios_guardados": 5,
            "estado_guardado": "PENDIENTE_REVISION"
        }
        ```
        
        Returns:
            JSON con resultado del guardado y creación de respuesta
        """
        try:
            from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
            
            usuario_id = get_user_id(user)
            
            # Observaciones generales opcionales (por ahora None, se puede agregar body después si es necesario)
            observaciones_generales = None
            
            logger.info(f"Guardando cambios y creando respuesta para pedido {pedido_id} (usuario: {usuario_id})")
            
            # Crear respuesta desde pedido (esto guarda los cambios y crea la respuesta)
            web_service = PedidoProveedorWebService()
            resultado = web_service.crear_respuesta_desde_pedido(
                pedido_id=pedido_id,
                usuario_id=usuario_id,
                observaciones_generales=observaciones_generales
            )
            
            # El resultado ya incluye toda la información necesaria
            # No se procesa confirmación, no se ajustan cantidades, no se recalculan costos
            logger.info(f"✅ Cambios guardados y respuesta creada para pedido {pedido_id}. Estado: RESPUESTA_PROVEEDOR_CARGADA")
            
            return JSONResponse(status_code=200, content=resultado)
            
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"❌ Error de validación al guardar cambios: {e}")
            raise HTTPException(status_code=400, detail=error_msg)
        except Exception as e:
            logger.error(f"❌ Error al guardar cambios del pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al guardar cambios del pedido: {str(e)}"
            )
    
    # ============================================================================
    # ENDPOINTS: Historial de Confirmaciones de EL RAYO
    # ============================================================================
    
    @app.get("/api/pedidos/{pedido_id}/confirmaciones-rayo",
             response_model=ConfirmacionRayoListResponse,
             tags=["Pedidos - Confirmaciones"])
    async def obtener_confirmaciones_rayo(
        pedido_id: str = Path(..., description="UUID del pedido"),
        limit: Optional[int] = Query(None, ge=1, le=100, description="Número máximo de confirmaciones a retornar (opcional)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene el historial de confirmaciones realizadas por EL RAYO para un pedido.
        
        **Funcionalidad:**
        - Muestra todas las confirmaciones realizadas por EL RAYO
        - Incluye valores anteriores y nuevos para cada confirmación
        - Permite ver qué cambios se realizaron en cada confirmación
        - Ordenado por fecha descendente (más reciente primero)
        
        **Query Parameters:**
        - `limit` (int, opcional): Número máximo de confirmaciones a retornar. Por defecto retorna todas.
        
        **Response:**
        ```json
        {
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "total_confirmaciones": 2,
            "confirmaciones": [
                {
                    "confirmacion_id": "...",
                    "pedido_id": "...",
                    "respuesta_id": "...",
                    "confirmado_por": "usuario@example.com",
                    "fecha_confirmacion": "2026-01-15T10:30:00",
                    "total_detalles_modificados": 3,
                    "detalles": [...]
                }
            ]
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_confirmacion_rayo_repository import PedidoConfirmacionRayoRepository
            from src.database.repositories.pedido_repository import PedidoRepository
            
            with get_db_connection_context() as conn:
                # Verificar que el pedido existe
                repo_pedido = PedidoRepository(conn)
                pedido = repo_pedido.get_pedido_completo(pedido_id)
                
                if not pedido:
                    raise HTTPException(status_code=404, detail=f"Pedido no encontrado: {pedido_id}")
                
                # Obtener confirmaciones
                repo_confirmacion = PedidoConfirmacionRayoRepository(conn)
                confirmaciones_data = repo_confirmacion.obtener_confirmaciones_por_pedido(
                    pedido_id=pedido_id,
                    limit=limit
                )
                
                # Construir respuesta con detalles
                confirmaciones = []
                for conf_data in confirmaciones_data:
                    # Obtener detalles de cada confirmación
                    confirmacion_completa = repo_confirmacion.obtener_confirmacion(conf_data["confirmacion_id"])
                    if confirmacion_completa:
                        confirmaciones.append(ConfirmacionRayoItem(**confirmacion_completa))
                
                return ConfirmacionRayoListResponse(
                    pedido_id=pedido_id,
                    numero_pedido=pedido["cabecera"].get("numero_pedido"),
                    total_confirmaciones=len(confirmaciones),
                    confirmaciones=confirmaciones
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener confirmaciones de EL RAYO: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener confirmaciones: {str(e)}"
            )
    
    @app.get("/api/pedidos/{pedido_id}/confirmaciones-rayo/{confirmacion_id}",
             response_model=ConfirmacionRayoDetailResponse,
             tags=["Pedidos - Confirmaciones"])
    async def obtener_detalle_confirmacion_rayo(
        pedido_id: str = Path(..., description="UUID del pedido"),
        confirmacion_id: str = Path(..., description="UUID de la confirmación"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene el detalle completo de una confirmación específica de EL RAYO.
        
        **Funcionalidad:**
        - Muestra todos los detalles de cambios realizados en una confirmación específica
        - Incluye valores anteriores y nuevos para cada campo modificado
        - Permite ver exactamente qué se cambió en cada detalle del pedido
        
        **Response:**
        ```json
        {
            "confirmacion": {
                "confirmacion_id": "...",
                "pedido_id": "...",
                "respuesta_id": "...",
                "confirmado_por": "usuario@example.com",
                "fecha_confirmacion": "2026-01-15T10:30:00",
                "total_detalles_modificados": 3,
                "detalles": [
                    {
                        "confirmacion_detalle_id": "...",
                        "pedido_detalle_id": "...",
                        "codigo_producto": "R225.1012.BCO",
                        "costo_anterior": 25.50,
                        "costo_nuevo": 26.00,
                        "total_anterior": 510,
                        "total_nuevo": 520,
                        "cambio_costo": true,
                        "cambio_total": true,
                        "cambio_comentario": false
                    }
                ]
            }
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_confirmacion_rayo_repository import PedidoConfirmacionRayoRepository
            from src.database.repositories.pedido_repository import PedidoRepository
            
            with get_db_connection_context() as conn:
                # Verificar que el pedido existe
                repo_pedido = PedidoRepository(conn)
                pedido = repo_pedido.get_pedido_completo(pedido_id)
                
                if not pedido:
                    raise HTTPException(status_code=404, detail=f"Pedido no encontrado: {pedido_id}")
                
                # Obtener confirmación
                repo_confirmacion = PedidoConfirmacionRayoRepository(conn)
                confirmacion_data = repo_confirmacion.obtener_confirmacion(confirmacion_id)
                
                if not confirmacion_data:
                    raise HTTPException(status_code=404, detail=f"Confirmación no encontrada: {confirmacion_id}")
                
                # Verificar que la confirmación pertenece al pedido
                if confirmacion_data["pedido_id"] != pedido_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"La confirmación {confirmacion_id} no pertenece al pedido {pedido_id}"
                    )
                
                return ConfirmacionRayoDetailResponse(
                    confirmacion=ConfirmacionRayoItem(**confirmacion_data)
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener detalle de confirmación: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener detalle de confirmación: {str(e)}"
            )
    
    # ============================================================================
    # ENDPOINTS FASE 4: Ajuste y Redistribución (MABEL TRADING)
    # ============================================================================
    
    @app.get("/api/pedidos/{pedido_id}/distribucion", 
             response_model=DistribucionPedidoResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_distribucion(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, obtiene la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene la distribución confirmada de un pedido.
        
        **Funcionalidad:**
        - Obtiene la redistribución realizada por MABEL TRADING
        - Incluye cantidades solicitadas, confirmadas y asignadas
        - Muestra costos originales y ajustados
        - Permite especificar una versión específica o obtener la última
        
        **Query Parameters:**
        - `version` (int, opcional): Versión específica a obtener. Si no se especifica, obtiene la última versión.
        
        **Response:**
        ```json
        {
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "version_actual": 1,
            "estado_pedido": "EN_AJUSTE_MABEL",
            "productos": [
                {
                    "pedido_detalle_id": "...",
                    "codigo_interno": "R225.1012.BCO",
                    "descripcion_sap": "...",
                    "cantidad_solicitada_total": 100,
                    "cantidad_confirmada_total": 80,
                    "cantidad_asignada_total": 75,
                    "distribuciones": [...]
                }
            ]
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            from src.database.repositories.pedido_repository import PedidoRepository
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener distribución
                distribucion_data = repo_dist.get_distribucion_completa(pedido_id, version)
                
                # Obtener datos del pedido para completar información
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                # Enriquecer productos con información del pedido
                productos_enriquecidos = []
                for producto_dist in distribucion_data["productos"]:
                    pedido_detalle_id = producto_dist["pedido_detalle_id"]
                    
                    # Buscar detalle en el pedido
                    detalle_pedido = next(
                        (d for d in pedido_data["detalles"] if d["pedido_detalle_id"] == pedido_detalle_id),
                        None
                    )
                    
                    if detalle_pedido:
                        productos_enriquecidos.append({
                            "pedido_detalle_id": pedido_detalle_id,
                            "codigo_interno": detalle_pedido.get("codigo_interno"),
                            "descripcion_sap": detalle_pedido.get("descripcion_sap"),
                            "cantidad_solicitada_total": producto_dist["cantidad_solicitada_total"],
                            "cantidad_confirmada_total": producto_dist["cantidad_confirmada_total"],
                            "cantidad_asignada_total": producto_dist["cantidad_asignada_total"],
                            "distribuciones": producto_dist["distribuciones"]
                        })
                    else:
                        productos_enriquecidos.append(producto_dist)
                
                return DistribucionPedidoResponse(
                    pedido_id=pedido_id,
                    numero_pedido=pedido_data["cabecera"]["numero_pedido"],
                    version_actual=distribucion_data["version_actual"],
                    estado_pedido=pedido_data["cabecera"].get("estado"),
                    productos=productos_enriquecidos
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener distribución: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener distribución: {str(e)}"
                }
            )
    
    @app.post("/api/pedidos/{pedido_id}/redistribuir", tags=["Pedidos - Redistribución"])
    async def redistribuir_pedido(
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: RedistribuirPedidoRequest = Body(..., description="Datos de la redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Crea una nueva redistribución para un pedido (OBLIGATORIO - Fase 4).
        
        **FASE 4: Redistribución por MABEL TRADING (OBLIGATORIA)**
        
        Este endpoint es OBLIGATORIO después de que EL RAYO confirma los cambios (Fase 3).
        MABEL TRADING debe redistribuir manualmente las cantidades por tienda desde el total confirmado.
        
        **Funcionalidad:**
        - Crea una nueva versión de redistribución
        - Valida reglas de negocio estrictas
        - Permite a MABEL TRADING redistribuir manualmente desde el total confirmado
        - Los costos unitarios NO se recalculan (permanecen como los guardó EL RAYO)
        - Versiona automáticamente la redistribución
        
        **Características importantes:**
        - ✅ Los costos unitarios permanecen tal como los guardó EL RAYO
        - ❌ NO se recalculan costos
        - ❌ NO se genera reporte de diferencias
        - ✅ La redistribución es OBLIGATORIA (no opcional)
        
        **Validaciones:**
        - No valores negativos
        - La suma por producto ≤ cantidad confirmada
        - Todas las tiendas pertenecen al pedido
        - No duplicados de tienda por producto
        - El pedido debe tener respuesta del proveedor
        - Estado del pedido debe permitir redistribución (RESPUESTA_PROVEEDOR_CARGADA, CONFIRMADO_PROVEEDOR, EN_AJUSTE_MABEL)
        
        **Request:**
        ```json
        {
            "productos": [
                {
                    "pedido_detalle_id": "...",
                    "distribuciones": [
                        {"tienda_id": "...", "cantidad_asignada": 50},
                        {"tienda_id": "...", "cantidad_asignada": 30}
                    ]
                }
            ],
            "observaciones": "Ajuste por disponibilidad de stock"
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Redistribución creada exitosamente (versión 1)",
            "data": {
                "pedido_id": "...",
                "version": 1,
                "distribuciones_insertadas": 2
            }
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            from src.database.repositories.pedido_repository import PedidoRepository
            from src.database.services.redistribucion_validator import RedistribucionValidator
            
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener datos completos del pedido
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                # Obtener respuestas del proveedor
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        rpd.pedido_detalle_id,
                        rpd.cantidad_solicitada_total,
                        rpd.cantidad_confirmada_total
                    FROM pedido_respuesta_proveedor_detalle rpd
                    INNER JOIN pedido_respuesta_proveedor rp ON rpd.respuesta_id = rp.respuesta_id
                    WHERE rp.pedido_id = ?
                    ORDER BY rp.version DESC, rp.fecha_respuesta DESC
                """, (pedido_id,))
                
                respuestas_proveedor = {}
                for row in cursor.fetchall():
                    respuestas_proveedor[str(row[0])] = {
                        "cantidad_solicitada_total": row[1],
                        "cantidad_confirmada_total": row[2]
                    }
                
                # Preparar datos para validación
                productos_redistribucion = []
                for producto in request_body.productos:
                    productos_redistribucion.append({
                        "pedido_detalle_id": producto.pedido_detalle_id,
                        "distribuciones": [
                            {
                                "tienda_id": d.tienda_id,
                                "cantidad_asignada": d.cantidad_asignada
                            }
                            for d in producto.distribuciones
                        ]
                    })
                
                # Validar redistribución
                validator = RedistribucionValidator()
                es_valido, errores = validator.validar_redistribucion(
                    pedido_data,
                    productos_redistribucion,
                    respuestas_proveedor
                )
                
                if not es_valido:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "validation_error",
                            "message": "La redistribución no cumple con las reglas de negocio",
                            "errores": errores
                        }
                    )
                
                # Crear redistribución
                resultado = repo_dist.crear_redistribucion(
                    pedido_id=pedido_id,
                    productos_redistribucion=productos_redistribucion,
                    usuario=user_id
                )
                
                # Actualizar estado del pedido
                repo_pedido.update_estado(pedido_id, "EN_AJUSTE_MABEL")
                
                logger.info(f"✅ Redistribución creada para pedido {pedido_id} por usuario {user_id}")
                
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "status": "success",
                        "message": resultado["mensaje"],
                        "data": {
                            "pedido_id": resultado["pedido_id"],
                            "version": resultado["version"],
                            "distribuciones_insertadas": resultado["distribuciones_insertadas"]
                        }
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al redistribuir pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al redistribuir pedido: {str(e)}"
                }
            )
    
    @app.post("/api/pedidos/{pedido_id}/confirmar-redistribucion",
             response_model=ConfirmarRedistribucionResponse,
             tags=["Pedidos - Redistribución"])
    async def confirmar_redistribucion(
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: ConfirmarRedistribucionRequest = Body(..., description="Datos de confirmación"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Confirma una redistribución, cambiando su estado a 'CONFIRMADO'.
        
        **Funcionalidad:**
        - Cambia el estado de todas las distribuciones a 'CONFIRMADO'
        - Actualiza el estado del pedido a 'REDISTRIBUIDO' (endpoint interno)
        - Registra auditoría de la confirmación
        
        **Request:**
        ```json
        {
            "version": 1,
            "observaciones": "Redistribución validada y confirmada"
        }
        ```
        
        **Response:**
        ```json
        {
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "version_confirmada": 1,
            "estado_anterior": "EN_AJUSTE_MABEL",
            "estado_nuevo": "REDISTRIBUIDO",
            "fecha_confirmacion": "2025-01-15T10:30:00Z",
            "mensaje": "Redistribución versión 1 confirmada exitosamente"
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            from src.database.repositories.pedido_repository import PedidoRepository
            from src.database.services.redistribucion_validator import RedistribucionValidator
            
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener estado actual del pedido
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                estado_anterior = pedido_data["cabecera"].get("estado", "PENDIENTE")
                
                # Obtener distribución para validar
                distribucion_data = repo_dist.get_distribucion_completa(
                    pedido_id, 
                    request_body.version
                )
                
                # Validar confirmación
                validator = RedistribucionValidator()
                es_valido, errores = validator.validar_confirmacion_redistribucion(
                    pedido_id,
                    request_body.version or distribucion_data["version_actual"],
                    distribucion_data
                )
                
                if not es_valido:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "validation_error",
                            "message": "La redistribución no puede ser confirmada",
                            "errores": errores
                        }
                    )
                
                # Confirmar redistribución
                resultado = repo_dist.confirmar_redistribucion(
                    pedido_id=pedido_id,
                    version=request_body.version,
                    usuario=user_id
                )
                
                # Actualizar estado del pedido a 'REDISTRIBUIDO' (endpoint interno)
                repo_pedido.update_estado(pedido_id, "REDISTRIBUIDO")
                estado_nuevo = "REDISTRIBUIDO"
                
                logger.info(f"✅ Redistribución confirmada para pedido {pedido_id} por usuario {user_id}")
                
                # NUEVO: Procesar pedido con SAP (similar a MIGRAR pero para pedidos)
                logger.info("=" * 70)
                logger.info("🔄 PROCESANDO: Consultando SAP y procesando productos del pedido...")
                logger.info("=" * 70)
                
                try:
                    from src.database.services.pedido_sap_service import procesar_pedido_con_sap
                    from src.database.services.homologacion_service import HomologacionService
                    from src.utils.email_notifier import send_homologacion_notification
                    
                    homologacion_service = HomologacionService()
                    
                    # Procesar pedido con SAP
                    resultado_sap = procesar_pedido_con_sap(
                        pedido_id=pedido_id,
                        usuario_id=user_id,
                        homologacion_service=homologacion_service,
                        continue_on_error=True
                    )
                    
                    logger.info(f"✅ Procesamiento SAP completado: {resultado_sap.get('productos_procesados', 0)} productos procesados")
                    
                    # Verificar productos no homologados y notificar
                    if resultado_sap.get("productos_no_homologados", 0) > 0:
                        logger.info("🔍 Verificando productos no homologados...")
                        
                        try:
                            from src.database.repositories.homologacion_repository import HomologacionRepository
                            
                            # Obtener TODOS los productos no homologados con estadísticas
                            todos_productos = homologacion_service.get_todos_productos_no_homologados()
                            productos_no_homologados = todos_productos.get("productos", [])
                            estadisticas = todos_productos.get("estadisticas", {})
                            
                            if productos_no_homologados and len(productos_no_homologados) > 0:
                                logger.info(f"⚠️ Se detectaron {len(productos_no_homologados)} productos no homologados")
                                
                                # Crear repository para filtrar productos ya notificados
                                repository = HomologacionRepository(conn)
                                
                                # Enviar notificación FILTRANDO productos ya notificados
                                email_enviado = send_homologacion_notification(
                                    productos_no_homologados=productos_no_homologados,
                                    estadisticas=estadisticas,
                                    fecha_ejecucion=datetime.now(),
                                    filtrar_ya_notificados=True,  # Filtrar ya notificados
                                    homologacion_repository=repository
                                )
                                
                                if email_enviado:
                                    logger.info("✅ Notificación de homologación enviada (solo productos nuevos)")
                                else:
                                    logger.info("⏭️ No se envió notificación (todos ya fueron notificados)")
                            else:
                                logger.info("✅ No hay productos no homologados nuevos para notificar")
                                
                        except Exception as homolog_error:
                            logger.warning(f"⚠️ Error al verificar homologaciones: {homolog_error}")
                            # No afectar la respuesta principal
                    
                except Exception as sap_error:
                    logger.error(f"❌ Error al procesar pedido con SAP: {sap_error}", exc_info=True)
                    # No afectar la confirmación de redistribución, solo loguear el error
                    logger.warning("⚠️ La redistribución fue confirmada pero el procesamiento SAP falló")
                
                logger.info("=" * 70)
                
                return ConfirmarRedistribucionResponse(
                    pedido_id=pedido_id,
                    numero_pedido=pedido_data["cabecera"]["numero_pedido"],
                    version_confirmada=resultado["version_confirmada"],
                    estado_anterior=estado_anterior,
                    estado_nuevo=estado_nuevo,
                    fecha_confirmacion=datetime.now(),
                    mensaje=resultado["mensaje"]
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al confirmar redistribución: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al confirmar redistribución: {str(e)}"
                }
            )
    
    @app.get("/api/pedidos/{pedido_id}/reporte-diferencias",
             response_model=ReporteDiferenciasResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_reporte_diferencias(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, analiza la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene el reporte de diferencias de una redistribución.
        
        **Funcionalidad:**
        - Calcula diferencias entre cantidades solicitadas, confirmadas y asignadas
        - Muestra diferencias por producto y por tienda
        - Calcula diferencias de costos
        - Genera totales consolidados
        
        **Query Parameters:**
        - `version` (int, opcional): Versión específica a analizar. Si no se especifica, analiza la última versión.
        
        **Response:**
        ```json
        {
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "version": 1,
            "fecha_generacion": "2025-01-15T10:30:00Z",
            "total_productos": 5,
            "total_cantidad_solicitada": 500,
            "total_cantidad_confirmada": 400,
            "total_cantidad_asignada": 380,
            "total_diferencia_cantidad": -20,
            "total_costo_original": 10000.00,
            "total_costo_ajustado": 9500.00,
            "total_diferencia_costo": -500.00,
            "diferencias_productos": [...],
            "diferencias_tiendas": [...]
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            from src.database.repositories.pedido_repository import PedidoRepository
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener datos del pedido
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                # Calcular diferencias
                diferencias = repo_dist.calcular_diferencias(pedido_id, version)
                
                return ReporteDiferenciasResponse(
                    pedido_id=pedido_id,
                    numero_pedido=pedido_data["cabecera"]["numero_pedido"],
                    version=diferencias["version"],
                    fecha_generacion=datetime.now(),
                    total_productos=diferencias["total_productos"],
                    total_cantidad_solicitada=diferencias["total_cantidad_solicitada"],
                    total_cantidad_confirmada=diferencias["total_cantidad_confirmada"],
                    total_cantidad_asignada=diferencias["total_cantidad_asignada"],
                    total_diferencia_cantidad=diferencias["total_diferencia_cantidad"],
                    total_costo_original=diferencias["total_costo_original"],
                    total_costo_ajustado=diferencias["total_costo_ajustado"],
                    total_diferencia_costo=diferencias["total_diferencia_costo"],
                    diferencias_productos=diferencias["diferencias_productos"],
                    diferencias_tiendas=diferencias["diferencias_tiendas"]
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener reporte de diferencias: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener reporte de diferencias: {str(e)}"
                }
            )
    
    @app.get("/api/pedidos/{pedido_id}/reporte-diferencias/excel", tags=["Pedidos - Redistribución"])
    async def exportar_reporte_diferencias_excel(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, analiza la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Exporta el reporte de diferencias a Excel.
        
        **Funcionalidad:**
        - Genera un archivo Excel con el reporte completo de diferencias
        - Incluye hojas para diferencias por producto y por tienda
        - Incluye resumen con totales
        
        **Query Parameters:**
        - `version` (int, opcional): Versión específica a analizar. Si no se especifica, analiza la última versión.
        
        **Response:**
        - Archivo Excel descargable (.xlsx)
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            from src.database.repositories.pedido_repository import PedidoRepository
            import pandas as pd
            from io import BytesIO
            from fastapi.responses import StreamingResponse
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener datos del pedido
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                # Calcular diferencias
                diferencias = repo_dist.calcular_diferencias(pedido_id, version)
                
                # Crear Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Hoja 1: Resumen
                    resumen_data = {
                        "Concepto": [
                            "Total Productos",
                            "Total Cantidad Solicitada",
                            "Total Cantidad Confirmada",
                            "Total Cantidad Asignada",
                            "Total Diferencia Cantidad",
                            "Total Costo Original",
                            "Total Costo Ajustado",
                            "Total Diferencia Costo"
                        ],
                        "Valor": [
                            diferencias["total_productos"],
                            diferencias["total_cantidad_solicitada"],
                            diferencias["total_cantidad_confirmada"],
                            diferencias["total_cantidad_asignada"],
                            diferencias["total_diferencia_cantidad"],
                            diferencias["total_costo_original"] or 0,
                            diferencias["total_costo_ajustado"] or 0,
                            diferencias["total_diferencia_costo"] or 0
                        ]
                    }
                    pd.DataFrame(resumen_data).to_excel(writer, sheet_name="Resumen", index=False)
                    
                    # Hoja 2: Diferencias por Producto
                    if diferencias["diferencias_productos"]:
                        df_productos = pd.DataFrame(diferencias["diferencias_productos"])
                        df_productos.to_excel(writer, sheet_name="Diferencias por Producto", index=False)
                    
                    # Hoja 3: Diferencias por Tienda
                    if diferencias["diferencias_tiendas"]:
                        df_tiendas = pd.DataFrame(diferencias["diferencias_tiendas"])
                        df_tiendas.to_excel(writer, sheet_name="Diferencias por Tienda", index=False)
                
                output.seek(0)
                
                numero_pedido = pedido_data["cabecera"]["numero_pedido"]
                filename = f"reporte_diferencias_{numero_pedido.replace(' ', '_')}_v{diferencias['version']}.xlsx"
                
                return StreamingResponse(
                    BytesIO(output.read()),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al exportar reporte de diferencias: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al exportar reporte: {str(e)}"
                }
            )
    
    # ============================================================================
    # ENDPOINTS FASE 4: Compatibles con Frontend (usando numero_pedido y AjusteDetalle)
    # ============================================================================
    
    @app.post("/api/pedidos/{numero_pedido}/redistribucion/borrador",
             response_model=GuardarBorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def guardar_borrador_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: GuardarBorradorRequest = Body(..., description="Datos del borrador de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Guarda un borrador de redistribución.
        
        **Funcionalidad:**
        - Guarda la redistribución como borrador (no la confirma)
        - Permite recuperar el borrador más tarde
        - No cambia el estado del pedido
        
        **Request:**
        ```json
        {
            "ajustes_detalle": [
                {
                    "codigo_producto": "R225.1012.BCO",
                    "descripcion": "Producto ejemplo",
                    "cantidad_solicitada": 100,
                    "cantidad_confirmada": 80,
                    "cantidad_ajustada": 75,
                    "distribucion_tiendas": [
                        {"tienda_codigo": "T001", "tienda_nombre": "Tienda 1", "cantidad": 50},
                        {"tienda_codigo": "T002", "tienda_nombre": "Tienda 2", "cantidad": 25}
                    ],
                    "costo_original": 25.50,
                    "costo_ajustado": 25.50,
                    "cambio_precio": false
                }
            ]
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Borrador guardado exitosamente",
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "fecha_guardado": "2025-01-15T10:30:00Z"
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            import json
            
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                
                # Obtener pedido por número
                pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
                
                pedido_id = pedido_data["cabecera"]["pedido_id"]
                
                # Guardar borrador en una tabla temporal o en JSON
                # Por ahora, guardamos en una tabla de borradores (crear si no existe)
                cursor = conn.cursor()
                
                # Verificar si existe tabla de borradores
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME = 'redistribucion_borrador'
                """)
                existe_tabla = cursor.fetchone()[0] > 0
                
                if not existe_tabla:
                    # Crear tabla de borradores
                    cursor.execute("""
                        CREATE TABLE redistribucion_borrador (
                            id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
                            pedido_id UNIQUEIDENTIFIER NOT NULL,
                            numero_pedido NVARCHAR(50) NOT NULL,
                            ajustes_detalle NVARCHAR(MAX) NOT NULL,
                            creado_por NVARCHAR(450) NULL,
                            fecha_guardado DATETIME DEFAULT GETDATE(),
                            CONSTRAINT FK_borrador_pedido 
                                FOREIGN KEY (pedido_id) 
                                REFERENCES pedido(pedido_id) 
                                ON DELETE CASCADE
                        )
                    """)
                    cursor.execute("""
                        CREATE INDEX idx_borrador_pedido_id ON redistribucion_borrador(pedido_id)
                    """)
                    cursor.execute("""
                        CREATE INDEX idx_borrador_numero_pedido ON redistribucion_borrador(numero_pedido)
                    """)
                
                # Guardar o actualizar borrador
                ajustes_json = json.dumps([ajuste.dict() for ajuste in request_body.ajustes_detalle])
                
                cursor.execute("""
                    IF EXISTS (SELECT 1 FROM redistribucion_borrador WHERE pedido_id = ?)
                        UPDATE redistribucion_borrador
                        SET ajustes_detalle = ?,
                            fecha_guardado = GETDATE(),
                            creado_por = ?
                        WHERE pedido_id = ?
                    ELSE
                        INSERT INTO redistribucion_borrador (pedido_id, numero_pedido, ajustes_detalle, creado_por)
                        VALUES (?, ?, ?, ?)
                """, (pedido_id, ajustes_json, user_id, pedido_id, pedido_id, numero_pedido, ajustes_json, user_id))
                
                conn.commit()
                
                logger.info(f"✅ Borrador guardado para pedido {numero_pedido} por usuario {user_id}")
                
                return GuardarBorradorResponse(
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    fecha_guardado=datetime.now(),
                    message="Borrador guardado exitosamente"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al guardar borrador: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al guardar borrador: {str(e)}"
                }
            )
    
    @app.get("/api/pedidos/{numero_pedido}/redistribucion/borrador",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_borrador_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene el borrador de redistribución guardado.
        
        **Funcionalidad:**
        - Recupera el borrador guardado previamente
        - Permite continuar editando desde donde se dejó
        
        **Response:**
        ```json
        {
            "status": "success",
            "ajustes_detalle": [...],
            "fecha_guardado": "2025-01-15T10:30:00Z"
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            import json
            
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                
                # Obtener pedido por número
                pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
                
                pedido_id = pedido_data["cabecera"]["pedido_id"]
                
                # Obtener borrador
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ajustes_detalle, fecha_guardado
                    FROM redistribucion_borrador
                    WHERE pedido_id = ?
                """, (pedido_id,))
                
                row = cursor.fetchone()
                
                if not row:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "borrador_not_found",
                            "message": "No se encontró un borrador guardado para este pedido"
                        }
                    )
                
                ajustes_json = row[0]
                fecha_guardado = row[1]
                
                # Parsear JSON
                ajustes_list = json.loads(ajustes_json)
                
                # Sincronizar costos y totales con los valores actuales del pedido
                detalles_pedido_map = {
                    detalle.get("codigo_interno"): detalle 
                    for detalle in pedido_data.get("detalles", [])
                }
                
                ajustes_detalle_sincronizados = []
                for ajuste_dict in ajustes_list:
                    codigo_producto = ajuste_dict.get("codigo_producto")
                    detalle_pedido = detalles_pedido_map.get(codigo_producto)
                    
                    if detalle_pedido:
                        # Sincronizar costo unitario con el valor actual del pedido
                        costo_actual = detalle_pedido.get("costo_doc_sin_iva")
                        if costo_actual is not None:
                            ajuste_dict["costo_original"] = costo_actual
                            ajuste_dict["costo_ajustado"] = costo_actual
                        
                        # Sincronizar total (cantidad confirmada) con el valor actual del pedido
                        total_actual = detalle_pedido.get("total")
                        if total_actual is not None:
                            try:
                                cantidad_confirmada_actual = int(float(total_actual))
                                ajuste_dict["cantidad_confirmada"] = cantidad_confirmada_actual
                                # Si cantidad_ajustada es mayor que confirmada, mantenerla, sino usar confirmada
                                if ajuste_dict.get("cantidad_ajustada", 0) > cantidad_confirmada_actual:
                                    ajuste_dict["cantidad_ajustada"] = cantidad_confirmada_actual
                            except (ValueError, TypeError):
                                pass
                    
                    ajustes_detalle_sincronizados.append(AjusteDetalle(**ajuste_dict))
                
                return BorradorResponse(
                    ajustes_detalle=ajustes_detalle_sincronizados,
                    fecha_guardado=fecha_guardado
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener borrador: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener borrador: {str(e)}"
                }
            )
    
    @app.get("/api/pedidos/{numero_pedido}/redistribucion/inicial",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_datos_iniciales_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Obtiene los datos iniciales para la redistribución sincronizados con el pedido actualizado.
        
        **Funcionalidad:**
        - Genera los datos iniciales de redistribución basándose en el pedido actualizado
        - Sincroniza costos unitarios y totales con los valores actuales del pedido (EL RAYO)
        - Obtiene cantidades confirmadas desde la respuesta del proveedor
        - Usa los costos y totales actualizados del pedido (no valores antiguos)
        - Incluye información de campos modificados manualmente para resaltado visual
        
        **Response:**
        ```json
        {
            "status": "success",
            "ajustes_detalle": [
                {
                    "codigo_producto": "R225.1012.BCO",
                    "descripcion": "Producto ejemplo",
                    "cantidad_solicitada": 100,
                    "cantidad_confirmada": 80,
                    "cantidad_ajustada": 80,
                    "distribucion_tiendas": [...],
                    "costo_original": 25.50,  // ⭐ Sincronizado con pedido actualizado
                    "costo_ajustado": 25.50,  // ⭐ Sincronizado con pedido actualizado
                    "cambio_precio": false,
                    "pedido_detalle_id": "uuid-123",  // ⭐ Para identificar la fila
                    "costo_modificado_manual": true,   // ⭐ Indica si el costo fue modificado
                    "total_modificado_manual": true    // ⭐ Indica si el total fue modificado
                }
            ],
            "fecha_guardado": "2025-01-15T10:30:00Z"
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                
                # Obtener pedido por número
                pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
                
                pedido_id = pedido_data["cabecera"]["pedido_id"]
                
                # Obtener cantidades confirmadas desde la respuesta del proveedor
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT TOP 1
                        rpd.pedido_detalle_id,
                        rpd.cantidad_solicitada_total,
                        rpd.cantidad_confirmada_total
                    FROM pedido_respuesta_proveedor_detalle rpd
                    INNER JOIN pedido_respuesta_proveedor rp ON rpd.respuesta_id = rp.respuesta_id
                    WHERE rp.pedido_id = ?
                    ORDER BY rp.version DESC, rp.fecha_respuesta DESC
                """, (pedido_id,))
                
                respuestas_map = {}
                for row in cursor.fetchall():
                    respuestas_map[str(row[0])] = {
                        "cantidad_solicitada_total": row[1],
                        "cantidad_confirmada_total": row[2]
                    }
                
                # Generar ajustes_detalle sincronizados con el pedido actualizado
                ajustes_detalle = []
                for detalle in pedido_data.get("detalles", []):
                    pedido_detalle_id = detalle.get("pedido_detalle_id")
                    codigo_producto = detalle.get("codigo_interno")
                    
                    if not codigo_producto:
                        continue
                    
                    # Obtener respuesta del proveedor para este producto
                    respuesta = respuestas_map.get(pedido_detalle_id, {})
                    cantidad_solicitada = respuesta.get("cantidad_solicitada_total", 0)
                    cantidad_confirmada = respuesta.get("cantidad_confirmada_total", 0)
                    
                    # Si no hay respuesta del proveedor, usar valores del pedido
                    if cantidad_solicitada == 0:
                        cantidad_solicitada = sum(t.get("cantidad", 0) for t in detalle.get("tiendas", []))
                    
                    if cantidad_confirmada == 0:
                        # Usar el campo "total" del detalle como cantidad confirmada (EL RAYO)
                        total_value = detalle.get("total")
                        if total_value is not None:
                            try:
                                cantidad_confirmada = int(float(total_value))
                            except (ValueError, TypeError):
                                cantidad_confirmada = cantidad_solicitada
                        else:
                            cantidad_confirmada = cantidad_solicitada
                    
                    # Obtener costos actualizados del pedido (EL RAYO)
                    costo_actual = detalle.get("costo_doc_sin_iva")
                    
                    # Preparar distribuciones de tienda
                    distribucion_tiendas = []
                    for tienda in detalle.get("tiendas", []):
                        distribucion_tiendas.append({
                            "tienda_codigo": tienda.get("codigo", ""),
                            "tienda_nombre": tienda.get("nombre", ""),
                            "cantidad": 0  # Inicialmente en 0, se debe distribuir
                        })
                    
                    # Obtener flags de modificación manual del detalle
                    costo_modificado = detalle.get("costo_modificado_manual", False)
                    total_modificado = detalle.get("total_modificado_manual", False)
                    
                    # Crear ajuste detalle sincronizado
                    ajuste = AjusteDetalle(
                        codigo_producto=codigo_producto,
                        descripcion=detalle.get("descripcion_sap", ""),
                        cantidad_solicitada=cantidad_solicitada,
                        cantidad_confirmada=cantidad_confirmada,
                        cantidad_ajustada=cantidad_confirmada,  # Inicialmente igual a confirmada
                        distribucion_tiendas=distribucion_tiendas,
                        costo_original=costo_actual,  # ⭐ Sincronizado con pedido actualizado
                        costo_ajustado=costo_actual,  # ⭐ Sincronizado con pedido actualizado
                        cambio_precio=False,
                        pedido_detalle_id=pedido_detalle_id,  # ⭐ Para identificar la fila en el frontend
                        costo_modificado_manual=costo_modificado,  # ⭐ Flag de modificación de costo
                        total_modificado_manual=total_modificado  # ⭐ Flag de modificación de total
                    )
                    
                    ajustes_detalle.append(ajuste)
                
                return BorradorResponse(
                    ajustes_detalle=ajustes_detalle,
                    fecha_guardado=datetime.now()
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener datos iniciales de redistribución: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener datos iniciales: {str(e)}"
                }
            )
    
    @app.post("/api/pedidos/{numero_pedido}/redistribucion/confirmar",
             response_model=ConfirmarRedistribucionResponseFrontend,
             tags=["Pedidos - Redistribución"])
    async def confirmar_redistribucion_frontend(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(..., description="Datos de confirmación de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Confirma una redistribución (compatible con frontend).
        
        **Funcionalidad:**
        - Confirma la redistribución usando la estructura AjusteDetalle del frontend
        - Convierte automáticamente códigos de tienda a UUIDs
        - Calcula resumen de confirmación
        - Actualiza estado del pedido a 'PEDIDO_CONFIRMADO' cuando se confirma desde el frontend
        
        **Request:**
        ```json
        {
            "ajustes_detalle": [
                {
                    "codigo_producto": "R225.1012.BCO",
                    "descripcion": "Producto ejemplo",
                    "cantidad_solicitada": 100,
                    "cantidad_confirmada": 80,
                    "cantidad_ajustada": 75,
                    "distribucion_tiendas": [
                        {"tienda_codigo": "T001", "tienda_nombre": "Tienda 1", "cantidad": 50},
                        {"tienda_codigo": "T002", "tienda_nombre": "Tienda 2", "cantidad": 25}
                    ],
                    "costo_original": 25.50,
                    "costo_ajustado": 25.50,
                    "cambio_precio": false
                }
            ]
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Redistribución confirmada exitosamente",
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "redistribucion_id": "...",
            "fecha_confirmacion": "2025-01-15T10:30:00Z",
            "resumen": {
                "total_productos": 1,
                "total_cantidad_solicitada": 100,
                "total_cantidad_confirmada": 80,
                "total_cantidad_ajustada": 75,
                "total_costo_original": 2550.00,
                "total_costo_ajustado": 1912.50,
                "diferencia_cantidad": -5,
                "diferencia_costo": -637.50
            },
            "ajustes_aplicados": 1
        }
        ```
        """
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.pedido_repository import PedidoRepository
            from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            from src.database.services.redistribucion_validator import RedistribucionValidator
            
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                repo_dist = DistribucionConfirmadaRepository(conn)
                
                # Obtener pedido por número
                pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
                
                pedido_id = pedido_data["cabecera"]["pedido_id"]
                
                # Convertir AjusteDetalle a estructura interna
                # Necesitamos mapear codigo_producto -> pedido_detalle_id y tienda_codigo -> tienda_id
                # IMPORTANTE: Sincronizar costos y totales con los valores actuales del pedido
                productos_redistribucion = []
                
                for ajuste in request_body.ajustes_detalle:
                    # Buscar pedido_detalle_id por codigo_producto
                    detalle_pedido = next(
                        (d for d in pedido_data["detalles"] 
                         if d.get("codigo_interno") == ajuste.codigo_producto),
                        None
                    )
                    
                    if not detalle_pedido:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "error": "producto_not_found",
                                "message": f"No se encontró el producto con código: {ajuste.codigo_producto}"
                            }
                        )
                    
                    # Sincronizar costos con los valores actuales del pedido
                    costo_actual = detalle_pedido.get("costo_doc_sin_iva")
                    if costo_actual is not None:
                        # Usar el costo actual del pedido, no el del request
                        ajuste.costo_original = costo_actual
                        ajuste.costo_ajustado = costo_actual
                    
                    # Sincronizar cantidad confirmada con el total actual del pedido (si existe)
                    total_actual = detalle_pedido.get("total")
                    if total_actual is not None:
                        try:
                            cantidad_confirmada_actual = int(float(total_actual))
                            ajuste.cantidad_confirmada = cantidad_confirmada_actual
                        except (ValueError, TypeError):
                            pass
                    
                    # Convertir distribuciones de tienda
                    distribuciones = []
                    for dist_tienda in ajuste.distribucion_tiendas:
                        # Buscar tienda_id por codigo
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT tienda_id FROM tienda WHERE codigo = ?
                        """, (dist_tienda.tienda_codigo,))
                        row = cursor.fetchone()
                        
                        if not row:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail={
                                    "error": "tienda_not_found",
                                    "message": f"No se encontró la tienda con código: {dist_tienda.tienda_codigo}"
                                }
                            )
                        
                        distribuciones.append({
                            "tienda_id": str(row[0]),
                            "cantidad_asignada": dist_tienda.cantidad
                        })
                    
                    productos_redistribucion.append({
                        "pedido_detalle_id": detalle_pedido["pedido_detalle_id"],
                        "distribuciones": distribuciones
                    })
                
                # Obtener respuestas del proveedor para validación
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        rpd.pedido_detalle_id,
                        rpd.cantidad_solicitada_total,
                        rpd.cantidad_confirmada_total
                    FROM pedido_respuesta_proveedor_detalle rpd
                    INNER JOIN pedido_respuesta_proveedor rp ON rpd.respuesta_id = rp.respuesta_id
                    WHERE rp.pedido_id = ?
                    ORDER BY rp.version DESC, rp.fecha_respuesta DESC
                """, (pedido_id,))
                
                respuestas_proveedor = {}
                for row in cursor.fetchall():
                    respuestas_proveedor[str(row[0])] = {
                        "cantidad_solicitada_total": row[1],
                        "cantidad_confirmada_total": row[2]
                    }
                
                # Validar redistribución
                validator = RedistribucionValidator()
                es_valido, errores = validator.validar_redistribucion(
                    pedido_data,
                    productos_redistribucion,
                    respuestas_proveedor
                )
                
                if not es_valido:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "validation_error",
                            "message": "La redistribución no cumple con las reglas de negocio",
                            "errores": errores
                        }
                    )
                
                # Crear redistribución
                resultado = repo_dist.crear_redistribucion(
                    pedido_id=pedido_id,
                    productos_redistribucion=productos_redistribucion,
                    usuario=user_id
                )
                
                # Confirmar redistribución
                resultado_confirmacion = repo_dist.confirmar_redistribucion(
                    pedido_id=pedido_id,
                    version=resultado["version"],
                    usuario=user_id
                )
                
                # Actualizar estado del pedido a "PEDIDO_CONFIRMADO" (específico para confirmación desde frontend)
                repo_pedido.update_estado(pedido_id, "PEDIDO_CONFIRMADO")
                
                # Calcular resumen
                total_productos = len(request_body.ajustes_detalle)
                total_cantidad_solicitada = sum(a.cantidad_solicitada for a in request_body.ajustes_detalle)
                total_cantidad_confirmada = sum(a.cantidad_confirmada for a in request_body.ajustes_detalle)
                total_cantidad_ajustada = sum(a.cantidad_ajustada for a in request_body.ajustes_detalle)
                diferencia_cantidad = total_cantidad_ajustada - total_cantidad_confirmada
                
                total_costo_original = sum(
                    (a.cantidad_solicitada * (a.costo_original or 0)) 
                    for a in request_body.ajustes_detalle
                ) or None
                
                total_costo_ajustado = sum(
                    (a.cantidad_ajustada * (a.costo_ajustado or 0)) 
                    for a in request_body.ajustes_detalle
                ) or None
                
                diferencia_costo = (
                    total_costo_ajustado - total_costo_original 
                    if total_costo_ajustado is not None and total_costo_original is not None 
                    else None
                )
                
                resumen = ResumenConfirmacion(
                    total_productos=total_productos,
                    total_cantidad_solicitada=total_cantidad_solicitada,
                    total_cantidad_confirmada=total_cantidad_confirmada,
                    total_cantidad_ajustada=total_cantidad_ajustada,
                    total_costo_original=total_costo_original,
                    total_costo_ajustado=total_costo_ajustado,
                    diferencia_cantidad=diferencia_cantidad,
                    diferencia_costo=diferencia_costo
                )
                
                logger.info(f"✅ Redistribución confirmada para pedido {numero_pedido} por usuario {user_id}")
                
                return ConfirmarRedistribucionResponseFrontend(
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    redistribucion_id=str(resultado["version"]),  # Usar version como ID
                    fecha_confirmacion=datetime.now(),
                    resumen=resumen,
                    ajustes_aplicados=total_productos,
                    message="Redistribución confirmada exitosamente"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al confirmar redistribución: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al confirmar redistribución: {str(e)}"
                }
            )

