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
    ActualizarComentarioRequest
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
    
    @app.post("/api/pedidos/{pedido_id}/procesar-confirmacion", tags=["Pedidos - Ajuste"])
    async def procesar_confirmacion_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        forzar_redistribucion: bool = Query(False, description="Forzar redistribución proporcional"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Procesa la confirmación del proveedor y ajusta el pedido.
        
        **Acciones realizadas:**
        1. ✅ Ajusta cantidades por tienda para coincidir con total confirmado
        2. ✅ Recalcula costos si hubo cambios de precio
        3. ✅ Actualiza estado del pedido a CONFIRMADO_PROVEEDOR
        4. ✅ Genera reporte de diferencias
        
        **Estrategia de redistribución:**
        - Si el proveedor especificó distribución por tienda, se usa esa
        - Si no, se redistribuye proporcionalmente según cantidades originales
        - Si `forzar_redistribucion=True`, siempre redistribuye proporcionalmente
        
        **Idempotencia:**
        - Si la respuesta ya fue procesada, retorna 409 Conflict (no error técnico)
        - El frontend debe tratar esto como mensaje informativo
        
        Returns:
            JSON con resultado del procesamiento y reporte de diferencias
        """
        try:
            from src.database.services.pedido_ajuste_service import PedidoAjusteService
            
            service = PedidoAjusteService()
            resultado = service.procesar_confirmacion_proveedor(
                pedido_id=pedido_id,
                usuario_id=user.get("sub") or user.get("id") or user.get("username", "unknown"),
                forzar_redistribucion=forzar_redistribucion
            )
            
            return resultado
            
        except ValueError as e:
            error_msg = str(e)
            
            # ✅ CORRECCIÓN PUNTO 4: Detectar conflictos de idempotencia
            if "ya fue procesada" in error_msg.lower() or "no está en estado" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "conflict",
                        "message": error_msg,
                        "type": "idempotency_check"
                    }
                )
            
            # Otros errores de validación
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "message": error_msg
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error al procesar confirmación: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": "Error interno al procesar confirmación del proveedor"
                }
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

