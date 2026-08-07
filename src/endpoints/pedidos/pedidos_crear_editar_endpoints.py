"""
Endpoints de creacion, edicion e importacion de pedidos.
"""

import logging
from typing import Dict

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Path, Query, Body, status, Request
from fastapi.responses import JSONResponse

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.exceptions import BusinessException
from src.logging_config import log_business_operation
from src.utils.audit_context import get_audit_context, ORIGEN_WEB
from src.models import (
    ModificarPedidoCabeceraRequest,
    ModificarPedidoCabeceraResponse,
    CrearPedidoRequest,
    CrearPedidoResponse
)
from .utils import get_user_id, MAX_FILE_SIZE

logger = logging.getLogger(__name__)

# Permisos (evita duplicación de literales)
_PERM_MABEL = 'mabel.view'
_PERM_ODCSAP = 'odcsap.view'


def _mapear_codigo_a_filas(data):
    """Construye un dict {codigoProducto: [filas]} para reportar errores por fila."""
    codigo_a_filas = {}
    for item in data:
        codigo = item.get("codigoProducto")
        fila = item.get("filaOrigen")
        if codigo and fila:
            codigo_a_filas.setdefault(codigo, []).append(fila)
    return codigo_a_filas


def _agregar_errores_por_fila(resultado, validacion_sap, codigo_a_filas, codigos, tipo, mensaje_default_fn):
    """Agrega errores/warnings SAP a `resultado['errores']`, expandidos por fila."""
    for codigo in codigos:
        detalle_codigo = validacion_sap.get("detalle", {}).get(codigo, {})
        mensaje = detalle_codigo.get("mensaje") or mensaje_default_fn(codigo)

        for fila in codigo_a_filas.get(codigo, []):
            resultado["errores"].append({
                "fila": fila,
                "campo": "CodigoProducto",
                "tipo": tipo,
                "mensaje": mensaje
            })


def _recalcular_filas_validas(resultado):
    """Recalcula filasValidas/filasInvalidas del resumen según los errores críticos."""
    filas_con_errores_criticos = set()
    for error in resultado.get("errores", []):
        if error.get("tipo") == "ERROR":
            fila = error.get("fila")
            if fila and fila > 0:
                filas_con_errores_criticos.add(fila)

    filas_leidas = resultado["resumen"].get("filasLeidas", 0)
    filas_invalidas_originales = resultado["resumen"].get("filasInvalidas", 0)
    filas_invalidas_finales = max(filas_invalidas_originales, len(filas_con_errores_criticos))

    resultado["resumen"]["filasInvalidas"] = filas_invalidas_finales
    resultado["resumen"]["filasValidas"] = max(0, filas_leidas - filas_invalidas_finales)


def _mapear_codigo_a_info_productos(data):
    """Construye un dict {codigoProducto: [info_producto, ...]} para sincronizar/validar contra SAP."""
    codigo_a_info_productos = {}
    for item in data:
        codigo = item.get("codigoProducto")
        info_producto = item.get("info_producto")
        if codigo and info_producto is not None:
            codigo_a_info_productos.setdefault(codigo, []).append(info_producto)
    return codigo_a_info_productos


def _agregar_error_pack(resultado, codigo_a_filas, codigo, pack_excel, pack_sap):
    """
    Agrega un ERROR por fila cuando el Pack del Excel no coincide con el de SAP (RN-02).

    Incluye `pack_excel`/`pack_sap` como campos estructurados (ademas del mensaje) para
    que el frontend pueda ofrecer la correccion sugerida sin tener que parsear texto.
    """
    mensaje = (
        f"El Pack '{pack_excel}' del Excel no coincide con el Pack registrado en SAP "
        f"para '{codigo}' ('{pack_sap}'). Use '{pack_sap}'."
    )
    for fila in codigo_a_filas.get(codigo, []):
        resultado["errores"].append({
            "fila": fila,
            "campo": "Pack",
            "tipo": "ERROR",
            "mensaje": mensaje,
            "pack_excel": pack_excel,
            "pack_sap": pack_sap
        })


def _valores_numericos_difieren(valor_excel, valor_sap, tolerancia=0.01):
    """Compara dos valores monetarios redondeados a 2 decimales, con tolerancia por tipo/redondeo."""
    try:
        return abs(round(float(valor_excel), 2) - round(float(valor_sap), 2)) > tolerancia
    except (TypeError, ValueError):
        return False


