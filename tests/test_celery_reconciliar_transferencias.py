"""
Tests de la tarea de reconciliación automática de Solicitudes de Transferencia.

Cubre: notificación única vía Redis, clasificación transitorio vs. no-transitorio,
el enrutamiento de resultados en _reconciliar_oc (éxito / sin pendientes /
escalamiento inmediato / escalamiento por recurrencia), el escalamiento por 2
corridas consecutivas, el colchón de seguridad (marca de última corrida exitosa,
verificado solo en la corrida del domingo), y el paso de dias_ventana/
verificar_salud_diaria hacia la consulta de candidatas (barrido corto entre
semana vs. barrido semanal ampliado del domingo).
"""

from unittest.mock import MagicMock, patch

from src.tasks.celery_reconciliar_transferencias import (
    _ya_fue_notificado,
    _marcar_notificado,
    _visto_pendiente_key,
    _limpiar_visto_pendiente,
    _marcar_ultima_corrida_exitosa,
    _verificar_salud_diaria,
    _tiene_error_no_transitorio,
    _evaluar_escalamiento_por_recurrencia,
    _reconciliar_oc,
    reconciliar_transferencias_pendientes,
)


class TestNotificacionRedis:
    def test_ya_fue_notificado_true(self):
        client = MagicMock()
        client.exists.return_value = 1
        assert _ya_fue_notificado(client, "oc-1") is True

    def test_ya_fue_notificado_false(self):
        client = MagicMock()
        client.exists.return_value = 0
        assert _ya_fue_notificado(client, "oc-1") is False

    def test_marcar_notificado_usa_ttl(self):
        client = MagicMock()
        _marcar_notificado(client, "oc-1")
        client.setex.assert_called_once()
        args = client.setex.call_args[0]
        assert args[0] == "reconciliar-st:notificado:oc-1"
        assert args[1] == 24 * 3600


class TestVistoPendiente:
    def test_limpiar_visto_pendiente_borra_la_clave(self):
        client = MagicMock()
        _limpiar_visto_pendiente(client, "oc-1")
        client.delete.assert_called_once_with(_visto_pendiente_key("oc-1"))

    def test_marcar_ultima_corrida_exitosa_usa_ttl_del_margen_colchon(self):
        client = MagicMock()
        _marcar_ultima_corrida_exitosa(client)
        client.setex.assert_called_once()
        args = client.setex.call_args[0]
        assert args[0] == "mba3:reconciliar-st:last-run"
        assert args[1] == 48 * 3600  # RECONCILIAR_ST_MARGEN_COLCHON_HORAS default

    def test_marcar_ultima_corrida_exitosa_no_propaga_si_redis_falla(self):
        client = MagicMock()
        client.setex.side_effect = Exception("redis caído")
        _marcar_ultima_corrida_exitosa(client)  # no debe lanzar


class TestTieneErrorNoTransitorio:
    def test_sin_resultados_es_false(self):
        assert _tiene_error_no_transitorio({}) is False

    def test_todas_exitosas_es_false(self):
        resultado_st = {"resultados": [{"success": True}]}
        assert _tiene_error_no_transitorio(resultado_st) is False

    def test_error_transitorio_es_false(self):
        resultado_st = {"resultados": [{"success": False, "error": "Error de conexión con SAP"}]}
        assert _tiene_error_no_transitorio(resultado_st) is False

    def test_error_no_transitorio_es_true(self):
        resultado_st = {
            "resultados": [
                {"success": False, "error": "Artículo no habilitado para compra en esta bodega"},
            ]
        }
        assert _tiene_error_no_transitorio(resultado_st) is True

    def test_una_transitoria_y_otra_no_es_true(self):
        resultado_st = {
            "resultados": [
                {"success": False, "error": "Timeout de conexión"},
                {"success": False, "error": "Item congelado"},
            ]
        }
        assert _tiene_error_no_transitorio(resultado_st) is True

    def test_itr_encolada_202_no_escala_como_error(self):
        """HTTP 202 (job SAP en curso) no debe escalar a técnicos: se resuelve solo."""
        resultado_st = {
            "resultados": [
                {"success": False, "queued": True, "job_id": "job-1", "error": "SAP saturado: encolada"},
            ]
        }
        assert _tiene_error_no_transitorio(resultado_st) is False


