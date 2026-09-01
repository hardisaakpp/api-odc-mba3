"""
Tests para _enrich_oc_actions con estado ENVIANDO.

Antes de esto, una ODC ENVIANDO caía en el else implícito (mostrar_descargar_pdf
= not mostrar_reintentar = True) -- mostraría un botón "Descargar PDF" sin
sentido para una ODC que todavía no tiene nada que descargar.
"""

from src.endpoints.ordenes_compra import _enrich_oc_actions


class TestEnrichOcActionsEnviando:
    def test_enviando_no_muestra_reintentar_ni_descargar_pdf(self):
        oc = {"estado": "ENVIANDO"}

        _enrich_oc_actions(oc)

        assert oc["mostrar_reintentar"] is False
        assert oc["mostrar_descargar_pdf"] is False

    def test_pendiente_sigue_mostrando_reintentar(self):
        """Regresión: no romper el comportamiento existente de los otros estados."""
        oc = {"estado": "PENDIENTE"}

        _enrich_oc_actions(oc)

        assert oc["mostrar_reintentar"] is True
        assert oc["mostrar_descargar_pdf"] is False

    def test_enviada_sigue_mostrando_descargar_pdf(self):
        oc = {"estado": "ENVIADA"}

        _enrich_oc_actions(oc)

        assert oc["mostrar_reintentar"] is False
        assert oc["mostrar_descargar_pdf"] is True
