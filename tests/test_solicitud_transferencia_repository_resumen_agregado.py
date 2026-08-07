"""
Tests de SolicitudTransferenciaRepository.get_resumen_agregado_por_oc_id.

Bug: el modal "Integración con SAP Completada" seguía mostrando el resumen del
primer envío (ej. "2 de 6 creadas") aunque un reintento posterior ya hubiera
creado las ITR faltantes, porque el endpoint dependía de un snapshot congelado
en envio_odc_sap en vez de agregar todos los batches de ST por oc_id.

Usa un cursor mockeado (mismo patrón que el resto de tests de repositorios en
este proyecto) ya que el método ejecuta SQL directo contra SQL Server. La
dedup por tienda (ROW_NUMBER/PARTITION BY, con prioridad a la fila 'Creada' de
cualquier batch) ocurre en el SQL real; aquí se asume que el cursor ya devuelve
una fila por tienda (post rn=1), y se verifica la agregación en Python sobre
esas filas.
"""

from unittest.mock import MagicMock

from src.database.repositories.solicitud_transferencia_repository import (
    SolicitudTransferenciaRepository,
)


def test_oc_id_vacio_no_consulta_bd():
    conn = MagicMock()
    repo = SolicitudTransferenciaRepository(conn)

    result = repo.get_resumen_agregado_por_oc_id("")

    assert result == {
        "total_tiendas": 0,
        "transferencias_creadas": 0,
        "transferencias_errores": 0,
        "resultados": [],
        "itrs_por_tienda": [],
    }
    conn.cursor.assert_not_called()


def test_agrega_creadas_y_errores_de_todos_los_batches():
    """
    Simula el escenario del bug: 2 tiendas creadas en el envío original, y las
    otras 4 aparecen ya 'Creada' porque un reintento posterior tuvo éxito.
    """
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        ("TRL-RGAI", "Tienda Rayo", 70215121, 111, "Creada", None),
        ("TRL-SMA", "Tienda SM", 70215122, 112, "Creada", None),
        ("TRL-A", "Tienda A", 70215999, 113, "Creada", None),
        ("TRL-B", "Tienda B", 70216000, 114, "Creada", None),
        ("TRL-C", "Tienda C", 70216001, 115, "Creada", None),
        ("TRL-D", "Tienda D", 70216002, 116, "Creada", None),
    ]
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_resumen_agregado_por_oc_id("oc-1")

    assert result["total_tiendas"] == 6
    assert result["transferencias_creadas"] == 6
    assert result["transferencias_errores"] == 0
    assert len(result["itrs_por_tienda"]) == 6
    assert {"doc_num": 70215121, "tienda_codigo": "TRL-RGAI"} in result["itrs_por_tienda"]


def test_tienda_sin_exito_en_ningun_batch_queda_como_error():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        ("TRL-RGAI", "Tienda Rayo", 70215121, 111, "Creada", None),
        ("TRL-X", "Tienda X", None, None, "Error", "Stock insuficiente"),
    ]
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_resumen_agregado_por_oc_id("oc-1")

    assert result["total_tiendas"] == 2
    assert result["transferencias_creadas"] == 1
    assert result["transferencias_errores"] == 1
    assert result["itrs_por_tienda"] == [{"doc_num": 70215121, "tienda_codigo": "TRL-RGAI"}]
    fila_error = next(r for r in result["resultados"] if r["tienda_codigo"] == "TRL-X")
    assert fila_error["success"] is False
    assert fila_error["error"] == "Stock insuficiente"


def test_creada_sin_doc_entry_no_cuenta_como_exito():
    """Salvaguarda: 'Creada' sin doc_entry (dato inconsistente) no debe sumar como éxito."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        ("TRL-RGAI", "Tienda Rayo", 70215121, None, "Creada", None),
    ]
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_resumen_agregado_por_oc_id("oc-1")

    assert result["transferencias_creadas"] == 0
    assert result["transferencias_errores"] == 1
    assert result["itrs_por_tienda"] == []


def test_sin_filas_retorna_resumen_vacio():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_resumen_agregado_por_oc_id("oc-sin-st")

    assert result["total_tiendas"] == 0
    assert result["resultados"] == []
    assert result["itrs_por_tienda"] == []


def test_error_de_sql_retorna_resumen_vacio():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("tabla no existe")
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_resumen_agregado_por_oc_id("oc-1")

    assert result == {
        "total_tiendas": 0,
        "transferencias_creadas": 0,
        "transferencias_errores": 0,
        "resultados": [],
        "itrs_por_tienda": [],
    }
