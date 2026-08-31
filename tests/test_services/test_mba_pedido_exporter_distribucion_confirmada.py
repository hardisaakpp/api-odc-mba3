"""
Tests para el bug de datos real corregido en el exportador TXT MBA3: "Cantidad
Pedido" (col. 22 en modo por-tienda; la cantidad consolidada en modo
consolidado) debe reflejar la cantidad FINAL asignada por tienda tras la
redistribución de MABEL TRADING (distribucion_confirmada.cantidad_asignada,
versión más alta), no el snapshot ORIGINAL del Excel cargado
(pedido_detalle_tienda.cantidad, que nunca se actualiza cuando el pedido se
edita o se redistribuye después).

Un producto+tienda que existía en el Excel original pero no tiene fila en
distribucion_confirmada para la versión más alta (nunca se le asignó nada en la
redistribución) se omite del TXT por completo -- no se exporta con cantidad 0.

Ver DistribucionConfirmadaRepository.get_cantidades_asignadas_por_pedido y
MBAPedidoExporter._resolver_cantidad_asignada.
"""

from unittest.mock import MagicMock, patch

from src.database.repositories.distribucion_confirmada_repository import (
    DistribucionConfirmadaRepository,
)
from src.database.services.mba_pedido_exporter import MBAExportConfig, MBAPedidoExporter


def _lineas_detalle(txt_bytes: bytes) -> list:
    return [linea for linea in txt_bytes.decode("utf-8").split("\n") if linea]


def _cabecera(**overrides) -> dict:
    base = {
        "numero_pedido": "PED-1",
        "fecha_pedido": None,
        "fecha_entrega": None,
        "origen_traslado": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Cantidad Pedido usa cantidad_asignada, NO pedido_detalle_tienda.cantidad
# ---------------------------------------------------------------------------

def _pedido_cantidad_distinta() -> dict:
    """El snapshot original (tienda["cantidad"]=999) y la cantidad asignada en la
    redistribución (42, mockeada aparte) son deliberadamente distintos: el test
    debe fallar si el exportador vuelve a leer el valor viejo."""
    return {
        "cabecera": _cabecera(),
        "detalles": [
            {
                "pedido_detalle_id": "detalle-1",
                "codigo_interno": "COD-1",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [{"tienda_id": "tienda-1", "codigo": "TRL-001", "cantidad": 999}],
            }
        ],
    }


def test_cantidad_pedido_usa_cantidad_asignada_no_snapshot_original():
    pedido = _pedido_cantidad_distinta()
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
        mock_oc_class.return_value.get_doc_num_by_pedido_id.return_value = None
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {
            "detalle-1": {"tienda-1": 42}
        }

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="pedido-1", config=MBAExportConfig(), incluir_encabezado=False,
        )

    lineas = _lineas_detalle(resultado)
    assert len(lineas) == 1
    assert lineas[0].split("\t")[21] == "42.0000"  # col 22: Cantidad Pedido


def test_cantidad_consolidada_usa_cantidad_asignada_no_snapshot_original():
    """Mismo bug, modo consolidado: la cantidad sumada debe salir de
    cantidad_asignada, no del snapshot original."""
    pedido = _pedido_cantidad_distinta()
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
        mock_oc_class.return_value.get_doc_num_by_pedido_id.return_value = None
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {
            "detalle-1": {"tienda-1": 42}
        }

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="pedido-1", config=MBAExportConfig(), incluir_encabezado=False,
        )

    lineas = _lineas_detalle(resultado)
    assert len(lineas) == 1
    assert lineas[0].split("\t")[21] == "42.0000"


# ---------------------------------------------------------------------------
# 2. Tienda sin fila en distribucion_confirmada se omite (modo por-tienda);
#    el resto del producto sí se exporta.
# ---------------------------------------------------------------------------

def _pedido_dos_tiendas_una_sin_asignar() -> dict:
    return {
        "cabecera": _cabecera(),
        "detalles": [
            {
                "pedido_detalle_id": "detalle-1",
                "codigo_interno": "COD-1",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [
                    {"tienda_id": "tienda-asignada", "codigo": "TRL-001", "cantidad": 5},
                    {"tienda_id": "tienda-sin-asignar", "codigo": "TRL-002", "cantidad": 7},
                ],
            }
        ],
    }


