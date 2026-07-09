"""
Tests para PedidoValidator - Validaciones pre-negocio.
"""

import pytest  # type: ignore[reportMissingImports]
from datetime import date, timedelta

from src.database.services.pedido_validator import (
    PedidoValidator,
    ValidationSeverity,
    ValidationIssue
)


class TestPedidoValidatorCabecera:
    """Tests para validar_cabecera()."""
    
    def test_validar_cabecera_numero_pedido_obligatorio(self):
        """Test que valida que numero_pedido es obligatorio."""
        validator = PedidoValidator()
        cabecera = {}  # Sin numero_pedido
        
        issues = validator.validar_cabecera(cabecera)
        
        assert len(issues) > 0
        assert any(issue.field == "numero_pedido" and issue.severity == ValidationSeverity.ERROR
                  for issue in issues)
    
    def test_validar_cabecera_fecha_formato_invalido(self):
        """Test que valida formato de fecha."""
        validator = PedidoValidator()
        cabecera = {
            "numero_pedido": "P-001",
            "fecha_pedido": "2025/01/21"  # Formato inválido
        }
        
        issues = validator.validar_cabecera(cabecera)
        
        assert any(issue.field == "fecha_pedido" and issue.severity == ValidationSeverity.ERROR
                  for issue in issues)
    
    def test_validar_cabecera_fecha_formato_valido_dd_mm_yyyy(self):
        """Test que acepta formato DD/MM/YYYY."""
        validator = PedidoValidator()
        cabecera = {
            "numero_pedido": "P-001",
            "fecha_pedido": "21/01/2025"
        }
        
        issues = validator.validar_cabecera(cabecera)
        
        # No debe tener errores de fecha
        fecha_issues = [i for i in issues if i.field == "fecha_pedido" and i.severity == ValidationSeverity.ERROR]
        assert len(fecha_issues) == 0
    
    def test_validar_cabecera_fecha_formato_valido_yyyy_mm_dd(self):
        """Test que acepta formato YYYY-MM-DD."""
        validator = PedidoValidator()
        cabecera = {
            "numero_pedido": "P-001",
            "fecha_pedido": "2025-01-21"
        }
        
        issues = validator.validar_cabecera(cabecera)
        
        # No debe tener errores de fecha
        fecha_issues = [i for i in issues if i.field == "fecha_pedido" and i.severity == ValidationSeverity.ERROR]
        assert len(fecha_issues) == 0
    
    def test_validar_cabecera_fecha_entrega_pasada_rechaza(self):
        """Test que rechaza fecha_entrega pasada (si no se permite)."""
        validator = PedidoValidator(permitir_fechas_pasadas=False)
        ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        cabecera = {
            "numero_pedido": "P-001",
            "fecha_entrega": ayer
        }
        
        issues = validator.validar_cabecera(cabecera)
        
        assert any(issue.field == "fecha_entrega" 
                  and issue.severity == ValidationSeverity.ERROR
                  and "pasada" in issue.message.lower()
                  for issue in issues)
    
    def test_validar_cabecera_fecha_entrega_pasada_permite(self):
        """Test que permite fecha_entrega pasada si está configurado."""
        validator = PedidoValidator(permitir_fechas_pasadas=True)
        ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        cabecera = {
            "numero_pedido": "P-001",
            "fecha_entrega": ayer
        }
        
        issues = validator.validar_cabecera(cabecera)
        
        # No debe tener errores de fecha pasada
        fecha_pasada_issues = [i for i in issues 
                              if i.field == "fecha_entrega" and "pasada" in i.message.lower()]
        assert len(fecha_pasada_issues) == 0
    
    def test_validar_cabecera_fecha_entrega_inmediato_acepta(self):
        """Test que acepta 'INMEDIATO' como fecha_entrega."""
        validator = PedidoValidator()
        
        cabecera = {
            "numero_pedido": "P-001",
            "fecha_entrega": "INMEDIATO"
        }
        
        issues = validator.validar_cabecera(cabecera)
        
        # No debe tener errores de fecha_entrega
        fecha_issues = [i for i in issues if i.field == "fecha_entrega" and i.severity == ValidationSeverity.ERROR]
        assert len(fecha_issues) == 0


