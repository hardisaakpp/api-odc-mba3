"""
Tests de SolicitudTransferenciaRepository.count_st_pendientes_reintento_por_oc_ids
(versión batched, una sola query en vez del N+1 anterior que delegaba a
get_st_pendiente_reintento_count por cada oc_id -- ver conversación 2026-09-11,
demora del footer de paginación en /proceso).

Debe devolver EXACTAMENTE el mismo conteo que la versión anterior (por oc_id):
- Tiendas en el último batch con estado Error/Encolada, menos las que ya tienen
  ITR OK (Creada + doc_entry) en cualquier batch.
- Si el último batch no tiene ninguna fila relacional (legacy), cae al fallback
  de resultado_json -- pero solo para esas OC, no para todas.
"""

from unittest.mock import MagicMock, patch

from src.database.repositories.solicitud_transferencia_repository import (
    SolicitudTransferenciaRepository,
)


def _mock_repo_con_filas(filas):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = filas
    conn.cursor.return_value = cursor
    return SolicitudTransferenciaRepository(conn), cursor


def test_lista_vacia_retorna_dict_vacio_sin_consultar():
    repo, cursor = _mock_repo_con_filas([])
    result = repo.count_st_pendientes_reintento_por_oc_ids([])
    assert result == {}
    cursor.execute.assert_not_called()


def test_una_sola_query_para_todas_las_oc_de_la_pagina():
    """La consulta principal es UNA sola, sin importar cuántas OC se pidan (batched,
    no N+1). Ambas OC ya tienen fila relacional en el mock -- ninguna dispara el
    fallback JSON aparte, así que esto aísla específicamente la query principal."""
    repo, cursor = _mock_repo_con_filas([
        ("oc-1", "T01", "Error", None),
        ("oc-2", "T02", "Creada", None),
    ])
    repo.count_st_pendientes_reintento_por_oc_ids(["oc-1", "oc-2"])
    assert cursor.execute.call_count == 1


def test_tienda_error_sin_itr_ok_cuenta_como_pendiente():
    repo, _ = _mock_repo_con_filas([
        ("oc-1", "T01", "Error", None),
        ("oc-1", "T02", "Encolada", None),
    ])
    result = repo.count_st_pendientes_reintento_por_oc_ids(["oc-1"])
    assert result == {"oc-1": 2}


def test_tienda_error_pero_con_itr_ok_no_cuenta():
    """La tienda quedó Error en el último batch, pero ya tiene ITR OK en un batch
    anterior (reintento manual ya resuelto por otra vía) -- no debe contar."""
    repo, _ = _mock_repo_con_filas([
        ("oc-1", "T01", "Error", "T01"),
    ])
    result = repo.count_st_pendientes_reintento_por_oc_ids(["oc-1"])
    assert result == {"oc-1": 0}


def test_solo_creada_en_ultimo_batch_no_cuenta_y_no_llama_fallback():
    """Último batch totalmente exitoso: 0 pendientes, y NO debe llamar al fallback
    JSON (a diferencia de la versión anterior, que lo llamaba siempre que el
    resultado relacional daba vacío, sin importar el motivo)."""
    repo, _ = _mock_repo_con_filas([
        ("oc-1", "T01", "Creada", None),
    ])
    with patch.object(repo, "get_tiendas_fallidas_desde_resultado_json_fallback") as mock_fallback:
        result = repo.count_st_pendientes_reintento_por_oc_ids(["oc-1"])
    assert result == {"oc-1": 0}
    mock_fallback.assert_not_called()


def test_oc_sin_ninguna_fila_relacional_usa_fallback_json():
    """OC legacy: el último batch no tiene ninguna fila en solicitud_transferencia_detalle
    -- debe recurrir al fallback JSON, igual que la versión por oc_id."""
    repo, _ = _mock_repo_con_filas([])
    with patch.object(
        repo, "get_tiendas_fallidas_desde_resultado_json_fallback", return_value=["T05", "T06"]
    ) as mock_fallback:
        result = repo.count_st_pendientes_reintento_por_oc_ids(["oc-legacy"])
    mock_fallback.assert_called_once_with("oc-legacy")
    assert result == {"oc-legacy": 2}


def test_mezcla_de_oc_con_y_sin_datos_relacionales_en_una_sola_pasada():
    """oc-1 tiene datos relacionales (pendiente real); oc-2 también tiene datos
    relacionales pero sin pendientes; oc-3 es legacy (fallback). El fallback solo
    se invoca para oc-3."""
    repo, _ = _mock_repo_con_filas([
        ("oc-1", "T01", "Error", None),
        ("oc-2", "T02", "Creada", None),
    ])
    with patch.object(
        repo, "get_tiendas_fallidas_desde_resultado_json_fallback", return_value=["T09"]
    ) as mock_fallback:
        result = repo.count_st_pendientes_reintento_por_oc_ids(["oc-1", "oc-2", "oc-3"])

    assert result == {"oc-1": 1, "oc-2": 0, "oc-3": 1}
    mock_fallback.assert_called_once_with("oc-3")


def test_deduplica_tienda_repetida_en_la_misma_oc():
    """Si la query devuelve la misma tienda dos veces para la misma OC (no debería
    pasar por el modelo de datos, pero por las dudas), no debe contarse doble."""
    repo, _ = _mock_repo_con_filas([
        ("oc-1", "T01", "Error", None),
        ("oc-1", " t01 ", "Error", None),
    ])
    result = repo.count_st_pendientes_reintento_por_oc_ids(["oc-1"])
    assert result == {"oc-1": 1}


def test_error_de_sql_retorna_ceros_para_todas_las_oc_pedidas():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("tabla no existe")
    conn.cursor.return_value = cursor
    repo = SolicitudTransferenciaRepository(conn)

    result = repo.count_st_pendientes_reintento_por_oc_ids(["oc-1", "oc-2"])

    assert result == {"oc-1": 0, "oc-2": 0}


def test_params_incluyen_la_lista_de_oc_ids_dos_veces():
    """La query usa oc_id IN (...) dos veces (latest y ok_tiendas) -- los params
    deben llevar la lista duplicada, en ese orden. Ambas OC tienen fila relacional
    en el mock para que ninguna dispare el fallback JSON aparte (que reusaría el
    mismo cursor y confundiría qué llamada es cuál)."""
    repo, cursor = _mock_repo_con_filas([
        ("oc-1", "T01", "Creada", None),
        ("oc-2", "T02", "Creada", None),
    ])
    repo.count_st_pendientes_reintento_por_oc_ids(["oc-1", "oc-2"])
    params = cursor.execute.call_args.args[1]
    assert params == ["oc-1", "oc-2", "oc-1", "oc-2"]
