"""
Tests para el cálculo del Margen de Rentabilidad en el backend (req. 1.5, SIS-PYTD-0002).

El cálculo vivía únicamente en el frontend (scnexus-front/utils/formatters.ts); se movió
a calcular_margen_rentabilidad (pedido_utils.py) para tener una sola fuente de verdad,
ya que los exportadores de Excel del backend también van a necesitar la fórmula. El
frontend ahora solo formatea el campo "margen" que llega en la respuesta.

El insumo de costo del margen es costo_unitario (costo_doc_sin_iva / unidad_conversion,
según el pack ya resuelto SAP/Excel), no costo_margen (columna "Costo" del Excel, que era
manual y desconectada de costo_doc_sin_iva/pack). costo_margen se mantiene en el detalle
solo como dato informativo, ya no alimenta el margen.
"""

from src.database.repositories.pedido.pedido_utils import (
    PedidoUtils,
    calcular_margen_rentabilidad,
)


class TestCalcularMargenRentabilidad:
    def test_formula_coincide_con_el_requerimiento(self):
        """Margen = 1 - (Costo unitario / (PVP / 1.15))."""
        margen = calcular_margen_rentabilidad(costo_unitario=3.2, pvp=6.99)
        assert margen == 1 - (3.2 / (6.99 / 1.15))

    def test_sin_costo_unitario_devuelve_none(self):
        assert calcular_margen_rentabilidad(costo_unitario=None, pvp=6.99) is None

    def test_pvp_none_devuelve_none(self):
        assert calcular_margen_rentabilidad(costo_unitario=3.2, pvp=None) is None

    def test_pvp_cero_devuelve_none(self):
        """PVP=0 división inválida, no debe reventar."""
        assert calcular_margen_rentabilidad(costo_unitario=3.2, pvp=0) is None

    def test_costo_cero_es_valido_da_margen_100_por_ciento(self):
        """Costo=0 es un valor legítimo (no ausente), a diferencia de PVP=0."""
        margen = calcular_margen_rentabilidad(costo_unitario=0, pvp=6.99)
        assert margen == 1.0

    def test_margen_negativo_cuando_el_costo_supera_al_pvp_sin_iva(self):
        margen = calcular_margen_rentabilidad(costo_unitario=18.3, pvp=3.99)
        assert margen is not None
        assert margen < 0


class TestConstruirDetalleDesdeRowIncluyeMargen:
    def _row(self, costo_margen, costo_unitario, pvp):
        # pedido_detalle_id, codigo_interno, descripcion_sap, marca, codigo_barras, pack,
        # costo_doc_sin_iva, descuento_1, pvp, subtotal, total, comentario,
        # costo_modificado_manual, total_modificado_manual, comentario_modificado_manual,
        # costo_margen, costo_unitario
        return (
            "abc-123", "SKU-1", "Producto Uno", "MARCA", "7501234567890", "X1",
            10.5, 0, pvp, 34.0, 35.0, "",
            0, 0, 0,
            costo_margen, costo_unitario,
        )

    def test_incluye_margen_calculado_con_costo_unitario_y_pvp_presentes(self):
        utils = PedidoUtils(conn=None)
        detalle = utils.construir_detalle_desde_row(
            self._row(costo_margen=3.2, costo_unitario=1.19, pvp=6.99),
            tiene_comentario=True,
            tiene_campos_modificados=True,
            tiendas_distribucion=[],
            tiene_costo_margen=True,
            tiene_costo_unitario=True,
        )
        assert detalle["costo_unitario"] == 1.19
        assert detalle["pvp"] == 6.99
        assert detalle["margen"] == calcular_margen_rentabilidad(1.19, 6.99)

    def test_costo_margen_es_informativo_y_no_afecta_el_margen(self):
        """costo_margen (columna "Costo" del Excel) queda expuesto pero no participa en la fórmula."""
        utils = PedidoUtils(conn=None)
        detalle = utils.construir_detalle_desde_row(
            self._row(costo_margen=99.0, costo_unitario=1.19, pvp=6.99),
            tiene_comentario=True,
            tiene_campos_modificados=True,
            tiendas_distribucion=[],
            tiene_costo_margen=True,
            tiene_costo_unitario=True,
        )
        assert detalle["costo_margen"] == 99.0
        assert detalle["margen"] == calcular_margen_rentabilidad(1.19, 6.99)

    def test_margen_none_si_bd_no_tiene_costo_unitario_aunque_tenga_costo_margen(self):
        """Ambiente a mitad de rollout (migración costo_margen aplicada, costo_unitario no): margen None."""
        utils = PedidoUtils(conn=None)
        fila_sin_costo_unitario = self._row(costo_margen=3.2, costo_unitario=None, pvp=6.99)[:16]
        detalle = utils.construir_detalle_desde_row(
            fila_sin_costo_unitario,
            tiene_comentario=True,
            tiene_campos_modificados=True,
            tiendas_distribucion=[],
            tiene_costo_margen=True,
            tiene_costo_unitario=False,
        )
        assert detalle["costo_margen"] == 3.2
        assert detalle["costo_unitario"] is None
        assert detalle["margen"] is None

    def test_margen_none_si_bd_antigua_no_tiene_ninguna_columna_nueva(self):
        """BD sin costo_margen ni costo_unitario (fallback en cascada): margen debe ser None, no reventar."""
        utils = PedidoUtils(conn=None)
        detalle = utils.construir_detalle_desde_row(
            self._row(costo_margen=None, costo_unitario=None, pvp=6.99)[:11],  # fila corta, sin campos opcionales
            tiene_comentario=False,
            tiene_campos_modificados=False,
            tiendas_distribucion=[],
            tiene_costo_margen=False,
            tiene_costo_unitario=False,
        )
        assert detalle["costo_margen"] is None
        assert detalle["costo_unitario"] is None
        assert detalle["margen"] is None