def _agregar_error_pvp(resultado, codigo_a_filas, codigo, pvp_excel, pvp_sap):
    """
    Agrega un ERROR por fila cuando el PVP del Excel no coincide con el de SAP (RN-02).

    PVP de SAP viene de ITM1 con PriceList=1 ("Precio Minorista"). Incluye
    `pvp_excel`/`pvp_sap` como campos estructurados (ademas del mensaje) para que
    el frontend pueda ofrecer la correccion sugerida sin tener que parsear texto.
    """
    pvp_excel_fmt = f"{float(pvp_excel):.2f}"
    pvp_sap_fmt = f"{float(pvp_sap):.2f}"
    mensaje = (
        f"El PVP '{pvp_excel_fmt}' del Excel no coincide con el PVP registrado en SAP "
        f"(Precio Minorista) para '{codigo}' ('{pvp_sap_fmt}'). Use '{pvp_sap_fmt}'."
    )
    for fila in codigo_a_filas.get(codigo, []):
        resultado["errores"].append({
            "fila": fila,
            "campo": "PVP",
            "tipo": "ERROR",
            "mensaje": mensaje,
            "pvp_excel": float(pvp_excel),
            "pvp_sap": float(pvp_sap)
        })


def _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas):
    """
    Para cada código válido en SAP: toma código de barras y descripción desde SAP
    (fuente de verdad; el Excel es solo referencia visual, no se valida contra SAP)
    y valida Pack y PVP contra SAP (obligatorios por RN-02, bloquean si difieren).
    """
    codigo_a_info_productos = _mapear_codigo_a_info_productos(resultado.get("data", []))
    detalle = validacion_sap.get("detalle", {})

    for codigo, info_productos in codigo_a_info_productos.items():
        sap_info = detalle.get(codigo, {}).get("info")
        if not sap_info:
            continue

        for info_producto in info_productos:
            if sap_info.get("codigo_barras"):
                info_producto["codigo_barras"] = sap_info["codigo_barras"]
            if sap_info.get("item_name"):
                info_producto["descripcion_sap"] = sap_info["item_name"]

        pack_excel = next((ip.get("pack") for ip in info_productos if ip.get("pack")), None)
        pack_sap = sap_info.get("pack_sap")
        if pack_excel and pack_sap and pack_excel.strip().upper() != pack_sap.strip().upper():
            _agregar_error_pack(resultado, codigo_a_filas, codigo, pack_excel, pack_sap)

        pvp_excel = next((ip.get("pvp") for ip in info_productos if ip.get("pvp")), None)
        pvp_sap = sap_info.get("pvp_sap")
        if pvp_excel and pvp_sap and _valores_numericos_difieren(pvp_excel, pvp_sap):
            _agregar_error_pvp(resultado, codigo_a_filas, codigo, pvp_excel, pvp_sap)


def _construir_resumen_validacion_sap(validacion_sap, codigos_productos, codigos_no_encontrados, codigos_errores, codigos_warnings):
    """Construye el resumen de validación SAP para agregar a la respuesta."""
    return {
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
                "mensaje": info.get("mensaje"),
                "mba3": info.get("mba3"),
                "sugerencias_sap": info.get("sugerencias_sap", [])
            }
            for codigo, info in validacion_sap.get("detalle", {}).items()
        }
    }


