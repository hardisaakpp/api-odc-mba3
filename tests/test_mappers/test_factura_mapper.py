"""
Tests para FacturaMapper.
"""

import pytest  # type: ignore[reportMissingImports]
from datetime import datetime

from src.database.mappers.factura_mapper import FacturaMapper


class TestFacturaMapperParseDate:
    """Tests para parse_date."""
    
    def test_parse_date_valid(self):
        """Test que parsea fecha válida correctamente."""
        result = FacturaMapper.parse_date("2025-01-21")
        assert result == "2025-01-21"
    
    def test_parse_date_long_format(self):
        """Test que extrae solo YYYY-MM-DD de formato largo."""
        result = FacturaMapper.parse_date("2025-01-21T12:00:00")
        assert result == "2025-01-21"
    
    def test_parse_date_none(self):
        """Test que retorna None para None."""
        result = FacturaMapper.parse_date(None)
        assert result is None
    
    def test_parse_date_empty_string(self):
        """Test que retorna None para string vacío."""
        result = FacturaMapper.parse_date("")
        assert result is None
    
    def test_parse_date_invalid_format(self):
        """Test que retorna None para formato inválido."""
        result = FacturaMapper.parse_date("invalid")
        assert result is None


class TestFacturaMapperExtractEmpresaFromCodigo:
    """Tests para extract_empresa_from_codigo."""
    
    def test_extract_empresa_fe_format(self):
        """Test que extrae empresa de formato FE-*-EMPRESA."""
        result = FacturaMapper.extract_empresa_from_codigo("FE-123-TRAYO")
        assert result == "TRAYO"
    
    def test_extract_empresa_remsi_format(self):
        """Test que extrae empresa de formato REMSI-*-EMPRESA."""
        result = FacturaMapper.extract_empresa_from_codigo("REMSI-456-MABEL")
        assert result == "MABEL"
    
    def test_extract_empresa_none(self):
        """Test que retorna None para None."""
        result = FacturaMapper.extract_empresa_from_codigo(None)
        assert result is None
    
    def test_extract_empresa_short_format(self):
        """Test que retorna None para formato corto."""
        result = FacturaMapper.extract_empresa_from_codigo("FE-123")
        assert result is None
    
    def test_extract_empresa_empty_string(self):
        """Test que retorna None para string vacío."""
        result = FacturaMapper.extract_empresa_from_codigo("")
        assert result is None


class TestFacturaMapperToDespachoCabecera:
    """Tests para to_despacho_cabecera."""
    
    def test_to_despacho_cabecera_complete(self):
        """Test que mapea factura completa correctamente."""
        factura = {
            "CODIGO_FACTURA": "FE-123-TRAYO",
            "EMPRESA": "TRAYO",
            "CODIGO_CLIENTE": "CLI001",
            "FECHA_FACTURA": "2025-01-21",
            "ANULADA": False,
            "NUMERO_PEDIDO_SISTEMA": "176120",
            "NUMERO_ORDEN": 129165,
            "NUMERO_FACTURA": 900125351,
            "TIPO_DOCUMENTO": "FE",
            "ORDEN_COMPRA": "OC001",
            "ORDEN_COMPRA_CLIENTE": "OC_CLI001",
            "Remision_Facturada": True,
            "NumIDFacturaRelacionada": 123,
            "CODIGO_DESPACHO": 456,
            "CODIGO_BODEGA": "BOD001",
            "CONFIRMADO": True
        }
        
        result = FacturaMapper.to_despacho_cabecera(factura)
        
        assert result["empresa"] == "TRAYO"
        assert result["codigo_cliente"] == "CLI001"
        assert result["fecha_despacho"] == "2025-01-21"
        assert result["fecha_factura"] == "2025-01-21"
        assert result["codigo_factura"] == "FE-123-TRAYO"
        assert result["anulada"] == 0
        assert result["confirmado"] == 1
        assert result["remision_facturada"] == 1
    
    def test_to_despacho_cabecera_without_empresa(self):
        """Test que extrae empresa del código si no está en factura."""
        factura = {
            "CODIGO_FACTURA": "FE-123-TRAYO",
            "FECHA_FACTURA": "2025-01-21",
            "CODIGO_CLIENTE": "CLI001",
            "TIPO_DOCUMENTO": "FE"
        }
        
        result = FacturaMapper.to_despacho_cabecera(factura)
        
        assert result["empresa"] == "TRAYO"  # Extraído del código
    
    def test_to_despacho_cabecera_without_fecha(self):
        """Test que usa fecha actual si no hay fecha de factura."""
        factura = {
            "CODIGO_FACTURA": "FE-123-TRAYO",
            "CODIGO_CLIENTE": "CLI001",
            "TIPO_DOCUMENTO": "FE"
        }
        
        result = FacturaMapper.to_despacho_cabecera(factura)
        
        # Debe tener una fecha (fecha actual)
        assert result["fecha_despacho"] is not None
        assert len(result["fecha_despacho"]) == 10  # YYYY-MM-DD
    
    def test_to_despacho_cabecera_defaults(self):
        """Test que usa valores por defecto para campos requeridos."""
        factura = {
            "CODIGO_FACTURA": "FE-123"
        }
        
        result = FacturaMapper.to_despacho_cabecera(factura)
        
        assert result["empresa"] == "SIN_EMPRESA"
        assert result["codigo_cliente"] == "SIN_CLIENTE"
        assert result["tipo_documento"] == "SIN_TIPO"
        assert result["numero_factura"] == 0
    
    def test_to_despacho_cabecera_extract_numero_factura(self):
        """Test que extrae número de factura del código."""
        factura = {
            "CODIGO_FACTURA": "FE-900125351-TRAYO",
            "CODIGO_CLIENTE": "CLI001",
            "TIPO_DOCUMENTO": "FE"
        }
        
        result = FacturaMapper.to_despacho_cabecera(factura)
        
        assert result["numero_factura"] == 900125351


