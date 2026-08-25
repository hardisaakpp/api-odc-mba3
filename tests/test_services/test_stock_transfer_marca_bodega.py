"""
Tests para la resolución de bodega/CD de una tienda con respaldo en tienda.marca
(sincronizada desde sc_maestros) y fallback al heurístico de prefijo de código.

Requerimiento PYTD002: base para detectar cuándo un pedido mezcla tiendas ROLAND
y REGIONS (StockTransferService.detectar_origenes_traslado).
"""

from unittest.mock import MagicMock, patch

from src.database.services.stock_transfer_service import StockTransferService


def _mock_conn_con_marca(marca):
    """Simula get_db_connection_context() cuyo cursor.fetchone() retorna (marca,) o None."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (marca,) if marca is not None else None
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn


def _patch_ctx(marca):
    mock_ctx = patch("src.database.services.stock_transfer_service.get_db_connection_context")
    mock = mock_ctx.start()
    mock.return_value.__enter__.return_value = _mock_conn_con_marca(marca)
    return mock_ctx


def test_obtener_bodega_prioriza_marca_de_bd_sobre_prefijo():
    """Un código con prefijo TRL- (heurístico → RL-CD) pero marca=REGIONS en BD debe resolver a RG-CD."""
    ctx = _patch_ctx("REGIONS")
    try:
        assert StockTransferService.obtener_bodega_de_tienda("TRL-QSN") == "RG-CD"
    finally:
        ctx.stop()


def test_obtener_bodega_cae_a_prefijo_si_no_hay_marca_en_bd():
    """Si tienda.marca es NULL (tienda aún no sincronizada), se mantiene el heurístico actual."""
    ctx = _patch_ctx(None)
    try:
        assert StockTransferService.obtener_bodega_de_tienda("TRL-QSN") == "RL-CD"
        assert StockTransferService.obtener_bodega_de_tienda("TOUT-BMB") == "OUT-CD"
        assert StockTransferService.obtener_bodega_de_tienda("RG-INT") == "RG-CD"
        assert StockTransferService.obtener_bodega_de_tienda("SIN-PATRON") is None
    finally:
        ctx.stop()


def test_obtener_bodega_codigo_vacio_retorna_none():
    assert StockTransferService.obtener_bodega_de_tienda("") is None
    assert StockTransferService.obtener_bodega_de_tienda(None) is None


def _detalle(tiendas):
    return {"tiendas": tiendas}


def test_detectar_origenes_traslado_una_sola_marca():
    ctx = _patch_ctx(None)  # sin marca en BD → heurístico de prefijo
    try:
        detalles = [
            _detalle([
                {"codigo": "TRL-QSN", "es_bodega": False},
                {"codigo": "TRL-SMA", "es_bodega": False},
            ])
        ]
        assert StockTransferService.detectar_origenes_traslado(detalles) == ["RL-CD"]
    finally:
        ctx.stop()


def test_detectar_origenes_traslado_pedido_mixto_roland_regions():
    """Simula tienda.marca resuelto por código: TRL-QSN→ROLAND, RG-INT→REGIONS."""
    mock_ctx = patch("src.database.services.stock_transfer_service.get_db_connection_context")
    mock = mock_ctx.start()

    def fake_context_manager():
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        def fake_execute(sql, params):
            codigo = params[0]
            marca = {"TRL-QSN": "ROLAND", "RG-INT": "REGIONS"}.get(codigo)
            mock_cursor.fetchone.return_value = (marca,) if marca else None

        mock_cursor.execute.side_effect = fake_execute
        mock_conn.cursor.return_value = mock_cursor
        cm = MagicMock()
        cm.__enter__.return_value = mock_conn
        return cm

    mock.side_effect = lambda: fake_context_manager()
    try:
        detalles = [
            _detalle([
                {"codigo": "TRL-QSN", "es_bodega": False},
                {"codigo": "RG-INT", "es_bodega": False},
            ])
        ]
        assert StockTransferService.detectar_origenes_traslado(detalles) == ["RG-CD", "RL-CD"]
    finally:
        mock_ctx.stop()


def test_detectar_origenes_traslado_excluye_filas_de_bodega():
    ctx = _patch_ctx(None)
    try:
        detalles = [
            _detalle([
                {"codigo": "TRL-QSN", "es_bodega": False},
                {"codigo": "RL-CD", "es_bodega": True},
            ])
        ]
        assert StockTransferService.detectar_origenes_traslado(detalles) == ["RL-CD"]
    finally:
        ctx.stop()


def test_detectar_origenes_traslado_sin_tiendas_retorna_lista_vacia():
    assert StockTransferService.detectar_origenes_traslado([]) == []
    assert StockTransferService.detectar_origenes_traslado([_detalle([])]) == []
