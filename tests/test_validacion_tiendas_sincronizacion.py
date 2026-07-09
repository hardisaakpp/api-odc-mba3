"""
Test: Validación de sincronización entre ID TIENDA y NOMBRE TIENDA

Regla: Si hay información en la columna ID TIENDA debe haber en NOMBRE TIENDA y viceversa.
Si no hay información en una de las 2 columnas, la subida del excel debe ser interrumpida.
"""

import io
import pytest
from typing import Sequence
from openpyxl import Workbook
from src.database.services.pedido_parser import PedidoParser


@pytest.fixture
def parser():
    """Crear una instancia del parser."""
    return PedidoParser()


def _create_excel_tiendas(rows: Sequence[tuple[str | None, str | None, str | None]]) -> bytes:
    """
    Crear un Excel con hoja Tiendas.
    
    Args:
        rows: Lista de tuplas (id_tienda, nombre_tienda, activo)
        
    Returns:
        Contenido del Excel en bytes
    """
    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("No se pudo crear hoja en Workbook")
    
    ws.title = "Tiendas"
    
    # Header
    ws['A1'] = 'ID TIENDA'
    ws['B1'] = 'NOMBRE TIENDA'
    ws['C1'] = 'ACTIVO'
    
    # Datos
    for idx, (id_tienda, nombre_tienda, activo) in enumerate(rows, start=2):
        ws[f'A{idx}'] = id_tienda
        ws[f'B{idx}'] = nombre_tienda
        ws[f'C{idx}'] = activo
    
    # Guardar a bytes
    excel_bytes = io.BytesIO()
    wb.save(excel_bytes)
    excel_bytes.seek(0)
    return excel_bytes.getvalue()


