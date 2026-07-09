"""
Tests del cliente SAP: validación de formato de ItemCode.

Verifica que se acepten códigos con los caracteres que SAP usa (incl. / y _).
"""

import pytest

from src.database.clients.sap_client import SAPClient


class TestSAPClientItemCodeValidation:
    """Validación de formato de ItemCode (sin conexión a SAP)."""

    def test_pattern_accepts_slash(self):
        """Códigos con barra (ej. R463.1012.GR/AZ) son válidos."""
        assert SAPClient.ITEM_CODE_PATTERN.match("R463.1012.GR/AZ") is not None

    def test_pattern_accepts_underscore(self):
        """Códigos con guion bajo son válidos."""
        assert SAPClient.ITEM_CODE_PATTERN.match("R463_1012_GR") is not None

    def test_pattern_accepts_common_codes(self):
        """Códigos típicos siguen siendo válidos."""
        assert SAPClient.ITEM_CODE_PATTERN.match("5-0012.9") is not None
        assert SAPClient.ITEM_CODE_PATTERN.match("756.10.GR") is not None
        assert SAPClient.ITEM_CODE_PATTERN.match("R5244.1012") is not None

    def test_validate_item_code_accepts_slash(self):
        """_validate_item_code acepta código con barra."""
        client = SAPClient()
        assert client._validate_item_code("R463.1012.GR/AZ") is True

    def test_validate_item_code_rejects_single_quote(self):
        """Caracteres peligrosos para SQL siguen rechazados."""
        client = SAPClient()
        assert client._validate_item_code("R463'; DROP TABLE OITM;--") is False