def _aplicar_validacion_sap(resultado, sap_obligatorio):
    """Valida los códigos de producto contra SAP y enriquece `resultado` con errores/warnings."""
    from src.database.services.pedido_validator import PedidoValidator

    # Extraer codigos unicos de productos (performance: validar una vez por codigo)
    codigos_productos = list(set([
        item.get("codigoProducto")
        for item in resultado.get("data", [])
        if item.get("codigoProducto")
    ]))

    if not codigos_productos:
        return

    validator = PedidoValidator()
    validacion_sap = validator.validar_productos_existen_en_sap_con_sugerencias(
        codigos_productos=codigos_productos,
        usar_cache=True,
        sap_obligatorio=sap_obligatorio,
        incluir_sugerencias=True,
        limite_sugerencias=20
    )

    # Mapear codigos a filas para reportar errores por fila
    codigo_a_filas = _mapear_codigo_a_filas(resultado.get("data", []))

    codigos_no_encontrados = set(validacion_sap.get("no_encontrados", []))
    codigos_errores = set(validacion_sap.get("errores", []))
    codigos_warnings = set(validacion_sap.get("warnings", []))

    # Errores: codigos no encontrados o errores criticos
    _agregar_errores_por_fila(
        resultado, validacion_sap, codigo_a_filas,
        codigos_no_encontrados | codigos_errores, "ERROR",
        lambda c: f"El codigo de producto '{c}' no es valido en SAP"
    )

    # Warnings
    _agregar_errores_por_fila(
        resultado, validacion_sap, codigo_a_filas,
        codigos_warnings, "WARNING",
        lambda c: f"No se pudo validar el codigo '{c}' en SAP"
    )

    # Codigo de barras/descripcion: se toman de SAP (fuente de verdad) para los codigos validos.
    # Pack y PVP: validacion obligatoria contra SAP (RN-02), bloquea si difieren.
    _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

    # Recalcular filasValidas/filasInvalidas
    _recalcular_filas_validas(resultado)

    # Agregar resumen de validacion SAP
    resultado["validacion_sap"] = _construir_resumen_validacion_sap(
        validacion_sap, codigos_productos, codigos_no_encontrados, codigos_errores, codigos_warnings
    )

    logger.info(
        f"📊 Validacion SAP: {len(validacion_sap.get('validos', []))} validos, "
        f"{len(codigos_no_encontrados)} no encontrados, "
        f"{len(codigos_errores)} errores, {len(codigos_warnings)} warnings"
    )


async def _importar_excel_pedido_handler(file, hoja_cabecera, hoja_detalle, validar_sap, sap_obligatorio):
    """Lógica del endpoint de importación/parsing de Excel de pedido."""
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

        # Validar tamano
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo es demasiado grande. Tamano maximo: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
            )

        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="El archivo esta vacio"
            )

        # Parsear Excel (solo parsing tecnico)
        from src.database.services.pedido_service import PedidoService

        service = PedidoService()
        resultado = service.parsear_excel_pedido(
            file_content=content,
            hoja_cabecera=hoja_cabecera,
            hoja_detalle=hoja_detalle
        )

        # ✅ VALIDACION SAP POST-PARSING (si esta habilitada)
        if validar_sap and resultado.get("data"):
            _aplicar_validacion_sap(resultado, sap_obligatorio)

        return JSONResponse(status_code=200, content=resultado)

    except HTTPException:
        raise
    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al importar Excel: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al importar el archivo: {str(e)}"
        )


def _determinar_status_crear(resultado):
    """Determina el código HTTP de la creación de pedido según el resultado."""
    if resultado["status"] == "validation_error":
        return 400
    if resultado["status"] == "error":
        if resultado.get("error_tipo") == "numero_pedido_duplicado":
            return 400
        return 500
    return 200


async def _crear_pedido_manual_handler(request, request_body, user):
    """Lógica del endpoint de creación manual de pedido (HU-01)."""
    try:
        from src.database.services.pedido_service import PedidoService

        # Crear contexto de auditoria (Buenas Practicas - Seccion 3)
        audit = get_audit_context(request, user, origen=ORIGEN_WEB)

        service = PedidoService()
        usuario_id = user.get("sub") or user.get("user_id")

        datos_pedido = request_body.model_dump(exclude_none=False)

        logger.debug(f"📦 Datos recibidos para crear pedido manual: {datos_pedido}")
        if datos_pedido.get("articulos"):
            logger.debug(f"📦 Primer articulo recibido: {datos_pedido['articulos'][0]}")

        resultado = service.crear_pedido_manual(
            datos_pedido=datos_pedido,
            usuario_id=usuario_id,
            validar_productos=datos_pedido.get("validar_productos", True),
            validar_tiendas=datos_pedido.get("validar_tiendas", True),
            audit_context=audit
        )

        # Determinar codigo de estado HTTP
        status_code = _determinar_status_crear(resultado)

        # Log funcional estandarizado (Buenas Practicas - Seccion 5)
        log_business_operation(
            operation="crear_pedido_manual",
            id_usuario=user.get('username', usuario_id),
            id_transaccion=resultado.get("pedido_id"),
            id_tienda=datos_pedido.get("codigo_tienda"),
            monto=datos_pedido.get("monto_total"),
            success=(resultado["status"] == "success"),
            detalles={
                "numero_pedido": resultado.get("numero_pedido"),
                "total_articulos": len(datos_pedido.get("articulos", [])),
                "proveedor": datos_pedido.get("razon_social")
            }
        )

        return JSONResponse(status_code=status_code, content=resultado)

    except HTTPException:
        raise
    except Exception as e:
        # Log funcional de error
        log_business_operation(
            operation="crear_pedido_manual",
            id_usuario=user.get('username', 'UNKNOWN'),
            success=False,
            detalles={"error": str(e)}
        )
        logger.error(f"❌ Error al crear pedido manual: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al crear el pedido: {str(e)}"
        )


