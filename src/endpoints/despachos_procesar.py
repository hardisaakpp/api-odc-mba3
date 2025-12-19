"""
Endpoint para procesar despachos y copiarlos a órdenes de compra.
"""

import logging
import asyncio
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import JSONResponse

from src.utils import get_source_from_headers
from src.database.repositories.despacho_repository import DespachoRepository
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.services.orden_compra_service import copy_despacho_to_orden_compra
from src.database.connection import get_db_connection
from src.security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)


def generar_process_id() -> str:
    """
    Genera un process_id único para trazabilidad.
    
    Returns:
        String con formato: odc-YYYY-MM-DD-UUID
    """
    timestamp = datetime.now().strftime("%Y-%m-%d")
    unique_id = str(uuid.uuid4())[:8]
    return f"odc-{timestamp}-{unique_id}"


def verificar_tiene_odc_actualizado(
    despacho_repo: DespachoRepository, 
    oc_repo: OrdenCompraRepository, 
    despacho_ids: List[str]
) -> bool:
    """
    Verifica que todos los despachos tienen OC asociada.
    
    NOTA: `tiene_odc` es un estado derivado, no persistido.
    Se calcula verificando si existe una relación despacho_id → oc_id en orden_compra_cabecera.
    
    Args:
        despacho_repo: Repositorio de despachos
        oc_repo: Repositorio de órdenes de compra
        despacho_ids: Lista de despacho_ids a verificar
        
    Returns:
        True si todos tienen OC, False en caso contrario
    """
    try:
        for despacho_id in despacho_ids:
            oc_id = oc_repo.find_by_despacho_id(despacho_id)
            if not oc_id:
                logger.warning(f"⚠️ Despacho {despacho_id} no tiene OC después del proceso")
                return False
        return True
    except Exception as e:
        logger.error(f"❌ Error al verificar tiene_odc: {e}")
        return False


def verificar_ocs_disponibles(oc_repo: OrdenCompraRepository, oc_ids: List[str]) -> bool:
    """
    Verifica que las OCs están disponibles para consulta.
    
    Args:
        oc_repo: Repositorio de órdenes de compra
        oc_ids: Lista de oc_ids a verificar
        
    Returns:
        True si todas están disponibles, False en caso contrario
    """
    try:
        for oc_id in oc_ids:
            oc_info = oc_repo.get_existing_cabecera(oc_id)
            if not oc_info:
                logger.warning(f"⚠️ OC {oc_id} no está disponible después del proceso")
                return False
        return True
    except Exception as e:
        logger.error(f"❌ Error al verificar OCs disponibles: {e}")
        return False


