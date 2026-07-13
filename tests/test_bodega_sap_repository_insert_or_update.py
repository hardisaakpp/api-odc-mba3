"""
Regresión: `insert_or_update` (bodega_sap_repository) agregó una rama
`if cursor.rowcount == 0: return False` en el UPDATE, ausente en `main`
(que siempre retornaba `True` en éxito). Esto sí tiene un caller activo:
`insert_or_update_batch` cuenta `updated_count` a partir de este valor de
retorno, así que un `rowcount == 0` (ej. la fila fue desactivada entre el
`find_by_whs_code` y el `UPDATE ... WHERE activo=1`) hacía que el batch
subcontara silenciosamente bodegas ya procesadas sin error.
"""

from unittest.mock import MagicMock

from src.database.repositories.bodega_sap_repository import BodegaSAPRepository


def _repo_con_conn_mock():
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return BodegaSAPRepository(conn)


def test_update_retorna_true_incluso_con_rowcount_cero():
    repo = _repo_con_conn_mock()
    repo.find_by_whs_code = MagicMock(return_value={"whs_code": "RL-CD"})
    repo.conn.cursor.return_value.rowcount = 0

    resultado = repo.insert_or_update({"whs_code": "RL-CD", "whs_name": "ROLAND CD"})

    assert resultado is True


def test_insert_retorna_true():
    repo = _repo_con_conn_mock()
    repo.find_by_whs_code = MagicMock(return_value=None)

    resultado = repo.insert_or_update({"whs_code": "NUEVA-BODEGA", "whs_name": "Nueva"})

    assert resultado is True


def test_batch_no_subcuenta_cuando_rowcount_es_cero():
    repo = _repo_con_conn_mock()
    repo.find_by_whs_code = MagicMock(return_value={"whs_code": "RL-CD"})
    repo.conn.cursor.return_value.rowcount = 0

    updated_count = repo.insert_or_update_batch([{"whs_code": "RL-CD", "whs_name": "ROLAND CD"}])

    assert updated_count == 1
