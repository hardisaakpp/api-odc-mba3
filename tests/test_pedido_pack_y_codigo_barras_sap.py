"""
Tests para la validacion de Pack y PVP contra SAP (RN-02, obligatoria/bloqueante) y
la sincronizacion de codigo de barras/descripcion desde SAP (fuente de verdad; el
Excel es solo una referencia visual para el usuario, no se valida contra SAP) durante
la carga de Excel de pedido.

PVP de SAP viene de ITM1 con PriceList=1 ("Precio Minorista"), confirmado contra datos
reales de SAP (ver docs/requeriments/PYTD002_ODC-MABEL-RAYO.md, requerimiento 1.3/RN-02).
"""

from src.database.clients.sap_client import SAPClient
from src.database.services.sap_service import SAPService
from src.database.services.pedido_sap_validator import PedidoSAPValidator
from src.endpoints.pedidos.pedidos_crear_editar_endpoints import (
    _mapear_codigo_a_filas,
    _sincronizar_maestro_sap_y_validar_pack_pvp,
)


def _resultado_con_item(
    codigo="5-0012.9",
    pack="X3",
    pvp=7.99,
    fila=2,
    codigo_barras_excel="EXCEL-BARRAS-VIEJO",
):
    info_producto = {
        "codigo_interno": codigo,
        "codigo_barras": codigo_barras_excel,
        "descripcion_sap": "DESCRIPCION DEL EXCEL",
        "pack": pack,
        "pvp": pvp,
    }
    return {
        "data": [
            {
                "codigoProducto": codigo,
                "idTienda": "T001",
                "cantidad": 10,
                "filaOrigen": fila,
                "es_bodega": False,
                "info_producto": info_producto,
            }
        ],
        "errores": [],
    }


def _validacion_sap_valida(
    codigo="5-0012.9",
    pack_sap="X3",
    pvp_sap=7.99,
    item_name="NOMBRE SAP",
    codigo_barras="7861234567890",
):
    return {
        "detalle": {
            codigo: {
                "existe": True,
                "info": {
                    "item_code": codigo,
                    "item_name": item_name,
                    "pack_sap": pack_sap,
                    "grupo_articulos": "GRUPO",
                    "unidad_conversion": 1.0,
                    "codigo_barras": codigo_barras,
                    "pvp_sap": pvp_sap,
                },
                "severity": None,
            }
        }
    }


class TestValidarPackContraSap:
    def test_pack_coincide_no_genera_error(self):
        resultado = _resultado_con_item(pack="X3")
        validacion_sap = _validacion_sap_valida(pack_sap="X3")
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["errores"] == []

    def test_pack_no_coincide_genera_error_bloqueante_con_valor_sugerido(self):
        resultado = _resultado_con_item(pack="X6", fila=5)
        validacion_sap = _validacion_sap_valida(pack_sap="X3")
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        errores_pack = [e for e in resultado["errores"] if e["campo"] == "Pack"]
        assert len(errores_pack) == 1
        assert errores_pack[0] == {
            "fila": 5,
            "campo": "Pack",
            "tipo": "ERROR",
            "mensaje": (
                "El Pack 'X6' del Excel no coincide con el Pack registrado en SAP "
                "para '5-0012.9' ('X3'). Use 'X3'."
            ),
            "pack_excel": "X6",
            "pack_sap": "X3",
        }

    def test_comparacion_de_pack_ignora_mayusculas_y_espacios(self):
        resultado = _resultado_con_item(pack=" x3 ")
        validacion_sap = _validacion_sap_valida(pack_sap="X3")
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["errores"] == []

    def test_pack_faltante_en_excel_no_genera_error(self):
        resultado = _resultado_con_item(pack=None)
        validacion_sap = _validacion_sap_valida(pack_sap="X3")
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["errores"] == []

    def test_producto_no_encontrado_en_sap_no_valida_pack(self):
        resultado = _resultado_con_item(pack="X6")
        validacion_sap = {"detalle": {"5-0012.9": {"existe": False, "info": None, "severity": "ERROR"}}}
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["errores"] == []


