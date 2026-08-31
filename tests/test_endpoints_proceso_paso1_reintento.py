"""
Regresión: el reintento de "Proceso completo SAP" (botón "Reintentar envío a SAP"
del modal de resultados parciales) re-ejecutaba PASO 1 (crear + confirmar
redistribución) sin importar que ya se hubiera confirmado en el intento anterior.
PASO 1 avanza el pedido a ESTADO_PEDIDO_CONFIRMADO, y si un paso posterior falla
el pedido queda en ESTADO_ERROR_ENVIO_SAP_REINTENTO -- ninguno de esos dos estados
está en ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION, así que
RedistribucionValidator._validar_estado_pedido rechazaba el reintento con "La
redistribución no cumple con las reglas de negocio", dejando el botón de
reintento permanentemente roto para cualquier pedido que fallara en PASO 2/3.
"""

from unittest.mock import MagicMock, patch

from src.database.pedido_estados import (
    ESTADO_ERROR_ENVIO_SAP_REINTENTO,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_REDISTRIBUCION,
)
from src.endpoints.pedidos.redistribucion.endpoints_proceso import _paso1_confirmar_redistribucion

_MODULO = "src.endpoints.pedidos.redistribucion.endpoints_proceso"


def _pedido_data(estado_id):
    return {"cabecera": {"pedido_id": "pedido-1", "estado_id": estado_id}, "detalles": []}


def test_reintento_con_redistribucion_ya_confirmada_no_repite_paso1():
    """estado_id=ERROR_ENVIO_SAP_REINTENTO (falló PASO 3 en el intento previo):
    no debe validar/crear/confirmar de nuevo, solo reutilizar la versión ya
    confirmada."""
    repo_pedido = MagicMock()
    repo_dist = MagicMock()
    repo_dist.get_version_actual.return_value = 3

    with patch(f"{_MODULO}.RedistribucionValidator") as mock_validator_cls, patch(
        f"{_MODULO}.convertir_ajustes_a_redistribucion"
    ) as mock_convertir, patch(
        f"{_MODULO}.procesar_pedido_sap_con_homologacion_sync",
        return_value={"productos_procesados": 0},
    ):
        resultado_redistribucion, resumen = _paso1_confirmar_redistribucion(
            conn=MagicMock(),
            repo_pedido=repo_pedido,
            repo_dist=repo_dist,
            pedido_id="pedido-1",
            ajustes_detalle=[],
            pedido_data=_pedido_data(ESTADO_ERROR_ENVIO_SAP_REINTENTO),
            user_id="user1",
            audit=MagicMock(),
        )

    mock_convertir.assert_not_called()
    mock_validator_cls.assert_not_called()
    repo_dist.crear_redistribucion.assert_not_called()
    repo_dist.confirmar_redistribucion.assert_not_called()
    repo_pedido.update_estado.assert_not_called()
    assert resultado_redistribucion["version_confirmada"] == 3
    assert resumen.total_productos == 0


def test_estado_pedido_confirmado_tambien_reutiliza_version():
    """estado_id=PEDIDO_CONFIRMADO (falló PASO 2, generar ODC, en el intento
    previo): mismo comportamiento que ERROR_ENVIO_SAP_REINTENTO."""
    repo_pedido = MagicMock()
    repo_dist = MagicMock()
    repo_dist.get_version_actual.return_value = 1

    with patch(f"{_MODULO}.RedistribucionValidator") as mock_validator_cls, patch(
        f"{_MODULO}.procesar_pedido_sap_con_homologacion_sync",
        return_value={"productos_procesados": 0},
    ):
        resultado_redistribucion, _ = _paso1_confirmar_redistribucion(
            conn=MagicMock(),
            repo_pedido=repo_pedido,
            repo_dist=repo_dist,
            pedido_id="pedido-1",
            ajustes_detalle=[],
            pedido_data=_pedido_data(ESTADO_PEDIDO_CONFIRMADO),
            user_id="user1",
            audit=MagicMock(),
        )

    mock_validator_cls.assert_not_called()
    repo_pedido.update_estado.assert_not_called()
    assert resultado_redistribucion["version_confirmada"] == 1


def test_sin_version_confirmada_previa_no_activa_el_atajo_de_reintento():
    """estado_id=PEDIDO_CONFIRMADO pero sin ninguna versión en
    distribucion_confirmada (estado inconsistente/defensivo): no debe activar el
    atajo de reintento -- debe seguir el camino normal de validación."""
    repo_pedido = MagicMock()
    repo_dist = MagicMock()
    repo_dist.get_version_actual.return_value = 0
    repo_dist.crear_redistribucion.return_value = {"version": 1}

    mock_validator = MagicMock()
    mock_validator.validar_redistribucion.return_value = (True, [])

    with patch(f"{_MODULO}.RedistribucionValidator", return_value=mock_validator), patch(
        f"{_MODULO}.convertir_ajustes_a_redistribucion", return_value=[]
    ) as mock_convertir, patch(
        f"{_MODULO}.obtener_respuestas_proveedor", return_value={}
    ), patch(
        f"{_MODULO}.procesar_pedido_sap_con_homologacion_sync",
        return_value={"productos_procesados": 0},
    ):
        _paso1_confirmar_redistribucion(
            conn=MagicMock(),
            repo_pedido=repo_pedido,
            repo_dist=repo_dist,
            pedido_id="pedido-1",
            ajustes_detalle=[],
            pedido_data=_pedido_data(ESTADO_PEDIDO_CONFIRMADO),
            user_id="user1",
            audit=MagicMock(),
        )

    mock_convertir.assert_called_once()
    repo_dist.crear_redistribucion.assert_called_once()


def test_primer_intento_normal_valida_y_confirma_como_antes():
    """estado_id=REDISTRIBUCION (primer intento, sin reintento previo): debe
    seguir corriendo la validación + creación + confirmación como antes del fix."""
    repo_pedido = MagicMock()
    repo_dist = MagicMock()
    repo_dist.get_version_actual.return_value = 0
    repo_dist.crear_redistribucion.return_value = {"version": 1}
    audit_mock = MagicMock()

    mock_validator = MagicMock()
    mock_validator.validar_redistribucion.return_value = (True, [])

    with patch(f"{_MODULO}.RedistribucionValidator", return_value=mock_validator), patch(
        f"{_MODULO}.convertir_ajustes_a_redistribucion", return_value=[]
    ), patch(f"{_MODULO}.obtener_respuestas_proveedor", return_value={}), patch(
        f"{_MODULO}.procesar_pedido_sap_con_homologacion_sync",
        return_value={"productos_procesados": 0},
    ):
        resultado_redistribucion, _ = _paso1_confirmar_redistribucion(
            conn=MagicMock(),
            repo_pedido=repo_pedido,
            repo_dist=repo_dist,
            pedido_id="pedido-1",
            ajustes_detalle=[],
            pedido_data=_pedido_data(ESTADO_REDISTRIBUCION),
            user_id="user1",
            audit=audit_mock,
        )

    repo_dist.crear_redistribucion.assert_called_once()
    repo_dist.confirmar_redistribucion.assert_called_once()
    repo_pedido.update_estado.assert_called_once_with(
        "pedido-1", ESTADO_PEDIDO_CONFIRMADO, audit_context=audit_mock
    )
    assert resultado_redistribucion["version_confirmada"] == 1
