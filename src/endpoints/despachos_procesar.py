"""
Endpoint para procesar despachos y copiarlos a órdenes de compra.
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import JSONResponse

from utils import get_source_from_headers
from database.repositories.despacho_repository import DespachoRepository
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.services.orden_compra_service import copy_despacho_to_orden_compra
from database.connection import get_db_connection
from security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)


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
        
        Returns:
            JSON con metadata del proceso de creación de ODC
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
        # Log del proceso
        logger.info("=" * 70)
        logger.info(f"🔄 PROCESAR-OC: Iniciado a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        
        try:
            # Obtener conexión y repositorios
            conn = get_db_connection()
            despacho_repo = DespachoRepository(conn)
            oc_repo = OrdenCompraRepository(conn)
            
            # Determinar qué despachos procesar
            if despacho_id:
                # Modo: Procesar despachos específicos
                despacho_ids_list = [id.strip() for id in despacho_id if id and id.strip()]
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
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "No se encontraron despachos válidos para procesar",
                            "despacho_ids_provistos": despacho_ids_list,
                            "despachos_no_encontrados": despachos_no_encontrados,
                            "oc_creadas": 0,
                            "oc_errores": 0
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "PROCESAR-OC"
                        }
                    )
                
                if despachos_no_encontrados:
                    logger.warning(f"⚠️ {len(despachos_no_encontrados)} despachos no encontrados: {despachos_no_encontrados}")
            else:
                # Modo: Procesar todos los despachos sin OC (comportamiento original)
                logger.info("📋 Modo: Procesar todos los despachos sin OC")
                despachos_a_procesar = despacho_repo.get_despachos_sin_oc()
                despachos_no_encontrados = []
                
                if not despachos_a_procesar:
                    logger.info("ℹ️ No se encontraron despachos sin orden de compra")
                    conn.close()
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "success",
                            "message": "No hay despachos pendientes de copiar a orden de compra",
                            "oc_creadas": 0,
                            "oc_errores": 0,
                            "total_despachos": 0
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "PROCESAR-OC"
                        }
                    )
            
            logger.info(f"📦 Total despachos a procesar: {len(despachos_a_procesar)}")
            logger.info("=" * 70)
            logger.info("🔄 PROCESANDO: Copiando despachos a orden de compra...")
            logger.info("=" * 70)
            
            # Procesar cada despacho
            oc_resultados = []
            oc_exitosas = 0
            oc_errores = 0
            
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
                        accion = "actualizada" if oc_resultado.get("cabecera_actualizada") else "creada"
                        
                        resultado_item = {
                            "despacho_id": despacho_id_item,
                            "oc_id": oc_id,
                            "proveedor": oc_resultado.get("proveedor"),
                            "detalles_insertados": oc_resultado.get("detalles_insertados", 0),
                            "accion": accion,
                            "estado": "PENDIENTE"  # Estado inicial de la ODC
                        }
                        
                        logger.info(f"   ✅ OC {accion}: {oc_id} (estado: PENDIENTE)")
                        
                        oc_resultados.append(resultado_item)
                    else:
                        oc_errores += 1
                        logger.warning(f"   ⚠️ No se pudo crear/actualizar OC para despacho: {despacho_id_item}")
                        oc_resultados.append({
                            "despacho_id": despacho_id_item,
                            "error": "No se pudo crear/actualizar OC"
                        })
                        
                except Exception as oc_error:
                    oc_errores += 1
                    logger.error(f"   ❌ Error al copiar despacho {despacho_id_item} a OC: {oc_error}")
                    oc_resultados.append({
                        "despacho_id": despacho_id_item,
                        "error": str(oc_error)
                    })
            
            # Cerrar conexión
            conn.close()
            
            oc_status = {
                "status": "success" if oc_errores == 0 else "partial",
                "oc_creadas": oc_exitosas,
                "oc_errores": oc_errores,
                "total_procesadas": len(oc_resultados),
                "total_despachos": len(despachos_a_procesar),
                "detalles": oc_resultados
            }
            
            # Agregar información de despachos no encontrados si aplica
            if despachos_no_encontrados:
                oc_status["despachos_no_encontrados"] = despachos_no_encontrados
            
            logger.info("=" * 70)
            logger.info(f"✅ PROCESAR-OC completado:")
            logger.info(f"   Total despachos procesados: {len(despachos_a_procesar)}")
            logger.info(f"   OCs creadas: {oc_exitosas}")
            logger.info(f"   Errores: {oc_errores}")
            if despachos_no_encontrados:
                logger.info(f"   Despachos no encontrados: {len(despachos_no_encontrados)}")
            logger.info(f"   Estado de OCs creadas: PENDIENTE (listas para enviar a SAP)")
            logger.info("=" * 70)
            
            # Preparar headers de respuesta
            headers = {
                "X-Source": source,
                "X-Endpoint": "PROCESAR-OC",
                "X-OC-Status": oc_status.get("status", "unknown"),
                "X-OC-Creadas": str(oc_exitosas),
                "X-OC-Errores": str(oc_errores),
                "X-Total-Despachos": str(len(despachos_a_procesar))
            }
            
            if despacho_id:
                headers["X-Modo"] = "selectivo"
            else:
                headers["X-Modo"] = "todos"
            
            # Construir mensaje
            mensaje = f"Proceso completado: {oc_exitosas} OCs creadas de {len(despachos_a_procesar)} despachos (estado: PENDIENTE)"
            if despachos_no_encontrados:
                mensaje += f". {len(despachos_no_encontrados)} despachos no encontrados."
            
            # Retornar respuesta con metadata
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": mensaje,
                    "metadata": oc_status
                },
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al procesar orden de compra: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al procesar orden de compra: {str(e)}"
                }
            )

