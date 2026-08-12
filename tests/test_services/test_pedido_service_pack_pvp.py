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


class TestCorreccionesPackPvp:
    """Reintento tras elegir 'usar SAP' o 'usar Excel' en pantalla para un mismatch de Pack/PVP."""

    def test_correccion_de_pack_usando_valor_de_sap_evita_bloqueo(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X6", pvp=7.99)
        validacion = _validacion_sap(pack_sap="X3", pvp_sap=7.99)
        correcciones = {"5-0012.9": {"pack": "X3"}}
        service._validar_pack_pvp_temprana(datos, None, validacion, correcciones)
        assert datos[0]["info_producto"]["pack"] == "X3"

    def test_correccion_de_pack_usando_valor_del_excel_tambien_evita_bloqueo(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X6", pvp=7.99)
        validacion = _validacion_sap(pack_sap="X3", pvp_sap=7.99)
        correcciones = {"5-0012.9": {"pack": "X6"}}
        service._validar_pack_pvp_temprana(datos, None, validacion, correcciones)
        assert datos[0]["info_producto"]["pack"] == "X6"

    def test_correccion_de_pvp_evita_bloqueo(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X3", pvp=6.99)
        validacion = _validacion_sap(pack_sap="X3", pvp_sap=7.99)
        correcciones = {"5-0012.9": {"pvp": 7.99}}
        service._validar_pack_pvp_temprana(datos, None, validacion, correcciones)
        assert datos[0]["info_producto"]["pvp"] == 7.99

    def test_correccion_solo_de_pack_no_exime_la_validacion_de_pvp(self):
        service = PedidoService()
        datos = _datos_parsing(pack="X6", pvp=6.99)
        validacion = _validacion_sap(pack_sap="X3", pvp_sap=7.99)
        correcciones = {"5-0012.9": {"pack": "X3"}}
        with pytest.raises(BusinessException) as exc_info:
            service._validar_pack_pvp_temprana(datos, None, validacion, correcciones)
        data = exc_info.value.data["validacion_pack_pvp"]
        assert data["pack_mismatches"] == []
        assert len(data["pvp_mismatches"]) == 1


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
            service._validar_sap_codigo_y_pack_pvp(datos, None, None)

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
            service._validar_sap_codigo_y_pack_pvp(datos, None, None)
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
            service._validar_sap_codigo_y_pack_pvp(datos, None, None)
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
            service._validar_sap_codigo_y_pack_pvp(datos, None, None)
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
            service._validar_sap_codigo_y_pack_pvp(datos, None, None)
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
            service._validar_sap_codigo_y_pack_pvp(datos, None, None)
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
            service._validar_sap_codigo_y_pack_pvp(datos, None, None)

        exc = exc_info.value
        assert exc.error_code == "PRODUCTOS_NO_VALIDOS_SAP"
        assert "códigos de producto no válidos en SAP" in exc.message
        assert "discrepancia(s) de Pack/PVP" in exc.message
        assert exc.data["validacion_sap"]["no_encontrados"] == 1
        assert exc.data["validacion_pack_pvp"]["pack_mismatches"] == [
            {"codigo": "GOOD1", "pack_excel": "X6", "pack_sap": "X9"}
        ]

    def test_correcciones_de_ambos_tipos_a_la_vez_evitan_el_bloqueo(self, monkeypatch):
        """Un solo reintento con correcciones de código Y de pack/pvp a la vez debe pasar limpio."""
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

        with _mock_conexion_pack_conversion({"X1": 12.0, "X9": 1.333333333}):
            service._validar_sap_codigo_y_pack_pvp(
                datos,
                correcciones_codigos={"BAD1": "BAD1-CORREGIDO"},
                correcciones_pack_pvp={"GOOD1": {"pack": "X9"}}
            )


def _datos_con_costo(codigo="5-0012.9", pack="X3", costo_doc_sin_iva=13.38):
    return [{
        "codigoProducto": codigo,
        "idTienda": "T001",
        "cantidad": 10,
        "filaOrigen": 2,
        "es_bodega": False,
        "info_producto": {
            "codigo_interno": codigo,
            "pack": pack,
            "pvp": 7.99,
            "costo_doc_sin_iva": costo_doc_sin_iva,
        },
    }]


class TestResolverCostoUnitarioTemprana:
    """
    costo_unitario = costo_doc_sin_iva / unidad_conversion (pack_conversion, según el pack
    ya resuelto SAP/Excel) reemplaza a costo_margen como insumo del Margen de Rentabilidad.
    Bloquea la carga si el pack final no tiene conversión configurada.
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

    def test_pack_ya_resuelto_por_correccion_usa_ese_valor_para_la_conversion(self):
        """El pack que llega a este método ya fue resuelto SAP/Excel por _evaluar_pack_producto;
        aquí solo se busca su unidad_conversion, sin importar de qué origen vino."""
        service = PedidoService()
        datos = _datos_con_costo(pack="X6", costo_doc_sin_iva=12.0)
        with _mock_conexion_pack_conversion({"X6": 2.0}):
            service._resolver_costo_unitario_temprana(datos, None)
        assert datos[0]["info_producto"]["costo_unitario"] == 6.0
