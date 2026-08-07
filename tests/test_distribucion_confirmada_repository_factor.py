"""Tests de DistribucionConfirmadaRepository.crear_redistribucion.

Regresión del bug donde la query de respuestas del proveedor usaba
`SELECT TOP 1 ... ORDER BY rp.version DESC, rp.fecha_respuesta DESC` sin
`PARTITION BY pedido_detalle_id`, colapsando el resultado a una sola fila para
todo el pedido. Con eso, `_calcular_factor_proporcion` caía a su fallback 1.0
para casi todos los productos, escribiendo `cantidad_confirmada =
cantidad_solicitada` en vez de lo realmente confirmado por El Rayo (ver
memoria `bug_factor_confirmacion_select_top1`).
"""

from unittest.mock import MagicMock

from src.database.repositories.distribucion_confirmada_repository import (
    DistribucionConfirmadaRepository,
)


def _mock_conn(fetchone_values, fetchall_values):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.side_effect = fetchone_values
    cursor.fetchall.side_effect = fetchall_values
    conn.cursor.return_value = cursor
    return conn, cursor


def test_query_respuestas_proveedor_usa_row_number_particionado_por_producto():
    """La query de respuestas del proveedor debe rankear por producto, no colapsar a 1 fila global."""
    conn, cursor = _mock_conn(fetchone_values=[(0,), (1,)], fetchall_values=[[], []])
    repo = DistribucionConfirmadaRepository(conn)

    repo.crear_redistribucion(pedido_id="pedido-1", productos_redistribucion=[])

    sql_respuestas = cursor.execute.call_args_list[1].args[0]
    assert "PARTITION BY rpd.pedido_detalle_id" in sql_respuestas
    assert "ROW_NUMBER()" in sql_respuestas
    assert "TOP 1" not in sql_respuestas


def test_cada_producto_recibe_su_propia_cantidad_confirmada():
    """Cada producto usa su propia respuesta del proveedor, no la de otro producto
    del mismo pedido (antes: factor 1.0 fallback para todos menos uno)."""
    det_a, det_b = "det-a", "det-b"
    tienda_a, tienda_b = "tienda-a", "tienda-b"

    respuestas_rows = [
        (det_a, 7, 10),  # El Rayo confirmó MÁS de lo solicitado
        (det_b, 7, 5),   # El Rayo confirmó MENOS de lo solicitado
    ]
    distribuciones_originales_rows = [
        (det_a, tienda_a, 7, 2.0, 0),
        (det_b, tienda_b, 7, 2.0, 0),
    ]
    conn, cursor = _mock_conn(
        fetchone_values=[(0,), (1,)],
        fetchall_values=[respuestas_rows, distribuciones_originales_rows],
    )
    repo = DistribucionConfirmadaRepository(conn)

    productos_redistribucion = [
        {"pedido_detalle_id": det_a, "distribuciones": [{"tienda_id": tienda_a, "cantidad_asignada": 7}]},
        {"pedido_detalle_id": det_b, "distribuciones": [{"tienda_id": tienda_b, "cantidad_asignada": 7}]},
    ]

    repo.crear_redistribucion(pedido_id="pedido-1", productos_redistribucion=productos_redistribucion)

    inserts = [
        call for call in cursor.execute.call_args_list
        if "INSERT INTO distribucion_confirmada" in call.args[0]
    ]
    assert len(inserts) == 2

    # Índice de parámetros del INSERT: 0=pedido_id, 1=pedido_detalle_id, 2=tienda_id,
    # 3=cantidad_solicitada, 4=cantidad_confirmada, 5=cantidad_asignada, ...
    confirmada_por_detalle = {call.args[1][1]: call.args[1][4] for call in inserts}

    assert confirmada_por_detalle[det_a] == 10.0
    assert confirmada_por_detalle[det_b] == 5.0