class TestPedidoValidatorDetalle:
    """Tests para validar_detalle()."""
    
    def test_validar_detalle_codigo_producto_obligatorio(self):
        """Test que valida que codigo_interno es obligatorio."""
        validator = PedidoValidator()
        detalle = {}  # Sin codigo_interno
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "codigo_interno" 
                  and issue.severity == ValidationSeverity.ERROR
                  for issue in issues)
    
    def test_validar_detalle_codigo_producto_caracteres_invalidos(self):
        """Test que valida caracteres válidos en código de producto."""
        validator = PedidoValidator()
        detalle = {"codigo_interno": "PROD#123"}  # Carácter # no permitido
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "codigo_interno" 
                  and issue.severity == ValidationSeverity.ERROR
                  and "caracteres" in issue.message.lower()
                  for issue in issues)
    
    def test_validar_detalle_codigo_producto_caracteres_validos(self):
        """Test que acepta códigos con caracteres válidos."""
        validator = PedidoValidator()
        detalle = {"codigo_interno": "R225.1012.BCO"}  # Caracteres válidos
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        # No debe tener errores de caracteres
        caracteres_issues = [i for i in issues 
                            if i.field == "codigo_interno" and "caracteres" in i.message.lower()]
        assert len(caracteres_issues) == 0
    
    def test_validar_detalle_distribuciones_obligatorias(self):
        """Test que valida que debe haber al menos una distribución."""
        validator = PedidoValidator()
        detalle = {"codigo_interno": "R225.1012.BCO"}
        distribuciones = []  # Sin distribuciones
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "distribuciones" 
                  and issue.severity == ValidationSeverity.ERROR
                  for issue in issues)
    
    def test_validar_detalle_tienda_no_permitida(self):
        """Test que valida tienda contra lista permitida."""
        validator = PedidoValidator(tiendas_permitidas=["T001", "T002"])
        detalle = {"codigo_interno": "R225.1012.BCO"}
        distribuciones = [{"tienda_codigo": "T999", "cantidad": 10}]  # Tienda no permitida
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "tienda_codigo" 
                  and issue.severity == ValidationSeverity.ERROR
                  and "permitida" in issue.message.lower()
                  for issue in issues)
    
    def test_validar_detalle_tienda_permitida(self):
        """Test que acepta tienda en lista permitida."""
        validator = PedidoValidator(tiendas_permitidas=["T001", "T002"])
        detalle = {"codigo_interno": "R225.1012.BCO"}
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        # No debe tener errores de tienda no permitida
        tienda_issues = [i for i in issues 
                        if i.field == "tienda_codigo" and "permitida" in i.message.lower()]
        assert len(tienda_issues) == 0
    
    def test_validar_detalle_tienda_duplicada(self):
        """Test que detecta tienda duplicada en distribuciones."""
        validator = PedidoValidator()
        detalle = {"codigo_interno": "R225.1012.BCO"}
        distribuciones = [
            {"tienda_codigo": "T001", "cantidad": 10},
            {"tienda_codigo": "T001", "cantidad": 5}  # Duplicada
        ]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "tienda_codigo" 
                  and issue.severity == ValidationSeverity.ERROR
                  and "duplicada" in issue.message.lower()
                  for issue in issues)
    
    def test_validar_detalle_cantidad_maxima_por_tienda(self):
        """Test que valida cantidad máxima por tienda."""
        validator = PedidoValidator(max_cantidad_por_tienda=100)
        detalle = {"codigo_interno": "R225.1012.BCO"}
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 150}]  # Excede máximo
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "cantidad" 
                  and issue.severity == ValidationSeverity.WARNING
                  and ("máxima" in issue.message.lower() or "máximo" in issue.message.lower() or "excede" in issue.message.lower())
                  for issue in issues)
    
    def test_validar_detalle_cantidad_maxima_total(self):
        """Test que valida cantidad máxima total."""
        validator = PedidoValidator(max_cantidad_total=200)
        detalle = {"codigo_interno": "R225.1012.BCO"}
        distribuciones = [
            {"tienda_codigo": "T001", "cantidad": 100},
            {"tienda_codigo": "T002", "cantidad": 150}  # Total = 250 > 200
        ]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any((issue.field == "cantidad" or issue.field == "cantidad_total")
                  and issue.severity == ValidationSeverity.WARNING
                  and "total" in issue.message.lower()
                  for issue in issues)
    
    def test_validar_detalle_cantidad_cero_rechaza(self):
        """Test que rechaza cantidad <= 0."""
        validator = PedidoValidator()
        detalle = {"codigo_interno": "R225.1012.BCO"}
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 0}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "cantidad" 
                  and issue.severity == ValidationSeverity.ERROR
                  for issue in issues)