class TestReconciliarOc:
    def test_omite_si_ya_notificado(self):
        redis_client = MagicMock()
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=True
        ):
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is None

    def test_omite_si_lock_ocupado(self):
        redis_client = MagicMock()
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock:
            mock_lock.return_value.__enter__.return_value = False
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is None

    def test_no_pendientes_no_escala_y_limpia_marca(self):
        redis_client = MagicMock()
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock, patch(
            "src.tasks.celery_reconciliar_transferencias.StockTransferService"
        ) as MockService, patch(
            "src.tasks.celery_reconciliar_transferencias._evaluar_escalamiento_por_recurrencia"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_inmediato"
        ) as mock_inmediato, patch(
            "src.tasks.celery_reconciliar_transferencias._limpiar_visto_pendiente"
        ) as mock_limpiar:
            mock_lock.return_value.__enter__.return_value = True
            MockService.return_value.reintentar_pendientes.return_value = {"status": "no_pendientes"}
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is not None
        assert resultado["status"] == "no_pendientes"
        mock_escalar.assert_not_called()
        mock_inmediato.assert_not_called()
        mock_limpiar.assert_called_once_with(redis_client, "oc-1")

    def test_exito_no_escala_y_limpia_marca(self):
        redis_client = MagicMock()
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock, patch(
            "src.tasks.celery_reconciliar_transferencias.StockTransferService"
        ) as MockService, patch(
            "src.tasks.celery_reconciliar_transferencias._evaluar_escalamiento_por_recurrencia"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_inmediato"
        ) as mock_inmediato, patch(
            "src.tasks.celery_reconciliar_transferencias._limpiar_visto_pendiente"
        ) as mock_limpiar:
            mock_lock.return_value.__enter__.return_value = True
            MockService.return_value.reintentar_pendientes.return_value = {"status": "success"}
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is not None
        assert resultado["status"] == "success"
        mock_escalar.assert_not_called()
        mock_inmediato.assert_not_called()
        mock_limpiar.assert_called_once_with(redis_client, "oc-1")

    def test_partial_con_error_transitorio_evalua_por_recurrencia(self):
        redis_client = MagicMock()
        resultado_st = {"resultados": [{"success": False, "error": "Timeout de conexión"}]}
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock, patch(
            "src.tasks.celery_reconciliar_transferencias.StockTransferService"
        ) as MockService, patch(
            "src.tasks.celery_reconciliar_transferencias._evaluar_escalamiento_por_recurrencia"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_inmediato"
        ) as mock_inmediato:
            mock_lock.return_value.__enter__.return_value = True
            MockService.return_value.reintentar_pendientes.return_value = {
                "status": "partial", "resultado_st": resultado_st,
            }
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is not None
        assert resultado["status"] == "partial"
        mock_escalar.assert_called_once_with("oc-1", resultado_st, redis_client)
        mock_inmediato.assert_not_called()

    def test_partial_con_error_no_transitorio_escala_inmediato_y_limpia_marca(self):
        redis_client = MagicMock()
        resultado_st = {"resultados": [{"success": False, "error": "Item congelado en SAP"}]}
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock, patch(
            "src.tasks.celery_reconciliar_transferencias.StockTransferService"
        ) as MockService, patch(
            "src.tasks.celery_reconciliar_transferencias._evaluar_escalamiento_por_recurrencia"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_inmediato"
        ) as mock_inmediato, patch(
            "src.tasks.celery_reconciliar_transferencias._limpiar_visto_pendiente"
        ) as mock_limpiar:
            mock_lock.return_value.__enter__.return_value = True
            MockService.return_value.reintentar_pendientes.return_value = {
                "status": "partial", "resultado_st": resultado_st,
            }
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is not None
        assert resultado["status"] == "partial"
        mock_inmediato.assert_called_once_with("oc-1", resultado_st, redis_client)
        mock_escalar.assert_not_called()
        mock_limpiar.assert_called_once_with(redis_client, "oc-1")


class TestEvaluarEscalamientoPorRecurrencia:
    def test_primera_vez_solo_marca_no_escala(self):
        redis_client = MagicMock()
        redis_client.exists.return_value = 0
        with patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_a_tecnicos"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._marcar_notificado"
        ) as mock_marcar:
            _evaluar_escalamiento_por_recurrencia("oc-1", {}, redis_client)
        mock_escalar.assert_not_called()
        mock_marcar.assert_not_called()
        redis_client.setex.assert_called_once()
        args = redis_client.setex.call_args[0]
        assert args[0] == _visto_pendiente_key("oc-1")
        assert args[1] == 48 * 3600
        redis_client.delete.assert_not_called()

    def test_segunda_vez_consecutiva_escala_y_limpia_la_marca(self):
        redis_client = MagicMock()
        redis_client.exists.return_value = 1
        resultado_st = {"resultados": [{"success": False, "error": "Timeout"}]}
        oc_cabecera = {"numero_oc_sap": 123, "doc_entry": 45}
        with patch(
            "src.tasks.celery_reconciliar_transferencias._fetch_oc_cabecera", return_value=oc_cabecera
        ), patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_a_tecnicos"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._marcar_notificado"
        ) as mock_marcar:
            _evaluar_escalamiento_por_recurrencia("oc-1", resultado_st, redis_client)
        mock_escalar.assert_called_once_with(oc_cabecera, resultado_st)
        mock_marcar.assert_called_once_with(redis_client, "oc-1")
        redis_client.delete.assert_called_once_with(_visto_pendiente_key("oc-1"))
        redis_client.setex.assert_not_called()

    def test_segunda_vez_sin_cabecera_no_escala(self):
        redis_client = MagicMock()
        redis_client.exists.return_value = 1
        with patch(
            "src.tasks.celery_reconciliar_transferencias._fetch_oc_cabecera", return_value=None
        ), patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_a_tecnicos"
        ) as mock_escalar:
            _evaluar_escalamiento_por_recurrencia("oc-1", {}, redis_client)
        mock_escalar.assert_not_called()


