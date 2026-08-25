"""
Vista previa administrativa de los correos del sistema (notificacion_tipo_correo).

Reutiliza los mismos constructores de HTML que usa el envío real
(src/utils/email_notifier.py, sección "Constructores de HTML puros"), con datos
de ejemplo fijos en vez de datos reales de negocio. No hace I/O: no consulta la
base de datos ni envía nada por SMTP.

El despachador está indexado por (tipo_notificacion, tipo_correo) porque esa es
la misma clave única que ya usa el catálogo (ver
notificacion_tipo_correo_repository.crear_tipo_correo). Un renglón del catálogo
sin entrada aquí (por ejemplo uno agregado a mano por un admin que no
corresponde a ningún código real de envío) simplemente no tiene vista previa
disponible.
"""

from typing import Callable, Dict, Optional, Tuple

from src.utils.timezone import ahora_naive
from src.utils import email_notifier as _en
from src.utils import email_notifier_pedido as _enp

_FECHA_EJEMPLO = ahora_naive()

_OC_CABECERA_EJEMPLO = {
    "proveedor": "Distribuidora Ejemplo S.A.",
    "numero_oc_sap": "48213",
    "referencia_despacho": "REF-EJEMPLO-001",
}

_OC_DETALLES_EJEMPLO = [
    {
        "sku_sap": "5-0012.9",
        "nombre_producto": "Producto de Ejemplo A",
        "cantidad_sap": 24.0,
        "unidad_sap": "DOC",
        "precio_unitario": 5.50,
        "total_linea": 132.0,
    },
    {
        "sku_sap": "5-0045.3",
        "nombre_producto": "Producto de Ejemplo B",
        "cantidad_sap": 10.0,
        "unidad_sap": "DOC",
        "precio_unitario": 12.75,
        "total_linea": 127.5,
    },
]

_SOLICITUDES_TRANSFERENCIA_EJEMPLO = {
    "total_tiendas": 2,
    "transferencias_creadas": 2,
    "transferencias_errores": 0,
    "resultados": [
        {"tienda_codigo": "T01", "tienda_nombre": "Tienda Centro", "success": True, "doc_num": "9001"},
        {"tienda_codigo": "T02", "tienda_nombre": "Tienda Norte", "success": True, "doc_num": "9002"},
    ],
}

_SOLICITUDES_TRANSFERENCIA_CON_ERROR_EJEMPLO = {
    "total_tiendas": 2,
    "transferencias_creadas": 1,
    "transferencias_errores": 1,
    "resultados": [
        {"tienda_codigo": "T01", "tienda_nombre": "Tienda Centro", "success": True, "doc_num": "9001"},
        {"tienda_codigo": "T02", "tienda_nombre": "Tienda Norte", "success": False, "error": "SAP no disponible (timeout)"},
    ],
}

_PRODUCTOS_NO_HOMOLOGADOS_EJEMPLO = [
    {
        "sku": "5-0099.1",
        "nombre_producto": "Producto Sin Homologar A",
        "veces_usado": 8,
        "total_docenas": 96.0,
        "total_valor": 528.0,
        "primera_aparicion": "2026-06-01",
        "ultima_aparicion": "2026-08-10",
        "tipo_problema": "no_existe",
    },
    {
        "sku": "5-0088.4",
        "nombre_producto": "Producto Sin Homologar B",
        "veces_usado": 3,
        "total_docenas": 36.0,
        "total_valor": 198.0,
        "item_code_sap": "5-0088.4-X",
        "primera_aparicion": "2026-07-05",
        "ultima_aparicion": "2026-08-09",
        "tipo_problema": "mismatch",
    },
]

_ESTADISTICAS_HOMOLOGACION_EJEMPLO = {
    "total_productos_mba3": 420,
    "productos_homologados": 418,
    "productos_no_homologados": 2,
    "porcentaje_homologacion": 99.52,
}

_PEDIDO_ID_EJEMPLO = "3f2a1c9e-4b7d-4a10-9c21-8f6e2d1b5a90"
_NUMERO_PEDIDO_EJEMPLO = "PED-2026-00123"
_USUARIO_EJEMPLO = "jperez"


def _preview_migracion() -> Tuple[str, str]:
    return _en._build_migracion_email(5, 2, 30, _FECHA_EJEMPLO)


def _preview_error_migracion() -> Tuple[str, str]:
    return _en._build_error_migracion_email(
        "Timeout al conectar con el servicio SAP Service Layer", _FECHA_EJEMPLO
    )


def _preview_homologacion() -> Tuple[str, str]:
    return _en._build_homologacion_email(
        _PRODUCTOS_NO_HOMOLOGADOS_EJEMPLO, _ESTADISTICAS_HOMOLOGACION_EJEMPLO, _FECHA_EJEMPLO
    )


def _preview_capacity_warning() -> Tuple[str, str]:
    return _en._build_capacity_warning_email(
        "time_limit", {"porcentaje_usado": 85, "tiempo_transcurrido_min": 51}, _FECHA_EJEMPLO
    )


def _preview_oc_proveedor() -> Tuple[str, str]:
    return _en._build_oc_proveedor_email(
        _OC_CABECERA_EJEMPLO, _OC_DETALLES_EJEMPLO, 48213, 987654, _FECHA_EJEMPLO
    )


def _preview_despacho() -> Tuple[str, str]:
    return _en._build_despacho_email(
        _OC_CABECERA_EJEMPLO, 48213, 987654,
        _SOLICITUDES_TRANSFERENCIA_EJEMPLO, _NUMERO_PEDIDO_EJEMPLO, _FECHA_EJEMPLO,
    )


