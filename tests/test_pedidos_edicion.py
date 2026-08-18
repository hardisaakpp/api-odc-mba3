"""
Tests para src/endpoints/pedidos/pedidos_edicion.py: _resolver_rol_modificador.

Deriva el rol responsable de una edición de TOTAL/COMENTARIO a partir del
estado del pedido (no del permiso del usuario), para que el resaltado de
columnas modificadas en el frontend persista el color de quien editó.
"""

from src.endpoints.pedidos.pedidos_edicion import _resolver_rol_modificador
from src.database.pedido_estados import (
    ESTADO_GESTIONAR_PEDIDO,
    ESTADO_CONFIRMADO_POR_PRODUCCION,
    ESTADO_NUEVO_PEDIDO,
)


def test_resolver_rol_modificador_gestionar_pedido_es_produccion_elrayo():
    assert _resolver_rol_modificador(ESTADO_GESTIONAR_PEDIDO) == "PRODUCCION_ELRAYO"


def test_resolver_rol_modificador_confirmado_por_produccion_es_odcsap():
    assert _resolver_rol_modificador(ESTADO_CONFIRMADO_POR_PRODUCCION) == "ODCSAP"


def test_resolver_rol_modificador_otro_estado_es_none():
    assert _resolver_rol_modificador(ESTADO_NUEVO_PEDIDO) is None


def test_resolver_rol_modificador_none_es_none():
    assert _resolver_rol_modificador(None) is None
