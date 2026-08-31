"""
Tests para el estado ENVIANDO de OCSAPService.enviar_oc_a_sap.

Antes de esto, mientras el envío a SAP estaba en curso (puede tardar varios
minutos por reintentos de prevalidación), `estado` seguía en PENDIENTE en BD --
cualquier otro visor de /mba3-consultas/proceso veía el botón "Reintentar"
completamente clickeable aunque un envío ya estuviera en curso. El lock Redis
(redis_lock_envio_odc, ver test_oc_sap_service_lock.py) ya impedía un doble envío
real; ENVIANDO es defensa en profundidad de UX -- estado preciso en BD para
cualquier otro visor -- y agrega una salvaguarda contra que quede "pegado" si el
proceso muere a mitad del envío (sin job_id, a diferencia de ENCOLADA, no hay
forma segura de verificar contra SAP antes de reintentar -- ver
ENVIANDO_ESTANCADO_UMBRAL_MINUTOS en config.py).
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from src.database.services.oc_sap_service import OCSAPService
from src.utils.timezone import ahora_naive


def _service_con_sap_client_mock():
    service = OCSAPService.__new__(OCSAPService)
    service.sap_client = MagicMock()
    return service


def _service_con_lock_libre(oc_repo, mock_lock=None):
    mock_lock = mock_lock or MagicMock()
    mock_lock.acquire.return_value = True
    mock_redis = MagicMock()
    mock_redis.lock.return_value = mock_lock
    return patch("src.database.services.oc_sap_service.get_redis_client", return_value=mock_redis)


class TestResolverEnvioEstancadoPrevio:
    def test_no_enviando_no_hace_nada(self):
        result = {}
        resultado = OCSAPService._resolver_envio_estancado_previo("oc-1", {"estado": "PENDIENTE"}, result)

        assert resultado is None
        assert result == {}

    def test_enviando_reciente_bloquea_sin_marcar_estancado(self):
        oc_cabecera = {"estado": "ENVIANDO", "fecha_envio_iniciado": ahora_naive() - timedelta(minutes=2)}
        result = {}

        resultado = OCSAPService._resolver_envio_estancado_previo("oc-1", oc_cabecera, result)

        assert resultado is False
        assert "en curso" in result["error"]
        assert result["retry_recommended"] is True

    def test_enviando_estancada_pasado_el_umbral_bloquea_como_interrumpido(self):
        oc_cabecera = {"estado": "ENVIANDO", "fecha_envio_iniciado": ahora_naive() - timedelta(minutes=20)}
        result = {}

        resultado = OCSAPService._resolver_envio_estancado_previo("oc-1", oc_cabecera, result)

        assert resultado is False
        assert "interrumpido" in result["error"]
        assert result["retry_recommended"] is False

    def test_enviando_sin_timestamp_se_trata_como_estancada(self):
        """No debería pasar (fecha_envio_iniciado se fija junto con el estado), pero
        si pasa, tratarla como estancada es la opción segura -- no hay forma de
        probar que es reciente."""
        oc_cabecera = {"estado": "ENVIANDO", "fecha_envio_iniciado": None}
        result = {}

        resultado = OCSAPService._resolver_envio_estancado_previo("oc-1", oc_cabecera, result)

        assert resultado is False
        assert "interrumpido" in result["error"]


class TestCargarYValidarCabeceraAceptaEnviando:
    def test_enviando_no_es_rechazada_por_el_whitelist(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {"estado": "ENVIANDO", "fecha_envio_iniciado": ahora_naive()}
        result = {}

        oc_cabecera = OCSAPService._cargar_y_validar_cabecera(oc_repo, "oc-1", result)

        assert oc_cabecera is not None
        assert result.get("error") is None


class TestEnviarOcASapConEnvioEstancado:
    def test_bloquea_sin_reintentar_ni_marcar_error_si_esta_estancada(self):
        """Regresión clave: el resolver inline nunca debe tocar la BD -- solo la
        reconciliación periódica hace el flip a ERROR (con UPDATE guardado)."""
        service = _service_con_sap_client_mock()
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIANDO", "fecha_envio_iniciado": ahora_naive() - timedelta(minutes=20),
        }

        with _service_con_lock_libre(oc_repo):
            result = service.enviar_oc_a_sap(oc_repo, "oc-1")

        assert result["success"] is False
        assert "interrumpido" in result["error"]
        oc_repo.update_estado.assert_not_called()
        service.sap_client.create_purchase_order.assert_not_called()


class TestEnviarOcASapMarcaEnviandoAntesDeValidar:
    def test_marca_enviando_antes_de_ejecutar_validaciones(self):
        """El punto de inserción es después de resolver ENCOLADA/ENVIANDO previos y
        antes de la prevalidación (que puede tardar varios minutos) -- se corta el
        flujo justo ahí (_ejecutar_validaciones_oc devuelve False) para verificar
        que la escritura ya ocurrió en ese punto, sin tener que mockear todo el
        resto de la cadena de envío."""
        service = _service_con_sap_client_mock()
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {"estado": "PENDIENTE"}
        oc_repo.get_detalles.return_value = [{"item_code": "SKU-1"}]

        with _service_con_lock_libre(oc_repo), \
             patch.object(service, "_cargar_y_validar_detalles", return_value=[{"item_code": "SKU-1"}]), \
             patch.object(service, "_resolver_warehouse_code", return_value="RG-CD"), \
             patch.object(service, "_ejecutar_validaciones_oc", return_value=False) as mock_validar:
            service.enviar_oc_a_sap(oc_repo, "oc-1")

        mock_validar.assert_called_once()
        oc_repo.update_estado.assert_called_once_with("oc-1", "ENVIANDO")
