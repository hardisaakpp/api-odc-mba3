"""
Excepciones personalizadas para la aplicación.
"""
from typing import Optional


class QueryValidationError(Exception):
    """Excepción para errores de validación de consultas SQL."""
    pass


class MBA3ConnectionError(Exception):
    """Excepción para errores de conexión con MBA3."""
    pass


class MBA3QueryError(Exception):
    """Excepción para errores al ejecutar consultas en MBA3."""
    pass


class BusinessException(Exception):
    """
    Excepción para errores de lógica de negocio.

    Se usa para validaciones críticas que deben bloquear operaciones,
    como validación SAP obligatoria antes de persistir pedidos.

    Attributes:
        message: Mensaje de error legible
        error_code: Código de error para identificación programática
        data: Datos estructurados adicionales (dict) para el frontend
    """
    def __init__(self, message: str, error_code: Optional[str] = None, data: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "BUSINESS_ERROR"
        self.data = data or {}


class SolicitudTransferenciaNoAplicaError(Exception):
    """
    No hay distribución válida hacia tiendas para crear Solicitudes de Transferencia (ITR).

    No es un error de SAP ni de Service Layer: es un resultado esperado cuando toda la
    distribución del pedido es hacia bodegas (no hacia tiendas), así que no corresponde
    generar ITR. Se lanza solo después de validar las tiendas en SAP (stock_transfer_service.
    _validar_tiendas_en_sap), por lo que nunca se confunde con una caída del Service Layer.
    Se distingue de otras excepciones para que ni el correo a técnicos ni el modal de
    integración SAP lo traten como una falla real.
    """
    pass


class SAPDataMasterError(BusinessException):
    """
    Excepción para errores de datos maestros en SAP.

    Se lanza cuando un artículo no está configurado correctamente en SAP:
    - No existe en SAP
    - No está dado de alta en la bodega requerida
    - No es inventariable
    - ItemCode incorrecto

    Esta excepción debe CORTAR el flujo inmediatamente, no continuar con validaciones.

    Attributes:
        item_code: Código del artículo con problema
        warehouse_code: Bodega donde se requiere el artículo
        error_type: Tipo de error ('no_warehouse_info', 'warehouse_not_found')
        available_warehouses: Lista de bodegas donde SÍ está configurado (si aplica)
    """
    def __init__(
        self, 
        item_code: str,
        warehouse_code: str,
        error_type: str,
        message: Optional[str] = None,
        available_warehouses: Optional[list] = None
    ):
        if message is None:
            if error_type == "no_warehouse_info":
                message = (
                    f"El artículo {item_code} no está asociado a la bodega {warehouse_code} en SAP. "
                    f"El artículo puede no existir, no estar dado de alta en ninguna bodega, "
                    f"no ser inventariable, o el ItemCode puede ser incorrecto. "
                    f"Contacte a logística o maestros de artículos para verificar la configuración del artículo."
                )
            elif error_type == "warehouse_not_found":
                warehouses_str = ", ".join(available_warehouses) if available_warehouses else "NINGUNA"
                message = (
                    f"El artículo {item_code} no está asociado a la bodega {warehouse_code} en SAP. "
                    f"Bodegas donde SÍ está configurado: {warehouses_str}. "
                    f"Contacte a logística o maestros de artículos para asociar el artículo a la bodega {warehouse_code}."
                )
            else:
                message = (
                    f"El artículo {item_code} no está correctamente configurado en la bodega {warehouse_code} en SAP. "
                    f"Contacte a logística o maestros de artículos para verificar la configuración del artículo."
                )
        
        super().__init__(
            message=message,
            error_code="SAP_DATA_MASTER_ERROR",
            data={
                "item_code": item_code,
                "warehouse_code": warehouse_code,
                "error_type": error_type,
                "available_warehouses": available_warehouses or []
            }
        )
        self.item_code = item_code
        self.warehouse_code = warehouse_code
        self.error_type = error_type
        self.available_warehouses = available_warehouses or []
