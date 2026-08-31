"""
Tests para Fecha Pedido (col. 5) y Fecha Entrega (col. 6) en el TXT MBA3 de un
pedido "hijo" (cabecera.pedido_padre_id no nulo, ver
PedidoService.crear_pedido_hijo_diferencia).

El hijo nunca transiciona por ESTADO_REDISTRIBUCION (pasa de PRODUCCION_POSPUESTA
a LISTO_PARA_REDISTRIBUCION directo, ver pedido_estados.py), así que
get_fecha_confirmacion_estado(hijo_id, ESTADO_REDISTRIBUCION) siempre devuelve
None para él. El hijo ya guarda su propia fecha_pedido/fecha_entrega en su
cabecera (ver crear_pedido_hijo_diferencia) -- deben usarse directo, sin ir a la
bitácora.
"""

from unittest.mock import MagicMock, patch

from src.database.services.mba_pedido_exporter import MBAExportConfig, MBAPedidoExporter


PEDIDO_DETALLE_ID = "detalle-1"
TIENDA_ID = "tienda-1"


def _pedido_hijo(cantidad: float = 1) -> dict:
    return {
        "cabecera": {
            "numero_pedido": "PED-1.01",
            "pedido_padre_id": "padre-uuid",
            "fecha_pedido": "2026-03-15",
            "fecha_entrega": "2026-03-20",
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


def _mock_repo(mock_repo_class, pedido: dict):
    mock_repo_class.return_value.get_pedido_completo.return_value = pedido
    # El hijo nunca tiene registro de ESTADO_REDISTRIBUCION en la bitácora.
    mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None


def _mock_distribucion(mock_dist_class, cantidad: float = 1):
    """Mockea DistribucionConfirmadaRepository devolviendo la misma cantidad que
    la fixture ya tenía en tienda["cantidad"], para no cambiar la intención de
    estos tests (verifican fecha del pedido hijo, no cantidad)."""
    mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {
        PEDIDO_DETALLE_ID: {TIENDA_ID: cantidad}
    }


def test_hijo_usa_su_propia_fecha_pedido_y_entrega():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_repo(mock_repo_class, _pedido_hijo())
        _mock_distribucion(mock_dist_class)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="hijo-uuid",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    fecha_pedido, fecha_entrega = _columnas_fecha(resultado)
    assert fecha_pedido == "15/03/2026"
    assert fecha_entrega == "20/03/2026"


def test_hijo_usa_su_propia_fecha_tambien_en_modo_consolidado():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_repo(mock_repo_class, _pedido_hijo())
        _mock_distribucion(mock_dist_class)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="hijo-uuid",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    fecha_pedido, fecha_entrega = _columnas_fecha(resultado)
    assert fecha_pedido == "15/03/2026"
    assert fecha_entrega == "20/03/2026"


def test_padre_sin_pedido_padre_id_sigue_usando_fecha_confirmacion():
    """Un pedido normal (o padre) no tiene pedido_padre_id -- debe seguir usando
    fecha_confirmacion de la bitácora, aunque su propia fecha_pedido/fecha_entrega
    de cabecera diga otra cosa (comportamiento histórico, sin cambios)."""
    from datetime import datetime

    pedido = _pedido_hijo()
    pedido["cabecera"]["pedido_padre_id"] = None

    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = datetime(2026, 5, 1)
        _mock_distribucion(mock_dist_class)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="padre-uuid",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    fecha_pedido, fecha_entrega = _columnas_fecha(resultado)
    assert fecha_pedido == "01/05/2026"
    assert fecha_entrega == "01/05/2026"
