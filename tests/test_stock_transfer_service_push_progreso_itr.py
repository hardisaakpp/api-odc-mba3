"""
Fase 2 (tiempo real, push en vivo) del arreglo de raíz: _empujar_progreso_itr
escribe el progreso de cada tienda al proceso SAP original a medida que se
resuelve, fusionando lo que ODC hermanas de un pedido mixto (mismo process_id,
threads distintos) ya hayan escrito -- sin este merge, cada ODC pisaría en
Redis el progreso de la otra.
"""

import threading

from src.database.services.proceso_estado_service import ProcesoEstadoService
from src.database.services.stock_transfer_service import StockTransferService


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl_seconds, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def _proceso_estado_service_con_fake_redis():
    service = ProcesoEstadoService.__new__(ProcesoEstadoService)
    service.redis_client = _FakeRedis()
    return service


def _preparar_proceso_en_curso(pe_service, process_id):
    pe_service._guardar_estado(
        process_id,
        {
            "process_id": process_id,
            "status": "processing",
            "step": "generando",
            "progress": 70,
            "version": 1,
        },
    )


def _service(sap_client=None):
    service = StockTransferService.__new__(StockTransferService)
    if sap_client is not None:
        service.sap_client = sap_client
    return service


def _resultado_tienda(tienda_codigo, estado="confirmada", doc_num=123):
    return {
        "tienda_codigo": tienda_codigo,
        "tienda_nombre": f"Tienda {tienda_codigo}",
        "estado": estado,
        "doc_num": doc_num,
    }


