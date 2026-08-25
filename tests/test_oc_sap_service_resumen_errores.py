"""
Tests para OCSAPService._resumir_errores_prevalidacion.

Bug real que corrige: cuando la prevalidación SAP fallaba por el mismo motivo
(ej. "SAP saturado") en TODAS las líneas de una ODC, el mensaje de error
mostrado al usuario era un muro de texto repitiendo la misma razón línea por
línea (12+ veces), sin dar ninguna información accionable adicional. Ahora,
si todas las líneas con error comparten el mismo motivo, se colapsa a una
sola oración con el conteo. Si los motivos difieren entre líneas, se
mantiene el detalle completo porque ahí sí importa saber qué línea falló y
por qué.
"""

from src.database.services.oc_sap_service import OCSAPService


class TestResumirErroresPrevalidacion:
    def test_errores_por_linea_con_mismo_motivo_se_colapsan(self):
        motivo = "SAP saturado: no se pudo validar en este momento, inténtalo de nuevo en unos segundos"
        errores = [f"Línea {i} (SKU-{i}): {motivo}" for i in range(1, 13)]

        resultado = OCSAPService._resumir_errores_prevalidacion(errores, total_lineas_oc=12)

        assert resultado == f"{motivo} (12 de 12 líneas)"

    def test_falla_parcial_refleja_total_de_lineas_de_la_oc(self):
        """3 de 12 líneas fallan con el mismo motivo: el conteo debe mostrar 3 de 12, no 3 de 3."""
        motivo = "SAP saturado: no se pudo validar en este momento, inténtalo de nuevo en unos segundos"
        errores = [f"Línea {i} ({f'SKU-{i}'}): {motivo}" for i in (2, 5, 9)]

        resultado = OCSAPService._resumir_errores_prevalidacion(errores, total_lineas_oc=12)

        assert resultado == f"{motivo} (3 de 12 líneas)"

    def test_errores_con_motivos_distintos_mantienen_detalle_completo(self):
        errores = [
            "Línea 1 (SKU-A): SKU no existe en SAP",
            "Línea 2 (SKU-B): Stock insuficiente",
        ]

        resultado = OCSAPService._resumir_errores_prevalidacion(errores, total_lineas_oc=2)

        assert resultado == "; ".join(errores)

    def test_error_de_proveedor_no_se_pierde_al_colapsar_lineas(self):
        motivo = "SAP saturado: no se pudo validar en este momento, inténtalo de nuevo en unos segundos"
        errores = [
            "Proveedor 'P123' no existe en SAP BusinessPartners",
            f"Línea 1 (SKU-A): {motivo}",
            f"Línea 2 (SKU-B): {motivo}",
        ]

        resultado = OCSAPService._resumir_errores_prevalidacion(errores, total_lineas_oc=2)

        assert resultado == (
            f"Proveedor 'P123' no existe en SAP BusinessPartners; {motivo} (2 de 2 líneas)"
        )

    def test_una_sola_linea_con_error_no_se_colapsa(self):
        errores = ["Línea 1 (SKU-A): SAP saturado: no se pudo validar en este momento"]

        resultado = OCSAPService._resumir_errores_prevalidacion(errores, total_lineas_oc=1)

        assert resultado == errores[0]

    def test_lista_vacia_retorna_vacio(self):
        assert OCSAPService._resumir_errores_prevalidacion([], total_lineas_oc=0) == ""
