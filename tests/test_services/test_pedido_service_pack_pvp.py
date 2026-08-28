"""
Tests para la validación de Pack/PVP contra SAP (RN-02, obligatoria/bloqueante) y la
sincronización de código de barras/descripción desde SAP (fuente de verdad; el Excel es
solo referencia visual, esos dos campos no se validan) en el flujo REAL de carga de
Excel de pedido: validar_y_procesar_archivo_excel -> _procesar_formato_nuevo_v1_0 ->
_validar_pack_pvp_temprana.

Este es el flujo que usa el frontend (/api/plantillas/upload), a diferencia del endpoint
/pedidos/importar-excel (registrado pero no consumido por ninguna pantalla).
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from src.database.services.pedido_service import PedidoService
from src.database.services.pedido_validator import PedidoValidator
from src.exceptions import BusinessException


@contextmanager
def _mock_conexion_pack_conversion(conversiones: dict):
    """
    Mockea get_db_connection_context/ProductoSAPRepository para que
    get_unidad_conversion_by_pack(pack) devuelva conversiones.get(pack) (None si no
    está en el dict), sin tocar una base de datos real.
    """
    with patch("src.database.services.pedido_service.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.pedido_service.ProductoSAPRepository") as mock_repo_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_unidad_conversion_by_pack.side_effect = (
            lambda pack: conversiones.get(pack)
        )
        yield mock_repo_class


def _datos_parsing(codigo="5-0012.9", pack="X3", pvp=7.99, codigo_barras_excel="EXCEL-BARRAS-VIEJO"):
    info_producto = {
        "codigo_interno": codigo,
        "codigo_barras": codigo_barras_excel,
        "descripcion_sap": "DESCRIPCION DEL EXCEL",
        "pack": pack,
        "pvp": pvp,
    }
    return [{
        "codigoProducto": codigo,
        "idTienda": "T001",
        "cantidad": 10,
        "filaOrigen": 2,
        "es_bodega": False,
        "info_producto": info_producto,
    }]


def _validacion_sap(
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


class TestValidarPackPvpTemprana:
    def test_pack_y_pvp_coinciden_no_lanza_excepcion(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X3", pvp=7.99)
        validacion = _validacion_sap(pack_sap="X3", pvp_sap=7.99)
        service._validar_pack_pvp_temprana(datos, None, validacion)

    def test_pack_no_coincide_lanza_business_exception(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X6", pvp=7.99)
        validacion = _validacion_sap(pack_sap="X3", pvp_sap=7.99)
        with pytest.raises(BusinessException) as exc_info:
            service._validar_pack_pvp_temprana(datos, None, validacion)
        exc = exc_info.value
        assert exc.error_code == "PACK_PVP_INVALIDOS_SAP"
        data = exc.data["validacion_pack_pvp"]
        assert data["pack_mismatches"] == [{"codigo": "5-0012.9", "pack_excel": "X6", "pack_sap": "X3"}]
        assert data["pvp_mismatches"] == []

    def test_pvp_no_coincide_lanza_business_exception(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X3", pvp=6.99)
        validacion = _validacion_sap(pack_sap="X3", pvp_sap=7.99)
        with pytest.raises(BusinessException) as exc_info:
            service._validar_pack_pvp_temprana(datos, None, validacion)
        data = exc_info.value.data["validacion_pack_pvp"]
        assert data["pvp_mismatches"] == [{"codigo": "5-0012.9", "pvp_excel": 6.99, "pvp_sap": 7.99}]
        assert data["pack_mismatches"] == []

    def test_pack_y_pvp_no_coinciden_reporta_ambos_en_una_sola_excepcion(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X6", pvp=6.99)
        validacion = _validacion_sap(pack_sap="X3", pvp_sap=7.99)
        with pytest.raises(BusinessException) as exc_info:
            service._validar_pack_pvp_temprana(datos, None, validacion)
        data = exc_info.value.data["validacion_pack_pvp"]
        assert len(data["pack_mismatches"]) == 1
        assert len(data["pvp_mismatches"]) == 1

    def test_comparacion_de_pack_ignora_mayusculas_y_espacios(self):
        service = PedidoService()
        datos = _datos_parsing(pack=" x3 ")
        validacion = _validacion_sap(pack_sap="X3")
        service._validar_pack_pvp_temprana(datos, None, validacion)

    def test_pvp_dentro_de_tolerancia_de_redondeo_no_lanza(self):
        service = PedidoService()
        datos = _datos_parsing(pvp=7.99)
        validacion = _validacion_sap(pvp_sap=7.990001)
        service._validar_pack_pvp_temprana(datos, None, validacion)

    def test_pack_o_pvp_faltantes_en_excel_no_bloquean(self):
        service = PedidoService()
        datos = _datos_parsing(pack=None, pvp=None)
        validacion = _validacion_sap(pack_sap="X3", pvp_sap=7.99)
        service._validar_pack_pvp_temprana(datos, None, validacion)

    def test_producto_no_encontrado_en_sap_no_valida_pack_pvp(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X6", pvp=6.99)
        validacion = {"detalle": {"5-0012.9": {"existe": False, "info": None, "severity": "ERROR"}}}
        service._validar_pack_pvp_temprana(datos, None, validacion)

    def test_sin_validacion_sap_no_hace_nada(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X6", pvp=6.99)
        service._validar_pack_pvp_temprana(datos, None, None)

    def test_codigo_barras_y_descripcion_se_sincronizan_desde_sap(self):
        service = PedidoService()
        datos = _datos_parsing(codigo_barras_excel="EXCEL-BARRAS-VIEJO")
        validacion = _validacion_sap(item_name="NOMBRE REAL SAP", codigo_barras="7861234567890")
        service._validar_pack_pvp_temprana(datos, None, validacion)
        info_producto = datos[0]["info_producto"]
        assert info_producto["codigo_barras"] == "7861234567890"
        assert info_producto["descripcion_sap"] == "NOMBRE REAL SAP"

    def test_producto_no_encontrado_no_sobreescribe_codigo_barras_del_excel(self):
        service = PedidoService()
        datos = _datos_parsing(codigo_barras_excel="EXCEL-BARRAS-VIEJO")
        validacion = {"detalle": {"5-0012.9": {"existe": False, "info": None, "severity": "ERROR"}}}
        service._validar_pack_pvp_temprana(datos, None, validacion)
        assert datos[0]["info_producto"]["codigo_barras"] == "EXCEL-BARRAS-VIEJO"


class TestValidarProductosSapTempranaRetornaResultado:
    """_validar_productos_sap_temprana debe retornar la validación para que
    _validar_pack_pvp_temprana la reutilice sin volver a consultar SAP."""

    def test_retorna_resultado_de_validacion_cuando_hay_codigos(self, monkeypatch):
        service = PedidoService()
        resultado_esperado = {"todos_validos": True, "detalle": {}, "validos": ["A1"]}
        monkeypatch.setattr(
            PedidoValidator,
            "validar_productos_existen_en_sap_con_sugerencias",
            lambda self, **kwargs: resultado_esperado
        )
        datos = _datos_parsing(codigo="A1")
        resultado = service._validar_productos_sap_temprana(datos, None)
        assert resultado == resultado_esperado

    def test_retorna_none_sin_codigos(self):
        service = PedidoService()
        resultado = service._validar_productos_sap_temprana([], None)
        assert resultado is None

    def test_codigo_invalido_ya_no_lanza_excepcion_por_si_solo(self, monkeypatch):
        """Antes _validar_productos_sap_temprana lanzaba BusinessException directo cuando el
        código no era válido. Ahora solo retorna el resultado (todos_validos=False); quien decide
        si bloquear es _validar_sap_codigo_y_pack_pvp, que lo combina con Pack/PVP."""
        service = PedidoService()
        resultado_invalido = {"todos_validos": False, "no_encontrados": ["A1"], "errores": [], "validos": [], "detalle": {}}
        monkeypatch.setattr(
            PedidoValidator,
            "validar_productos_existen_en_sap_con_sugerencias",
            lambda self, **kwargs: resultado_invalido
        )
        datos = _datos_parsing(codigo="A1")
        resultado = service._validar_productos_sap_temprana(datos, None)
        assert resultado == resultado_invalido


def _datos_dos_productos():
    """Dos productos: BAD1 (no existe en SAP) y GOOD1 (existe, con pack que no coincide)."""
    return [
        {
            "codigoProducto": "BAD1",
            "idTienda": "T001",
            "cantidad": 5,
            "filaOrigen": 2,
            "es_bodega": False,
            "info_producto": {"codigo_interno": "BAD1", "pack": "X1", "pvp": 5.0},
        },
        {
            "codigoProducto": "GOOD1",
            "idTienda": "T001",
            "cantidad": 5,
            "filaOrigen": 3,
            "es_bodega": False,
            "info_producto": {"codigo_interno": "GOOD1", "pack": "X6", "pvp": 5.0},
        },
    ]


class TestValidarSapCodigoYPackPvpCombinado:
    """
    Flujo ideal (RN-02): antes, código inválido bloqueaba de inmediato y Pack/PVP solo se
    evaluaba en un reintento posterior una vez el código ya estaba corregido — el usuario
    corregía en rondas separadas. _validar_sap_codigo_y_pack_pvp combina las 3 validaciones
    (código, pack, pvp) en una sola BusinessException para que se vean y corrijan juntas.
    """

    def test_todo_valido_no_lanza_excepcion(self, monkeypatch):
        service = PedidoService()
        datos = _datos_parsing(codigo="A1", pack="X3", pvp=7.99)
        monkeypatch.setattr(
            PedidoValidator,
            "validar_productos_existen_en_sap_con_sugerencias",
            lambda self, **kwargs: {
                "todos_validos": True, "no_encontrados": [], "errores": [], "validos": ["A1"],
                "detalle": {"A1": {"existe": True, "info": {"pack_sap": "X3", "pvp_sap": 7.99, "item_name": "N", "codigo_barras": "1"}, "severity": None}},
            }
        )
        with _mock_conexion_pack_conversion({"X3": 4.0}):
            service._validar_sap_codigo_y_pack_pvp(datos, None)

    def test_solo_codigo_invalido_no_incluye_pack_pvp_en_la_excepcion(self, monkeypatch):
        service = PedidoService()
        datos = _datos_parsing(codigo="BAD1", pack="X1", pvp=5.0)
        monkeypatch.setattr(
            PedidoValidator,
            "validar_productos_existen_en_sap_con_sugerencias",
            lambda self, **kwargs: {
                "todos_validos": False, "no_encontrados": ["BAD1"], "errores": [], "validos": [],
                "detalle": {"BAD1": {"existe": False, "info": None, "severity": "ERROR", "error": "no encontrado", "mensaje": "no encontrado", "mba3": None, "sugerencias_sap": []}},
            }
        )
        with pytest.raises(BusinessException) as exc_info:
            service._validar_sap_codigo_y_pack_pvp(datos, None)
        exc = exc_info.value
        assert exc.error_code == "PRODUCTOS_NO_VALIDOS_SAP"
        assert exc.message == "Existen códigos de producto no válidos en SAP"
        assert "validacion_sap" in exc.data
        assert "validacion" in exc.data
        assert "validacion_pack_pvp" not in exc.data

    def test_codigo_invalido_incluye_pack_pvp_del_excel_para_detectar_mismatch_en_la_misma_ronda(self, monkeypatch):
        """
        Al elegir una sugerencia SAP para un código inválido, el frontend necesita el
        Pack/PVP tal como venían en ESE Excel para poder compararlos contra el
        pack_sap/pvp_sap de la sugerencia elegida (vía GET .../sap-info-productos) y
        detectar el mismatch en la misma ronda, sin esperar al reintento siguiente.
        """
        service = PedidoService()
        datos = _datos_parsing(codigo="BAD1", pack="X1", pvp=5.0)
        monkeypatch.setattr(
            PedidoValidator,
            "validar_productos_existen_en_sap_con_sugerencias",
            lambda self, **kwargs: {
                "todos_validos": False, "no_encontrados": ["BAD1"], "errores": [], "validos": [],
                "detalle": {"BAD1": {"existe": False, "info": None, "severity": "ERROR", "error": "no encontrado", "mensaje": "no encontrado", "mba3": None, "sugerencias_sap": []}},
            }
        )
        with pytest.raises(BusinessException) as exc_info:
            service._validar_sap_codigo_y_pack_pvp(datos, None)
        detalle = exc_info.value.data["validacion_sap"]["detalle_validacion"]["BAD1"]
        assert detalle["pack_excel"] == "X1"
        assert detalle["pvp_excel"] == 5.0

    def test_codigo_invalido_sin_pack_ni_pvp_en_excel_reporta_none_sin_reventar(self, monkeypatch):
        service = PedidoService()
        datos = _datos_parsing(codigo="BAD1", pack=None, pvp=None)
        monkeypatch.setattr(
            PedidoValidator,
            "validar_productos_existen_en_sap_con_sugerencias",
            lambda self, **kwargs: {
                "todos_validos": False, "no_encontrados": ["BAD1"], "errores": [], "validos": [],
                "detalle": {"BAD1": {"existe": False, "info": None, "severity": "ERROR", "error": "no encontrado", "mensaje": "no encontrado", "mba3": None, "sugerencias_sap": []}},
            }
        )
        with pytest.raises(BusinessException) as exc_info:
            service._validar_sap_codigo_y_pack_pvp(datos, None)
        detalle = exc_info.value.data["validacion_sap"]["detalle_validacion"]["BAD1"]
        assert detalle["pack_excel"] is None
        assert detalle["pvp_excel"] is None

    def test_codigo_invalido_en_filas_duplicadas_usa_el_primer_valor_no_nulo(self, monkeypatch):
        """Misma convención que _evaluar_pack_producto/_evaluar_pvp_producto (códigos ya
        válidos): ante varias filas del mismo código, se toma el primer valor no nulo,
        sin comparar entre filas ni marcar inconsistencia interna del Excel."""
        service = PedidoService()
        datos = [
            {
                "codigoProducto": "BAD1", "idTienda": "T001", "cantidad": 5,
                "filaOrigen": 2, "es_bodega": False,
                "info_producto": {"codigo_interno": "BAD1", "pack": None, "pvp": None},
            },
            {
                "codigoProducto": "BAD1", "idTienda": "T002", "cantidad": 3,
                "filaOrigen": 3, "es_bodega": False,
                "info_producto": {"codigo_interno": "BAD1", "pack": "X1", "pvp": 5.0},
            },
        ]
        monkeypatch.setattr(
            PedidoValidator,
            "validar_productos_existen_en_sap_con_sugerencias",
            lambda self, **kwargs: {
                "todos_validos": False, "no_encontrados": ["BAD1"], "errores": [], "validos": [],
                "detalle": {"BAD1": {"existe": False, "info": None, "severity": "ERROR", "error": "no encontrado", "mensaje": "no encontrado", "mba3": None, "sugerencias_sap": []}},
            }
        )
        with pytest.raises(BusinessException) as exc_info:
            service._validar_sap_codigo_y_pack_pvp(datos, None)
        detalle = exc_info.value.data["validacion_sap"]["detalle_validacion"]["BAD1"]
        assert detalle["pack_excel"] == "X1"
        assert detalle["pvp_excel"] == 5.0

    def test_solo_pack_pvp_invalido_no_incluye_datos_de_codigo(self, monkeypatch):
        service = PedidoService()
        datos = _datos_parsing(codigo="A1", pack="X6", pvp=7.99)
        monkeypatch.setattr(
            PedidoValidator,
            "validar_productos_existen_en_sap_con_sugerencias",
            lambda self, **kwargs: {
                "todos_validos": True, "no_encontrados": [], "errores": [], "validos": ["A1"],
                "detalle": {"A1": {"existe": True, "info": {"pack_sap": "X3", "pvp_sap": 7.99, "item_name": "N", "codigo_barras": "1"}, "severity": None}},
            }
        )
        with pytest.raises(BusinessException) as exc_info:
            service._validar_sap_codigo_y_pack_pvp(datos, None)
        exc = exc_info.value
        assert exc.error_code == "PACK_PVP_INVALIDOS_SAP"
        assert exc.message == "Existen 1 discrepancia(s) de Pack/PVP contra SAP"
        assert "validacion_pack_pvp" in exc.data
        assert "validacion_sap" not in exc.data
        assert "validacion" not in exc.data

    def test_codigo_y_pack_pvp_invalidos_se_reportan_juntos_en_una_sola_excepcion(self, monkeypatch):
        """El caso central del flujo ideal: un Excel con un código inexistente Y un producto
        válido con pack que no coincide debe reportar AMBOS problemas en un solo intento."""
        service = PedidoService()
        datos = _datos_dos_productos()

        def fake_validar(self, **kwargs):
            return {
                "todos_validos": False,
                "no_encontrados": ["BAD1"],
                "errores": [],
                "validos": ["GOOD1"],
                "detalle": {
                    "BAD1": {"existe": False, "info": None, "severity": "ERROR", "error": "no encontrado", "mensaje": "no encontrado", "mba3": None, "sugerencias_sap": []},
                    "GOOD1": {"existe": True, "info": {"pack_sap": "X9", "pvp_sap": 5.0, "item_name": "Y", "codigo_barras": "456"}, "severity": None},
                },
            }

        monkeypatch.setattr(PedidoValidator, "validar_productos_existen_en_sap_con_sugerencias", fake_validar)

        with pytest.raises(BusinessException) as exc_info:
            service._validar_sap_codigo_y_pack_pvp(datos, None)

        exc = exc_info.value
        assert exc.error_code == "PRODUCTOS_NO_VALIDOS_SAP"
        assert "códigos de producto no válidos en SAP" in exc.message
        assert "discrepancia(s) de Pack/PVP" in exc.message
        assert exc.data["validacion_sap"]["no_encontrados"] == 1
        assert exc.data["validacion_pack_pvp"]["pack_mismatches"] == [
            {"codigo": "GOOD1", "pack_excel": "X6", "pack_sap": "X9"}
        ]

    def test_correccion_de_codigo_no_exime_el_bloqueo_de_pack_pvp_de_otro_producto(self, monkeypatch):
        """Req. 1.3: ya no existe forma de eximir una discrepancia de Pack/PVP en pantalla.
        Corregir el código inválido de un producto no libera el bloqueo si otro producto de
        la misma carga sigue con Pack/PVP distinto de SAP — solo queda corregir el Excel/SAP
        y volver a subir el archivo."""
        service = PedidoService()
        datos = _datos_dos_productos()

        def fake_validar(self, **kwargs):
            return {
                "todos_validos": True,
                "no_encontrados": [],
                "errores": [],
                "validos": ["BAD1-CORREGIDO", "GOOD1"],
                "detalle": {
                    "BAD1-CORREGIDO": {"existe": True, "info": {"pack_sap": "X1", "pvp_sap": 5.0, "item_name": "Z", "codigo_barras": "789"}, "severity": None},
                    "GOOD1": {"existe": True, "info": {"pack_sap": "X9", "pvp_sap": 5.0, "item_name": "Y", "codigo_barras": "456"}, "severity": None},
                },
            }

        monkeypatch.setattr(PedidoValidator, "validar_productos_existen_en_sap_con_sugerencias", fake_validar)

        with pytest.raises(BusinessException) as exc_info:
            service._validar_sap_codigo_y_pack_pvp(datos, correcciones_codigos={"BAD1": "BAD1-CORREGIDO"})

        exc = exc_info.value
        assert exc.error_code == "PACK_PVP_INVALIDOS_SAP"
        assert exc.data["validacion_pack_pvp"]["pack_mismatches"] == [
            {"codigo": "GOOD1", "pack_excel": "X6", "pack_sap": "X9"}
        ]


def _datos_con_costo(codigo="5-0012.9", pack="X3", costo_doc_sin_iva=13.38, costo_unitario_excel=None, num_tiendas=1):
    """num_tiendas simula una misma fila del Excel con cantidad en varias columnas de
    tienda/bodega: el parser genera un item de datos_parsing por cada una, todos
    compartiendo la MISMA instancia de info_producto (ver _procesar_tiendas_fila/
    _procesar_bodegas_fila en pedido_parser_detalle.py)."""
    info_producto = {
        "codigo_interno": codigo,
        "pack": pack,
        "pvp": 7.99,
        "costo_doc_sin_iva": costo_doc_sin_iva,
    }
    if costo_unitario_excel is not None:
        info_producto["costo_unitario_excel"] = costo_unitario_excel
    return [
        {
            "codigoProducto": codigo,
            "idTienda": f"T{i:03d}",
            "cantidad": 10,
            "filaOrigen": 2,
            "es_bodega": False,
            "info_producto": info_producto,
        }
        for i in range(1, num_tiendas + 1)
    ]


class TestResolverCostoUnitarioTemprana:
    """
    costo_unitario = costo_doc_sin_iva / unidad_conversion (pack_conversion, según el pack
    tal como viene en el Excel) reemplaza a costo_margen como insumo del Margen de
    Rentabilidad. Bloquea la carga si el pack final no tiene conversión configurada.
    """

    def test_calcula_costo_unitario_con_pack_valido(self):
        service = PedidoService()
        datos = _datos_con_costo(pack="X3", costo_doc_sin_iva=13.38)
        with _mock_conexion_pack_conversion({"X3": 4.0}):
            service._resolver_costo_unitario_temprana(datos, None)
        assert datos[0]["info_producto"]["costo_unitario"] == 13.38 / 4.0

    def test_pack_sin_conversion_configurada_bloquea_la_carga(self):
        service = PedidoService()
        datos = _datos_con_costo(codigo="ABC123", pack="X9Z")
        with _mock_conexion_pack_conversion({}):
            with pytest.raises(BusinessException) as exc_info:
                service._resolver_costo_unitario_temprana(datos, None)
        exc = exc_info.value
        assert exc.error_code == "PACK_SIN_UNIDAD_CONVERSION"
        packs_invalidos = exc.data["validacion_pack_conversion"]["packs_invalidos"]
        assert packs_invalidos == [{"codigo": "ABC123", "pack": "X9Z"}]

    def test_pack_ausente_en_excel_bloquea_la_carga(self):
        service = PedidoService()
        datos = _datos_con_costo(codigo="ABC123", pack=None)
        with _mock_conexion_pack_conversion({}):
            with pytest.raises(BusinessException) as exc_info:
                service._resolver_costo_unitario_temprana(datos, None)
        assert exc_info.value.error_code == "PACK_SIN_UNIDAD_CONVERSION"

    def test_costo_doc_sin_iva_ausente_da_costo_unitario_none_sin_reventar(self):
        service = PedidoService()
        datos = _datos_con_costo(pack="X3", costo_doc_sin_iva=None)
        with _mock_conexion_pack_conversion({"X3": 4.0}):
            service._resolver_costo_unitario_temprana(datos, None)
        assert datos[0]["info_producto"]["costo_unitario"] is None

    def test_usa_el_pack_del_producto_para_buscar_la_conversion(self):
        """Este método corre ANTES de validar el pack contra SAP (ver
        TestOrdenCostoUnitarioAntesDeSap): usa el pack tal como viene en el Excel, sin
        esperar a que _validar_pack_pvp_temprana confirme que coincide con SAP."""
        service = PedidoService()
        datos = _datos_con_costo(pack="X6", costo_doc_sin_iva=12.0)
        with _mock_conexion_pack_conversion({"X6": 2.0}):
            service._resolver_costo_unitario_temprana(datos, None)
        assert datos[0]["info_producto"]["costo_unitario"] == 6.0


class TestValidarCostoUnitarioExcel:
    """
    La columna "Costo Unitario" del Excel (fórmula =SI.ERROR(COSTO_SIN_IVA/(12/pack);""))
    usa la misma convención 12/pack que pack_conversion.unidad_conversion. Se contrasta contra
    el costo_unitario calculado por el backend para detectar una fórmula mal aplicada en esa
    celda (ej. referencia a la fila incorrecta), igual que ya se hace con TOTAL/SUBTOTAL.
    """

    def test_costo_unitario_excel_coincide_no_lanza_excepcion(self):
        service = PedidoService()
        datos = _datos_con_costo(pack="X3", costo_doc_sin_iva=13.38, costo_unitario_excel=13.38 / 4.0)
        with _mock_conexion_pack_conversion({"X3": 4.0}):
            service._resolver_costo_unitario_temprana(datos, None)

    def test_costo_unitario_excel_no_coincide_lanza_business_exception(self):
        service = PedidoService()
        datos = _datos_con_costo(codigo="5-0012.9", pack="X3", costo_doc_sin_iva=13.38, costo_unitario_excel=99.0)
        with _mock_conexion_pack_conversion({"X3": 4.0}):
            with pytest.raises(BusinessException) as exc_info:
                service._resolver_costo_unitario_temprana(datos, None)
        exc = exc_info.value
        assert exc.error_code == "COSTO_UNITARIO_EXCEL_INCONSISTENTE"
        mismatches = exc.data["validacion_costo_unitario"]["mismatches"]
        assert mismatches == [{
            "codigo": "5-0012.9",
            "pack": "X3",
            "costo_unitario_excel": 99.0,
            "costo_unitario_calculado": 13.38 / 4.0,
        }]
        # El mensaje debe ser accionable por sí solo: el frontend, al no reconocer este
        # error_code, muestra `message` tal cual (ver useFileUpload.ts::processUploadError,
        # rama `(e as any).isBusinessException`) — no basta con el conteo, tiene que decir
        # qué producto/pack y qué valores no cuadran.
        assert "5-0012.9" in exc.message
        assert "X3" in exc.message
        assert "99.0000" in exc.message

    def test_costo_unitario_excel_no_coincide_con_muchas_tiendas_reporta_un_solo_mismatch(self):
        """Bug real: una fila con cantidad en 30 columnas de tienda generaba 30 items en
        datos_parsing para el mismo código (uno por tienda), y el mismatch de Costo Unitario
        se reportaba 30 veces, idéntico, en vez de una sola vez por producto."""
        service = PedidoService()
        datos = _datos_con_costo(
            codigo="REG-028.1012", pack="X1", costo_doc_sin_iva=1.525, costo_unitario_excel=2.0, num_tiendas=30
        )
        with _mock_conexion_pack_conversion({"X1": 1.0}):
            with pytest.raises(BusinessException) as exc_info:
                service._resolver_costo_unitario_temprana(datos, None)
        mismatches = exc_info.value.data["validacion_costo_unitario"]["mismatches"]
        assert len(mismatches) == 1
        assert mismatches[0]["codigo"] == "REG-028.1012"
        assert exc_info.value.message.count("REG-028.1012") == 1

    def test_costo_unitario_excel_ausente_no_bloquea(self):
        """Plantillas sin la columna "Costo Unitario" (o formato antiguo) siguen funcionando."""
        service = PedidoService()
        datos = _datos_con_costo(pack="X3", costo_doc_sin_iva=13.38)
        with _mock_conexion_pack_conversion({"X3": 4.0}):
            service._resolver_costo_unitario_temprana(datos, None)

    def test_costo_unitario_excel_dentro_de_tolerancia_de_redondeo_no_lanza(self):
        service = PedidoService()
        datos = _datos_con_costo(pack="X3", costo_doc_sin_iva=13.38, costo_unitario_excel=(13.38 / 4.0) + 0.00001)
        with _mock_conexion_pack_conversion({"X3": 4.0}):
            service._resolver_costo_unitario_temprana(datos, None)


class TestOrdenCostoUnitarioAntesDeSap:
    """
    El cruce de "Costo Unitario" (columna del Excel) debe bloquear la carga ANTES de
    consultar SAP, igual que TOTAL/SUBTOTAL: es una verificación interna del propio Excel
    (no depende de SAP) y la consulta a SAP es la parte lenta del flujo. Antes, este
    cruce corría DESPUÉS de validar código/pack/pvp contra SAP (dentro de
    _validar_sap_codigo_y_pack_pvp), por lo que un error de fórmula en esa columna solo
    se veía tras esperar la respuesta de SAP, y encima combinado con mensajes de código/pack
    que no tenían relación con el problema real.
    """

    @staticmethod
    def _resultado_parsing_con_mismatch_costo():
        info_producto = {
            "codigo_interno": "5-0012.9",
            "pack": "X3",
            "pvp": 7.99,
            "costo_doc_sin_iva": 13.38,
            "costo_unitario_excel": 99.0,
        }
        return {
            "cabecera": {},
            "data": [{
                "codigoProducto": "5-0012.9",
                "idTienda": "T001",
                "cantidad": 10,
                "filaOrigen": 2,
                "es_bodega": False,
                "info_producto": info_producto,
            }],
            "errores": [],
        }

    def test_costo_unitario_bloquea_sin_llegar_a_consultar_sap(self, monkeypatch):
        service = PedidoService()
        monkeypatch.setattr(
            service.parser, "parsear_excel_pedido",
            lambda **kwargs: self._resultado_parsing_con_mismatch_costo()
        )
        sap_llamado = {"veces": 0}

        def fake_validar_sap(self, **kwargs):
            sap_llamado["veces"] += 1
            return {"todos_validos": True, "detalle": {}, "validos": []}

        monkeypatch.setattr(
            PedidoValidator, "validar_productos_existen_en_sap_con_sugerencias", fake_validar_sap
        )

        with _mock_conexion_pack_conversion({"X3": 4.0}):
            with pytest.raises(BusinessException) as exc_info:
                service._procesar_formato_nuevo_v1_0(
                    file_content=b"", hoja_cabecera="cabecera", hoja_detalle="detalle",
                    filename="test.xlsx", usuario_id=None, validar_sap=True, correcciones_codigos=None
                )

        assert exc_info.value.error_code == "COSTO_UNITARIO_EXCEL_INCONSISTENTE"
        assert sap_llamado["veces"] == 0
