"""Tests unitarios para helpers de redistribución."""

from typing import Any, Dict, Optional

import pytest
from fastapi import HTTPException

from src.database.pedido_estados import ESTADO_LIMITE_CANCELAR_PEDIDO
from src.models import AjusteDetalle, DistribucionTiendaFrontend
from src.endpoints.pedidos.redistribucion._helpers import (
    calcular_estado_puede_descartar,
    enriquecer_productos_con_pedido,
    obtener_pedido_o_404,
    obtener_respuestas_proveedor,
)
from src.endpoints.pedidos.redistribucion._converters import (
    construir_distribucion_proporcional,
    convertir_ajustes_a_redistribucion,
)
from src.endpoints.pedidos.redistribucion._resumen import calcular_resumen_confirmacion
from src.endpoints.pedidos.redistribucion._excel_generators import (
    generar_excel_reporte_diferencias,
)


class FakeRepoPedido:
    def __init__(self, pedido_data: Dict[str, Any], respuestas: Optional[Dict[str, Dict[str, Any]]] = None):
        self._pedido_data = pedido_data
        self._respuestas = respuestas or {}

    def get_pedido_completo(self, pedido_id: str):
        return self._pedido_data

    def get_pedido_completo_por_numero(self, numero: str):
        return self._pedido_data

    def get_respuestas_proveedor(self, _pedido_id: str, *, top_one: bool = False):
        return self._respuestas


class FakeTiendaRepo:
    def __init__(self, tienda_map: Optional[Dict[str, str]] = None):
        self._tienda_map = tienda_map or {}

    def get_tienda_id_by_codigo(self, codigo: str):
        return self._tienda_map.get(codigo)


def test_obtener_pedido_o_404_uuid():
    pedido_data = {"cabecera": {"pedido_id": "uuid-1"}}
    repo = FakeRepoPedido(pedido_data)
    assert obtener_pedido_o_404(repo, "uuid-1") == pedido_data


def test_obtener_pedido_o_404_numero():
    pedido_data = {"cabecera": {"pedido_id": "uuid-2"}}
    repo = FakeRepoPedido(pedido_data)
    assert obtener_pedido_o_404(repo, "P-100", es_numero=True) == pedido_data


def test_obtener_pedido_o_404_not_found():
    class EmptyRepo:
        def get_pedido_completo(self, _pedido_id: str):
            return None

    with pytest.raises(HTTPException):
        obtener_pedido_o_404(EmptyRepo(), "uuid-x")


def test_obtener_respuestas_proveedor():
    respuestas_map = {
        "det-1": {"cantidad_solicitada_total": 10, "cantidad_confirmada_total": 8},
        "det-2": {"cantidad_solicitada_total": 20, "cantidad_confirmada_total": 18},
    }
    repo = FakeRepoPedido({"cabecera": {}}, respuestas=respuestas_map)
    respuestas = obtener_respuestas_proveedor(repo, "pedido-1")
    assert respuestas["det-1"]["cantidad_solicitada_total"] == 10
    assert respuestas["det-2"]["cantidad_confirmada_total"] == 18


def test_enriquecer_productos_con_pedido():
    distribucion = [{"pedido_detalle_id": "d1", "cantidad_asignada_total": 5}]
    detalles = [{"pedido_detalle_id": "d1", "codigo_interno": "C1", "descripcion_sap": "Desc"}]
    result = enriquecer_productos_con_pedido(distribucion, detalles)
    assert result[0]["codigo_interno"] == "C1"
    assert result[0]["descripcion_sap"] == "Desc"


def test_calcular_estado_puede_descartar():
    cabecera = {"estado_id": ESTADO_LIMITE_CANCELAR_PEDIDO - 1}
    assert calcular_estado_puede_descartar(cabecera) is True
    cabecera = {"estado_id": ESTADO_LIMITE_CANCELAR_PEDIDO}
    assert calcular_estado_puede_descartar(cabecera) is False


def test_construir_distribucion_proporcional():
    tiendas = [
        {"codigo": "T1", "nombre": "Tienda 1", "cantidad": 60, "es_bodega": False},
        {"codigo": "T2", "nombre": "Tienda 2", "cantidad": 40, "es_bodega": True},
    ]
    result = construir_distribucion_proporcional(tiendas, cantidad_confirmada=50, cantidad_total_original=100)
    assert sum(t.cantidad for t in result) == 50
    assert result[0].tienda_codigo == "T1"


def test_convertir_ajustes_a_redistribucion():
    pedido_data = {
        "detalles": [
            {
                "pedido_detalle_id": "det-1",
                "codigo_interno": "C1",
                "costo_doc_sin_iva": 10,
                "total": 5,
            }
        ]
    }
    ajustes = [
        AjusteDetalle(
            codigo_producto="C1",
            descripcion="Prod",
            cantidad_solicitada=10,
            cantidad_confirmada=5,
            cantidad_ajustada=5,
            distribucion_tiendas=[
                DistribucionTiendaFrontend(tienda_codigo="T1", tienda_nombre="Tienda 1", cantidad=5)
            ],
            costo_original=1,
            costo_ajustado=1,
            cambio_precio=False,
            pedido_detalle_id=None,
        )
    ]
    tienda_repo = FakeTiendaRepo(tienda_map={"T1": "uuid-t1"})
    productos = convertir_ajustes_a_redistribucion(ajustes, pedido_data, tienda_repo)
    assert productos[0]["pedido_detalle_id"] == "det-1"
    assert productos[0]["distribuciones"][0]["tienda_id"] == "uuid-t1"


def test_calcular_resumen_confirmacion():
    ajustes = [
        AjusteDetalle(
            codigo_producto="C1",
            descripcion="Prod",
            cantidad_solicitada=10,
            cantidad_confirmada=8,
            cantidad_ajustada=7,
            distribucion_tiendas=[
                DistribucionTiendaFrontend(
                    tienda_codigo="T1",
                    tienda_nombre="Tienda 1",
                    cantidad=7,
                )
            ],
            costo_original=2,
            costo_ajustado=2,
            cambio_precio=False,
            pedido_detalle_id=None,
        )
    ]
    resumen = calcular_resumen_confirmacion(ajustes)
    assert resumen.total_productos == 1
    assert resumen.total_cantidad_ajustada == 7
    assert resumen.diferencia_cantidad == -1


def test_generar_excel_reporte_diferencias():
    diferencias = {
        "total_productos": 1,
        "total_cantidad_solicitada": 10,
        "total_cantidad_confirmada": 8,
        "total_cantidad_asignada": 7,
        "total_diferencia_cantidad": -1,
        "total_costo_original": 100,
        "total_costo_ajustado": 80,
        "total_diferencia_costo": -20,
        "diferencias_productos": [{"codigo": "C1"}],
        "diferencias_tiendas": [{"tienda": "T1"}],
    }
    output = generar_excel_reporte_diferencias(diferencias)
    assert output.getbuffer().nbytes > 0