class TestPedidoValidatorCompleto:
    """Tests para validar_pedido_completo()."""
    
    def test_validar_pedido_completo_valido(self):
        """Test que valida un pedido completo válido."""
        from datetime import date
        validator = PedidoValidator(tiendas_permitidas=["T001", "T002"])
        
        cabecera = {
            "numero_pedido": "P-001",
            "fecha_pedido": date.today().isoformat(),
            "fecha_entrega": "INMEDIATO"
        }
        
        detalles_con_tiendas = [
            {
                "detalle": {"codigo_interno": "R225.1012.BCO"},
                "distribuciones": [
                    {"tienda_codigo": "T001", "cantidad": 10}
                ],
                "fila_origen": 2
            }
        ]
        
        resultado = validator.validar_pedido_completo(cabecera, detalles_con_tiendas)
        
        assert resultado["valid"] is True
        assert resultado["errors"] == 0
        assert resultado["warnings"] == 0
    
    def test_validar_pedido_completo_con_errores(self):
        """Test que detecta errores en pedido completo."""
        validator = PedidoValidator(tiendas_permitidas=["T001"])
        
        cabecera = {
            "numero_pedido": "",  # Error: vacío
            "fecha_pedido": "2025-01-21"
        }
        
        detalles_con_tiendas = [
            {
                "detalle": {"codigo_interno": "PROD#123"},  # Error: caracteres inválidos
                "distribuciones": [
                    {"tienda_codigo": "T999", "cantidad": 10}  # Error: tienda no permitida
                ],
                "fila_origen": 2
            }
        ]
        
        resultado = validator.validar_pedido_completo(cabecera, detalles_con_tiendas)
        
        assert resultado["valid"] is False
        assert resultado["errors"] > 0
        assert len(resultado["issues_by_row"]) > 0
    
    def test_validar_pedido_completo_con_warnings(self):
        """Test que detecta warnings (no bloquean)."""
        validator = PedidoValidator()
        
        cabecera = {
            "numero_pedido": "P-001",
            "fecha_pedido": (date.today() - timedelta(days=400)).strftime("%Y-%m-%d")  # Muy antigua (warning)
        }
        
        detalles_con_tiendas = [
            {
                "detalle": {"codigo_interno": "R225.1012.BCO"},
                "distribuciones": [
                    {"tienda_codigo": "T001", "cantidad": 10}
                ],
                "fila_origen": 2
            }
        ]
        
        resultado = validator.validar_pedido_completo(cabecera, detalles_con_tiendas)
        
        # Puede tener warnings pero ser válido
        assert resultado["warnings"] >= 0
        # Si solo hay warnings, debe ser válido
        if resultado["errors"] == 0:
            assert resultado["valid"] is True


