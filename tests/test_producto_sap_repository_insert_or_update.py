"""
Regresión: `insert_or_update` cambió su contrato en la rama UPDATE, retornando
`False` en vez de `True` (la rama INSERT seguía en `True`). El contrato
original en `main` era "True si se insertó/actualizó correctamente" -- ambas
ramas devuelven True en éxito.
"""

from unittest.mock import MagicMock

from src.database.repositories.producto_sap_repository import ProductoSAPRepository


def _repo_con_conn_mock():
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return ProductoSAPRepository(conn)


def test_update_retorna_true():
    repo = _repo_con_conn_mock()
    repo.find_by_sku = MagicMock(return_value={"sku": "SKU1"})

    resultado = repo.insert_or_update({"sku": "SKU1", "item_code": "IC1"})

    assert resultado is True


def test_insert_retorna_true():
    repo = _repo_con_conn_mock()
    repo.find_by_sku = MagicMock(return_value=None)

    resultado = repo.insert_or_update({"sku": "SKU-NUEVO", "item_code": "IC2"})

    assert resultado is True
