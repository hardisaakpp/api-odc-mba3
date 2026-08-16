"""
Tests para PedidoCabeceraRepository._filtro_redistribucion.

CONFIRMADO_POR_PRODUCCION (23) y PRODUCCION_POSPUESTA (22) ocurren ANTES de
REDISTRIBUCION (4) en el flujo real (entre GESTIONAR_PEDIDO y CONFIRMADO POR EL
RAYO), pero tienen estado_id numéricamente mayor a 4 porque se agregaron después
al catálogo. El filtro de la vista /redistribucion debe excluirlos explícitamente
o el simple "estado_id >= 4" los deja pasar por error.
"""

from unittest.mock import MagicMock

from src.database.pedido_estados import (
    ESTADO_REDISTRIBUCION,
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADO_FINALIZADO,
    ESTADO_CANCELADO,
    ESTADO_CANCELADO_POR_EL_RAYO,
    ESTADO_CONFIRMADO_POR_PRODUCCION,
    ESTADO_PRODUCCION_POSPUESTA,
)
from src.database.repositories.pedido.pedido_cabecera_repository import PedidoCabeceraRepository


def _repository():
    return PedidoCabeceraRepository(MagicMock())


def test_excluye_confirmado_por_produccion_y_produccion_pospuesta_con_estado_id():
    conditions, params = _repository()._filtro_redistribucion(tiene_estado_id=True)

    assert conditions == ["p.estado_id >= ?", "p.estado_id NOT IN (?, ?, ?, ?, ?, ?)"]
    assert params[0] == ESTADO_REDISTRIBUCION
    excluidos = params[1:]
    assert set(excluidos) == {
        ESTADO_DESPACHAR_Y_FACTURAR,
        ESTADO_FINALIZADO,
        ESTADO_CANCELADO,
        ESTADO_CANCELADO_POR_EL_RAYO,
        ESTADO_CONFIRMADO_POR_PRODUCCION,
        ESTADO_PRODUCCION_POSPUESTA,
    }
    # 1 placeholder para ">= ?" + 6 para "NOT IN (...)" deben calzar con params.
    placeholders_totales = conditions[0].count("?") + conditions[1].count("?")
    assert placeholders_totales == len(params)


def test_excluye_confirmado_por_produccion_y_produccion_pospuesta_fallback_legacy():
    conditions, params = _repository()._filtro_redistribucion(tiene_estado_id=False)

    assert params == []
    (clause,) = conditions
    assert "CONFIRMADO POR PRODUCCION" in clause
    assert "CONFIRMADO_POR_PRODUCCION" in clause
    assert "PRODUCCION POSPUESTA" in clause
    assert "PRODUCCION_POSPUESTA" in clause
