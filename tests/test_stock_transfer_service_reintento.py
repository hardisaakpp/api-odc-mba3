"""
Tests de StockTransferService.reintentar_pendientes y el lock distribuido asociado.

Cubre la lógica compartida por el endpoint manual "Reintentar ST" y por la
reconciliación automática (Celery): resolución de tiendas objetivo, validaciones
de precondición, y el contrato de retorno (status interno).
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from src.database.services.stock_transfer_service import (
    StockTransferService,
    redis_lock_reintento_st,
)


def _service():
    return StockTransferService.__new__(StockTransferService)


class TestResolverTiendasObjetivo:
    def test_usa_detalle_cuando_hay_pendientes(self):
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TRL-QSN"]
        tiendas, origen = StockTransferService._resolver_tiendas_objetivo(st_repo, "oc-1")
        assert tiendas == ["TRL-QSN"]
        assert origen == "detalle"
        st_repo.get_tiendas_fallidas_desde_resultado_json_fallback.assert_not_called()

    def test_cae_a_fallback_json_si_detalle_vacio(self):
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = []
        st_repo.get_tiendas_fallidas_desde_resultado_json_fallback.return_value = ["TOUT-ABC"]
        tiendas, origen = StockTransferService._resolver_tiendas_objetivo(st_repo, "oc-1")
        assert tiendas == ["TOUT-ABC"]
        assert origen == "resultado_json"

    def test_sin_pendientes_en_ninguna_fuente(self):
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = []
        st_repo.get_tiendas_fallidas_desde_resultado_json_fallback.return_value = []
        tiendas, origen = StockTransferService._resolver_tiendas_objetivo(st_repo, "oc-1")
        assert tiendas == []
        assert origen == "ninguno"

    def test_agrega_tiendas_faltantes_a_las_pendientes_de_detalle(self):
        """F4.5: una tienda que nunca se intentó (sin registro en detalle) debe
        sumarse a las que sí fallaron, no reemplazarlas."""
        st_repo = MagicMock()
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TRL-QSN"]
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = ["TOUT-NEW"]
        tiendas, origen = StockTransferService._resolver_tiendas_objetivo(st_repo, "oc-1")
        assert tiendas == ["TRL-QSN", "TOUT-NEW"]
        assert origen == "detalle+faltantes"

    def test_tienda_faltante_duplicada_no_se_repite(self):
        """Si get_tiendas_faltantes_por_oc_id devuelve una tienda que ya venía de
        get_tiendas_pendientes_reintento_st (normalizando espacios/mayúsculas), no
        debe duplicarse en la lista final."""
        st_repo = MagicMock()
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TRL-QSN"]
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = [" trl-qsn "]
        tiendas, origen = StockTransferService._resolver_tiendas_objetivo(st_repo, "oc-1")
        assert tiendas == ["TRL-QSN"]
        assert origen == "detalle"

    def test_solo_hay_tiendas_faltantes_sin_ninguna_pendiente_de_error(self):
        """Caso puro F4.5: nada quedó en Error/Encolada, pero la distribución
        confirmada espera una tienda que nunca se intentó."""
        st_repo = MagicMock()
        st_repo.get_tiendas_pendientes_reintento_st.return_value = []
        st_repo.get_tiendas_fallidas_desde_resultado_json_fallback.return_value = []
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = ["TOUT-NEW"]
        tiendas, origen = StockTransferService._resolver_tiendas_objetivo(st_repo, "oc-1")
        assert tiendas == ["TOUT-NEW"]
        assert origen == "faltantes"


class TestParseOcDocNum:
    def test_valor_valido(self):
        assert StockTransferService._parse_oc_doc_num("12345") == 12345

    def test_valor_none(self):
        assert StockTransferService._parse_oc_doc_num(None) is None

    def test_valor_invalido(self):
        assert StockTransferService._parse_oc_doc_num("abc") is None


class TestReintentarPendientes:
    @staticmethod
    @contextmanager
    def _mock_conn_context(oc_repo, st_repo, pedido_repo=None):
        with patch(
            "src.database.services.stock_transfer_service.OrdenCompraRepository", return_value=oc_repo
        ), patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository", return_value=st_repo
        ), patch(
            "src.database.services.stock_transfer_service.PedidoRepository",
            return_value=pedido_repo or MagicMock(get_pedido_completo=MagicMock(return_value=None)),
        ), patch(
            "src.database.services.stock_transfer_service.get_db_connection_context"
        ) as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            yield

    def test_oc_no_encontrada(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = None
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        service = _service()
        with self._mock_conn_context(oc_repo, st_repo):
            resultado = service.reintentar_pendientes("oc-1", "user1")
        assert resultado["status"] == "no_encontrada"

    def test_estado_no_es_enviada(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {"estado": "PENDIENTE"}
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        service = _service()
        with self._mock_conn_context(oc_repo, st_repo):
            resultado = service.reintentar_pendientes("oc-1", "user1")
        assert resultado["status"] == "estado_invalido"

    def test_sin_tiendas_pendientes(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {"estado": "ENVIADA"}
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = []
        st_repo.get_tiendas_fallidas_desde_resultado_json_fallback.return_value = []
        service = _service()
        with self._mock_conn_context(oc_repo, st_repo):
            resultado = service.reintentar_pendientes("oc-1", "user1")
        assert resultado["status"] == "no_pendientes"
        assert resultado["reintentadas"] == 0

    def test_sin_pedido_id(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {"estado": "ENVIADA", "pedido_id": None}
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TRL-QSN"]
        service = _service()
        with self._mock_conn_context(oc_repo, st_repo):
            resultado = service.reintentar_pendientes("oc-1", "user1")
        assert resultado["status"] == "sin_pedido"

    def test_reintento_exitoso_llama_crear_st_con_filtro(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIADA", "pedido_id": "pedido-1",
            "codigo_bodega": "RL-CD", "numero_oc_sap": "555",
        }
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TRL-QSN"]
        service = _service()
        with self._mock_conn_context(oc_repo, st_repo):
            with patch.object(
                service, "crear_solicitudes_transferencia_desde_pedido",
                return_value={"success": True, "transferencias_creadas": 1},
            ) as mock_crear, patch.object(
                service, "_notificar_st_creadas_en_reintento"
            ) as mock_notificar:
                resultado = service.reintentar_pendientes("oc-1", "user1")

        mock_crear.assert_called_once()
        _, kwargs = mock_crear.call_args
        assert kwargs["tiendas_destino_filtro"] == ["TRL-QSN"]
        assert kwargs["oc_doc_num"] == 555
        assert kwargs["bodega_origen"] == "RL-CD"
        assert kwargs["verificar_ya_existente_en_sap"] is True
        assert resultado["status"] == "success"
        assert resultado["tiendas_count"] == 1
        mock_notificar.assert_called_once()

    def test_notificacion_usa_resumen_agregado_no_solo_el_reintento(self):
        """
        Bug real: el correo de despacho tras un reintento solo mostraba las tiendas
        recién reprocesadas (ej. 2 de 5), y las que ya habían tenido éxito en el
        envío original (ej. las otras 3) desaparecían del correo más reciente que
        ve El Rayo. _notificar_st_creadas_en_reintento debe recibir el resumen
        agregado de TODOS los batches, no el resultado parcial de este reintento.
        """
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIADA", "pedido_id": "pedido-1",
            "codigo_bodega": "RL-CD", "numero_oc_sap": "555",
        }
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TRL-QSN", "TRL-PSC"]
        resumen_agregado_completo = {
            "total_tiendas": 5, "transferencias_creadas": 5, "transferencias_errores": 0,
            "resultados": [{"tienda_codigo": f"T{i}", "success": True} for i in range(5)],
        }
        st_repo.get_resumen_agregado_por_oc_id.return_value = resumen_agregado_completo
        service = _service()
        with self._mock_conn_context(oc_repo, st_repo):
            with patch.object(
                service, "crear_solicitudes_transferencia_desde_pedido",
                # Resultado parcial de este reintento: solo las 2 tiendas reprocesadas.
                return_value={"success": True, "transferencias_creadas": 2},
            ), patch.object(
                service, "_notificar_st_creadas_en_reintento"
            ) as mock_notificar:
                service.reintentar_pendientes("oc-1", "user1")

        mock_notificar.assert_called_once()
        args, _ = mock_notificar.call_args
        resumen_pasado_al_correo = args[2]
        assert resumen_pasado_al_correo == resumen_agregado_completo
        assert resumen_pasado_al_correo["total_tiendas"] == 5

    def test_reintento_parcial_si_crear_st_falla(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIADA", "pedido_id": "pedido-1", "codigo_bodega": "RL-CD",
        }
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TRL-QSN"]
        service = _service()
        with self._mock_conn_context(oc_repo, st_repo):
            with patch.object(
                service, "crear_solicitudes_transferencia_desde_pedido",
                return_value={"success": False},
            ), patch.object(
                service, "_notificar_st_creadas_en_reintento"
            ) as mock_notificar:
                resultado = service.reintentar_pendientes("oc-1", "user1")
        assert resultado["status"] == "partial"
        mock_notificar.assert_not_called()

    def test_todas_las_tiendas_en_cola_no_se_reenvia_y_status_en_cola(self):
        """HTTP 202 (job SAP en curso): no reenviar, informar 'en_cola', no 'success' engañoso."""
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIADA", "pedido_id": "pedido-1", "codigo_bodega": "RL-CD",
        }
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TRL-PSC"]
        service = _service()
        with self._mock_conn_context(oc_repo, st_repo):
            with patch.object(
                service, "crear_solicitudes_transferencia_desde_pedido",
                return_value={
                    "success": True, "transferencias_creadas": 0,
                    "tiendas_en_cola": ["TRL-PSC"],
                },
            ), patch.object(
                service, "_notificar_st_creadas_en_reintento"
            ) as mock_notificar:
                resultado = service.reintentar_pendientes("oc-1", "user1")
        assert resultado["status"] == "en_cola"
        mock_notificar.assert_not_called()


class TestReevaluarCierrePedidoTrasReintento:
    """
    Bug real (pedido PDES-08.26.2026.XM, 21/08/2026): la ODC se enviaba bien y el
    primer intento de ST fallaba, dejando el pedido en PENDIENTE_LOGISTICA; un
    reintento de ST posterior tenía éxito, pero como reintentar_pendientes() nunca
    volvía a llamar a cerrar_pedido_si_corresponde, el pedido quedaba congelado en
    PENDIENTE_LOGISTICA para siempre aunque en SAP ya estuviera todo correctamente
    enviado. Hubo que corregirlo manualmente en BD.
    """

    def test_reintento_exitoso_dispara_reevaluacion_de_cierre(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIADA", "pedido_id": "pedido-1",
            "codigo_bodega": "OUT-CD", "numero_oc_sap": "1201916",
        }
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TOUT-REC"]
        st_repo.get_resumen_agregado_por_oc_id.return_value = {
            "total_tiendas": 1, "transferencias_creadas": 1, "transferencias_errores": 0,
            "resultados": [{"tienda_codigo": "TOUT-REC", "success": True}],
        }
        service = _service()
        with TestReintentarPendientes._mock_conn_context(oc_repo, st_repo):
            with patch.object(
                service, "crear_solicitudes_transferencia_desde_pedido",
                return_value={"success": True, "transferencias_creadas": 1},
            ), patch.object(
                service, "_notificar_st_creadas_en_reintento"
            ), patch(
                "src.database.services.pedido_cierre_service.PedidoCierreService"
            ) as mock_cierre_cls:
                mock_cierre = mock_cierre_cls.return_value
                mock_cierre.cerrar_pedido_si_corresponde.return_value = {
                    "cerrado": True, "estado_anterior": "PENDIENTE_LOGISTICA",
                    "estado_nuevo": "CONFIRMADO_ENVIADO",
                }
                resultado = service.reintentar_pendientes("oc-1", "user1")

        assert resultado["status"] == "success"
        mock_cierre.cerrar_pedido_si_corresponde.assert_called_once()
        _, kwargs = mock_cierre.cerrar_pedido_si_corresponde.call_args
        assert kwargs["pedido_id"] == "pedido-1"
        assert kwargs["resultado_st"]["success"] is True
        assert kwargs["resultado_st"]["transferencias_errores"] == 0

    def test_reintento_aun_con_errores_igual_reevalua_pero_no_fuerza_exito(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIADA", "pedido_id": "pedido-1", "codigo_bodega": "OUT-CD",
        }
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TOUT-REC", "TOUT-BMB"]
        st_repo.get_resumen_agregado_por_oc_id.return_value = {
            "total_tiendas": 2, "transferencias_creadas": 1, "transferencias_errores": 1,
            "resultados": [
                {"tienda_codigo": "TOUT-REC", "success": True},
                {"tienda_codigo": "TOUT-BMB", "success": False, "error": "conexión"},
            ],
        }
        service = _service()
        with TestReintentarPendientes._mock_conn_context(oc_repo, st_repo):
            with patch.object(
                service, "crear_solicitudes_transferencia_desde_pedido",
                return_value={"success": False, "transferencias_creadas": 1},
            ), patch.object(
                service, "_notificar_st_creadas_en_reintento"
            ), patch(
                "src.database.services.pedido_cierre_service.PedidoCierreService"
            ) as mock_cierre_cls:
                mock_cierre = mock_cierre_cls.return_value
                mock_cierre.cerrar_pedido_si_corresponde.return_value = {
                    "cerrado": False, "estado_anterior": "PENDIENTE_LOGISTICA",
                    "estado_nuevo": "PENDIENTE_LOGISTICA",
                }
                resultado = service.reintentar_pendientes("oc-1", "user1")

        assert resultado["status"] == "partial"
        mock_cierre.cerrar_pedido_si_corresponde.assert_called_once()
        _, kwargs = mock_cierre.cerrar_pedido_si_corresponde.call_args
        assert kwargs["resultado_st"]["success"] is False

    def test_tiendas_en_cola_no_dispara_reevaluacion(self):
        """Si el job SAP sigue en curso no hay nada definitivo que reevaluar todavía."""
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIADA", "pedido_id": "pedido-1", "codigo_bodega": "OUT-CD",
        }
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TOUT-REC"]
        service = _service()
        with TestReintentarPendientes._mock_conn_context(oc_repo, st_repo):
            with patch.object(
                service, "crear_solicitudes_transferencia_desde_pedido",
                return_value={
                    "success": True, "transferencias_creadas": 0,
                    "tiendas_en_cola": ["TOUT-REC"],
                },
            ), patch.object(
                service, "_notificar_st_creadas_en_reintento"
            ), patch(
                "src.database.services.pedido_cierre_service.PedidoCierreService"
            ) as mock_cierre_cls:
                resultado = service.reintentar_pendientes("oc-1", "user1")

        assert resultado["status"] == "en_cola"
        mock_cierre_cls.return_value.cerrar_pedido_si_corresponde.assert_not_called()

    def test_error_al_reevaluar_no_rompe_la_respuesta_del_reintento(self):
        """No crítico: un fallo al reevaluar el cierre no debe tumbar la respuesta
        del reintento de ST, que ya reporta su propio resultado real."""
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIADA", "pedido_id": "pedido-1", "codigo_bodega": "OUT-CD",
        }
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_pendientes_reintento_st.return_value = ["TOUT-REC"]
        # transferencias_creadas=0 evita la llamada a get_resumen_agregado_por_oc_id
        # del bloque de notificación (no es lo que este test cubre); el side_effect
        # solo debe afectar la llamada que hace _reevaluar_cierre_pedido_tras_reintento.
        st_repo.get_resumen_agregado_por_oc_id.side_effect = Exception("boom")
        service = _service()
        with TestReintentarPendientes._mock_conn_context(oc_repo, st_repo):
            with patch.object(
                service, "crear_solicitudes_transferencia_desde_pedido",
                return_value={"success": True, "transferencias_creadas": 0},
            ), patch.object(
                service, "_notificar_st_creadas_en_reintento"
            ) as mock_notificar:
                resultado = service.reintentar_pendientes("oc-1", "user1")

        assert resultado["status"] == "success"
        mock_notificar.assert_not_called()


class TestNotificarStCreadasEnReintento:
    """
    Cubre el vacío detectado: antes de esto, El Rayo solo recibía los códigos de ST
    en el envío original; un reintento (manual o automático) que creaba ITRs nuevas
    nunca las notificaba.
    """

    def test_envia_notificacion_cuando_hay_creadas(self):
        with patch(
            "src.utils.email_notifier.send_oc_ready_for_dispatch_notification"
        ) as mock_send:
            mock_send.return_value = True
            StockTransferService._notificar_st_creadas_en_reintento(
                "oc-1",
                {"numero_oc_sap": "555", "doc_entry": 111},
                {"transferencias_creadas": 1, "resultados": []},
                "PED-001",
                "manual",
            )
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["doc_num"] == "555"
        assert kwargs["pedido_numero"] == "PED-001"

    def test_no_lanza_si_el_envio_de_correo_falla(self):
        with patch(
            "src.utils.email_notifier.send_oc_ready_for_dispatch_notification",
            side_effect=Exception("SMTP caído"),
        ):
            StockTransferService._notificar_st_creadas_en_reintento(
                "oc-1", {}, {"transferencias_creadas": 1}, None, "automatico"
            )  # no debe propagar la excepción


class TestObtenerNumeroPedido:
    def test_retorna_numero_pedido(self):
        pedido_repo = MagicMock()
        pedido_repo.get_pedido_completo.return_value = {"cabecera": {"numero_pedido": "PED-001"}}
        with patch(
            "src.database.services.stock_transfer_service.PedidoRepository", return_value=pedido_repo
        ):
            assert StockTransferService._obtener_numero_pedido("pedido-1", MagicMock()) == "PED-001"

    def test_retorna_none_si_falla(self):
        with patch(
            "src.database.services.stock_transfer_service.PedidoRepository",
            side_effect=Exception("boom"),
        ):
            assert StockTransferService._obtener_numero_pedido("pedido-1", MagicMock()) is None


class TestBuscarItrsExistentesEnSap:
    """
    Verificación preventiva de duplicados: matching estricto contra SAP
    (comentario exacto + FromWarehouse) antes de reintentar crear ITRs.
    """

    _COMENTARIO = "Transferencia desde OC 555 - Pedido P-12.4"

    def _service_con_itrs(self, itrs):
        service = _service()
        service.sap_client = MagicMock()
        service.sap_client.get_inventory_transfer_requests_by_comment.return_value = itrs
        return service

    def test_match_exacto_construye_mapa(self):
        service = self._service_con_itrs([
            {
                "comments": self._COMENTARIO,
                "from_warehouse": "RL-CD",
                "to_warehouse": "TRL-QSN",
                "doc_num": 22175,
                "doc_entry": 358178,
            }
        ])
        existentes = service._buscar_itrs_existentes_en_sap(self._COMENTARIO, "RL-CD")
        assert existentes == {"TRL-QSN": {"doc_num": 22175, "doc_entry": 358178}}

    def test_rechaza_comentario_de_otro_pedido_por_substring(self):
        # "Pedido P-12.4" es substring de "Pedido P-12.48": la igualdad exacta lo excluye.
        service = self._service_con_itrs([
            {
                "comments": "Transferencia desde OC 555 - Pedido P-12.48",
                "from_warehouse": "RL-CD",
                "to_warehouse": "TRL-QSN",
                "doc_num": 999,
                "doc_entry": 111,
            }
        ])
        assert service._buscar_itrs_existentes_en_sap(self._COMENTARIO, "RL-CD") == {}

    def test_rechaza_bodega_origen_distinta(self):
        service = self._service_con_itrs([
            {
                "comments": self._COMENTARIO,
                "from_warehouse": "OUT-CD",
                "to_warehouse": "TRL-QSN",
                "doc_num": 22175,
                "doc_entry": 358178,
            }
        ])
        assert service._buscar_itrs_existentes_en_sap(self._COMENTARIO, "RL-CD") == {}

    def test_ignora_itr_sin_doc_entry(self):
        service = self._service_con_itrs([
            {
                "comments": self._COMENTARIO,
                "from_warehouse": "RL-CD",
                "to_warehouse": "TRL-QSN",
                "doc_num": 22175,
                "doc_entry": None,
            }
        ])
        assert service._buscar_itrs_existentes_en_sap(self._COMENTARIO, "RL-CD") == {}

    def test_retorna_vacio_si_consulta_falla(self):
        service = _service()
        service.sap_client = MagicMock()
        service.sap_client.get_inventory_transfer_requests_by_comment.side_effect = Exception("boom")
        assert service._buscar_itrs_existentes_en_sap(self._COMENTARIO, "RL-CD") == {}


class TestEnviarItrsConVerificacionPrevia:
    """_enviar_itrs_a_sap adopta ITRs ya existentes en SAP en vez de recrearlas."""

    @staticmethod
    def _result_inicial():
        return {
            "success": False,
            "total_tiendas": 1,
            "transferencias_creadas": 0,
            "transferencias_errores": 0,
            "transferencias_encoladas": 0,
            "resultados": [],
        }

    def test_itr_existente_no_se_reenvia(self):
        service = _service()
        result = self._result_inicial()
        with patch.object(service, "_enviar_itr_con_reintento") as mock_enviar:
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-QSN"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={"TRL-QSN": "ROLAND QUICENTRO NORTE"},
                result=result,
                itrs_existentes={"TRL-QSN": {"doc_num": 22175, "doc_entry": 358178}},
            )
        mock_enviar.assert_not_called()
        assert result["transferencias_creadas"] == 1
        resultado_tienda = result["resultados"][0]
        assert resultado_tienda["success"] is True
        assert resultado_tienda["doc_num"] == 22175
        assert resultado_tienda["doc_entry"] == 358178
        assert resultado_tienda["recuperada"] is True
        assert resultado_tienda["tienda_nombre"] == "ROLAND QUICENTRO NORTE"

    def test_itr_no_existente_sigue_camino_normal(self):
        service = _service()
        result = self._result_inicial()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={
                "success": True,
                "response": {"success": True, "doc_entry": 400, "doc_num": 500},
                "attempts": 1,
                "error": None,
            },
        ) as mock_enviar:
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-QSN"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={},
                result=result,
                itrs_existentes={"TOUT-ABC": {"doc_num": 1, "doc_entry": 2}},
            )
        mock_enviar.assert_called_once()
        assert result["transferencias_creadas"] == 1
        assert result["resultados"][0]["doc_entry"] == 400

    def test_itr_encolada_202_no_cuenta_como_error(self):
        """HTTP 202 (job SAP en curso) no es un error definitivo: no incrementa
        transferencias_errores, se registra aparte con su job_id."""
        service = _service()
        service.sap_client = MagicMock()
        # Job recién encolado en este mismo intento: la reconciliación al cierre
        # (_reconciliar_pendientes_confirmacion) lo consulta y sigue en curso, no
        # se adopta -- el resultado se mantiene 'pendiente_confirmacion'/queued.
        service.sap_client.get_job_status.return_value = {"status": "ENCOLADO"}
        result = self._result_inicial()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={
                "success": False,
                "response": {"success": False, "queued": True, "job_id": "job-123", "error": "SAP saturado"},
                "attempts": 1,
                "error": "SAP saturado",
            },
        ):
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-PSC"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={},
                result=result,
            )
        assert result["transferencias_errores"] == 0
        assert result["transferencias_encoladas"] == 1
        resultado_tienda = result["resultados"][0]
        assert resultado_tienda["success"] is False
        assert resultado_tienda["queued"] is True
        assert resultado_tienda["job_id"] == "job-123"

    def test_sin_mapa_es_comportamiento_actual(self):
        service = _service()
        result = self._result_inicial()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={
                "success": True,
                "response": {"success": True, "doc_entry": 400, "doc_num": 500},
                "attempts": 1,
                "error": None,
            },
        ) as mock_enviar:
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-QSN"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={},
                result=result,
            )
        mock_enviar.assert_called_once()
        assert result["transferencias_creadas"] == 1


class TestResolverJobsEncoladosPendientes:
    """
    Antes de reintentar, resuelve tiendas 'Encolada' (HTTP 202) consultando el
    job real en vez de reenviar a ciegas (evita ITR duplicada en SAP).
    """

    def _service_con_job_status(self, pendientes, job_status_por_id):
        service = _service()
        service.sap_client = MagicMock()
        service.sap_client.get_job_status.side_effect = lambda job_id: job_status_por_id.get(job_id)
        st_repo = MagicMock()
        st_repo.get_tiendas_faltantes_por_oc_id.return_value = []
        st_repo.get_tiendas_encoladas_con_job_id.return_value = pendientes
        return service, st_repo

    def test_job_completado_se_adopta(self):
        service, st_repo = self._service_con_job_status(
            pendientes={"TRL-PSC": "job-1"},
            job_status_por_id={
                "job-1": {"status": "COMPLETADO", "result": {"docEntry": 400, "docNum": 500}},
            },
        )
        with patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository",
            return_value=st_repo,
        ):
            adoptadas, en_cola = service._resolver_jobs_encolados_pendientes(
                MagicMock(), "oc-1", ["TRL-PSC"]
            )
        assert adoptadas == {"TRL-PSC": {"doc_num": 500, "doc_entry": 400}}
        assert en_cola == set()

    def test_job_aun_encolado_no_se_reenvia(self):
        service, st_repo = self._service_con_job_status(
            pendientes={"TRL-PSC": "job-1"},
            job_status_por_id={"job-1": {"status": "ENCOLADO"}},
        )
        with patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository",
            return_value=st_repo,
        ):
            adoptadas, en_cola = service._resolver_jobs_encolados_pendientes(
                MagicMock(), "oc-1", ["TRL-PSC"]
            )
        assert adoptadas == {}
        assert en_cola == {"TRL-PSC"}

    def test_job_procesando_no_se_reenvia(self):
        service, st_repo = self._service_con_job_status(
            pendientes={"TRL-PSC": "job-1"},
            job_status_por_id={"job-1": {"status": "PROCESANDO"}},
        )
        with patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository",
            return_value=st_repo,
        ):
            _, en_cola = service._resolver_jobs_encolados_pendientes(MagicMock(), "oc-1", ["TRL-PSC"])
        assert en_cola == {"TRL-PSC"}

    def test_job_error_queda_libre_para_reintento_normal(self):
        service, st_repo = self._service_con_job_status(
            pendientes={"TRL-PSC": "job-1"},
            job_status_por_id={"job-1": {"status": "ERROR", "error": "SAP saturado: se agotaron los reintentos."}},
        )
        with patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository",
            return_value=st_repo,
        ):
            adoptadas, en_cola = service._resolver_jobs_encolados_pendientes(
                MagicMock(), "oc-1", ["TRL-PSC"]
            )
        assert adoptadas == {}
        assert en_cola == set()

    def test_job_no_consultable_queda_libre_para_reintento_normal(self):
        """get_job_status devuelve None (middleware caído/job expirado): no bloquear el reintento."""
        service, st_repo = self._service_con_job_status(
            pendientes={"TRL-PSC": "job-1"},
            job_status_por_id={},
        )
        with patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository",
            return_value=st_repo,
        ):
            adoptadas, en_cola = service._resolver_jobs_encolados_pendientes(
                MagicMock(), "oc-1", ["TRL-PSC"]
            )
        assert adoptadas == {}
        assert en_cola == set()

    def test_sin_pendientes_no_llama_get_job_status(self):
        service, st_repo = self._service_con_job_status(pendientes={}, job_status_por_id={})
        with patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository",
            return_value=st_repo,
        ):
            adoptadas, en_cola = service._resolver_jobs_encolados_pendientes(
                MagicMock(), "oc-1", ["TRL-PSC"]
            )
        assert adoptadas == {} and en_cola == set()
        service.sap_client.get_job_status.assert_not_called()


class TestRedisLockReintentoSt:
    def test_lock_adquirido(self):
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_client = MagicMock()
        mock_client.lock.return_value = mock_lock
        with patch(
            "src.database.services.stock_transfer_service.get_redis_client", return_value=mock_client
        ):
            with redis_lock_reintento_st("oc-1", blocking_timeout=1.0) as acquired:
                assert acquired is True
        mock_lock.release.assert_called_once()

    def test_lock_no_adquirido_no_libera(self):
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False
        mock_client = MagicMock()
        mock_client.lock.return_value = mock_lock
        with patch(
            "src.database.services.stock_transfer_service.get_redis_client", return_value=mock_client
        ):
            with redis_lock_reintento_st("oc-1", blocking_timeout=1.0) as acquired:
                assert acquired is False
        mock_lock.release.assert_not_called()