def _preview_oc_st_error() -> Tuple[str, str]:
    return _en._build_oc_st_error_email(
        _OC_CABECERA_EJEMPLO, 48213, 987654,
        _SOLICITUDES_TRANSFERENCIA_CON_ERROR_EJEMPLO, _NUMERO_PEDIDO_EJEMPLO, _FECHA_EJEMPLO,
    )


def _preview_oc_creacion_error() -> Tuple[str, str]:
    return _en._build_oc_creacion_error_email(
        _OC_CABECERA_EJEMPLO, "Artículo no habilitado para compra en esta bodega", _NUMERO_PEDIDO_EJEMPLO, _FECHA_EJEMPLO,
    )


def _preview_plantilla() -> Tuple[str, str]:
    return _en._build_plantilla_email(
        _PEDIDO_ID_EJEMPLO, _NUMERO_PEDIDO_EJEMPLO, "pedido_agosto.xlsx", _USUARIO_EJEMPLO,
        18, 4, "Formato Est&aacute;ndar", _FECHA_EJEMPLO,
    )


def _preview_pedido_cancelado() -> Tuple[str, str]:
    return _en._build_pedido_cancelado_email(
        _PEDIDO_ID_EJEMPLO, _NUMERO_PEDIDO_EJEMPLO, _USUARIO_EJEMPLO, _FECHA_EJEMPLO
    )


def _preview_pedido_descartado() -> Tuple[str, str]:
    return _en._build_pedido_descartado_email(
        _PEDIDO_ID_EJEMPLO, _NUMERO_PEDIDO_EJEMPLO, _USUARIO_EJEMPLO, _FECHA_EJEMPLO
    )


def _preview_redistribucion_confirmada() -> Tuple[str, str]:
    return _en._build_redistribucion_confirmada_email(
        _PEDIDO_ID_EJEMPLO, _NUMERO_PEDIDO_EJEMPLO, _USUARIO_EJEMPLO, 2, 15, 120, _FECHA_EJEMPLO
    )


def _preview_pedido_confirmado_produccion() -> Tuple[str, str]:
    return _en._build_pedido_confirmado_produccion_email(
        _PEDIDO_ID_EJEMPLO, _NUMERO_PEDIDO_EJEMPLO, _USUARIO_EJEMPLO, _FECHA_EJEMPLO
    )


def _preview_pedido_cancelado_por_el_rayo() -> Tuple[str, str]:
    return _en._build_pedido_cancelado_por_el_rayo_email(
        _PEDIDO_ID_EJEMPLO, _NUMERO_PEDIDO_EJEMPLO, _USUARIO_EJEMPLO, _FECHA_EJEMPLO
    )


def _preview_pedido_confirmado_por_el_rayo() -> Tuple[str, str]:
    return _enp._build_pedido_confirmado_por_el_rayo_email(
        _PEDIDO_ID_EJEMPLO, _NUMERO_PEDIDO_EJEMPLO, _USUARIO_EJEMPLO, 3, _FECHA_EJEMPLO
    )


# Clave: (tipo_notificacion, tipo_correo) tal como se guardan en
# notificacion_tipo_correo (ver seed en scripts/migrations/create_notificacion_tipo_correo.sql).
_DISPATCH: Dict[Tuple[str, str], Callable[[], Tuple[str, str]]] = {
    ("PRODUCCION_ELRAYO", "Plantilla Excel Procesada (Pedido Enviado)"): _preview_plantilla,
    ("OPERACIONES", "Pedido Descartado"): _preview_pedido_descartado,
    ("OPERACIONES", "Pedido Cancelado por Mabel"): _preview_pedido_cancelado,
    ("MABEL_TRADING", "Pedido Cancelado por El Rayo"): _preview_pedido_cancelado_por_el_rayo,
    ("MABEL_TRADING", "Pedido Confirmado por El Rayo"): _preview_pedido_confirmado_por_el_rayo,
    ("OPERACIONES", "Pedido Confirmado por Producción"): _preview_pedido_confirmado_produccion,
    ("OPERACIONES", "Redistribución Confirmada por MABEL TRADING"): _preview_redistribucion_confirmada,
    ("OPERACIONES", "Orden de Compra Generada"): _preview_oc_proveedor,
    ("OPERACIONES", "OC y Solicitudes de Transferencia - Listo para Despacho"): _preview_despacho,
    ("MABEL_TRADING", "OC y Solicitudes de Transferencia - Listo para Despacho"): _preview_despacho,
    ("TECNICOS", "Error en OC y Solicitudes de Transferencia"): _preview_oc_st_error,
    ("TECNICOS", "Error al crear ODC en SAP (reconciliación automática)"): _preview_oc_creacion_error,
    ("OPERACIONES", "Nuevos Registros Migrados"): _preview_migracion,
    ("HOMOLOGACIONES", "Productos NO Homologados Detectados"): _preview_homologacion,
    ("TECNICOS", "Error en Migración Automática"): _preview_error_migracion,
    ("TECNICOS", "Advertencia de Capacidad"): _preview_capacity_warning,
}


def construir_vista_previa(tipo_notificacion: str, tipo_correo: str) -> Optional[Tuple[str, str]]:
    """
    Devuelve (subject, html) de ejemplo para una fila del catálogo, o None si
    no hay un código de envío real asociado a ese (tipo_notificacion, tipo_correo).
    """
    builder = _DISPATCH.get((tipo_notificacion, tipo_correo))
    if builder is None:
        return None
    return builder()