class TestVerificarSaludDiaria:
    """Colchón de seguridad: se llama solo el domingo (verificar_salud_diaria=True),
    dentro de la misma corrida semanal -- no en una tarea aparte cada hora."""

    def test_al_dia_no_envia_correo(self):
        with patch(
            "src.tasks.celery_reconciliar_transferencias.reconciliacion_st_al_dia", return_value=True
        ), patch(
            "src.utils.email_notifier.send_reconciliacion_st_caida_notification"
        ) as mock_email:
            _verificar_salud_diaria()
        mock_email.assert_not_called()

    def test_caida_envia_correo(self):
        with patch(
            "src.tasks.celery_reconciliar_transferencias.reconciliacion_st_al_dia", return_value=False
        ), patch(
            "src.utils.email_notifier.send_reconciliacion_st_caida_notification"
        ) as mock_email:
            _verificar_salud_diaria()
        mock_email.assert_called_once()

    def test_fallo_al_enviar_correo_no_propaga(self):
        with patch(
            "src.tasks.celery_reconciliar_transferencias.reconciliacion_st_al_dia", return_value=False
        ), patch(
            "src.utils.email_notifier.send_reconciliacion_st_caida_notification",
            side_effect=Exception("smtp caído"),
        ):
            _verificar_salud_diaria()  # no debe lanzar


class TestReconciliarTransferenciasPendientesTask:
    """Wiring del task: dias_ventana viaja a la consulta de candidatas, y
    verificar_salud_diaria solo dispara el chequeo de salud cuando es True
    (la corrida del domingo)."""

    def _mocks_base(self, stack, oc_ids=None):
        redis_client = MagicMock()
        stack.enter_context(patch(
            "src.tasks.celery_reconciliar_transferencias.get_redis_client", return_value=redis_client
        ))
        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__enter__.return_value = MagicMock()
        stack.enter_context(patch(
            "src.tasks.celery_reconciliar_transferencias.get_db_connection_context",
            return_value=mock_conn_ctx,
        ))
        mock_repo_cls = stack.enter_context(patch(
            "src.tasks.celery_reconciliar_transferencias.SolicitudTransferenciaRepository"
        ))
        mock_repo_cls.return_value.get_oc_ids_con_tiendas_pendientes.return_value = oc_ids or []
        mock_repo_cls.return_value.get_oc_ids_con_tiendas_faltantes.return_value = []
        return redis_client, mock_repo_cls

    def test_corrida_diaria_pasa_dias_ventana_y_no_verifica_salud(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            _, mock_repo_cls = self._mocks_base(stack)
            mock_salud = stack.enter_context(patch(
                "src.tasks.celery_reconciliar_transferencias._verificar_salud_diaria"
            ))
            reconciliar_transferencias_pendientes(dias_ventana=2)
        mock_repo_cls.return_value.get_oc_ids_con_tiendas_pendientes.assert_called_once_with(2)
        mock_salud.assert_not_called()

    def test_corrida_semanal_pasa_ventana_amplia_y_verifica_salud(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            _, mock_repo_cls = self._mocks_base(stack)
            mock_salud = stack.enter_context(patch(
                "src.tasks.celery_reconciliar_transferencias._verificar_salud_diaria"
            ))
            reconciliar_transferencias_pendientes(dias_ventana=7, verificar_salud_diaria=True)
        mock_repo_cls.return_value.get_oc_ids_con_tiendas_pendientes.assert_called_once_with(7)
        mock_salud.assert_called_once()

    def test_une_pendientes_y_faltantes_sin_duplicar_oc_ids(self):
        """F4.5: get_oc_ids_con_tiendas_faltantes complementa (no reemplaza) a
        get_oc_ids_con_tiendas_pendientes; una OC en ambas listas se reconcilia
        una sola vez."""
        from contextlib import ExitStack
        with ExitStack() as stack:
            _, mock_repo_cls = self._mocks_base(stack, oc_ids=["oc-1", "oc-2"])
            mock_repo_cls.return_value.get_oc_ids_con_tiendas_faltantes.return_value = ["oc-2", "oc-3"]
            mock_reconciliar = stack.enter_context(patch(
                "src.tasks.celery_reconciliar_transferencias._reconciliar_oc",
                return_value={"status": "success"},
            ))
            resultado = reconciliar_transferencias_pendientes(dias_ventana=2)

        oc_ids_procesadas = [call.args[0] for call in mock_reconciliar.call_args_list]
        assert oc_ids_procesadas == ["oc-1", "oc-2", "oc-3"]
        assert resultado["candidatas"] == 3