def test_tienda_sin_distribucion_confirmada_se_omite_pero_resto_del_producto_se_exporta():
    pedido = _pedido_dos_tiendas_una_sin_asignar()
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
        mock_oc_class.return_value.get_doc_num_by_pedido_id.return_value = None
        # Solo "tienda-asignada" tiene fila -- "tienda-sin-asignar" nunca recibió nada.
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {
            "detalle-1": {"tienda-asignada": 3}
        }

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="pedido-1", config=MBAExportConfig(), incluir_encabezado=False,
        )

    lineas = _lineas_detalle(resultado)
    assert len(lineas) == 1  # solo la tienda asignada genera línea
    cols = lineas[0].split("\t")
    assert cols[20] == "COD-1"
    assert cols[21] == "3.0000"


# ---------------------------------------------------------------------------
# 3. Producto sin NINGUNA tienda asignada se omite completo en consolidado.
# ---------------------------------------------------------------------------

def _pedido_dos_productos() -> dict:
    return {
        "cabecera": _cabecera(),
        "detalles": [
            {
                "pedido_detalle_id": "detalle-a",
                "codigo_interno": "COD-A",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [{"tienda_id": "tienda-1", "codigo": "TRL-001", "cantidad": 5}],
            },
            {
                "pedido_detalle_id": "detalle-b",
                "codigo_interno": "COD-B",
                "costo_doc_sin_iva": 20.0,
                "tiendas": [{"tienda_id": "tienda-2", "codigo": "TRL-002", "cantidad": 8}],
            },
        ],
    }


def test_producto_sin_ninguna_tienda_asignada_se_omite_completo_en_consolidado():
    pedido = _pedido_dos_productos()
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
        mock_oc_class.return_value.get_doc_num_by_pedido_id.return_value = None
        # detalle-b (COD-B) no tiene ninguna fila -- ninguna de sus tiendas fue asignada.
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {
            "detalle-a": {"tienda-1": 5}
        }

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="pedido-1", config=MBAExportConfig(), incluir_encabezado=False,
        )

    codigos = [linea.split("\t")[20] for linea in _lineas_detalle(resultado)]
    assert codigos == ["COD-A"]  # COD-B se omitió por completo


# ---------------------------------------------------------------------------
# 4. cantidad_asignada = 0 explícito (la fila SÍ existe) se exporta como "0",
#    no se omite -- distinto de "no existe la fila".
# ---------------------------------------------------------------------------

def test_cantidad_asignada_cero_explicita_se_exporta_no_se_omite():
    pedido = _pedido_cantidad_distinta()
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
        mock_oc_class.return_value.get_doc_num_by_pedido_id.return_value = None
        # La fila EXISTE, con cantidad_asignada=0 (distinto de que no exista la fila).
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {
            "detalle-1": {"tienda-1": 0}
        }

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="pedido-1", config=MBAExportConfig(), incluir_encabezado=False,
        )

    lineas = _lineas_detalle(resultado)
    assert len(lineas) == 1  # no se omite
    assert lineas[0].split("\t")[21] == "0.0000"


# ---------------------------------------------------------------------------
# 5. Se usa la versión MÁS ALTA cuando hay más de una `version` para el mismo
#    pedido_id (re-redistribución) -- mismo criterio que get_version_actual.
# ---------------------------------------------------------------------------

def _mock_conn(fetchone_values, fetchall_values):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.side_effect = fetchone_values
    cursor.fetchall.side_effect = fetchall_values
    conn.cursor.return_value = cursor
    return conn, cursor


def test_get_cantidades_asignadas_usa_la_version_mas_alta():
    """Con 2 versiones para el mismo pedido_id, debe traer las filas de la
    versión MÁS ALTA (MAX(version)), no filtrar por estado='CONFIRMADO' --
    pueden coexistir varias versiones con ese estado tras una re-redistribución."""
    conn, cursor = _mock_conn(
        fetchone_values=[(2,)],  # MAX(version) = 2 (hay una version 1 previa, ignorada)
        fetchall_values=[[("detalle-1", "tienda-1", 99)]],  # filas de la version 2 únicamente
    )
    repo = DistribucionConfirmadaRepository(conn)

    resultado = repo.get_cantidades_asignadas_por_pedido("pedido-1")

    assert resultado == {"detalle-1": {"tienda-1": 99.0}}
    calls = cursor.execute.call_args_list
    assert len(calls) == 2
    assert "MAX(version)" in calls[0].args[0]  # 1ra query: resuelve la versión más alta
    assert calls[1].args[1] == ("pedido-1", 2)  # 2da query: filas de esa version exacta


# ---------------------------------------------------------------------------
# 6. Funciona igual para un pedido "hijo" (mismo criterio, sin caso especial).
# ---------------------------------------------------------------------------