class TestValidacionSincronizacionTiendas:
    """Tests para validar sincronización ID TIENDA ↔ NOMBRE TIENDA"""

    def test_tiendas_validas_sincronizadas(self, parser):
        """✅ TEST 1: Tiendas válidas con ID y NOMBRE sincronizados"""
        rows = [
            ("TRL-QSN", "ROLAND QUICENTRO NORTE", "SI"),
            ("TRL-CCR", "ROLAND CENTRO COMERCIAL", "SI"),
            ("TRL-AQZ", "ROLAND ANTARES QUITO", "NO"),
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        catalogo = parser.leer_hoja_tiendas(excel_bytes)
        
        assert len(catalogo) == 3
        assert catalogo["TRL-QSN"]["nombre"] == "ROLAND QUICENTRO NORTE"
        assert catalogo["TRL-QSN"]["activa"] is True
        assert catalogo["TRL-AQZ"]["activa"] is False

    def test_tienda_con_id_sin_nombre(self, parser):
        """❌ TEST 2: Tienda con ID TIENDA pero SIN NOMBRE TIENDA"""
        rows = [
            ("TRL-QSN", "ROLAND QUICENTRO NORTE", "SI"),
            ("TRL-CCR", None, "SI"),  # ❌ ID sin NOMBRE
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        # Debe lanzar ValueError
        with pytest.raises(ValueError) as exc_info:
            parser.leer_hoja_tiendas(excel_bytes)
        
        error_msg = str(exc_info.value)
        assert "sincronización" in error_msg.lower()
        assert "ID TIENDA" in error_msg
        assert "NOMBRE TIENDA" in error_msg

    def test_tienda_sin_id_con_nombre(self, parser):
        """❌ TEST 3: Tienda con NOMBRE TIENDA pero SIN ID TIENDA"""
        rows = [
            ("TRL-QSN", "ROLAND QUICENTRO NORTE", "SI"),
            (None, "ROLAND CENTRO COMERCIAL", "SI"),  # ❌ NOMBRE sin ID
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        # Debe lanzar ValueError
        with pytest.raises(ValueError) as exc_info:
            parser.leer_hoja_tiendas(excel_bytes)
        
        error_msg = str(exc_info.value)
        assert "sincronización" in error_msg.lower()

    def test_tienda_sin_id_sin_nombre(self, parser):
        """⚠️ TEST 4: Tienda vacía en ID y NOMBRE (debe ignorarse)"""
        rows = [
            ("TRL-QSN", "ROLAND QUICENTRO NORTE", "SI"),
            (None, None, "SI"),  # Fila sin datos - se ignora
            ("TRL-AQZ", "ROLAND ANTARES", "NO"),
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        catalogo = parser.leer_hoja_tiendas(excel_bytes)
        
        # Debe cargar solo las 2 tiendas válidas
        assert len(catalogo) == 2
        assert "TRL-QSN" in catalogo
        assert "TRL-AQZ" in catalogo

    def test_tiendas_completamente_vacias(self, parser):
        """⚠️ TEST 5: Todas las filas de tiendas están vacías"""
        rows = [
            (None, None, None),
            (None, None, None),
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        catalogo = parser.leer_hoja_tiendas(excel_bytes)
        
        # Debe retornar catálogo vacío sin error
        assert catalogo == {}

    def test_espacios_en_blanco_son_considerados_vacios(self, parser):
        """❌ TEST 6: Espacios en blanco son considerados como vacío"""
        rows = [
            ("TRL-QSN", "ROLAND QUICENTRO NORTE", "SI"),
            ("TRL-CCR", "   ", "SI"),  # ❌ Solo espacios = vacío
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        with pytest.raises(ValueError) as exc_info:
            parser.leer_hoja_tiendas(excel_bytes)
        
        error_msg = str(exc_info.value)
        assert "sincronización" in error_msg.lower()

    def test_id_vacio_nombre_con_espacios(self, parser):
        """❌ TEST 7: ID vacío pero NOMBRE con espacios (debe fallar)"""
        rows = [
            ("TRL-QSN", "ROLAND QUICENTRO NORTE", "SI"),
            (None, "ROLAND CON ESPACIO", "SI"),  # ❌ NOMBRE sin ID
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        with pytest.raises(ValueError) as exc_info:
            parser.leer_hoja_tiendas(excel_bytes)
        
        error_msg = str(exc_info.value)
        assert "sincronización" in error_msg.lower()

    def test_multiples_filas_problematicas(self, parser):
        """❌ TEST 8: Múltiples filas con problemas de sincronización"""
        rows = [
            ("TRL-QSN", "ROLAND QUICENTRO NORTE", "SI"),
            ("TRL-CCR", None, "SI"),  # ❌ Problema 1
            ("TRL-AQZ", "ROLAND ANTARES", "NO"),
            (None, "ROLAND SIN ID", "SI"),  # ❌ Problema 2
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        with pytest.raises(ValueError) as exc_info:
            parser.leer_hoja_tiendas(excel_bytes)
        
        error_msg = str(exc_info.value)
        assert "sincronización" in error_msg.lower()
        assert "2" in error_msg or "filas" in error_msg.lower()

    def test_tiendas_con_activo_vacio_pero_id_nombre_completo(self, parser):
        """✅ TEST 9: ID y NOMBRE completos pero ACTIVO vacío (DEBE permitirse)"""
        rows = [
            ("TRL-QSN", "ROLAND QUICENTRO NORTE", "SI"),
            ("TRL-CCR", "ROLAND CENTRO COMERCIAL", None),  # ACTIVO vacío pero ID y NOMBRE presentes
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        # Debe cargarse sin error (ACTIVO toma valor por defecto True)
        catalogo = parser.leer_hoja_tiendas(excel_bytes)
        
        assert len(catalogo) == 2
        assert catalogo["TRL-CCR"]["activa"] is True  # Por defecto

    def test_caso_real_con_multiples_tiendas_validas_y_una_invalida(self, parser):
        """❌ TEST 10: Caso real con 5 tiendas válidas pero 1 invalida al medio"""
        rows = [
            ("TRL-QSN", "ROLAND QUICENTRO NORTE", "SI"),
            ("TRL-CCR", "ROLAND CENTRO COMERCIAL", "SI"),
            ("TRL-AQZ", None, "SI"),  # ❌ ID sin NOMBRE
            ("TRL-SAN", "ROLAND SANTIAGO", "NO"),
            ("TRL-VIC", "ROLAND VICTORIA", "SI"),
        ]
        excel_bytes = _create_excel_tiendas(rows)
        
        with pytest.raises(ValueError) as exc_info:
            parser.leer_hoja_tiendas(excel_bytes)
        
        error_msg = str(exc_info.value)
        assert "sincronización" in error_msg.lower()
        # Fila problemática es la 4 (tercera fila de datos después del header)
        assert ("Filas problemáticas" in error_msg) or ("filas" in error_msg.lower())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
