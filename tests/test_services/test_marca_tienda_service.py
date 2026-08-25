"""
Tests para MarcaTiendaService: resolución de marca de tienda contra
sc_maestros.dbo.almacenes_local.

Nota clave (confirmada 20/08/2026 contra datos reales): en esa tabla whs_code
es el código del Centro de Distribución (RL-CD/RG-CD/OUT-CD), NO el código de
tienda del Excel — el código de tienda vive en u_bod_tra. La consulta debe
filtrar por u_bod_tra, no por whs_code.
"""

from unittest.mock import MagicMock, patch

from src.database.services.marca_tienda_service import MarcaTiendaService


def _mock_ctx(row):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = row
    mock_conn.cursor.return_value = mock_cursor
    ctx = patch("src.database.services.marca_tienda_service.get_maestros_db_connection_context")
    mock = ctx.start()
    mock.return_value.__enter__.return_value = mock_conn
    return ctx, mock_cursor


def test_buscar_marca_filtra_por_u_bod_tra_no_por_whs_code():
    ctx, mock_cursor = _mock_ctx(("ROLAND",))
    try:
        resultado = MarcaTiendaService().buscar_marca("TRL-QSN")
        assert resultado == "ROLAND"

        sql_ejecutado = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert "u_bod_tra" in sql_ejecutado
        assert "whs_code" not in sql_ejecutado
        assert params == ("TRL-QSN",)
    finally:
        ctx.stop()


def test_buscar_marca_sin_match_retorna_none():
    ctx, _ = _mock_ctx(None)
    try:
        assert MarcaTiendaService().buscar_marca("NO-EXISTE") is None
    finally:
        ctx.stop()


def test_buscar_marca_desconocida_retorna_none():
    ctx, _ = _mock_ctx(("MARCA-RARA",))
    try:
        assert MarcaTiendaService().buscar_marca("TRL-XXX") is None
    finally:
        ctx.stop()


def test_buscar_marca_codigo_vacio_no_consulta_bd():
    with patch("src.database.services.marca_tienda_service.get_maestros_db_connection_context") as mock:
        assert MarcaTiendaService().buscar_marca("") is None
        assert MarcaTiendaService().buscar_marca(None) is None
        mock.assert_not_called()


def test_buscar_marca_error_de_conexion_no_propaga():
    with patch("src.database.services.marca_tienda_service.get_maestros_db_connection_context") as mock:
        mock.side_effect = Exception("timeout")
        assert MarcaTiendaService().buscar_marca("TRL-QSN") is None
