"""
Tests para RedistribucionValidator._validar_tiendas_pertenecen_al_pedido.

Cubre el cambio que permite, solo en pedidos hijo (pedido_padre_id no nulo), redistribuir
hacia tiendas que no venían en el Excel original del pedido (catálogo maestro de tiendas).
"""

from src.database.services.redistribucion_validator import RedistribucionValidator


def _pedido_data(pedido_padre_id=None):
    return {
        "cabecera": {"pedido_padre_id": pedido_padre_id},
        "detalles": [
            {
                "pedido_detalle_id": "det-1",
                "tiendas": [{"tienda_id": "tienda-original"}],
            }
        ],
    }


def _producto(tienda_id: str):
    return [
        {
            "pedido_detalle_id": "det-1",
            "distribuciones": [{"tienda_id": tienda_id, "cantidad_asignada": 10}],
        }
    ]


class TestValidarTiendasPertenecenAlPedido:
    def test_pedido_padre_rechaza_tienda_ajena_al_pedido(self):
        """Regresión: en pedidos padre (sin pedido_padre_id) se mantiene el comportamiento actual."""
        errores = RedistribucionValidator._validar_tiendas_pertenecen_al_pedido(
            _pedido_data(pedido_padre_id=None),
            _producto("tienda-nueva"),
        )
        assert len(errores) == 1
        assert "no pertenece al pedido" in errores[0]

    def test_pedido_padre_acepta_tienda_que_ya_pertenecia(self):
        errores = RedistribucionValidator._validar_tiendas_pertenecen_al_pedido(
            _pedido_data(pedido_padre_id=None),
            _producto("tienda-original"),
        )
        assert errores == []

    def test_pedido_hijo_acepta_tienda_que_no_estaba_en_el_pedido(self):
        """Pedido hijo (pedido_padre_id no nulo): se permite una tienda nueva del catálogo maestro."""
        errores = RedistribucionValidator._validar_tiendas_pertenecen_al_pedido(
            _pedido_data(pedido_padre_id="padre-uuid"),
            _producto("tienda-nueva"),
        )
        assert errores == []

    def test_pedido_hijo_sigue_rechazando_producto_inexistente_en_el_pedido(self):
        """La excepción es solo sobre tiendas; el producto sigue debiendo existir en el pedido."""
        productos = [
            {
                "pedido_detalle_id": "det-inexistente",
                "distribuciones": [{"tienda_id": "tienda-nueva", "cantidad_asignada": 10}],
            }
        ]
        errores = RedistribucionValidator._validar_tiendas_pertenecen_al_pedido(
            _pedido_data(pedido_padre_id="padre-uuid"),
            productos,
        )
        assert len(errores) == 1
        assert "No existe en el pedido" in errores[0]