async def _modificar_pedido_cabecera_handler(request, pedido_id, request_body, user):
    """Lógica del endpoint de modificación de cabecera de pedido (HU-03)."""
    try:
        # Crear contexto de auditoria (Buenas Practicas - Seccion 3)
        audit = get_audit_context(request, user, origen=ORIGEN_WEB)

        datos_cabecera = request_body.model_dump(exclude_unset=True)
        campos_modificados = list(datos_cabecera.keys())

        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)

            pedido_existente = repo.get_pedido_completo(pedido_id)
            if not pedido_existente:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "pedido_not_found",
                        "message": f"No se encontro el pedido con ID: {pedido_id}"
                    }
                )

            resultado = repo.update_cabecera(pedido_id, datos_cabecera, audit_context=audit)

            if not resultado:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "update_failed",
                        "message": "No se pudo actualizar la cabecera del pedido"
                    }
                )

        logger.info(f"✅ Cabecera del pedido {pedido_id} actualizada por usuario {user.get('username', 'UNKNOWN')}")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "message": "Cabecera del pedido actualizada correctamente",
                "pedido_id": pedido_id,
                "campos_modificados": campos_modificados
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al modificar cabecera del pedido: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Error interno al modificar cabecera del pedido: {str(e)}"
            }
        )


async def _enviar_pedido_handler(pedido_id, user):
    """Lógica del endpoint de envío de pedido a EL RAYO."""
    try:
        from src.database.services.pedido_service import PedidoService
        service = PedidoService()
        usuario_id = get_user_id(user)
        resultado = service.enviar_pedido(pedido_id=pedido_id, usuario_id=usuario_id)

        # 📢 Notificacion: otros MABEL + EL RAYO (excl. autor)
        try:
            from src.utils.notification_manager import notification_manager, NotificationType
            numero_pedido = resultado.get("numero_pedido", "")
            _username = user.get("username") or user.get("sub") or "unknown"
            await notification_manager.notify_by_actor(
                actor_permission=_PERM_MABEL,
                actor_username=_username,
                title="Ingresa pedido de MABEL TRADING",
                message=f"Se ha recibido el pedido {numero_pedido}. Revisa el detalle para gestionarlo.",
                notification_type=NotificationType.INFO,
                metadata={"pedido_id": pedido_id, "numero_pedido": numero_pedido, "accion": "pedido_enviado"},
            )
        except Exception as notif_err:
            logger.warning(f"⚠️ Error al enviar notificacion en tiempo real: {notif_err}")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=resultado
        )
    except BusinessException as e:
        if e.error_code == "not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": e.error_code, "message": e.message}
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": e.error_code, "message": e.message}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al enviar pedido {pedido_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Error al enviar el pedido: {str(e)}"
            }
        )