def test_funciona_igual_para_pedido_hijo_sin_caso_especial():
    pedido = _pedido_cantidad_distinta()
    pedido["cabecera"]["pedido_padre_id"] = "padre-uuid"
    pedido["cabecera"]["fecha_pedido"] = "2026-01-01"
    pedido["cabecera"]["fecha_entrega"] = "2026-01-02"

    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        # El hijo nunca transiciona por ESTADO_REDISTRIBUCION.
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
        mock_oc_class.return_value.get_doc_num_by_pedido_id.return_value = None
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {
            "detalle-1": {"tienda-1": 15}
        }

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="hijo-uuid", config=MBAExportConfig(), incluir_encabezado=False,
        )

    lineas = _lineas_detalle(resultado)
    assert len(lineas) == 1
    assert lineas[0].split("\t")[21] == "15.0000"


# ---------------------------------------------------------------------------
# 7. Compone correctamente con codigo_bodega: el filtro de bodega y el filtro
#    de distribución confirmada aplican juntos, sin interferir uno con otro.
# ---------------------------------------------------------------------------

BODEGA_POR_TIENDA = {
    "TRL-QSN": "RL-CD",
    "TRL-OUT": "RL-CD",
    "RG-INT": "RG-CD",
}


def _pedido_bodega_y_distribucion() -> dict:
    return {
        "cabecera": _cabecera(),
        "detalles": [
            {
                "pedido_detalle_id": "detalle-roland",
                "codigo_interno": "COD-ROLAND",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [
                    # Misma bodega (RL-CD): una asignada, otra sin fila en distribucion.
                    {"tienda_id": "tienda-trl-qsn", "codigo": "TRL-QSN", "cantidad": 5},
                    {"tienda_id": "tienda-trl-out", "codigo": "TRL-OUT", "cantidad": 9},
                ],
            },
            {
                "pedido_detalle_id": "detalle-regions",
                "codigo_interno": "COD-REGIONS",
                "costo_doc_sin_iva": 20.0,
                # Asignada en distribucion, pero de otra bodega (RG-CD) -- debe filtrarse
                # por bodega igual, sin que la distribución "la salve".
                "tiendas": [{"tienda_id": "tienda-rg-int", "codigo": "RG-INT", "cantidad": 7}],
            },
        ],
    }


def test_codigo_bodega_y_distribucion_confirmada_componen_sin_interferir():
    pedido = _pedido_bodega_y_distribucion()
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class, \
         patch("src.database.services.stock_transfer_service.StockTransferService") as mock_stock_service:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
        mock_stock_service.obtener_bodega_de_tienda.side_effect = lambda codigo: BODEGA_POR_TIENDA.get(codigo)
        mock_oc_class.return_value.get_doc_num_by_pedido_id_y_bodega.return_value = "DOCNUM-ROLAND"
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {
            "detalle-roland": {"tienda-trl-qsn": 5},  # TRL-OUT no tiene fila -- se omite aunque sea de esta bodega
            "detalle-regions": {"tienda-rg-int": 7},  # asignada, pero de otra bodega -- filtrada igual
        }

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="pedido-1", config=MBAExportConfig(), incluir_encabezado=False,
            codigo_bodega="RL-CD",
        )

    lineas = _lineas_detalle(resultado)
    # Solo TRL-QSN: TRL-OUT se omite por falta de distribución, RG-INT se filtra por bodega.
    assert len(lineas) == 1
    cols = lineas[0].split("\t")
    assert cols[20] == "COD-ROLAND"
    assert cols[21] == "5.0000"
    assert cols[11] == "DOCNUM-ROLAND"


# ---------------------------------------------------------------------------
# 8. Regresión: un producto sin NINGUNA tienda en pedido_detalle_tienda (lista
#    "tiendas" estructuralmente vacía) y SIN codigo_bodega no debe omitirse --
#    ese caso es anterior y ajeno a este fix (nunca hubo distribución que leer,
#    no "se le quitó todo en la redistribución"). Se exporta con cantidad "0",
#    igual que antes de este cambio.
# ---------------------------------------------------------------------------

def test_producto_sin_tiendas_estructural_sin_codigo_bodega_no_se_omite():
    pedido = {
        "cabecera": _cabecera(),
        "detalles": [
            {
                "pedido_detalle_id": "detalle-1",
                "codigo_interno": "COD-1",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [],
            }
        ],
    }
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
        mock_oc_class.return_value.get_doc_num_by_pedido_id.return_value = None
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = {}

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="pedido-1", config=MBAExportConfig(), incluir_encabezado=False,
        )

    lineas = _lineas_detalle(resultado)
    assert len(lineas) == 1
    cols = lineas[0].split("\t")
    assert cols[20] == "COD-1"
    assert cols[21] == "0.0000"