class TestEmpujarProgresoItr:
    def test_no_hace_nada_sin_process_id(self):
        # No debe lanzar ni requerir Redis si process_id es None.
        StockTransferService._empujar_progreso_itr(
            None, None, "oc-1", _resultado_tienda("TRL-QSN"), 5, 1
        )

    def test_empuja_una_entrada(self, monkeypatch):
        pe_service = _proceso_estado_service_con_fake_redis()
        monkeypatch.setattr(
            "src.database.services.proceso_estado_service.get_redis_client",
            lambda: pe_service.redis_client,
        )
        process_id = "proceso-sap-abc"
        _preparar_proceso_en_curso(pe_service, process_id)

        StockTransferService._empujar_progreso_itr(
            process_id, None, "oc-1", _resultado_tienda("TRL-MSU", doc_num=70215584), 23, 1
        )

        estado = pe_service.obtener_estado(process_id)
        assert estado["data"]["itr_detalle"] == [
            {
                "oc_id": "oc-1",
                "tienda_codigo": "TRL-MSU",
                "tienda_nombre": "Tienda TRL-MSU",
                "estado": "confirmada",
                "doc_num": 70215584,
            }
        ]
        assert estado["progress"] >= 75  # avanzó dentro del rango 75-95%

    def test_fusiona_entradas_de_dos_odc_hermanas_sin_pisarse(self, monkeypatch):
        """Simula un pedido mixto: 2 ODC (oc-RL, oc-RG) empujando al MISMO
        process_id. Sin el merge, la segunda escritura pisaría la primera."""
        pe_service = _proceso_estado_service_con_fake_redis()
        monkeypatch.setattr(
            "src.database.services.proceso_estado_service.get_redis_client",
            lambda: pe_service.redis_client,
        )
        process_id = "proceso-sap-mixto"
        _preparar_proceso_en_curso(pe_service, process_id)
        lock = threading.Lock()

        StockTransferService._empujar_progreso_itr(
            process_id, lock, "oc-RL", _resultado_tienda("TRL-QSN", doc_num=1), 2, 1
        )
        StockTransferService._empujar_progreso_itr(
            process_id, lock, "oc-RG", _resultado_tienda("TOUT-CEN", doc_num=2), 2, 1
        )

        estado = pe_service.obtener_estado(process_id)
        oc_ids = {e["oc_id"] for e in estado["data"]["itr_detalle"]}
        assert oc_ids == {"oc-RL", "oc-RG"}
        assert len(estado["data"]["itr_detalle"]) == 2

    def test_reemplaza_entrada_previa_de_la_misma_tienda(self, monkeypatch):
        """Una reconciliación posterior que sube 'pendiente_confirmacion' a
        'confirmada' para la MISMA tienda debe reemplazar la entrada anterior,
        no duplicarla."""
        pe_service = _proceso_estado_service_con_fake_redis()
        monkeypatch.setattr(
            "src.database.services.proceso_estado_service.get_redis_client",
            lambda: pe_service.redis_client,
        )
        process_id = "proceso-sap-reconciliacion"
        _preparar_proceso_en_curso(pe_service, process_id)

        StockTransferService._empujar_progreso_itr(
            process_id, None, "oc-1",
            _resultado_tienda("TRL-PSM", estado="pendiente_confirmacion", doc_num=None), 1, 1,
        )
        StockTransferService._empujar_progreso_itr(
            process_id, None, "oc-1",
            _resultado_tienda("TRL-PSM", estado="confirmada", doc_num=70215585), 1, 1,
        )

        estado = pe_service.obtener_estado(process_id)
        assert estado["data"]["itr_detalle"] == [
            {
                "oc_id": "oc-1",
                "tienda_codigo": "TRL-PSM",
                "tienda_nombre": "Tienda TRL-PSM",
                "estado": "confirmada",
                "doc_num": 70215585,
            }
        ]

    def test_no_falla_si_el_proceso_ya_no_existe(self, monkeypatch):
        pe_service = _proceso_estado_service_con_fake_redis()
        monkeypatch.setattr(
            "src.database.services.proceso_estado_service.get_redis_client",
            lambda: pe_service.redis_client,
        )
        # No hay _preparar_proceso_en_curso -- el proceso nunca existió/expiró.
        StockTransferService._empujar_progreso_itr(
            "proceso-sap-no-existe", None, "oc-1", _resultado_tienda("TRL-QSN"), 1, 1
        )
        # No debe haber creado nada.
        assert pe_service.obtener_estado("proceso-sap-no-existe") is None

    def test_fallo_al_empujar_no_rompe_el_envio(self, monkeypatch):
        """Best-effort: un fallo (ej. Redis caído) no debe propagar."""
        def _redis_roto():
            raise RuntimeError("redis caído")

        monkeypatch.setattr(
            "src.database.services.proceso_estado_service.get_redis_client", _redis_roto
        )
        # No debe lanzar excepción.
        StockTransferService._empujar_progreso_itr(
            "proceso-sap-x", None, "oc-1", _resultado_tienda("TRL-QSN"), 1, 1
        )


class TestEnviarItrsASapEmpujaProgreso:
    def test_cada_tienda_resuelta_empuja_progreso(self, monkeypatch):
        pe_service = _proceso_estado_service_con_fake_redis()
        monkeypatch.setattr(
            "src.database.services.proceso_estado_service.get_redis_client",
            lambda: pe_service.redis_client,
        )
        process_id = "proceso-sap-envio"
        _preparar_proceso_en_curso(pe_service, process_id)

        service = _service()
        result = {
            "total_tiendas": 1, "transferencias_creadas": 0, "transferencias_errores": 0,
            "transferencias_encoladas": 0, "resultados": [],
        }
        from unittest.mock import patch
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={
                "success": True,
                "response": {"success": True, "doc_entry": 400970, "doc_num": 70215585},
                "attempts": 1,
                "error": None,
            },
        ):
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-PSM"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={"TRL-PSM": "ROLAND PORTAL SHOPPING MANTA"},
                result=result,
                process_id=process_id,
                oc_id="oc-1",
            )

        estado = pe_service.obtener_estado(process_id)
        assert estado["data"]["itr_detalle"] == [
            {
                "oc_id": "oc-1",
                "tienda_codigo": "TRL-PSM",
                "tienda_nombre": "ROLAND PORTAL SHOPPING MANTA",
                "estado": "confirmada",
                "doc_num": 70215585,
            }
        ]