class TestValidarPvpContraSap:
    def test_pvp_coincide_no_genera_error(self):
        resultado = _resultado_con_item(pvp=7.99)
        validacion_sap = _validacion_sap_valida(pvp_sap=7.99)
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["errores"] == []

    def test_pvp_no_coincide_genera_error_bloqueante_con_valor_sugerido(self):
        resultado = _resultado_con_item(pvp=6.99, fila=5)
        validacion_sap = _validacion_sap_valida(pvp_sap=7.99)
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        errores_pvp = [e for e in resultado["errores"] if e["campo"] == "PVP"]
        assert len(errores_pvp) == 1
        assert errores_pvp[0] == {
            "fila": 5,
            "campo": "PVP",
            "tipo": "ERROR",
            "mensaje": (
                "El PVP '6.99' del Excel no coincide con el PVP registrado en SAP "
                "(Precio Minorista) para '5-0012.9' ('7.99'). Use '7.99'."
            ),
            "pvp_excel": 6.99,
            "pvp_sap": 7.99,
        }

    def test_pvp_dentro_de_tolerancia_de_redondeo_no_genera_error(self):
        resultado = _resultado_con_item(pvp=7.99)
        validacion_sap = _validacion_sap_valida(pvp_sap=7.990001)
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["errores"] == []

    def test_pvp_faltante_en_excel_no_genera_error(self):
        resultado = _resultado_con_item(pvp=None)
        validacion_sap = _validacion_sap_valida(pvp_sap=7.99)
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["errores"] == []

    def test_pvp_sap_en_cero_no_genera_error(self):
        """PriceList=1 en 0.00 se trata como 'no configurado', no como el precio real."""
        resultado = _resultado_con_item(pvp=7.99)
        validacion_sap = _validacion_sap_valida(pvp_sap=0.0)
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["errores"] == []

    def test_producto_no_encontrado_en_sap_no_valida_pvp(self):
        resultado = _resultado_con_item(pvp=6.99)
        validacion_sap = {"detalle": {"5-0012.9": {"existe": False, "info": None, "severity": "ERROR"}}}
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["errores"] == []

    def test_pack_y_pvp_no_coinciden_generan_dos_errores(self):
        resultado = _resultado_con_item(pack="X6", pvp=6.99, fila=3)
        validacion_sap = _validacion_sap_valida(pack_sap="X3", pvp_sap=7.99)
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        campos = sorted(e["campo"] for e in resultado["errores"])
        assert campos == ["PVP", "Pack"]


class TestSincronizarCodigoBarrasYDescripcionDesdeSap:
    def test_codigo_barras_y_descripcion_se_sobreescriben_con_sap(self):
        resultado = _resultado_con_item()
        validacion_sap = _validacion_sap_valida(item_name="NOMBRE REAL SAP", codigo_barras="7861234567890")
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        info_producto = resultado["data"][0]["info_producto"]
        assert info_producto["codigo_barras"] == "7861234567890"
        assert info_producto["descripcion_sap"] == "NOMBRE REAL SAP"

    def test_sap_sin_codigo_barras_mantiene_la_referencia_del_excel(self):
        resultado = _resultado_con_item(codigo_barras_excel="EXCEL-BARRAS-VIEJO")
        validacion_sap = _validacion_sap_valida(codigo_barras=None)
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["data"][0]["info_producto"]["codigo_barras"] == "EXCEL-BARRAS-VIEJO"

    def test_producto_no_encontrado_en_sap_no_sobreescribe_referencia_del_excel(self):
        resultado = _resultado_con_item(codigo_barras_excel="EXCEL-BARRAS-VIEJO")
        validacion_sap = {"detalle": {"5-0012.9": {"existe": False, "info": None, "severity": "ERROR"}}}
        codigo_a_filas = _mapear_codigo_a_filas(resultado["data"])

        _sincronizar_maestro_sap_y_validar_pack_pvp(resultado, validacion_sap, codigo_a_filas)

        assert resultado["data"][0]["info_producto"]["codigo_barras"] == "EXCEL-BARRAS-VIEJO"


class TestPedidoSAPValidatorExponeCodigoBarrasYPvp:
    def test_info_de_producto_valido_incluye_codigo_barras_y_pvp(self):
        validator = PedidoSAPValidator()
        producto_info = {
            "item_code": "5-0012.9",
            "item_name": "NOMBRE SAP",
            "pack_sap": "X3",
            "grupo_articulos": "GRUPO",
            "unidad_conversion": 1.0,
            "codigo_barras": "7861234567890",
            "pvp_sap": 7.99,
        }
        resultado = validator._procesar_resultado_producto("5-0012.9", producto_info, sap_obligatorio=True)
        assert resultado["tipo"] == "valido"
        assert resultado["detalle"]["info"]["codigo_barras"] == "7861234567890"
        assert resultado["detalle"]["info"]["pvp_sap"] == 7.99


class TestCodeBarsYPricePropagacionSapClientYSapService:
    def test_build_producto_dict_incluye_codebars_y_price(self):
        client = SAPClient()
        resultado = client._build_producto_dict(
            ("5-0012.9", "Nombre", "X3", "R-MEDIAS", "Y", "7861234567890", 7.99)
        )
        assert resultado["CodeBars"] == "7861234567890"
        assert resultado["Price"] == 7.99

    def test_build_producto_dict_sin_codebars_ni_price_en_fila_legacy(self):
        client = SAPClient()
        resultado = client._build_producto_dict(("5-0012.9", "Nombre", "X3", "R-MEDIAS", "Y"))
        assert resultado["CodeBars"] is None
        assert resultado["Price"] is None

    def test_mapear_item_batch_incluye_codebars_y_price(self):
        item = {
            "ItemCode": "5-0012.9",
            "ItemName": "Nombre",
            "U_IXX_PACK": "X3",
            "ItmsGrpNam": "R-MEDIAS",
            "Valid": "tYES",
            "CodeBars": "7861234567890",
            "Price": 7.99,
        }
        resultado = SAPService._mapear_item_batch_a_sap_info(item)
        assert resultado["CodeBars"] == "7861234567890"
        assert resultado["Price"] == 7.99
