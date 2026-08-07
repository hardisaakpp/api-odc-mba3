"""
Tests del soporte 'Encolada' (HTTP 202) en SolicitudTransferenciaRepository.

El middleware SAP encola una ITR (202 + jobId) cuando el Service Layer está
saturado, en vez de fallar. Antes de esto ese 202 se persistía como
estado='Error' definitivo y el reintento reenviaba la creación a ciegas —
riesgo de ITR duplicada si el job original terminaba completándose en
segundo plano. Estos tests cubren: persistir el job_id con estado 'Encolada',
que 'Encolada' cuente como pendiente de reintento, y la consulta que permite
resolverla antes de reenviar.

Usa un cursor mockeado (mismo patrón que el resto de tests de repositorios).
"""

from unittest.mock import MagicMock

from src.database.repositories.solicitud_transferencia_repository import (
    SolicitudTransferenciaRepository,
)


class TestInsertOneDetalleEncolada:
    def test_resultado_queued_persiste_estado_encolada_y_job_id(self):
        conn = MagicMock()
        cursor = MagicMock()
        repo = SolicitudTransferenciaRepository(conn)

        ok = repo._insert_one_detalle(
            cursor,
            "solicitud-1",
            {
                "tienda_codigo": "TRL-PSC",
                "tienda_nombre": "Portal Shopping",
                "success": False,
                "queued": True,
                "job_id": "job-123",
                "error": "SAP saturado: la solicitud fue encolada por el middleware (jobId=job-123)",
            },
        )

        assert ok is True
        args = cursor.execute.call_args.args[1]
        # Orden de columnas: solicitud_transferencia_id, tienda_codigo, tienda_nombre,
        # estado, doc_num, doc_entry, error_mensaje, job_id
        assert args[3] == "Encolada"
        assert args[7] == "job-123"

    def test_resultado_normal_no_afectado_por_el_cambio(self):
        conn = MagicMock()
        cursor = MagicMock()
        repo = SolicitudTransferenciaRepository(conn)

        repo._insert_one_detalle(
            cursor, "solicitud-1",
            {"tienda_codigo": "TRL-QSN", "success": True, "doc_num": 1, "doc_entry": 2},
        )
        args = cursor.execute.call_args.args[1]
        assert args[3] == "Creada"
        assert args[7] is None

    def test_resultado_error_normal_no_marca_encolada(self):
        conn = MagicMock()
        cursor = MagicMock()
        repo = SolicitudTransferenciaRepository(conn)

        repo._insert_one_detalle(
            cursor, "solicitud-1",
            {"tienda_codigo": "TRL-QSN", "success": False, "error": "Error real de SAP"},
        )
        args = cursor.execute.call_args.args[1]
        assert args[3] == "Error"
        assert args[7] is None


class TestGetTiendasPendientesReintentoStIncluyeEncolada:
    def test_encolada_cuenta_como_pendiente(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        # 1ra query: _get_latest_solicitud_transferencia_id -> fetchone
        # 2da query: get_tiendas_itr_ok_norms_por_oc_id -> fetchall (vacío)
        # 3ra query: SELECT DISTINCT tienda_codigo ... estado IN ('Error','Encolada') -> fetchall
        cursor.fetchone.side_effect = [("solicitud-1",)]
        cursor.fetchall.side_effect = [[], [("TRL-PSC",)]]

        repo = SolicitudTransferenciaRepository(conn)
        pendientes = repo.get_tiendas_pendientes_reintento_st("oc-1")

        assert pendientes == ["TRL-PSC"]
        ultima_query = cursor.execute.call_args_list[-1].args[0]
        assert "'Error', 'Encolada'" in ultima_query


class TestGetTiendasEncoladasConJobId:
    def test_retorna_mapa_tienda_normalizada_a_job_id(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = ("solicitud-1",)
        cursor.fetchall.return_value = [("trl-psc", "job-123")]

        repo = SolicitudTransferenciaRepository(conn)
        resultado = repo.get_tiendas_encoladas_con_job_id("oc-1", ["TRL-PSC"])

        assert resultado == {"TRL-PSC": "job-123"}

    def test_filtra_tiendas_fuera_del_objetivo(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = ("solicitud-1",)
        cursor.fetchall.return_value = [("TRL-PSC", "job-123"), ("TRL-OTRA", "job-999")]

        repo = SolicitudTransferenciaRepository(conn)
        resultado = repo.get_tiendas_encoladas_con_job_id("oc-1", ["TRL-PSC"])

        assert resultado == {"TRL-PSC": "job-123"}

    def test_sin_tiendas_no_consulta_bd(self):
        conn = MagicMock()
        repo = SolicitudTransferenciaRepository(conn)
        assert repo.get_tiendas_encoladas_con_job_id("oc-1", []) == {}
        conn.cursor.assert_not_called()

    def test_sin_solicitud_previa_retorna_vacio(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = None

        repo = SolicitudTransferenciaRepository(conn)
        assert repo.get_tiendas_encoladas_con_job_id("oc-1", ["TRL-PSC"]) == {}
