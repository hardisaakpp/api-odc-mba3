"""
Tests para PedidoService.crear_pedido_hijo_diferencia (req. 1.2, pedidos parciales):
el pedido "hijo" generado con la diferencia debe heredar el comentario del padre y el
resaltado de color (rol_modificador) de COSTO UNIT./TOTAL/COMENTARIO -- para que Cargar
Plantilla / Detalle del Pedido sigan mostrando quién modificó cada campo por última vez,
aunque haya sido en el padre antes de generarse el hijo.
"""

from unittest.mock import MagicMock, patch

from src.database.services.pedido_service import PedidoService


def _pedido_padre():
    return {
        "cabecera": {
            "pedido_id": "padre-id",
            "numero_pedido": "P-100",
        },
        "detalles": [
            {
                "pedido_detalle_id": "det-1",
                "codigo_interno": "5-0012.9",
                "descripcion_sap": "Producto A",
                "marca": "ROLAND",
                "codigo_barras": "123456",
                "pack": "X3",
                "costo_doc_sin_iva": 10.0,
                "descuento_1": 0,
                "pvp": 15.0,
                "subtotal": 100.0,
                "costo_margen": 5.0,
                "costo_unitario": 10.0,
                "comentario": "Nota del padre: revisar con proveedor",
                "tiendas": [],
            }
        ],
    }


def _detalles_con_diferencia():
    return [{"pedido_detalle_id": "det-1", "cantidad_solicitada_original": 10, "diferencia": 4}]


def test_hereda_comentario_del_padre():
    with patch("src.database.services.pedido_service.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.pedido_service.PedidoRepository") as mock_repo_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        repo = mock_repo_class.return_value
        repo.contar_hijos.return_value = 0
        repo.insert_cabecera.return_value = "hijo-pedido-id"
        repo.insert_detalle.return_value = "det-hijo-1"
        repo.obtener_modificaciones_columnas.return_value = {"success": True, "modificaciones": []}

        PedidoService().crear_pedido_hijo_diferencia(
            pedido_padre=_pedido_padre(),
            detalles_con_diferencia=_detalles_con_diferencia(),
            nueva_fecha_entrega="2026-09-01",
            usuario_id="user1",
        )

        datos_detalle = repo.insert_detalle.call_args.args[1]
        assert datos_detalle["comentario"] == "Nota del padre: revisar con proveedor"


def test_hereda_resaltado_agrupado_por_rol():
    """El padre tiene COSTO UNIT. modificado por ODCSAP y TOTAL modificado por
    PRODUCCION_ELRAYO en la misma línea: el hijo debe recibir 2 llamadas separadas a
    guardar_modificaciones_columnas (una por rol), no una mezclada."""
    with patch("src.database.services.pedido_service.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.pedido_service.PedidoRepository") as mock_repo_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        repo = mock_repo_class.return_value
        repo.contar_hijos.return_value = 0
        repo.insert_cabecera.return_value = "hijo-pedido-id"
        repo.insert_detalle.return_value = "det-hijo-1"
        repo.obtener_modificaciones_columnas.return_value = {
            "success": True,
            "modificaciones": [
                {"pedido_detalle_id": "det-1", "columna_key": "costo_doc_sin_iva", "rol_modificador": "ODCSAP"},
                {"pedido_detalle_id": "det-1", "columna_key": "total", "rol_modificador": "PRODUCCION_ELRAYO"},
            ],
        }

        PedidoService().crear_pedido_hijo_diferencia(
            pedido_padre=_pedido_padre(),
            detalles_con_diferencia=_detalles_con_diferencia(),
            nueva_fecha_entrega="2026-09-01",
            usuario_id="user1",
        )

        assert repo.guardar_modificaciones_columnas.call_count == 2
        llamadas_por_rol = {
            kwargs["rol_modificador"]: kwargs["modificaciones"]
            for _, kwargs in repo.guardar_modificaciones_columnas.call_args_list
        }
        assert llamadas_por_rol["ODCSAP"] == [{"pedido_detalle_id": "det-hijo-1", "columna_key": "costo_doc_sin_iva"}]
        assert llamadas_por_rol["PRODUCCION_ELRAYO"] == [{"pedido_detalle_id": "det-hijo-1", "columna_key": "total"}]


def test_sin_modificaciones_previas_no_llama_guardar_modificaciones():
    with patch("src.database.services.pedido_service.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.pedido_service.PedidoRepository") as mock_repo_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        repo = mock_repo_class.return_value
        repo.contar_hijos.return_value = 0
        repo.insert_cabecera.return_value = "hijo-pedido-id"
        repo.insert_detalle.return_value = "det-hijo-1"
        repo.obtener_modificaciones_columnas.return_value = {"success": True, "modificaciones": []}

        PedidoService().crear_pedido_hijo_diferencia(
            pedido_padre=_pedido_padre(),
            detalles_con_diferencia=_detalles_con_diferencia(),
            nueva_fecha_entrega="2026-09-01",
            usuario_id="user1",
        )

        repo.guardar_modificaciones_columnas.assert_not_called()