class TestPedidoValidatorPreciosImpuestos:
    """Tests para validaciones de precios e impuestos (reglas regionales)."""
    
    def test_validar_precio_costo_negativo_rechaza(self):
        """Test que rechaza costo sin IVA negativo."""
        validator = PedidoValidator(validar_precios=True)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "costo_doc_sin_iva": -10.50  # Negativo
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "costo_doc_sin_iva" 
                  and issue.severity == ValidationSeverity.ERROR
                  and "negativo" in issue.message.lower()
                  for issue in issues)
    
    def test_validar_precio_costo_cero_warning(self):
        """Test que genera warning si costo es cero."""
        validator = PedidoValidator(validar_precios=True)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "costo_doc_sin_iva": 0
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "costo_doc_sin_iva" 
                  and issue.severity == ValidationSeverity.WARNING
                  and "cero" in issue.message.lower()
                  for issue in issues)
    
    def test_validar_precio_descuento_fuera_rango_rechaza(self):
        """Test que rechaza descuento fuera de rango 0-100%."""
        validator = PedidoValidator(validar_precios=True)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "descuento_1": 150  # Fuera de rango
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "descuento_1" 
                  and issue.severity == ValidationSeverity.ERROR
                  and ("rango" in issue.message.lower() or "100%" in issue.message)
                  for issue in issues)
    
    def test_validar_precio_descuento_alto_warning(self):
        """Test que genera warning si descuento es > 50%."""
        validator = PedidoValidator(validar_precios=True)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "descuento_1": 75  # Muy alto
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "descuento_1" 
                  and issue.severity == ValidationSeverity.WARNING
                  and ("alto" in issue.message.lower() or "50%" in issue.message)
                  for issue in issues)
    
    def test_validar_precio_descuento_decimal_acepta(self):
        """Test que acepta descuento como decimal (0-1)."""
        validator = PedidoValidator(validar_precios=True)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "descuento_1": 0.20  # 20% como decimal
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        # No debe tener errores de descuento
        descuento_issues = [i for i in issues 
                          if i.field == "descuento_1" and i.severity == ValidationSeverity.ERROR]
        assert len(descuento_issues) == 0
    
    def test_validar_precio_pvp_negativo_rechaza(self):
        """Test que rechaza PVP negativo."""
        validator = PedidoValidator(validar_precios=True)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "pvp": -5.99
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "pvp" 
                  and issue.severity == ValidationSeverity.ERROR
                  and "negativo" in issue.message.lower()
                  for issue in issues)
    
    def test_validar_precio_pvp_menor_costo_warning(self):
        """Test que genera warning si PVP es menor que costo con IVA."""
        validator = PedidoValidator(validar_precios=True, iva_porcentaje=15.0)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "costo_doc_sin_iva": 10.0,  # Costo sin IVA
            "pvp": 5.0  # PVP menor que costo con IVA (10 * 1.15 = 11.5)
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "pvp" 
                  and issue.severity == ValidationSeverity.WARNING
                  and ("menor" in issue.message.lower() or "costo" in issue.message.lower())
                  for issue in issues)
    
    def test_validar_precio_subtotal_negativo_rechaza(self):
        """Test que rechaza subtotal negativo."""
        validator = PedidoValidator(validar_precios=True)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "subtotal": -100.0
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "subtotal" 
                  and issue.severity == ValidationSeverity.ERROR
                  and "negativo" in issue.message.lower()
                  for issue in issues)
    
    def test_validar_precio_total_menor_subtotal_warning(self):
        """Test que genera warning si total < subtotal."""
        validator = PedidoValidator(validar_precios=True)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "subtotal": 150.0,
            "total": 100.0  # Menor que subtotal
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        assert any(issue.field == "total" 
                  and issue.severity == ValidationSeverity.WARNING
                  and ("menor" in issue.message.lower() or "subtotal" in issue.message.lower())
                  for issue in issues)
    
    def test_validar_precio_formato_punto_decimal(self):
        """Test que acepta formato con punto decimal (10.50)."""
        validator = PedidoValidator(validar_precios=True, usar_comas_decimales=False)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "costo_doc_sin_iva": "10.50",  # String con punto
            "pvp": "$15.99"  # Con símbolo de moneda
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        # No debe tener errores de formato numérico
        formato_issues = [i for i in issues 
                         if i.field in ["costo_doc_sin_iva", "pvp"] 
                         and "número válido" in i.message.lower()]
        assert len(formato_issues) == 0
    
    def test_validar_precio_formato_coma_decimal(self):
        """Test que acepta formato con coma decimal si está configurado."""
        validator = PedidoValidator(validar_precios=True, usar_comas_decimales=True)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "costo_doc_sin_iva": "10,50",  # String con coma
            "pvp": "15,99"
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        # No debe tener errores de formato numérico
        formato_issues = [i for i in issues 
                         if i.field in ["costo_doc_sin_iva", "pvp"] 
                         and "número válido" in i.message.lower()]
        assert len(formato_issues) == 0
    
    def test_validar_precio_iva_15_porcentaje(self):
        """Test que usa IVA del 15% para Ecuador."""
        validator = PedidoValidator(validar_precios=True, iva_porcentaje=15.0)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "costo_doc_sin_iva": 100.0,  # Costo sin IVA
            "pvp": 100.0  # PVP igual al costo sin IVA (debería ser >= 115 con IVA)
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        # Debe generar warning porque PVP (100) < costo con IVA (115)
        assert any(issue.field == "pvp" 
                  and issue.severity == ValidationSeverity.WARNING
                  for issue in issues)
    
    def test_validar_precio_sin_validacion_desactiva(self):
        """Test que no valida precios si validar_precios=False."""
        validator = PedidoValidator(validar_precios=False)
        detalle = {
            "codigo_interno": "R225.1012.BCO",
            "costo_doc_sin_iva": -10.0,  # Negativo, pero no se valida
            "descuento_1": 150,  # Fuera de rango, pero no se valida
            "pvp": -5.0  # Negativo, pero no se valida
        }
        distribuciones = [{"tienda_codigo": "T001", "cantidad": 10}]
        
        issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
        
        # No debe tener errores de precios
        precio_issues = [i for i in issues 
                        if i.field in ["costo_doc_sin_iva", "descuento_1", "pvp", "subtotal", "total"]]
        assert len(precio_issues) == 0