def register_pedidos_crear_editar_endpoints(app: FastAPI):
    """Registra endpoints de creacion, edicion e importacion de pedidos."""

    @app.post("/pedidos/importar-excel", tags=["Pedidos"])
    async def importar_excel_pedido(
        file: UploadFile = File(..., description="Archivo Excel (.xlsx) con hojas 'cabecera' y 'detalle' (formato v1.0)"),
        hoja_cabecera: str = Query("cabecera", description="Nombre de la hoja de cabecera (default: 'cabecera')"),
        hoja_detalle: str = Query("detalle", description="Nombre de la hoja de detalle (default: 'detalle')"),
        validar_sap: bool = Query(True, description="Validar codigos de producto contra SAP"),
        sap_obligatorio: bool = Query(True, description="Si True, errores de SAP bloquean la importacion. Si False, solo genera warnings"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Importa y parsea un archivo Excel de pedido en formato v1.0.

        **Formato esperado (Template_Pedido_Inicial_v1.0.xlsx):**
        - **Hoja 1: "cabecera"** - Formato clave-valor (Campo | Valor | Ejemplo)
        - **Hoja 2: "detalle"** - Formato tabular con:
          - Columnas A-I: Informacion del producto (CODIGO PRODUCTO, CODIGO BARRAS, DESCRIPCION, etc.)
          - Columnas J-L: Bodegas centrales (RL-CD, OUT-CD, RG-CD) - NO incluidas en SUBTOTAL
          - Columnas M+: Tiendas individuales - SI incluidas en SUBTOTAL (parsea hasta ultima columna con informacion)

        **Solo parsing tecnico:** lee, normaliza y valida estructura.
        NO aplica reglas de negocio, NO consolida duplicados.
        NO calcula SUBTOTAL ni TOTAL - solo parsea los valores que contiene el Excel.

        **Validaciones tecnicas:**
        - Extension: .xlsx
        - Tamano maximo: 10 MB
        - Hojas obligatorias: "cabecera" y "detalle" (en minusculas)
        - Columnas obligatorias en detalle: CODIGO PRODUCTO (columna A)
        - Parsea desde columna M (indice 12) hasta la ultima columna con informacion

        **Estructura de respuesta:**
        ```json
        {
            "cabecera": {...},
            "resumen": {
                "filasLeidas": 120,
                "filasValidas": 115,
                "filasInvalidas": 5
            },
            "errores": [...],
            "data": [...]
        }
        ```

        Returns:
            JSON con resultado del parsing tecnico incluyendo cabecera y detalle
        """
        return await _importar_excel_pedido_handler(
            file, hoja_cabecera, hoja_detalle, validar_sap, sap_obligatorio
        )

    @app.post("/api/pedidos",
             response_model=CrearPedidoResponse,
             tags=["Pedidos"])
    async def crear_pedido_manual(
        request: Request,
        request_body: CrearPedidoRequest = Body(..., description="Datos del pedido a crear"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Crea un pedido manualmente desde la pantalla web (HU-01 - Carga por Pantalla).

        Este endpoint permite crear pedidos directamente desde la interfaz web
        sin necesidad de subir un archivo Excel.

        Returns:
            JSON con resultado completo de creacion del pedido
        """
        return await _crear_pedido_manual_handler(request, request_body, user)

    @app.put("/api/pedidos/{pedido_id}",
             response_model=ModificarPedidoCabeceraResponse,
             tags=["Pedidos - Edicion"])
    async def modificar_pedido_cabecera(
        request: Request,
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: ModificarPedidoCabeceraRequest = Body(..., description="Datos de la cabecera a modificar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL]))
    ):
        """
        Modifica la cabecera de un pedido (HU-03 - Modificacion de pedidos).

        Este endpoint permite modificar los datos de la cabecera del pedido.

        Returns:
            JSON con resultado de la modificacion
        """
        return await _modificar_pedido_cabecera_handler(request, pedido_id, request_body, user)

    @app.post("/api/pedidos/{pedido_id}/enviar", tags=["Pedidos"])
    async def enviar_pedido(
        pedido_id: str = Path(..., description="UUID del pedido a enviar a EL RAYO"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Enviar pedido a EL RAYO: cambia estado de BORRADOR a NUEVO_PEDIDO y envía notificación por correo.

        Solo se permite para pedidos en estado BORRADOR (estado_id = 1).
        Valida que el pedido tenga detalles. Si el correo falla, el pedido se marca como enviado
        igualmente; la respuesta incluye email_enviado: true/false.

        - **404**: Pedido no encontrado.
        - **400**: Pedido no en BORRADOR o sin detalles.
        - **200**: Pedido enviado (estado actualizado; email_enviado indica si el correo se envió).
        """
        return await _enviar_pedido_handler(pedido_id, user)
