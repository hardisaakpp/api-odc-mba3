"""
Endpoint para realizar cruce de productos entre MBA3 y SAP.
"""

import logging
import re
import pyodbc
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Query

from src.database.services.cruce_productos_service import CruceProductosService
from src.database.services.sugerencias_homologacion_service import SugerenciasHomologacionService
from src.database.services.producto_staging_sync_service import ProductoStagingSyncService
from src.database.repositories.sync_control_repository import SyncControlRepository
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.config import SAP_LINKED_SERVER, SAP_DATABASE, ENABLE_SAP_QUERIES
from src.database.connection import get_sap_db_connection, get_db_connection

logger = logging.getLogger(__name__)


def register_cruce_productos_endpoints(app: FastAPI):
    """
    Registra los endpoints de cruce de productos en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.get("/cruce-productos/realizar-cruce", tags=["Cruce de Productos"])
    async def realizar_cruce_productos(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Realiza un cruce completo entre productos de MBA3 y SAP.
        
        Identifica:
        - Homologados exactos: PRODUCT_ID === ItemCode
        - Homologables: normalizar(PRODUCT_ID) === normalizar(ItemCode) pero códigos diferentes
        - Solo en MBA3: productos que no tienen match en SAP
        - Solo en SAP: productos que no tienen match en MBA3
        
        Returns:
            Resultado del cruce con estadísticas y listas de productos
        """
        try:
            logger.info("🔍 Iniciando cruce de productos MBA3 vs SAP...")
            service = CruceProductosService()
            resultado = service.realizar_cruce()
            
            return {
                "status": "success",
                "data": resultado,
                "message": "Cruce de productos completado exitosamente"
            }
        except Exception as e:
            logger.error(f"❌ Error al realizar cruce de productos: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al realizar cruce: {str(e)}")
    
    @app.get("/cruce-productos/sugerencias", tags=["Cruce de Productos"])
    async def obtener_sugerencias_homologacion(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Obtiene sugerencias de homologación para productos que no tienen match exacto.
        
        IMPORTANTE: Este endpoint NO debe llenar la pestaña "Homologables" actual.
        Es una nueva categoría: "Sugerencias" que debe mostrarse en una pestaña separada
        o como vista secundaria al seleccionar un SKU solo MBA3.
        
        Este endpoint NO homologa automáticamente, solo SUGIERE posibles coincidencias
        entre productos MBA3 (solo_en_mba3) y productos SAP para revisión humana.
        
        Cada sugerencia incluye:
        - Score normalizado (0.0 - 1.0) para usar como porcentaje en frontend
        - Score original (para debugging)
        - Motivos del match (explicación del por qué se sugiere)
        - Máximo 5 sugerencias por producto MBA3
        - Solo sugerencias con score >= 0.5 (umbral mínimo)
        
        Reutiliza el resultado del cruce si está disponible,
        pero puede ejecutarse independientemente.
        
        Returns:
            Lista de productos MBA3 con sus sugerencias ordenadas por score
        """
        try:
            logger.info("🔍 Obteniendo sugerencias de homologación...")
            
            # Obtener datos del cruce una sola vez
            cruce_service = CruceProductosService()
            cruce = cruce_service.realizar_cruce()
            
            productos_solo_mba3 = cruce.get("solo_en_mba3", [])
            productos_sap = cruce_service.obtener_productos_sap()
            
            # Obtener códigos ya homologados
            homologados_exactos = cruce.get("homologados_exactos", [])
            homologables = cruce.get("homologables", [])
            
            productos_ya_homologados = set()
            for item in homologados_exactos:
                codigo_sap = item.get("codigo_sap")
                if codigo_sap:
                    productos_ya_homologados.add(codigo_sap)
            for item in homologables:
                codigo_sap = item.get("codigo_sap")
                if codigo_sap:
                    productos_ya_homologados.add(codigo_sap)
            
            # Generar sugerencias
            sugerencias_service = SugerenciasHomologacionService()
            sugerencias = sugerencias_service.obtener_sugerencias(
                productos_solo_mba3,
                productos_sap,
                productos_ya_homologados
            )
            
            return {
                "status": "success",
                "data": sugerencias,
                "message": f"Sugerencias generadas para {len(sugerencias)} productos",
                "metadata": {
                    "total_productos": len(sugerencias),
                    "productos_con_sugerencias": sum(1 for s in sugerencias if s["sugerencias"]),
                    "productos_sin_sugerencias": sum(1 for s in sugerencias if not s["sugerencias"]),
                    "min_score": SugerenciasHomologacionService.MIN_SCORE_SUGERENCIA,
                    "max_sugerencias_por_producto": SugerenciasHomologacionService.MAX_SUGERENCIAS_POR_PRODUCTO
                }
            }
        except Exception as e:
            logger.error(f"❌ Error al obtener sugerencias: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al obtener sugerencias: {str(e)}")
    
    @app.post("/cruce-productos/sincronizar-maestros/mba3", tags=["Cruce de Productos"])
    async def sincronizar_maestros_mba3(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Sincroniza maestros de productos MBA3 desde API a staging.
        
        Este endpoint:
        1. Consulta productos MBA3 desde API (tabla INVT_FICHA_PRINCIPAL)
        2. Normaliza códigos y guarda/actualiza en producto_mba3_staging
        3. Registra estadísticas en sync_control
        
        ⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
        No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.
        
        Returns:
            Estadísticas de sincronización para MBA3
        """
        try:
            logger.info("🔄 Iniciando sincronización manual de maestros MBA3...")
            service = ProductoStagingSyncService()
            resultado = service.sync_mba3_products()
            
            return {
                "status": "success",
                "data": resultado,
                "message": "Sincronización MBA3 completada exitosamente"
            }
        except Exception as e:
            logger.error(f"❌ Error al sincronizar maestros MBA3: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al sincronizar MBA3: {str(e)}")
    
    @app.post("/cruce-productos/sincronizar-maestros/sap", tags=["Cruce de Productos"])
    async def sincronizar_maestros_sap(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Sincroniza maestros de productos SAP desde OPENQUERY a staging.
        
        Este endpoint:
        1. Consulta productos SAP desde OPENQUERY
        2. Normaliza códigos y guarda/actualiza en producto_sap_staging
        3. Registra estadísticas en sync_control
        
        ⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
        No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.
        
        Returns:
            Estadísticas de sincronización para SAP
        """
        try:
            logger.info("🔄 Iniciando sincronización manual de maestros SAP...")
            service = ProductoStagingSyncService()
            resultado = service.sync_sap_products()
            
            return {
                "status": "success",
                "data": resultado,
                "message": "Sincronización SAP completada exitosamente"
            }
        except Exception as e:
            logger.error(f"❌ Error al sincronizar maestros SAP: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al sincronizar SAP: {str(e)}")
    
    @app.post("/cruce-productos/sincronizar-maestros", tags=["Cruce de Productos"])
    async def sincronizar_maestros(
        force_full: bool = Query(False, description="Forzar sincronización completa desde el inicio (útil para pruebas o cuando se eliminan datos)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Sincroniza ambos maestros de productos (MBA3 y SAP) desde ERPs a staging.
        
        Este endpoint ejecuta ambos procesos en secuencia:
        1. Consulta productos MBA3 desde API
        2. Consulta productos SAP desde OPENQUERY
        3. Normaliza códigos y guarda/actualiza en tablas staging
        4. Registra estadísticas en sync_control
        
        **Estrategia de sincronización:**
        - Por defecto: Sincronización incremental (continúa desde el último producto procesado)
        - Si la tabla está vacía o tiene < 100 productos: Sincronización completa automática
        - Con `force_full=true`: Fuerza sincronización completa desde el inicio
        
        ⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
        No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.
        
        **Parámetros:**
        - `force_full` (bool, default: false): Si true, fuerza sincronización completa desde el inicio.
          Útil cuando eliminas datos para pruebas o necesitas re-sincronizar todo.
        
        **Ejemplos:**
        - Sincronización incremental: `POST /cruce-productos/sincronizar-maestros`
        - Sincronización completa: `POST /cruce-productos/sincronizar-maestros?force_full=true`
        
        Para sincronizar solo MBA3 o solo SAP, usar los endpoints específicos:
        - POST /cruce-productos/sincronizar-maestros/mba3
        - POST /cruce-productos/sincronizar-maestros/sap
        
        Returns:
            Estadísticas de sincronización para MBA3 y SAP
        """
        try:
            logger.info(f"🔄 Iniciando sincronización manual de maestros (MBA3 y SAP)... force_full={force_full}")
            service = ProductoStagingSyncService()
            resultado = service.sync_all(force_full_sync=force_full)
            
            return {
                "status": "success",
                "data": resultado,
                "message": "Sincronización completada exitosamente"
            }
        except Exception as e:
            logger.error(f"❌ Error al sincronizar maestros: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al sincronizar: {str(e)}")
    
    @app.get("/cruce-productos/buscar-sku/mba3", tags=["Cruce de Productos"])
    async def buscar_sku_mba3(
        sku: str = Query(..., description="SKU del producto a buscar en MBA3"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Busca un SKU directamente en la base de datos de MBA3.
        
        Consulta directamente la tabla INVT_FICHA_PRINCIPAL de MBA3.
        
        Args:
            sku: Código del producto (PRODUCT_ID) a buscar
        
        Returns:
            Información del producto en MBA3 si se encuentra
        """
        try:
            # Validar formato del SKU para prevenir SQL injection
            sku_clean = sku.strip()
            if not sku_clean:
                raise HTTPException(status_code=400, detail="SKU no puede estar vacío")
            
            # Validar que el SKU tenga formato seguro (alfanumérico, guiones, puntos, espacios)
            if not re.match(r'^[A-Za-z0-9.\- ]{1,50}$', sku_clean):
                raise HTTPException(
                    status_code=400, 
                    detail="SKU contiene caracteres no permitidos. Solo se permiten letras, números, guiones, puntos y espacios."
                )
            
            logger.info(f"🔍 Buscando SKU en MBA3: {sku_clean}")
            
            # Escapar comillas simples para la query (aunque ya está validado)
            sku_escaped = sku_clean.replace("'", "''")
            
            # Consulta directa a MBA3 - solo busca por PRODUCT_ID sin filtros adicionales
            query = (
                "SELECT PRODUCT_NAME, PRODUCT_ID, GrupoPrenda, CORP, Talla, PRESENTACION, "
                "Descontinuado, GROUP_CODE, INACTIVE, Tipo_Origen, SELL, CODE_PROV_O_ALT, "
                "CATEGORY, Familia, Codigo_Marca, PRODUCT_NAME_2, Fecha_Ultima_Venta, FechaUltimoMovimiento "
                "FROM INVT_FICHA_PRINCIPAL "
                f"WHERE PRODUCT_ID = '{sku_escaped}'"
            )
            
            # Ejecutar en thread pool para no bloquear el event loop
            from src.services.mba3_service import MBA3Service
            mba3_service = MBA3Service()
            
            try:
                # Timeout de 50 segundos para dar margen a:
                # - Delays de JWT (hasta 5s: 2s post-login + 3s si JWT reciente)
                # - Consultas que pueden tardar 30-40s en MBA3
                # El frontend tiene timeout de 60s, así que 50s da margen suficiente
                result = await asyncio.wait_for(
                    asyncio.to_thread(mba3_service.execute_query, query),
                    timeout=50.0
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ Timeout al buscar SKU en MBA3: {sku_clean} (más de 50 segundos)")
                raise HTTPException(
                    status_code=504,
                    detail=f"Timeout al buscar SKU en MBA3. La consulta tardó más de 50 segundos. Verifique la conexión con MBA3."
                )
            except Exception as e:
                logger.error(f"❌ Error al ejecutar consulta MBA3: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500, 
                    detail=f"Error al buscar SKU en MBA3: {str(e)}"
                )
            
            # Normalizar resultado
            if isinstance(result, list):
                productos = result
            elif isinstance(result, dict):
                # Buscar la clave que contiene la lista de resultados
                productos = []
                for key, value in result.items():
                    if isinstance(value, list):
                        productos = value
                        break
                if not productos and result:
                    productos = [result]
            else:
                productos = []
            
            if not productos:
                return {
                    "status": "not_found",
                    "message": f"SKU no encontrado en MBA3: {sku_clean}",
                    "sku": sku_clean,
                    "data": None
                }
            
            producto = productos[0]
            
            # Normalizar nombres de campos (el API puede devolver diferentes formatos)
            # Mapear a los campos que el frontend espera
            producto_info = {
                "codigo": producto.get("PRODUCT_ID") or producto.get("product_id") or producto.get("Product_ID") or sku_clean,
                "nombre": producto.get("PRODUCT_NAME") or producto.get("product_name") or producto.get("Product_Name") or "",
                "corp": producto.get("CORP") or producto.get("corp") or producto.get("Corp") or "",
                "grupo_prenda": producto.get("GrupoPrenda") or producto.get("grupoPrenda") or producto.get("grupo_prenda") or "",
                "talla": producto.get("Talla") or producto.get("talla") or "",
                "presentacion": producto.get("PRESENTACION") or producto.get("presentacion") or producto.get("Presentacion") or "",
                "group_code": producto.get("GROUP_CODE") or producto.get("group_code") or producto.get("Group_Code") or "",
                "tipo_origen": producto.get("Tipo_Origen") or producto.get("tipo_origen") or producto.get("Tipo_Origen") or "",
                "descontinuado": producto.get("Descontinuado") or producto.get("descontinuado") or "",
                "inactive": producto.get("INACTIVE") or producto.get("inactive") or producto.get("Inactive") or ""
            }
            
            return {
                "status": "success",
                "message": "SKU encontrado en MBA3",
                "sku": sku_clean,
                "data": producto_info
            }
            
        except HTTPException:
            # Re-lanzar excepciones HTTP (validaciones)
            raise
        except Exception as e:
            logger.error(f"❌ Error al buscar SKU en MBA3: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al buscar SKU en MBA3: {str(e)}")
    
    @app.get("/cruce-productos/buscar-sku/sap", tags=["Cruce de Productos"])
    async def buscar_sku_sap(
        sku: str = Query(..., description="SKU (ItemCode) del producto a buscar en SAP"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Busca un SKU directamente en la base de datos de SAP.
        
        Consulta directamente SAP usando OPENQUERY.
        
        Args:
            sku: Código del producto (ItemCode) a buscar en SAP
        
        Returns:
            Información del producto en SAP si se encuentra
        """
        try:
            # Validar formato del SKU para prevenir SQL injection
            sku_clean = sku.strip()
            if not sku_clean:
                raise HTTPException(status_code=400, detail="SKU no puede estar vacío")
            
            # Validar que el SKU tenga formato seguro (alfanumérico, guiones, puntos, espacios)
            if not re.match(r'^[A-Za-z0-9.\- ]{1,50}$', sku_clean):
                raise HTTPException(
                    status_code=400, 
                    detail="SKU contiene caracteres no permitidos. Solo se permiten letras, números, guiones, puntos y espacios."
                )
            
            logger.info(f"🔍 Buscando SKU en SAP: {sku_clean}")
            
            # Verificar si SAP está habilitado
            if not ENABLE_SAP_QUERIES:
                raise HTTPException(
                    status_code=400,
                    detail="Consultas SAP están deshabilitadas. Configura ENABLE_SAP_QUERIES=true en .env"
                )
            
            # Escapar comillas simples para la query (aunque ya está validado)
            # En OPENQUERY, las comillas simples dentro de la query remota se escapan duplicándolas
            # Pero el valor del SKU debe escaparse correctamente
            sku_escaped = sku_clean.replace("'", "''")
            
            # Consulta directa a SAP usando OPENQUERY
            # CORRECCIÓN: El formato correcto para OPENQUERY es usar comillas simples dobles ('') 
            # dentro de la query remota para representar una comilla simple
            query = f"""
            SELECT 
                T0."ItemCode",
                T0."ItemName",
                T0."U_IXX_PACK",
                T0."ItmsGrpCod",
                T0."CardCode",
                T0."validFor"
            FROM OPENQUERY([{SAP_LINKED_SERVER}], '
                SELECT 
                    "ItemCode",
                    "ItemName",
                    "U_IXX_PACK",
                    "ItmsGrpCod",
                    "CardCode",
                    "validFor"
                FROM "{SAP_DATABASE}"."OITM"
                WHERE "ItemCode" = ''{sku_escaped}''
            ') T0;
            """
            
            # Función auxiliar para ejecutar la query en thread pool
            def execute_sap_query():
                conn = None
                try:
                    conn = get_sap_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(query)
                    result = cursor.fetchone()
                    return result
                finally:
                    if conn:
                        try:
                            cursor.close()
                            conn.close()
                        except:
                            pass
            
            try:
                # Timeout de 50 segundos (consistente con MBA3)
                # SAP suele ser más rápido, pero mantener mismo timeout para consistencia
                # El frontend tiene timeout de 60s, así que 50s da margen suficiente
                result = await asyncio.wait_for(
                    asyncio.to_thread(execute_sap_query),
                    timeout=50.0
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ Timeout al buscar SKU en SAP: {sku_clean} (más de 50 segundos)")
                raise HTTPException(
                    status_code=504,
                    detail=f"Timeout al buscar SKU en SAP. La consulta tardó más de 50 segundos. Verifique la conexión con SAP."
                )
            except pyodbc.Error as e:
                logger.error(f"❌ Error de base de datos al consultar SAP: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Error al consultar SAP: {str(e)}")
            except Exception as e:
                logger.error(f"❌ Error al ejecutar consulta SAP: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Error al buscar SKU en SAP: {str(e)}")
            
            if not result:
                return {
                    "status": "not_found",
                    "message": f"SKU no encontrado en SAP: {sku_clean}",
                    "sku": sku_clean,
                    "data": None
                }
            
            # Normalizar formato de respuesta
            valid_for_raw = result[5] if len(result) > 5 and result[5] is not None else 'N'
            valid_for = str(valid_for_raw).upper() == 'Y'
            
            producto_info = {
                "codigo": result[0] if result[0] else sku_clean,
                "nombre": result[1] if result[1] else "",
                "pack": result[2] if result[2] else "",
                "group_code": result[3] if result[3] else None,
                "card_code": result[4] if result[4] else None,
                "valid_for": valid_for_raw,
                "estado": "activo" if valid_for else "inactivo"
            }
            
            return {
                "status": "success",
                "message": "SKU encontrado en SAP",
                "sku": sku_clean,
                "data": producto_info
            }
            
        except HTTPException:
            # Re-lanzar excepciones HTTP (validaciones)
            raise
        except Exception as e:
            logger.error(f"❌ Error al buscar SKU en SAP: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al buscar SKU en SAP: {str(e)}")
    
    @app.get("/cruce-productos/estado-sincronizacion", tags=["Cruce de Productos"])
    async def obtener_estado_sincronizacion(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Obtiene el estado actual de sincronización de maestros MBA3 y SAP.
        
        Retorna información sobre:
        - Última sincronización exitosa (fecha y hora en ISO 8601)
        - Estado actual: "exitoso", "error", "en_proceso", o null si no hay registros
        - Mensaje descriptivo del estado
        
        ⚠️ Nota: Si hay una sincronización EN_PROGRESO con más de 2 horas,
           se considera inconsistente (proceso colgado) y se retorna como error.
        
        Returns:
            {
                "status": "success",
                "data": {
                    "mba3": {
                        "ultima_sync": "2024-01-15T10:30:00" | null,
                        "estado": "exitoso" | "error" | "en_proceso" | null,
                        "mensaje": "Sincronización completada exitosamente..."
                    },
                    "sap": {
                        "ultima_sync": "2024-01-15T10:30:00" | null,
                        "estado": "exitoso" | "error" | "en_proceso" | null,
                        "mensaje": "Sincronización completada exitosamente..."
                    }
                }
            }
        """
        try:
            conn = get_db_connection()
            try:
                sync_control_repo = SyncControlRepository(conn)
                
                # Obtener estado para MBA3
                estado_mba3 = sync_control_repo.get_estado_sincronizacion('MBA3')
                
                # Obtener estado para SAP
                estado_sap = sync_control_repo.get_estado_sincronizacion('SAP')
                
                return {
                    "status": "success",
                    "data": {
                        "mba3": {
                            "ultima_sync": estado_mba3.get("ultima_sync"),
                            "estado": estado_mba3.get("estado"),
                            "mensaje": estado_mba3.get("mensaje")
                        },
                        "sap": {
                            "ultima_sync": estado_sap.get("ultima_sync"),
                            "estado": estado_sap.get("estado"),
                            "mensaje": estado_sap.get("mensaje")
                        }
                    }
                }
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"❌ Error al obtener estado de sincronización: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al obtener estado: {str(e)}")

