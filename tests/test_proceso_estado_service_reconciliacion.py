"""
Tests de la Fase 2 (arreglo de raíz, tiempo real) del incidente 2026-08-27:
alias oc_id<->process_id y actualizar_resultado_final, que permiten corregir
el snapshot ya congelado de un proceso SAP cuando una reconciliación posterior
(botón manual "Reintentar ST" o el job Celery Beat) confirma tardíamente en
SAP algo que el proceso original reportó como pendiente/error.
"""

from src.database.services.proceso_estado_service import ProcesoEstadoService


class _FakeRedis:
    """Redis en memoria suficiente para setex/get con decode_responses=True."""

    def __init__(self):
        self.store = {}

    def setex(self, key, ttl_seconds, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def _service():
    service = ProcesoEstadoService.__new__(ProcesoEstadoService)
    service.redis_client = _FakeRedis()
    return service


def _resultado_proceso_completo(oc_id_principal="oc-1", oc_id_adicional=None):
    envio_principal = {
        "oc_id": oc_id_principal,
        "success": True,
        "doc_entry": 45987,
        "doc_num": 24715,
        "solicitudes_transferencia": {
            "total_tiendas": 23,
            "transferencias_creadas": 0,
            "transferencias_errores": 0,
            "transferencias_pendientes_confirmacion": 23,
            "resultados": [],
            "itrs_por_tienda": [],
        },
    }
    envios_sap = [envio_principal]
    if oc_id_adicional:
        envios_sap.append({
            "oc_id": oc_id_adicional,
            "success": True,
            "doc_entry": 45988,
            "doc_num": 24716,
            "solicitudes_transferencia": {"total_tiendas": 0, "transferencias_creadas": 0, "resultados": []},
        })
    return {
        "status": "success",
        "message": "Proceso completado exitosamente.",
        "pedido_id": "pedido-1",
        "numero_pedido": "pedido prueba 130",
        "envio_sap": envio_principal,
        "envios_sap": envios_sap,
        "solicitudes_transferencia": envio_principal["solicitudes_transferencia"],
    }


class TestAliasOcProcessId:
    def test_crear_y_resolver_alias(self):
        service = _service()
        service.crear_alias_oc("proceso-sap-abc123", "oc-1")
        assert service.obtener_process_id_por_oc("oc-1") == "proceso-sap-abc123"

    def test_alias_inexistente_devuelve_none(self):
        service = _service()
        assert service.obtener_process_id_por_oc("oc-no-existe") is None


class TestActualizarResultadoFinal:
    def _completar(self, service, process_id, resultado):
        service._guardar_estado(
            process_id,
            {
                "process_id": process_id,
                "status": "completed",
                "step": "completado",
                "progress": 100,
                "resultado": resultado,
                "version": 1,
                "updated_at": "2026-08-27T14:35:03",
            },
        )

    def test_corrige_solicitudes_transferencia_de_la_odc_unica(self):
        service = _service()
        process_id = "proceso-sap-ce42f4102dc2"
        self._completar(service, process_id, _resultado_proceso_completo(oc_id_principal="oc-1"))

        corregidas = {
            "total_tiendas": 23,
            "transferencias_creadas": 15,
            "transferencias_errores": 0,
            "transferencias_pendientes_confirmacion": 8,
            "resultados": [{"tienda_codigo": "TRL-MSU", "doc_num": 70215584, "success": True}],
            "itrs_por_tienda": [{"doc_num": 70215584, "tienda_codigo": "TRL-MSU"}],
        }
        aplicado = service.actualizar_resultado_final(
            process_id, "oc-1", corregidas, origen="reintentar_st_manual"
        )
        assert aplicado is True

        estado = service.obtener_estado(process_id)
        # No se reabre el proceso ni se toca su status.
        assert estado["status"] == "completed"
        assert estado["version"] == 2
        # El bloque de la ODC (envio_sap, primer/único elemento) queda corregido...
        assert estado["resultado"]["envio_sap"]["solicitudes_transferencia"] == corregidas
        assert estado["resultado"]["envios_sap"][0]["solicitudes_transferencia"] == corregidas
        # ...y el campo de conveniencia a nivel de respuesta también.
        assert estado["resultado"]["solicitudes_transferencia"] == corregidas

    def test_pedido_mixto_corrige_solo_la_odc_indicada(self):
        """2 ODC (pedido mixto): la corrección de una no debe tocar la otra."""
        service = _service()
        process_id = "proceso-sap-mixto1"
        self._completar(
            service, process_id,
            _resultado_proceso_completo(oc_id_principal="oc-1", oc_id_adicional="oc-2"),
        )

        corregidas_oc2 = {"total_tiendas": 5, "transferencias_creadas": 5, "resultados": []}
        aplicado = service.actualizar_resultado_final(
            process_id, "oc-2", corregidas_oc2, origen="reconciliacion_celery"
        )
        assert aplicado is True

        estado = service.obtener_estado(process_id)
        envios = estado["resultado"]["envios_sap"]
        assert envios[1]["oc_id"] == "oc-2"
        assert envios[1]["solicitudes_transferencia"] == corregidas_oc2
        # La ODC principal (oc-1) no se tocó.
        assert envios[0]["oc_id"] == "oc-1"
        assert envios[0]["solicitudes_transferencia"]["transferencias_pendientes_confirmacion"] == 23
        # El campo de conveniencia sigue reflejando la ODC principal (oc-1), no oc-2.
        assert estado["resultado"]["solicitudes_transferencia"]["transferencias_pendientes_confirmacion"] == 23

    def test_no_aplica_si_oc_id_no_esta_en_el_resultado(self):
        service = _service()
        process_id = "proceso-sap-abc"
        self._completar(service, process_id, _resultado_proceso_completo(oc_id_principal="oc-1"))

        aplicado = service.actualizar_resultado_final(
            process_id, "oc-que-no-existe", {"transferencias_creadas": 1}, origen="test"
        )
        assert aplicado is False

    def test_no_aplica_si_proceso_no_esta_completed(self):
        service = _service()
        process_id = "proceso-sap-en-curso"
        service._guardar_estado(
            process_id,
            {"process_id": process_id, "status": "processing", "progress": 40, "version": 1},
        )
        aplicado = service.actualizar_resultado_final(
            process_id, "oc-1", {"transferencias_creadas": 1}, origen="test"
        )
        assert aplicado is False

    def test_no_aplica_si_proceso_no_existe(self):
        service = _service()
        aplicado = service.actualizar_resultado_final(
            "proceso-sap-no-existe", "oc-1", {"transferencias_creadas": 1}, origen="test"
        )
        assert aplicado is False
