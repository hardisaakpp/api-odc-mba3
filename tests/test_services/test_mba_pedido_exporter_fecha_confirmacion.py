"""
Tests para Fecha Pedido (col. 5) y Fecha Entrega (col. 6) en el TXT MBA3.

Regla de negocio: ambas columnas usan la fecha en que el pedido transicionó a
CONFIRMADO POR EL RAYO (estado_id=4, clic en "Confirmar" en el detalle del
pedido), obtenida de pedido_estado_historial — no la fecha_pedido/fecha_entrega
capturada originalmente en el Excel/creación del pedido.

Si no existe ese registro de confirmación, ambas se exportan vacías (00/00/0000).
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from src.database.pedido_estados import ESTADO_REDISTRIBUCION
from src.database.services.mba_pedido_exporter import MBAExportConfig, MBAPedidoExporter


PEDIDO_DETALLE_ID = "detalle-1"
TIENDA_ID = "tienda-1"


def _pedido(cantidad: float = 1) -> dict:
    return {
        "cabecera": {
            "numero_pedido": "PED-1",
            # Fechas "de Excel" distintas a la de confirmación: deben ser ignoradas.
            "fecha_pedido": "2020-01-01",
            "fecha_entrega": "2020-01-02",
            "origen_traslado": "",
        },
        "detalles": [
            {
                "pedido_detalle_id": PEDIDO_DETALLE_ID,
                "codigo_interno": "COD-1",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [{"tienda_id": TIENDA_ID, "codigo": "TRL-001", "cantidad": cantidad}],
            }
        ],
    }


def _columnas_fecha(txt_bytes: bytes) -> tuple:
    linea_detalle = txt_bytes.decode("utf-8").split("\n")[-1]
    cols = linea_detalle.split("\t")
    return cols[4], cols[5]  # col 5 (Fecha Pedido), col 6 (Fecha Entrega)


def _mock_repo(mock_repo_class, fecha_confirmacion):
    mock_repo_class.return_value.get_pedido_completo.return_value = _pedido()
    mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = fecha_confirmacion


def _mock_distribucion(mock_dist_class, cantidad: float = 1):
    """Mockea DistribucionConfirmadaRepository devolviendo la misma cantidad que
    la fixture ya tenía en tienda["cantidad"], para no cambiar la intención de
    estos tests (verifican fecha, no cantidad)."""
    mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {
        PEDIDO_DETALLE_ID: {TIENDA_ID: cantidad}
    }


def test_fecha_pedido_y_entrega_usan_fecha_confirmacion():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_repo(mock_repo_class, datetime(2026, 3, 15, 10, 30))
        _mock_distribucion(mock_dist_class)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    fecha_pedido, fecha_entrega = _columnas_fecha(resultado)
    assert fecha_pedido == "15/03/2026"
    assert fecha_entrega == "15/03/2026"


def test_fecha_vacia_si_no_hay_registro_de_confirmacion():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_repo(mock_repo_class, None)
        _mock_distribucion(mock_dist_class)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    fecha_pedido, fecha_entrega = _columnas_fecha(resultado)
    assert fecha_pedido == "00/00/0000"
    assert fecha_entrega == "00/00/0000"


def test_fecha_confirmacion_tambien_en_modo_consolidado():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_repo(mock_repo_class, datetime(2026, 7, 1, 23, 59))
        _mock_distribucion(mock_dist_class)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    fecha_pedido, fecha_entrega = _columnas_fecha(resultado)
    assert fecha_pedido == "01/07/2026"
    assert fecha_entrega == "01/07/2026"


def test_consulta_historial_con_pedido_id_y_estado_redistribucion():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_repo(mock_repo_class, datetime(2026, 3, 15))
        _mock_distribucion(mock_dist_class)
        pedido_id = "00000000-0000-0000-0000-000000000000"

        exporter = MBAPedidoExporter()
        exporter.exportar_pedido_formato_mba(
            pedido_id=pedido_id,
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    mock_repo_class.return_value.get_fecha_confirmacion_estado.assert_called_once_with(
        pedido_id, ESTADO_REDISTRIBUCION
    )
