"""
Endpoints relacionados con integración SAP.
"""

import logging
import uuid
from datetime import datetime

from src.utils.timezone import ahora_naive
from typing import Optional, List
from fastapi import FastAPI, Request, Query as FastAPIQuery, Depends, Query
from fastapi.responses import JSONResponse

from src.utils import get_source_from_headers
from src.database.services.sap_service import SAPService
from src.database.clients.sap_client import SAPClient
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.repositories.sap_integration_log_repository import SAPIntegrationLogRepository
from src.database.services.oc_sap_service import OCSAPService
from src.database.connection import get_db_connection, get_db_connection_context
from src.config import ENABLE_SAP_QUERIES, SAP_LINKED_SERVER, ENABLE_SAP_SERVICE_LAYER
from src.security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)


def register_sap_endpoints(app: FastAPI):
    """
    Registra los endpoints de SAP en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.post("/integrar-sap", tags=["Integración SAP"])
    async def integrar_sap(
        request: Request,
        oc_id: Optional[List[str]] = Query(None, description="UUID(s) de la(s) orden(es) de compra a enviar. Puede especificarse múltiples veces (ej: ?oc_id=xxx&oc_id=yyy)."),
        referencia_despacho: Optional[List[str]] = Query(None, description="Referencia(s) del despacho (número de factura) para buscar OC(s) específica(s). Puede especificarse múltiples veces (ej: ?referencia_despacho=xxx&referencia_despacho=yyy). Si no se proporciona oc_id ni referencia_despacho, se procesa la primera OC pendiente."),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Endpoint INTEGRAR-SAP: Envía órdenes de compra a SAP Service Layer.
        
        **Responsabilidad:** INTEGRAR (endpoint #4 de los 4 requeridos)
        
        Este endpoint realiza:
        1. ❌ NO consulta (ya lo hizo CONSULTAR)
        2. ❌ NO guarda en despacho (ya lo hizo MIGRAR)
        3. ❌ NO copia a OC (ya lo hizo PROCESAR)
        4. ✅ Envía ODCs con estado "PENDIENTE" a SAP Service Layer
        5. ✅ Actualiza estado a "ENVIADA" o "ERROR" según resultado
        
        **Características:**
        - ✅ Puede enviar 1 o varios ODC en una sola llamada
        - ✅ Si se proporciona `oc_id`: envía las ODC(s) especificada(s) por UUID
        - ✅ Si se proporciona `referencia_despacho`: busca y envía las ODC(s) por referencia
        - ✅ Si NO se proporciona ningún parámetro: busca y envía la primera ODC pendiente
        - ✅ Convierte cada ODC a formato JSON de SAP Service Layer
        - ✅ Envía cada ODC directamente a SAP Service Layer (sin middleware)
        - ✅ Actualiza estado a "ENVIADA" o "ERROR" según resultado
        - ✅ Retorna información detallada de cada ODC procesada
        
        **Query Parameters:**
        - `oc_id` (opcional, múltiple): UUID de la orden de compra. Puede especificarse múltiples veces.
        - `referencia_despacho` (opcional, múltiple): Número de factura/despacho. Puede especificarse múltiples veces.
        
        **Ejemplos de uso:**
        ```
        # Enviar una OC específica por UUID
        POST /integrar-sap?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325
        
        # Enviar múltiples OC por UUID
        POST /integrar-sap?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325&oc_id=ABC123-DEF456-GHI789
        
        # Buscar OC específica por referencia
        POST /integrar-sap?referencia_despacho=900125353
        
        # Buscar múltiples OC por referencia
        POST /integrar-sap?referencia_despacho=900125353&referencia_despacho=900125354
        
        # Procesar primera OC pendiente (comportamiento por defecto)
        POST /integrar-sap
        ```
        
        **Nota:** Este endpoint asume que las ODCs ya están creadas con estado "PENDIENTE".
        Para proceso completo (consulta + guarda + copia + integración), usar los 4 endpoints en secuencia.
        
        **Flujo recomendado:**
        1. GET /consultar - Solo consulta
        2. GET /migrar - Consulta + Guarda en despacho
        3. GET /procesar-oc - Copia despachos a ODC (estado: PENDIENTE)
        4. POST /integrar-sap - Envía ODC a SAP Service Layer
        
        **Estados de ODC:**
        - `PENDIENTE`: Creada pero no enviada a SAP (estado inicial)
        - `ENVIADA`: Enviada exitosamente a SAP (se actualiza aquí)
        - `ERROR`: Error al enviar a SAP (se actualiza aquí)
        
        **Configuración requerida:**
        - Variables de entorno en `.env`:
          - `SAP_SERVICE_LAYER_URL`
          - `SAP_SERVICE_LAYER_USERNAME`
          - `SAP_SERVICE_LAYER_PASSWORD`
          - `SAP_SERVICE_LAYER_DATABASE`
          - `ENABLE_SAP_SERVICE_LAYER=true`
        
        Returns:
            JSON con metadata del proceso de envío a SAP
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log del proceso
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"🚀 INTEGRAR-SAP iniciado (usuario: {username}, fuente: {source})")
        
        try:
            # Verificar si SAP Service Layer está habilitado
            if not ENABLE_SAP_SERVICE_LAYER:
                logger.warning("⚠️ SAP Service Layer está deshabilitado")
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "SAP Service Layer está deshabilitado",
                        "hint": "Configura ENABLE_SAP_SERVICE_LAYER=true en .env"
                    },
                    headers={
                        "X-Source": source,
                        "X-Endpoint": "INTEGRAR-SAP"
                    }
                )
            
            # Generar ID único para este proceso
            proceso_id = str(uuid.uuid4())
            
            # Obtener conexión y repositorios
            conn = get_db_connection()
            oc_repo = OrdenCompraRepository(conn)
            log_repo = SAPIntegrationLogRepository(conn)
            
            # Guardar log de inicio
            try:
                log_repo.guardar_log(
                    proceso_id=proceso_id,
                    nivel_log="INFO",
                    mensaje=f"INTEGRAR-SAP iniciado (usuario: {username}, fuente: {source})",
                    usuario=username,
                    fuente=source
                )
            except Exception as e:
                logger.warning(f"No se pudo guardar log de inicio: {e}")
            
            # Guardar log de conexión
            try:
                log_repo.guardar_log(
                    proceso_id=proceso_id,
                    nivel_log="INFO",
                    mensaje="Conexión a SQL Server establecida",
                    usuario=username,
                    fuente=source
                )
            except Exception as e:
                logger.warning(f"No se pudo guardar log de conexión: {e}")
            
            # Inicializar servicio SAP
            oc_sap_service = OCSAPService()
            
            # Determinar qué OC procesar
            oc_ids_a_procesar = []
            referencias_usadas = []
            
            # Normalizar parámetros: convertir string único a lista si es necesario
            # FastAPI debería hacer esto automáticamente, pero por si acaso
            if oc_id and not isinstance(oc_id, list):
                oc_id = [oc_id]
            if referencia_despacho and not isinstance(referencia_despacho, list):
                referencia_despacho = [referencia_despacho]
            
            if oc_id:
                # Modo: Procesar OCs específicas por UUID
                oc_ids_list = [id.strip() for id in oc_id if id and id.strip()]
                logger.info(f"📋 Procesando {len(oc_ids_list)} OCs por UUID")
                
                # Validar que las OCs existan y estén en estado PENDIENTE
                for oc_id_item in oc_ids_list:
                    oc_cabecera = oc_repo.get_existing_cabecera(oc_id_item)
                    if not oc_cabecera:
                        logger.warning(f"⚠️ OC {oc_id_item[:8]}... no encontrada, omitiendo")
                        continue
                    
                    estado_actual = oc_cabecera.get("estado")
                    if estado_actual != "PENDIENTE":
                        logger.warning(f"⚠️ OC {oc_id_item[:8]}... no está en estado PENDIENTE (estado: {estado_actual}), omitiendo")
                        continue
                    
                    oc_ids_a_procesar.append(oc_id_item)
                
                if not oc_ids_a_procesar:
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "No se encontraron OCs válidas para procesar",
                            "oc_ids_provistos": oc_ids_list,
                            "enviadas": 0,
                            "errores": 0
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "INTEGRAR-SAP"
                        }
                    )
            
            elif referencia_despacho:
                # Modo: Procesar OCs específicas por referencia
                referencias_list = [ref.strip() for ref in referencia_despacho if ref and ref.strip()]
                logger.info(f"📋 Procesando OCs por referencia ({len(referencias_list)} referencias)")
                
                # Buscar OCs por referencia
                for referencia in referencias_list:
                    oc_encontrada = oc_repo.find_by_referencia_despacho(referencia)
                    if not oc_encontrada:
                        logger.warning(f"⚠️ No se encontró OC con referencia: {referencia}")
                        continue
                    
                    oc_id_encontrado = oc_encontrada.get("oc_id")
                    estado_actual = oc_encontrada.get("estado")
                    
                    if estado_actual != "PENDIENTE":
                        logger.warning(f"⚠️ OC con ref {referencia} no está en estado PENDIENTE (estado: {estado_actual})")
                        continue
                    
                    oc_ids_a_procesar.append(oc_id_encontrado)
                    referencias_usadas.append(referencia)
                
                if not oc_ids_a_procesar:
                    conn.close()
                    return JSONResponse(
                        status_code=404,
                        content={
                            "status": "not_found",
                            "message": "No se encontraron OCs válidas con las referencias proporcionadas",
                            "referencias_provistas": referencias_list,
                            "enviadas": 0,
                            "errores": 0
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "INTEGRAR-SAP"
                        }
                    )
            
            else:
                # Modo: Procesar primera OC pendiente (comportamiento por defecto)
                logger.info("📋 Procesando primera OC pendiente")
                ocs_pendientes = oc_repo.get_by_estado("PENDIENTE")
                
                if not ocs_pendientes:
                    conn.close()
                    logger.info("ℹ️ No hay OCs pendientes")
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "success",
                            "message": "No hay órdenes de compra pendientes de enviar a SAP",
                            "metadata": {
                                "total_pendientes": 0,
                                "enviadas": 0,
                                "errores": 0,
                                "pendientes_restantes": 0,
                                "detalles": []
                            }
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "INTEGRAR-SAP"
                        }
                    )
                
                # Tomar solo la primera ODC pendiente
                oc_pendiente = ocs_pendientes[0]
                oc_id_primera = oc_pendiente.get("oc_id")
                if oc_id_primera:
                    oc_ids_a_procesar = [oc_id_primera]
            
            logger.info(f"📦 Procesando {len(oc_ids_a_procesar)} OCs...")
            
            # Guardar log de procesamiento
            try:
                log_repo.guardar_log(
                    proceso_id=proceso_id,
                    nivel_log="INFO",
                    mensaje=f"Procesando {len(oc_ids_a_procesar)} OCs...",
                    usuario=username,
                    fuente=source
                )
            except Exception as e:
                logger.warning(f"No se pudo guardar log de procesamiento: {e}")
            
            # Procesar cada ODC
            detalles = []
            enviadas = 0
            errores = 0
            
            for idx, oc_id_item in enumerate(oc_ids_a_procesar, 1):
                try:
                    # Obtener información de la OC para el log y respuesta
                    oc_info = oc_repo.get_existing_cabecera(oc_id_item)
                    proveedor = oc_info.get("proveedor") if oc_info else "UNKNOWN"
                    referencia = oc_info.get("referencia_despacho") if oc_info else None
                    
                    # Guardar log de inicio de procesamiento de OC
                    try:
                        log_repo.guardar_log(
                            proceso_id=proceso_id,
                            nivel_log="INFO",
                            mensaje=f"Procesando ODC {oc_id_item[:8]}...",
                            usuario=username,
                            fuente=source,
                            oc_id=oc_id_item,
                            proveedor=proveedor,
                            referencia_despacho=referencia
                        )
                    except Exception as e:
                        logger.warning(f"No se pudo guardar log de OC: {e}")
                    
                    # Enviar ODC a SAP
                    # ⭐ La bodega se determina automáticamente desde el pedido:
                    # 1. Si hay distribuciones con es_bodega=True y cantidad > 0, usa la primera bodega encontrada
                    # 2. Si no, usa origen_traslado del pedido
                    # 3. Si no hay ninguno, se envía sin WarehouseCode (SAP usará su configuración por defecto)
                    resultado = oc_sap_service.enviar_oc_a_sap(
                        oc_repo=oc_repo,
                        oc_id=oc_id_item,
                        warehouse_code=None  # Se determina automáticamente desde el pedido
                    )
                    
                    success = resultado.get("success", False)
                    error = resultado.get("error")
                    doc_entry = resultado.get("doc_entry")
                    doc_num = resultado.get("doc_num")
                    sap_response = resultado.get("sap_response")  # Respuesta completa de SAP
                    error_code = resultado.get("error_code")  # Código de error de SAP
                    error_source = resultado.get("error_source")  # Origen del error (SAP, BACKEND, etc.)
                    sap_error_details = resultado.get("sap_error_details")  # Detalles completos del error de SAP
                    resultado_st = resultado.get("solicitudes_transferencia")  # Resultado de Solicitudes de Transferencia (por tienda)
                    resultado_itr = resultado.get("inventory_transfer_requests")  # Resultado de ITR (por bodega destino)
                    
                    # Guardar log de resultado
                    try:
                        if success:
                            log_repo.guardar_log(
                                proceso_id=proceso_id,
                                nivel_log="INFO",
                                mensaje=f"ODC {oc_id_item[:8]}... enviada exitosamente: DocNum={doc_num}",
                                usuario=username,
                                fuente=source,
                                oc_id=oc_id_item,
                                proveedor=proveedor,
                                referencia_despacho=referencia,
                                doc_entry=doc_entry,
                                doc_num=doc_num,
                                success=True,
                                detalles_adicionales={"sap_response": sap_response} if sap_response else None
                            )
                        else:
                            log_repo.guardar_log(
                                proceso_id=proceso_id,
                                nivel_log="ERROR",
                                mensaje=f"Error ODC {oc_id_item[:8]}...: {error}",
                                usuario=username,
                                fuente=source,
                                oc_id=oc_id_item,
                                proveedor=proveedor,
                                referencia_despacho=referencia,
                                error_code=error_code,
                                error_source=error_source,
                                success=False,
                                detalles_adicionales={"sap_error_details": sap_error_details} if sap_error_details else None
                            )
                    except Exception as e:
                        logger.warning(f"No se pudo guardar log de resultado: {e}")
                    
                    # Preparar detalle con información completa
                    detalle_resultado = {
                        "oc_id": oc_id_item,
                        "proveedor": proveedor,
                        "success": success,
                        "doc_entry": doc_entry,
                        "doc_num": doc_num,
                        "error": error,
                        "error_message": error,  # Alias para compatibilidad con frontend
                        "error_code": error_code,  # Código de error de SAP (ej: -4013)
                        "error_source": error_source,  # Origen: "SAP", "BACKEND", "SAP_CONNECTION", o None si éxito
                        "sap_response": sap_response,  # Respuesta completa de SAP (éxito)
                        "sap_error_details": sap_error_details,  # Detalles del error de SAP (si aplica)
                        "solicitudes_transferencia": resultado_st,  # Resultado de ST por tienda (para evaluación de cierre)
                        "inventory_transfer_requests": resultado_itr  # Resultado de ITR por bodega destino
                    }
                    
                    # ⭐ Construir warnings cuando OC es exitosa pero ITR/ST fallaron
                    # Esto permite que la UI muestre mensajes de advertencia junto al éxito de la OC
                    detalle_warnings = []
                    
                    # Warnings de Solicitudes de Transferencia (por tienda)
                    if resultado_st:
                        if not resultado_st.get("success", True):
                            st_error = resultado_st.get("error", "")
                            st_errores_detalle = resultado_st.get("errores_detalle", [])
                            st_resultados = resultado_st.get("resultados", [])
                            
                            if st_errores_detalle:
                                # Usar errores detallados si están disponibles
                                for e in st_errores_detalle:
                                    detalle_warnings.append(e.get("mensaje", str(e)))
                            elif st_resultados:
                                # Extraer de resultados individuales
                                for r in st_resultados:
                                    if not r.get("success") and r.get("error"):
                                        tienda = r.get("tienda_codigo", "N/A")
                                        detalle_warnings.append(
                                            f"ST no creada hacia {tienda}: {r['error']}"
                                        )
                            elif st_error:
                                detalle_warnings.append(f"Solicitudes de Transferencia: {st_error}")
                        elif resultado_st.get("warnings"):
                            # Éxito parcial con warnings
                            detalle_warnings.extend(resultado_st["warnings"])
                    
                    # Warnings de Inventory Transfer Requests (por bodega destino)
                    if resultado_itr:
                        itr_errors = resultado_itr.get("errors", 0)
                        if itr_errors > 0:
                            itr_resultados = resultado_itr.get("resultados", [])
                            for r in itr_resultados:
                                if not r.get("success") and r.get("error"):
                                    to_wh = r.get("ToWarehouse", "N/A")
                                    detalle_warnings.append(
                                        f"ITR no creado hacia {to_wh}: {r['error']}"
                                    )
                    
                    if detalle_warnings:
                        detalle_resultado["warnings"] = detalle_warnings
                    
                    # Agregar referencia si está disponible
                    if referencia:
                        detalle_resultado["referencia_despacho"] = referencia
                    
                    detalles.append(detalle_resultado)
                    
                    if success:
                        enviadas += 1
                    else:
                        errores += 1
                        logger.error(f"❌ Error ODC {oc_id_item[:8]}...: {error}")
                        
                except Exception as e:
                    errores += 1
                    logger.error(f"❌ Error al procesar ODC {oc_id_item[:8]}...: {e}", exc_info=True)
                    
                    # Guardar log de error excepcional
                    try:
                        log_repo.guardar_log(
                            proceso_id=proceso_id,
                            nivel_log="ERROR",
                            mensaje=f"Error al procesar ODC {oc_id_item[:8]}...: {str(e)}",
                            usuario=username,
                            fuente=source,
                            oc_id=oc_id_item,
                            proveedor=proveedor if 'proveedor' in locals() else "UNKNOWN",
                            error_source="BACKEND",
                            success=False
                        )
                    except Exception:
                        pass
                    
                    detalles.append({
                        "oc_id": oc_id_item,
                        "proveedor": proveedor if 'proveedor' in locals() else "UNKNOWN",
                        "success": False,
                        "doc_entry": None,
                        "doc_num": None,
                        "error": str(e),
                        "error_message": str(e),  # Alias para compatibilidad con frontend
                        "error_code": None,
                        "error_source": "BACKEND",
                        "sap_response": None,
                        "sap_error_details": None
                    })
            
            conn.close()
            
            # ============================================================
            # FASE 6: Log final consolidado
            # ============================================================
            
            # Generar resumen consolidado del proceso
            resumen_cierre = {
                "proceso_id": proceso_id,
                "timestamp": ahora_naive().isoformat(),
                "usuario": username,
                "fuente": source,
                "total_procesadas": len(oc_ids_a_procesar),
                "enviadas": enviadas,
                "errores": errores,
                "detalles_por_oc": detalles,
                "pedidos_cerrados": []  # Se llenará si hay pedidos cerrados
            }
            
            # Identificar pedidos únicos procesados y guardar resultados de ST
            pedidos_procesados = {}
            for detalle in detalles:
                if detalle.get("success"):
                    # Obtener pedido_id de la OC exitosa y resultado de ST
                    try:
                        # Usar context manager para garantizar cierre de conexión
                        with get_db_connection_context() as conn_temp:
                            oc_repo_temp = OrdenCompraRepository(conn_temp)
                            oc_info = oc_repo_temp.get_existing_cabecera(detalle["oc_id"])
                            if oc_info and oc_info.get("pedido_id"):
                                pedido_id = oc_info["pedido_id"]
                                # Obtener resultado de ST desde el detalle
                                resultado_st = detalle.get("solicitudes_transferencia")
                                
                                # Si el pedido ya está en el diccionario, combinar resultados de ST
                                # (un pedido puede tener múltiples OCs)
                                if pedido_id in pedidos_procesados:
                                    # Si ya hay un resultado de ST, verificar si ambos son exitosos
                                    st_existente = pedidos_procesados[pedido_id].get("resultado_st")
                                    if st_existente and resultado_st:
                                        # Combinar: éxito solo si ambos son exitosos
                                        st_combinado = {
                                            "success": st_existente.get("success", False) and resultado_st.get("success", False),
                                            "transferencias_creadas": (st_existente.get("transferencias_creadas", 0) + 
                                                                       resultado_st.get("transferencias_creadas", 0)),
                                            "transferencias_errores": (st_existente.get("transferencias_errores", 0) + 
                                                                       resultado_st.get("transferencias_errores", 0)),
                                            "total_tiendas": max(st_existente.get("total_tiendas", 0), 
                                                                 resultado_st.get("total_tiendas", 0))
                                        }
                                        pedidos_procesados[pedido_id]["resultado_st"] = st_combinado
                                    elif resultado_st:
                                        pedidos_procesados[pedido_id]["resultado_st"] = resultado_st
                                else:
                                    pedidos_procesados[pedido_id] = {
                                        "oc_id": detalle["oc_id"],
                                        "resultado_st": resultado_st
                                    }
                    except Exception:
                        pass
            
            # Evaluar cierre de pedidos procesados
            if pedidos_procesados:
                try:
                    from src.database.repositories.pedido_repository import PedidoRepository
                    from src.database.services.pedido_cierre_service import PedidoCierreService
                    
                    # Usar context manager para garantizar transacción y cierre de conexión
                    with get_db_connection_context() as conn_temp:
                        oc_repo_temp = OrdenCompraRepository(conn_temp)
                        pedido_repo_temp = PedidoRepository(conn_temp)
                        cierre_service = PedidoCierreService()
                        
                        for pedido_id, info_pedido in pedidos_procesados.items():
                            # Obtener resultado de ST desde el resultado de enviar_oc_a_sap si está disponible
                            resultado_st = info_pedido.get("resultado_st")
                            
                            resultado = cierre_service.cerrar_pedido_si_corresponde(
                                pedido_id=pedido_id,
                                oc_repo=oc_repo_temp,
                                pedido_repo=pedido_repo_temp,
                                resultado_st=resultado_st  # Puede ser None si no está disponible
                            )
                            if resultado.get("cerrado"):
                                resumen_cierre["pedidos_cerrados"].append({
                                    "pedido_id": pedido_id,
                                    "estado_anterior": resultado["estado_anterior"],
                                    "estado_nuevo": resultado["estado_nuevo"],
                                    "evaluacion": resultado["evaluacion"]
                                })
                            elif resultado.get("estado_nuevo"):
                                # También registrar si se actualizó el estado (aunque no se cerró)
                                resumen_cierre["pedidos_cerrados"].append({
                                    "pedido_id": pedido_id,
                                    "estado_anterior": resultado["estado_anterior"],
                                    "estado_nuevo": resultado["estado_nuevo"],
                                    "evaluacion": resultado["evaluacion"],
                                    "razon_estado": resultado.get("razon_estado")
                                })
                except Exception as e:
                    logger.warning(f"⚠️ Error al generar resumen de cierre (no crítico): {e}")
            
            # Guardar log final consolidado
            try:
                # Usar context manager para garantizar transacción y cierre de conexión
                with get_db_connection_context() as conn_final:
                    log_repo_final = SAPIntegrationLogRepository(conn_final)
                    log_repo_final.guardar_log(
                        proceso_id=proceso_id,
                        nivel_log="INFO",
                        mensaje=f"INTEGRAR-SAP completado: {enviadas} enviadas, {errores} errores. "
                                f"Pedidos cerrados: {len(resumen_cierre['pedidos_cerrados'])}",
                        usuario=username,
                        fuente=source,
                        success=enviadas > 0 and errores == 0,
                        detalles_adicionales=resumen_cierre
                    )
            except Exception as e:
                logger.warning(f"⚠️ No se pudo guardar log final consolidado: {e}")
            
            # Determinar status general
            status_general = "success" if errores == 0 else "partial"
            if enviadas == 0:
                status_general = "error"
            
            # ⭐ Recopilar warnings de ITR/ST de todos los detalles para mostrar en la UI
            all_warnings = []
            for detalle in detalles:
                detalle_warnings_list = detalle.get("warnings", [])
                if detalle_warnings_list:
                    all_warnings.extend(detalle_warnings_list)
            
            # Preparar mensaje
            if len(oc_ids_a_procesar) == 1:
                if enviadas > 0:
                    mensaje = f"ODC enviada exitosamente a SAP"
                    if detalles[0].get("doc_num"):
                        mensaje += f" (DocNum: {detalles[0].get('doc_num')})"
                    # ⭐ Agregar info de warnings de ST/ITR al mensaje principal
                    if all_warnings:
                        mensaje += f". ADVERTENCIA: {len(all_warnings)} Solicitud(es) de Transferencia con problemas"
                else:
                    mensaje = f"Error al enviar ODC a SAP: {detalles[0].get('error', 'Error desconocido')}"
            else:
                mensaje = f"Proceso completado: {enviadas} ODC(s) enviada(s), {errores} error(es) de {len(oc_ids_a_procesar)} procesada(s)"
                if all_warnings:
                    mensaje += f". ADVERTENCIA: {len(all_warnings)} Solicitud(es) de Transferencia con problemas"
            
            logger.info(f"✅ INTEGRAR-SAP completado: {enviadas} enviadas, {errores} errores de {len(oc_ids_a_procesar)} procesadas")
            
            # Guardar log de finalización
            try:
                log_repo.guardar_log(
                    proceso_id=proceso_id,
                    nivel_log="INFO",
                    mensaje=f"INTEGRAR-SAP completado: {enviadas} enviadas, {errores} errores de {len(oc_ids_a_procesar)} procesadas",
                    usuario=username,
                    fuente=source
                )
            except Exception as e:
                logger.warning(f"No se pudo guardar log de finalización: {e}")
            
            # Preparar headers de respuesta
            headers = {
                "X-Source": source,
                "X-Endpoint": "INTEGRAR-SAP",
                "X-OC-Status": status_general,
                "X-Enviadas": str(enviadas),
                "X-Errores": str(errores),
                "X-Total-Procesadas": str(len(oc_ids_a_procesar))
            }
            
            # Preparar metadata
            metadata = {
                "enviadas": enviadas,
                "errores": errores,
                "total_procesadas": len(oc_ids_a_procesar),
                "detalles": detalles
            }
            
            if referencias_usadas:
                metadata["referencias_usadas"] = referencias_usadas
            
            # Si no se especificaron OCs, calcular pendientes restantes
            if not oc_id and not referencia_despacho:
                # Obtener total pendientes (sin contar las que acabamos de procesar)
                with get_db_connection_context() as conn_check:
                    oc_repo_temp = OrdenCompraRepository(conn_check)
                    ocs_pendientes_restantes = oc_repo_temp.get_by_estado("PENDIENTE")
                    total_pendientes = len(ocs_pendientes_restantes)
                metadata["total_pendientes"] = total_pendientes
                metadata["pendientes_restantes"] = total_pendientes
                headers["X-Total-Pendientes"] = str(total_pendientes)
                headers["X-Pendientes-Restantes"] = str(total_pendientes)
            
            # Retornar respuesta
            # Siempre retornamos 200 con información del error en el contenido
            # El status_code 500 se reserva solo para errores inesperados del servidor
            # Los errores de validación (como ODC sin detalles) se reportan con 200 y status: "error"
            status_code = 200
            
            response_content = {
                "status": status_general,
                "message": mensaje,
                "metadata": metadata
            }
            
            # ⭐ Incluir warnings de ITR/ST a nivel raíz de la respuesta para fácil acceso en la UI
            if all_warnings:
                response_content["warnings"] = all_warnings
            
            return JSONResponse(
                status_code=status_code,
                content=response_content,
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al integrar con SAP: {e}", exc_info=True)
            # Asegurar cierre de conexión en caso de error
            try:
                if 'conn' in locals() and conn:
                    conn.close()
            except Exception:
                pass
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al integrar con SAP: {str(e)}"
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "INTEGRAR-SAP"
                }
            )
    
    @app.get("/sap/test", tags=["Integración SAP"])
    async def test_sap_query(
        request: Request,
        sku: str = FastAPIQuery(..., description="SKU del producto a consultar en SAP (ej: 5-0012.9)")
    ):
        """
        Endpoint de prueba para consultar información de un producto desde SAP.
        
        Este endpoint permite probar la integración con SAP sin necesidad de procesar
        una factura completa. Consulta información del producto y muestra el resultado.
        
        **Parámetros:**
        - `sku`: SKU del producto a consultar (requerido)
        
        **Ejemplo de uso:**
        ```
        GET /sap/test?sku=5-0012.9
        ```
        
        **Respuesta:**
        - Información del producto desde SAP (ItemCode, ItemName, U_IXX_PACK)
        - Información del cache si está disponible
        - Unidad de conversión calculada
        
        Returns:
            JSON con información del producto desde SAP o error si falla
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log
        logger.info("=" * 70)
        logger.info(f"Prueba de consulta SAP recibida a las {ahora_naive().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"SKU: {sku}")
        logger.info("=" * 70)
        
        try:
            # Verificar si SAP está habilitado
            if not ENABLE_SAP_QUERIES:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "Consultas SAP están deshabilitadas",
                        "hint": "Configura ENABLE_SAP_QUERIES=true en .env"
                    }
                )
            
            # Inicializar servicio SAP
            sap_service = SAPService()
            
            # Obtener información del producto (consultará SAP o usará cache)
            producto_info = sap_service.get_or_fetch_producto_info(sku)
            
            if producto_info:
                # Preparar respuesta detallada
                response_data = {
                    "status": "success",
                    "sku": sku,
                    "sap_info": {
                        "item_code": producto_info.get("item_code"),
                        "item_name": producto_info.get("item_name"),
                        "pack_sap": producto_info.get("pack_sap"),
                        "pack_id": producto_info.get("pack_id"),
                        "unidad_conversion": producto_info.get("unidad_conversion"),
                    },
                    "config": {
                        "sap_linked_server": SAP_LINKED_SERVER,
                        "sap_enabled": ENABLE_SAP_QUERIES,
                    },
                    "message": "Producto encontrado en SAP",
                    "timestamp": ahora_naive().isoformat()
                }
                
                # Agregar información de conversión si está disponible
                unidad = producto_info.get("unidad_conversion")
                if unidad:
                    response_data["conversion_info"] = {
                        "unidad_conversion": unidad,
                        "formula": "1 docena = {unidad} packs".format(unidad=unidad),
                        "ejemplo": {
                            "docenas": 456,
                            "packs": 456 * unidad,
                            "formula_ejemplo": f"456 docenas × {unidad} = {456 * unidad} packs"
                        }
                    }
                
                logger.info(f"✅ Consulta SAP exitosa para SKU: {sku}")
                logger.info(f"   Pack: {producto_info.get('pack_sap')}, Unidad: {producto_info.get('unidad_conversion')}")
                
                return JSONResponse(
                    status_code=200,
                    content=response_data,
                    headers={
                        "X-Source": source,
                        "X-SKU": sku,
                        "X-Pack-SAP": producto_info.get("pack_sap") or "N/A"
                    }
                )
            else:
                logger.warning(f"⚠️ Producto no encontrado en SAP: {sku}")
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": "not_found",
                        "message": f"Producto no encontrado en SAP para SKU: {sku}",
                        "sku": sku,
                        "hint": "Verifica que el SKU exista en SAP y que el servidor vinculado esté configurado correctamente",
                        "timestamp": ahora_naive().isoformat()
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error al consultar SAP: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al consultar SAP: {str(e)}",
                    "sku": sku,
                    "timestamp": ahora_naive().isoformat()
                }
            )
    
    @app.get("/sap/test/direct", tags=["Integración SAP"])
    async def test_sap_direct(
        request: Request,
        sku: str = FastAPIQuery(..., description="SKU del producto a consultar directamente en SAP")
    ):
        """
        Endpoint de prueba para consulta directa a SAP (sin usar cache).
        
        Este endpoint consulta directamente a SAP sin verificar el cache primero.
        Útil para forzar una consulta nueva y verificar que la conexión funciona.
        
        **Parámetros:**
        - `sku`: SKU del producto a consultar (requerido)
        
        **Ejemplo de uso:**
        ```
        GET /sap/test/direct?sku=5-0012.9
        ```
        
        Returns:
            JSON con información del producto desde SAP (sin cache)
        """
        source = get_source_from_headers(request)
        
        logger.info("=" * 70)
        logger.info(f"Prueba de consulta SAP directa recibida a las {ahora_naive().isoformat()}")
        logger.info(f"SKU: {sku}")
        logger.info("=" * 70)
        
        try:
            if not ENABLE_SAP_QUERIES:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "Consultas SAP están deshabilitadas"
                    }
                )
            
            # Consulta directa sin cache
            client = SAPClient()
            resultado = client.get_producto_info(sku)
            
            if resultado:
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "sku": sku,
                        "sap_direct_result": resultado,
                        "message": "Consulta directa a SAP exitosa",
                        "timestamp": ahora_naive().isoformat()
                    },
                    headers={
                        "X-Source": source,
                        "X-SKU": sku
                    }
                )
            else:
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": "not_found",
                        "message": f"Producto no encontrado en SAP: {sku}",
                        "sku": sku
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error en consulta directa SAP: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al consultar SAP: {str(e)}",
                    "sku": sku
                }
            )

