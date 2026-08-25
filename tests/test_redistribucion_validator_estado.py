"""
Tests de RedistribucionValidator._validar_estado_pedido.

Bug real que corrige: un pedido "hijo" (generado por "Confirmar pedido, generar nuevo
pedido con la diferencia") que Mabel Trading acepta pasa directo a
LISTO_PARA_REDISTRIBUCION (25) sin pasar por CONFIRMADO_POR_EL_RAYO (4) -- así lo definió
el commit cb24f2f ("botón Aceptar/Rechazar sobre Producción Pospuesta con redistribución
completa"), y el flag `puede_confirmar_redistribucion` (pedidos_crud_helpers.py) ya
contempla ambos estados vía ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION. Pero este validador
seguía comparando contra el único estado ESTADO_REDISTRIBUCION (4), hardcodeado en vez de
usar el mismo set compartido -- así que "confirmar redistribución" para un pedido hijo en
estado 25 siempre fallaba con "Solo se permite en estado CONFIRMADO POR EL RAYO", pese a
que el botón "Enviar ODC a SAP" se mostraba habilitado.
"""

from src.database.services.redistribucion_validator import RedistribucionValidator


def _pedido_con_estado(estado_id):
    return {"cabecera": {"estado_id": estado_id, "estado_nombre": f"estado-{estado_id}"}}


class TestValidarEstadoPedido:
    def test_estado_confirmado_por_el_rayo_es_valido(self):
        errores = RedistribucionValidator._validar_estado_pedido(_pedido_con_estado(4))
        assert errores == []

    def test_pedido_hijo_en_listo_para_redistribucion_es_valido(self):
        errores = RedistribucionValidator._validar_estado_pedido(_pedido_con_estado(25))
        assert errores == []

    def test_estado_no_habilitado_retorna_error(self):
        errores = RedistribucionValidator._validar_estado_pedido(_pedido_con_estado(3))
        assert len(errores) == 1
        assert "no permite confirmar redistribución" in errores[0]

    def test_estado_none_usa_fallback_legacy(self):
        pedido = {"cabecera": {"estado_id": None, "estado": "CONFIRMADO POR EL RAYO"}}
        errores = RedistribucionValidator._validar_estado_pedido(pedido)
        assert errores == []