class TestFacturaMapperToDespachoDetalle:
    """Tests para to_despacho_detalle."""
    
    def test_to_despacho_detalle_complete(self):
        """Test que mapea línea completa correctamente."""
        linea = {
            "Codigo": "5-0012.9",
            "Nombre": "Producto Test",
            "Cantidad": 10.0,
            "PrecioUnitario": 4.65,
            "TotalLinea": 46.5,
            "Descuento": 0.0,
            "Impuesto": 8.37
        }
        
        result = FacturaMapper.to_despacho_detalle(linea, "GrabarLineasProd")
        
        assert result is not None
        assert result["sku"] == "5-0012.9"
        assert result["nombre_producto"] == "Producto Test"
        assert result["cantidad"] == 10.0
        assert result["precio_unitario"] == 4.65
        assert result["total_linea"] == 46.5
        assert result["tipo_linea"] == "GrabarLineasProd"
    
    def test_to_despacho_detalle_with_sap_info(self):
        """Test que calcula conversiones SAP correctamente."""
        linea = {
            "Codigo": "5-0012.9",
            "Cantidad": 10.0,  # 10 docenas
            "TotalLinea": 46.5
        }
        
        sap_info = {
            "unidad_conversion": 4.0,  # 1 docena = 4 packs
            "pack_sap": "X3"
        }
        
        result = FacturaMapper.to_despacho_detalle(linea, "GrabarLineasProd", sap_info)
        
        assert result is not None
        # 10 docenas × 4 = 40 packs
        assert result["cantidad_sap"] == 40.0
        # 46.5 / 40 = 1.1625 precio por pack
        assert result["precio_unitario_sap"] == pytest.approx(1.1625, rel=1e-3)
        assert result["unidad_sap"] == "X3"
    
    def test_to_despacho_detalle_without_codigo(self):
        """Test que retorna None si no hay código."""
        linea = {
            "Nombre": "Producto sin código"
        }
        
        result = FacturaMapper.to_despacho_detalle(linea, "GrabarLineasProd")
        
        assert result is None
    
    def test_to_despacho_detalle_empty_codigo(self):
        """Test que retorna None si código está vacío."""
        linea = {
            "Codigo": "   ",
            "Cantidad": 10.0
        }
        
        result = FacturaMapper.to_despacho_detalle(linea, "GrabarLineasProd")
        
        assert result is None
    
    def test_to_despacho_detalle_with_none_values(self):
        """Test que maneja valores None correctamente."""
        linea = {
            "Codigo": "5-0012.9",
            "Cantidad": None,
            "TotalLinea": None,
            "PrecioUnitario": None
        }
        
        result = FacturaMapper.to_despacho_detalle(linea, "GrabarLineasProd")
        
        assert result is not None
        assert result["cantidad"] == 0
        assert result["total_linea"] == 0
        assert result["precio_unitario"] == 0

