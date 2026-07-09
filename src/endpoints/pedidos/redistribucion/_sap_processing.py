"""Procesamiento SAP y notificación de homologaciones."""

from typing import Any, Dict


def _enviar_notificacion_homologacion(conn, homologacion_service, logger) -> None:
    from src.database.repositories.homologacion_repository import HomologacionRepository
    from src.utils.email_notifier import send_homologacion_notification
    from src.utils.timezone import ahora_naive

    todos_productos = homologacion_service.get_todos_productos_no_homologados()
    productos_no_homologados = todos_productos.get("productos", [])
    estadisticas = todos_productos.get("estadisticas", {})

    if not productos_no_homologados:
        logger.info("✅ No hay productos no homologados nuevos para notificar")
        return

    logger.info(f"⚠️ Se detectaron {len(productos_no_homologados)} productos no homologados")

    repository = HomologacionRepository(conn)
    email_enviado = send_homologacion_notification(
        productos_no_homologados=productos_no_homologados,
        estadisticas=estadisticas,
        fecha_ejecucion=ahora_naive(),
        filtrar_ya_notificados=True,
        homologacion_repository=repository,
    )

    if email_enviado:
        logger.info("✅ Notificación de homologación enviada (solo productos nuevos)")
    else:
        logger.info("⏭️ No se envió notificación (todos ya fueron notificados)")


def _procesar_sap_con_homologacion_impl(
    pedido_id: str,
    user_id: str,
    conn,
    *,
    logger,
) -> Dict[str, Any]:
    """
    Implementación síncrona del procesamiento SAP + homologaciones.
    Usado tanto por la versión async como por asyncio.to_thread().
    """
    from src.database.services.pedido_sap_service import procesar_pedido_con_sap
    from src.database.services.homologacion_service import HomologacionService

    homologacion_service = HomologacionService()

    resultado_sap = procesar_pedido_con_sap(
        pedido_id=pedido_id,
        usuario_id=user_id,
        homologacion_service=homologacion_service,
        continue_on_error=True,
    )

    logger.info(
        "✅ Procesamiento SAP completado: %s productos procesados",
        resultado_sap.get("productos_procesados", 0),
    )

    if resultado_sap.get("productos_no_homologados", 0) > 0:
        logger.info("🔍 Verificando productos no homologados...")
        try:
            _enviar_notificacion_homologacion(conn, homologacion_service, logger)
        except Exception as homolog_error:
            logger.warning(f"⚠️ Error al verificar homologaciones: {homolog_error}")

    return resultado_sap


async def procesar_pedido_sap_con_homologacion(
    pedido_id: str,
    user_id: str,
    conn,
    *,
    logger,
) -> Dict[str, Any]:
    """Ejecuta procesamiento SAP + verificación de homologaciones + notificación email.

    NOTA: Esta función es async pero internamente solo ejecuta operaciones síncronas.
    Para endpoints que usan asyncio.to_thread(), usar procesar_pedido_sap_con_homologacion_sync().
    """
    return _procesar_sap_con_homologacion_impl(
        pedido_id=pedido_id, user_id=user_id, conn=conn, logger=logger,
    )


def procesar_pedido_sap_con_homologacion_sync(
    pedido_id: str,
    user_id: str,
    conn,
    *,
    logger,
) -> Dict[str, Any]:
    """Versión síncrona para usar dentro de asyncio.to_thread().

    Idéntica a procesar_pedido_sap_con_homologacion pero sin async,
    para ser llamada desde threads que no bloquean el event loop.
    """
    return _procesar_sap_con_homologacion_impl(
        pedido_id=pedido_id, user_id=user_id, conn=conn, logger=logger,
    )
