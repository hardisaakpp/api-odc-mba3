"""
Endpoint para realizar cruce de productos entre MBA3 y SAP.
"""

import logging
import re
import pyodbc
from fastapi import FastAPI, HTTPException, Depends, Query

from src.database.services.cruce_productos_service import CruceProductosService
from src.database.services.sugerencias_homologacion_service import SugerenciasHomologacionService
from src.database.services.producto_staging_sync_service import ProductoStagingSyncService
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.config import SAP_LINKED_SERVER, SAP_DATABASE, ENABLE_SAP_QUERIES
from src.database.connection import get_sap_db_connection

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
        
        ⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
        No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.
        
        Para sincronizar solo MBA3 o solo SAP, usar los endpoints específicos:
        - POST /cruce-productos/sincronizar-maestros/mba3
        - POST /cruce-productos/sincronizar-maestros/sap
        
        Returns:
            Estadísticas de sincronización para MBA3 y SAP
        """
        try:
            logger.info("🔄 Iniciando sincronización manual de maestros (MBA3 y SAP)...")
            service = ProductoStagingSyncService()
            resultado = service.sync_all()
            
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
            
            # Consulta directa a MBA3 con filtros adicionales
            query = (
                "SELECT PRODUCT_NAME, PRODUCT_ID, GrupoPrenda, CORP, Talla, PRESENTACION, "
                "Descontinuado, GROUP_CODE, INACTIVE, Tipo_Origen "
                "FROM INVT_FICHA_PRINCIPAL "
                f"WHERE PRODUCT_ID IS NOT NULL AND PRODUCT_ID='{sku_escaped}' "
                f"AND Descontinuado='false' AND GROUP_CODE='PTERM' "
                f"AND INACTIVE='false' AND Tipo_Origen!='ESPEC' "
                f"AND Tipo_Origen!='EXPOR' AND Tipo_Origen!='MAPRO'"
            )
            
            from src.services.mba3_service import MBA3Service
            mba3_service = MBA3Service()
            result = mba3_service.execute_query(query)
            
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
            producto_info = {
                "codigo": producto.get("PRODUCT_ID") or producto.get("product_id") or producto.get("Product_ID") or sku_clean,
                "nombre": producto.get("PRODUCT_NAME") or producto.get("product_name") or producto.get("Product_Name") or "",
                "corp": producto.get("CORP") or producto.get("corp") or producto.get("Corp") or "",
                "grupo_prenda": producto.get("GrupoPrenda") or producto.get("grupoPrenda") or producto.get("grupo_prenda") or "",
                "talla": producto.get("Talla") or producto.get("talla") or "",
                "presentacion": producto.get("PRESENTACION") or producto.get("presentacion") or producto.get("Presentacion") or "",
                "descontinuado": producto.get("Descontinuado") or producto.get("descontinuado") or "",
                "group_code": producto.get("GROUP_CODE") or producto.get("group_code") or producto.get("Group_Code") or "",
                "inactive": producto.get("INACTIVE") or producto.get("inactive") or producto.get("Inactive") or "",
                "tipo_origen": producto.get("Tipo_Origen") or producto.get("tipo_origen") or producto.get("Tipo_Origen") or ""
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
            sku_escaped = sku_clean.replace("'", "''")
            
            # Consulta directa a SAP usando OPENQUERY (según ejemplo proporcionado)
            
            query = f"""
            SELECT 
                T0."ItemCode",
                T0."ItemName",
                T0."U_IXX_PACK",
                T0."ItmsGrpCod",
                T0."CardCode"
            FROM OPENQUERY([{SAP_LINKED_SERVER}], '
                SELECT 
                    "ItemCode",
                    "ItemName",
                    "U_IXX_PACK",
                    "ItmsGrpCod",
                    "CardCode"
                FROM "{SAP_DATABASE}"."OITM"
                WHERE "ItemCode" = ''{sku_escaped}''
            ') T0;
            """
            
            conn = None
            try:
                conn = get_sap_db_connection()
                cursor = conn.cursor()
                cursor.execute(query)
                result = cursor.fetchone()
                
                if not result:
                    return {
                        "status": "not_found",
                        "message": f"SKU no encontrado en SAP: {sku_clean}",
                        "sku": sku_clean,
                        "data": None
                    }
                
                # Normalizar formato de respuesta
                producto_info = {
                    "codigo": result[0] if result[0] else sku_clean,
                    "nombre": result[1] if result[1] else "",
                    "pack": result[2] if result[2] else "",
                    "group_code": result[3] if result[3] else None,
                    "card_code": result[4] if result[4] else None,
                    "estado": "activo"  # Asumimos activo si existe
                }
                
                return {
                    "status": "success",
                    "message": "SKU encontrado en SAP",
                    "sku": sku_clean,
                    "data": producto_info
                }
                
            except pyodbc.Error as e:
                logger.error(f"❌ Error de base de datos al consultar SAP: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Error al consultar SAP: {str(e)}")
            finally:
                if conn:
                    try:
                        cursor.close()
                        conn.close()
                    except:
                        pass
            
        except HTTPException:
            # Re-lanzar excepciones HTTP (validaciones)
            raise
        except Exception as e:
            logger.error(f"❌ Error al buscar SKU en SAP: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al buscar SKU en SAP: {str(e)}")