def register_procesar_endpoint(app: FastAPI):
    """
    Registra el endpoint /procesar-oc en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    @app.get("/procesar-oc", tags=["Procesamiento"])
    async def procesar_orden_compra(
        request: Request,
        despacho_id: Optional[List[str]] = Query(None, description="UUID(s) del despacho a procesar. Puede especificarse múltiples veces (ej: ?despacho_id=xxx&despacho_id=yyy). Si no se proporciona, procesa todos los despachos sin OC."),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Endpoint PROCESAR-OC: Copia despachos a orden de compra.
        
        **Responsabilidad:** PROCESAR (endpoint #3 de los 4 requeridos)
        
        Este endpoint realiza:
        1. ❌ NO consulta (ya lo hizo CONSULTAR)
        2. ❌ NO guarda en despacho (ya lo hizo MIGRAR)
        3. ✅ Copia despachos existentes a orden_compra_cabecera/detalle
        4. ❌ NO envía a SAP (ese paso lo hace el endpoint INTEGRAR)
        
        **Modo de uso:**
        1. **Sin parámetros**: Procesa TODOS los despachos sin OC
           ```
           GET /procesar-oc
           ```
        
        2. **Con un despacho_id**: Procesa solo un despacho específico
           ```
           GET /procesar-oc?despacho_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325
           ```
        
        3. **Con múltiples despacho_id**: Procesa varios despachos seleccionados
           ```
           GET /procesar-oc?despacho_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325&despacho_id=ABC123-DEF456-GHI789
           ```
        
        **Query Parameters:**
        - `despacho_id` (string, opcional, múltiple) - UUID del despacho. Puede especificarse múltiples veces.
        
        **Características:**
        - ✅ Busca despachos en despacho_cabecera que NO tienen OC asociada (modo todos)
        - ✅ Permite procesar despachos específicos seleccionados (modo selectivo)
        - ✅ Copia cada despacho a orden_compra_cabecera/detalle
        - ✅ Mapea empresa → proveedor desde tabla cliente
        - ✅ Usa upsert: actualiza si existe OC, crea si no existe
        - ✅ Crea las ODC con estado "PENDIENTE" (listas para enviar a SAP)
        - ✅ Verifica post-commit que los datos estén sincronizados
        - ✅ Retorna `process_id` único para trazabilidad
        
        **Nota:** Este endpoint asume que los despachos ya están guardados en despacho_cabecera/detalle.
        Para proceso completo (consulta + guarda + copia + integración), usar los 4 endpoints en secuencia.
        
        **Flujo recomendado:**
        1. GET /consultar - Solo consulta
        2. GET /migrar - Consulta + Guarda en despacho
        3. GET /procesar-oc - Copia despachos a ODC (estado: PENDIENTE)
        4. POST /integrar-sap - Envía ODC a SAP usando middleware
        
        **Estados de ODC:**
        - `PENDIENTE`: Creada pero no enviada a SAP (estado inicial)
        - `ENVIADA`: Enviada exitosamente a SAP (se actualiza en endpoint INTEGRAR)
        - `ERROR`: Error al enviar a SAP (se actualiza en endpoint INTEGRAR)
        
        **Respuesta:**
        - HTTP Status: Siempre 200 si el proceso terminó (éxito o error parcial)
        - Estado real: Ver `metadata.oc_status.status`:
          - `'completed'`: Todas las OCs se crearon exitosamente
          - `'partial'`: Algunas OCs se crearon, otras fallaron
          - `'error'`: Todas las OCs fallaron
          - `'processing'`: Proceso asíncrono (futuro, no usado actualmente)
        - `process_id`: ID único para trazabilidad y debugging
        - `despachos_actualizados`: true si `tiene_odc` está actualizado (verificado post-commit)
        - `datos_sincronizados`: true si las OCs están disponibles para consulta
        
        **IMPORTANTE:** El frontend debe guiarse por `metadata.oc_status.status`, NO por el HTTP status code.
        
        Returns:
            JSON con estructura mejorada:
            {
                "status": "success" | "error",
                "process_id": "odc-YYYY-MM-DD-UUID",
                "message": "...",
                "data": {
                    "oc_ids": [...],
                    "despachos_procesados": [...],
                    "oc_creadas": N,
                    "oc_errores": N
                },
                "metadata": {
                    "oc_status": {
                        "status": "completed" | "partial" | "error",
                        "despachos_actualizados": true | false,
                        "datos_sincronizados": true | false,
                        "detalles": [...]
                    },
                    "timestamp": "ISO-8601"
                }
            }
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
        # Generar process_id único para trazabilidad
        process_id = generar_process_id()
        
        # Log del proceso
        logger.info("=" * 70)
        logger.info(f"🔄 PROCESAR-OC: Iniciado a las {datetime.now().isoformat()}")
        logger.info(f"Process ID: {process_id}")
        logger.info(f"Fuente: {source}")
        
        try:
            # Función helper que se ejecutará en thread pool para no bloquear el event loop
            # Esto permite que el endpoint responda inmediatamente incluso si el proceso
            # automático está ejecutándose simultáneamente
            def _procesar_despachos_helper(despacho_ids_param: Optional[List[str]]) -> Dict[str, Any]:
                """Función helper que ejecuta el procesamiento en thread separado"""
                conn = get_db_connection()
                try:
                    despacho_repo = DespachoRepository(conn)
                    oc_repo = OrdenCompraRepository(conn)
                    
                    # Determinar qué despachos procesar
                    if despacho_ids_param:
                        # Modo: Procesar despachos específicos
                        despacho_ids_list = [id.strip() for id in despacho_ids_param if id and id.strip()]
                        logger.info(f"📋 Modo: Procesar despachos específicos ({len(despacho_ids_list)} despachos)")
                        logger.info(f"   IDs: {despacho_ids_list}")
                        
                        # Validar que los despachos existan
                        despachos_a_procesar = []
                        despachos_no_encontrados = []
                        
                        for despacho_id_item in despacho_ids_list:
                            # Verificar que el despacho existe
                            cabecera = despacho_repo.get_existing_cabecera(despacho_id_item)
                            if not cabecera:
                                logger.warning(f"⚠️ Despacho {despacho_id_item} no encontrado, se omitirá")
                                despachos_no_encontrados.append(despacho_id_item)
                                continue
                            
                            # Verificar si ya tiene OC (solo informativo)
                            existing_oc_id = oc_repo.find_by_despacho_id(despacho_id_item)
                            if existing_oc_id:
                                logger.info(f"ℹ️ Despacho {despacho_id_item} ya tiene OC ({existing_oc_id}), se actualizará")
                            
                            despachos_a_procesar.append(despacho_id_item)
                        
                        if not despachos_a_procesar:
                            return {
                                "status": "error",
                                "status_code": 400,
                                "process_id": process_id,
                                "message": "No se encontraron despachos válidos para procesar",
                                "data": {
                                    "oc_ids": [],
                                    "despachos_procesados": [],
                                    "oc_creadas": 0,
                                    "oc_errores": 0
                                },
                                "metadata": {
                                    "oc_status": {
                                        "status": "error",
                                        "oc_creadas": 0,
                                        "oc_errores": len(despacho_ids_list),
                                        "total_procesadas": 0,
                                        "despachos_actualizados": False,
                                        "datos_sincronizados": False,
                                        "detalles": []
                                    },
                                    "timestamp": datetime.now().isoformat()
                                }
                            }
                        
                        if despachos_no_encontrados:
                            logger.warning(f"⚠️ {len(despachos_no_encontrados)} despachos no encontrados: {despachos_no_encontrados}")
                    else:
                        # Modo: Procesar todos los despachos sin OC (comportamiento original)
                        logger.info("📋 Modo: Procesar todos los despachos sin OC")
                        despachos_a_procesar = despacho_repo.get_despachos_sin_oc()
                        despachos_no_encontrados = []
                        
                        if not despachos_a_procesar:
                            logger.info("ℹ️ No se encontraron despachos sin orden de compra")
                            return {
                                "status": "success",
                                "status_code": 200,
                                "process_id": process_id,
                                "message": "No hay despachos pendientes de copiar a orden de compra",
                                "data": {
                                    "oc_ids": [],
                                    "despachos_procesados": [],
                                    "oc_creadas": 0,
                                    "oc_errores": 0
                                },
                                "metadata": {
                                    "oc_status": {
                                        "status": "completed",
                                        "oc_creadas": 0,
                                        "oc_errores": 0,
                                        "total_procesadas": 0,
                                        "despachos_actualizados": True,
                                        "datos_sincronizados": True,
                                        "detalles": []
                                    },
                                    "timestamp": datetime.now().isoformat()
                                }
                            }
                    
                    logger.info(f"📦 Total despachos a procesar: {len(despachos_a_procesar)}")
                    logger.info("=" * 70)
                    logger.info("🔄 PROCESANDO: Copiando despachos a orden de compra...")
                    logger.info("=" * 70)
                    
                    # Procesar cada despacho
                    oc_resultados = []
                    oc_exitosas = 0
                    oc_errores = 0
                    oc_ids_creadas = []
                    
                    for idx, despacho_id_item in enumerate(despachos_a_procesar, 1):
                        try:
                            logger.info(f"[{idx}/{len(despachos_a_procesar)}] Procesando despacho: {despacho_id_item}")
                            
                            # Copiar despacho a orden de compra (con upsert)
                            oc_resultado = copy_despacho_to_orden_compra(
                                despacho_repo=despacho_repo,
                                oc_repo=oc_repo,
                                despacho_id=despacho_id_item,
                                upsert=True
                            )
                            
                            if oc_resultado:
                                oc_exitosas += 1
                                oc_id = oc_resultado.get("oc_id")
                                oc_ids_creadas.append(oc_id)
                                accion = "actualizada" if oc_resultado.get("cabecera_actualizada") else "creada"
                                
                                resultado_item = {
                                    "despacho_id": despacho_id_item,
                                    "oc_id": oc_id,
                                    "proveedor": oc_resultado.get("proveedor"),
                                    "detalles_insertados": oc_resultado.get("detalles_insertados", 0),
                                    "accion": accion,
                                    "estado": "PENDIENTE",  # Estado inicial de la ODC
                                    "success": True,
                                    "tiene_odc_actualizado": True  # Se actualiza en la misma transacción
                                }
                                
                                logger.info(f"   ✅ OC {accion}: {oc_id} (estado: PENDIENTE)")
                                
                                oc_resultados.append(resultado_item)
                            else:
                                oc_errores += 1
                                logger.warning(f"   ⚠️ No se pudo crear/actualizar OC para despacho: {despacho_id_item}")
                                oc_resultados.append({
                                    "despacho_id": despacho_id_item,
                                    "oc_id": None,
                                    "success": False,
                                    "error": "No se pudo crear/actualizar OC",
                                    "tiene_odc_actualizado": False
                                })
                                
                        except Exception as oc_error:
                            oc_errores += 1
                            logger.error(f"   ❌ Error al copiar despacho {despacho_id_item} a OC: {oc_error}", exc_info=True)
                            oc_resultados.append({
                                "despacho_id": despacho_id_item,
                                "oc_id": None,
                                "success": False,
                                "error": str(oc_error),
                                "tiene_odc_actualizado": False
                            })
                    
                    # CRÍTICO: Verificar que tiene_odc está actualizado
                    # Esto debe hacerse DESPUÉS del commit (que ocurre en copy_despacho_to_orden_compra)
                    despachos_actualizados = verificar_tiene_odc_actualizado(
                        despacho_repo, oc_repo, despachos_a_procesar
                    )
                    
                    # CRÍTICO: Verificar que las OCs están disponibles
                    datos_sincronizados = verificar_ocs_disponibles(oc_repo, oc_ids_creadas) if oc_ids_creadas else True
                    
                    # Determinar status final
                    if oc_errores == 0:
                        oc_status_value = "completed"
                    elif oc_exitosas > 0:
                        oc_status_value = "partial"
                    else:
                        oc_status_value = "error"
                    
                    # Cerrar conexión
                    conn.close()
                    
                    # Invalidar caché si se crearon OCs (los datos han cambiado)
                    if oc_exitosas > 0:
                        try:
                            from endpoints.despachos_info import invalidate_despachos_cache
                            from endpoints.ordenes_compra import invalidate_ordenes_compra_cache
                            
                            invalidate_despachos_cache()
                            invalidate_ordenes_compra_cache()
                            logger.debug("🗑️ Caché invalidado después de crear órdenes de compra")
                        except Exception as cache_error:
                            # No fallar el proceso si hay error al invalidar caché
                            logger.warning(f"⚠️ Error al invalidar caché: {cache_error}")
                    
                    oc_status = {
                        "status": oc_status_value,
                        "oc_creadas": oc_exitosas,
                        "oc_errores": oc_errores,
                        "total_procesadas": len(oc_resultados),
                        "despachos_actualizados": despachos_actualizados,
                        "datos_sincronizados": datos_sincronizados,
                        "detalles": oc_resultados
                    }
                    
                    # Agregar información de despachos no encontrados si aplica
                    if despachos_no_encontrados:
                        oc_status["despachos_no_encontrados"] = despachos_no_encontrados
                    
                    logger.info("=" * 70)
                    logger.info(f"✅ PROCESAR-OC completado (Process ID: {process_id}):")
                    logger.info(f"   Total despachos procesados: {len(despachos_a_procesar)}")
                    logger.info(f"   OCs creadas: {oc_exitosas}")
                    logger.info(f"   Errores: {oc_errores}")
                    logger.info(f"   Estado: {oc_status_value}")
                    logger.info(f"   Despachos actualizados: {despachos_actualizados}")
                    logger.info(f"   Datos sincronizados: {datos_sincronizados}")
                    if despachos_no_encontrados:
                        logger.info(f"   Despachos no encontrados: {len(despachos_no_encontrados)}")
                    logger.info(f"   Estado de OCs creadas: PENDIENTE (listas para enviar a SAP)")
                    logger.info("=" * 70)
                    
                    mensaje = f"Proceso completado: {oc_exitosas} OCs creadas de {len(despachos_a_procesar)} despachos (estado: PENDIENTE)"
                    if despachos_no_encontrados:
                        mensaje += f". {len(despachos_no_encontrados)} despachos no encontrados."
                    
                    return {
                        "status": "success" if oc_errores == 0 else "partial",
                        "status_code": 200,
                        "process_id": process_id,
                        "message": mensaje,
                        "data": {
                            "oc_ids": oc_ids_creadas,
                            "despachos_procesados": despachos_a_procesar,
                            "oc_creadas": oc_exitosas,
                            "oc_errores": oc_errores
                        },
                        "metadata": {
                            "oc_status": oc_status,
                            "timestamp": datetime.now().isoformat()
                        }
                    }
                except Exception as e:
                    logger.error(f"❌ Error en helper de procesamiento (Process ID: {process_id}): {e}", exc_info=True)
                    return {
                        "status": "error",
                        "status_code": 500,
                        "process_id": process_id,
                        "message": f"Error al procesar orden de compra: {str(e)}",
                        "data": {
                            "oc_ids": [],
                            "despachos_procesados": [],
                            "oc_creadas": 0,
                            "oc_errores": 0
                        },
                        "metadata": {
                            "oc_status": {
                                "status": "error",
                                "oc_creadas": 0,
                                "oc_errores": 0,
                                "total_procesadas": 0,
                                "despachos_actualizados": False,
                                "datos_sincronizados": False,
                                "detalles": []
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                    }
            
            # Ejecutar procesamiento en thread pool para no bloquear el event loop
            logger.debug("🔄 Ejecutando procesamiento en thread pool (no bloquea otras peticiones)...")
            resultado = await asyncio.to_thread(_procesar_despachos_helper, despacho_id)
            
            # Preparar headers de respuesta
            headers = {
                "X-Source": source,
                "X-Endpoint": "PROCESAR-OC",
                "X-OC-Status": resultado.get("metadata", {}).get("oc_status", {}).get("status", "unknown"),
                "X-Process-ID": resultado.get("process_id", "unknown"),
            }
            
            if "data" in resultado:
                headers["X-OC-Creadas"] = str(resultado["data"].get("oc_creadas", 0))
                headers["X-OC-Errores"] = str(resultado["data"].get("oc_errores", 0))
                headers["X-Total-Despachos"] = str(len(resultado["data"].get("despachos_procesados", [])))
            
            # Retornar respuesta según el resultado
            return JSONResponse(
                status_code=resultado.get("status_code", 200),
                content={
                    "status": resultado.get("status"),
                    "message": resultado.get("message"),
                    "process_id": resultado.get("process_id"),
                    "data": resultado.get("data"),
                    "metadata": resultado.get("metadata")
                },
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al procesar orden de compra (Process ID: {process_id}): {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "process_id": process_id,
                    "message": f"Error al procesar orden de compra: {str(e)}",
                    "data": {
                        "oc_ids": [],
                        "despachos_procesados": [],
                        "oc_creadas": 0,
                        "oc_errores": 0
                    },
                    "metadata": {
                        "oc_status": {
                            "status": "error",
                            "oc_creadas": 0,
                            "oc_errores": 0,
                            "total_procesadas": 0,
                            "despachos_actualizados": False,
                            "datos_sincronizados": False,
                            "detalles": []
                        },
                        "timestamp": datetime.now().isoformat()
                    }
                }
            )
