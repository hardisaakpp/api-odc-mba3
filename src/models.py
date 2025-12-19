"""
Modelos Pydantic para la API de consultas MBA3.

Define los esquemas de request y response para los endpoints.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class QueryRequest(BaseModel):
    """Modelo para recibir consultas SQL."""
    
    query: Optional[str] = Field(None, description="Consulta SQL completa como string")
    select: Optional[str] = Field(None, description="Campos SELECT")
    from_: Optional[str] = Field(None, alias="from", description="Tabla FROM")
    where: Optional[str] = Field(None, description="Cláusula WHERE")
    orderBy: Optional[str] = Field(None, description="Cláusula ORDER BY")
    limit: Optional[str] = Field(None, description="Cláusula LIMIT")
    
    class Config:
        populate_by_name = True  # Permite usar tanto "from" como "from_"


class ParsedQuery(BaseModel):
    """Modelo para representar una consulta parseada."""
    
    select: Optional[str] = None
    from_: Optional[str] = Field(None, alias="from")
    where: Optional[str] = None
    orderBy: Optional[str] = None
    limit: Optional[str] = None
    
    class Config:
        populate_by_name = True


class QueryResponse(BaseModel):
    """Modelo de respuesta para el endpoint /query."""
    
    original: str = Field(..., description="Consulta SQL original tal cual fue enviada")
    parsed: Dict[str, Any] = Field(..., description="Objeto con campos parseados")
    received_at: str = Field(..., description="Timestamp ISO8601 de recepción")
    source: str = Field(..., description="Fuente de la consulta (Postman, API, etc.)")
    note: str = Field(..., description="Estado del parseo (PARSE_OK, PARSE_FAIL, etc.)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "original": "select * from clnt_factura_principal where NUMERO_PEDIDO_SISTEMA='176120'",
                "parsed": {
                    "select": "*",
                    "from": "clnt_factura_principal",
                    "where": "NUMERO_PEDIDO_SISTEMA='176120'",
                    "orderBy": None,
                    "limit": None
                },
                "received_at": "2025-01-21T12:00:00-05:00",
                "source": "Postman",
                "note": "PARSE_OK"
            }
        }


class HealthResponse(BaseModel):
    """Modelo de respuesta para el endpoint /health."""
    
    status: str = Field(..., description="Estado del servicio")
    time: str = Field(..., description="Timestamp ISO8601")


# Modelos para la respuesta de MBA3
class LineaFactura(BaseModel):
    """Modelo para una línea de factura dentro de ObjDatosFactura."""
    
    Codigo: Optional[str] = None
    Nombre: Optional[str] = None
    Cantidad: Optional[float] = None
    PrecioUnitario: Optional[float] = None
    TotalLinea: Optional[float] = None
    Descuento: Optional[float] = None
    Impuesto: Optional[float] = None
    RegNum: Optional[int] = None


class ObjDatosFactura(BaseModel):
    """Modelo para el objeto anidado ObjDatosFactura de MBA3."""
    
    Lineas: Optional[list[LineaFactura]] = None
    CtrlEliminados1: Optional[list[LineaFactura]] = None
    CtrlEliminados2: Optional[list[LineaFactura]] = None
    CtrlEliminados3: Optional[list[LineaFactura]] = None
    CtrlEliminados4: Optional[list[LineaFactura]] = None
    CtrlEliminadosA: Optional[list[LineaFactura]] = None
    CtrlEliminadosB: Optional[list[LineaFactura]] = None
    GrabarLineasProd: Optional[list[LineaFactura]] = None


class FacturaMBA3(BaseModel):
    """
    Modelo para representar una factura devuelta por la API de MBA3.
    
    Ejemplo de respuesta JSON de MBA3:
    {
      "CODIGO_FACTURA": "REMSI-900125351-TRAYO",
      "NUMERO_FACTURA": 900125351,
      "EMPRESA": "TRAYO",
      "CODIGO_CLIENTE": "CLI0513",
      "FECHA_FACTURA": "2025-11-20",
      "FECHA_VENCIMIENTO": "2026-02-18",
      "NUMERO_ORDEN": 129165,
      "NUMERO_PEDIDO_SISTEMA": 176120,
      "VALOR_FACTURA": 2438.46,
      "TOTAL_IMPUESTOS": 318.06,
      "ObjDatosFactura": {
        "Lineas": [
          {
            "Codigo": "5-0012.9",
            "Nombre": "MDS TOB M/FELPA T.9-11",
            "Cantidad": 456,
            "PrecioUnitario": 4.65,
            "TotalLinea": 2120.4
          }
        ]
      }
    }
    """
    
    CODIGO_FACTURA: Optional[str] = None
    NUMERO_FACTURA: Optional[int] = None
    EMPRESA: Optional[str] = None
    CODIGO_CLIENTE: Optional[str] = None
    FECHA_FACTURA: Optional[str] = None
    FECHA_VENCIMIENTO: Optional[str] = None
    NUMERO_ORDEN: Optional[int] = None
    NUMERO_PEDIDO_SISTEMA: Optional[int] = None
    VALOR_FACTURA: Optional[float] = None
    TOTAL_IMPUESTOS: Optional[float] = None
    ANULADA: Optional[bool] = None
    CODIGO_DESPACHO: Optional[int] = None
    TIPO_DOCUMENTO: Optional[str] = None
    ORDEN_COMPRA: Optional[str] = None
    ORDEN_COMPRA_CLIENTE: Optional[str] = None
    Remision_Facturada: Optional[bool] = None
    NumIDFacturaRelacionada: Optional[int] = None
    ObjDatosFactura: Optional[ObjDatosFactura] = None
    
    class Config:
        # Permitir campos adicionales que puedan venir de MBA3
        extra = "allow"


# ============================================================================
# Modelos para Preferencias de Usuario
# ============================================================================

class TablePreferencesDto(BaseModel):
    """Modelo para las preferencias de una tabla (formato del frontend)."""
    
    visibleColumns: list[str] = Field(..., description="Lista de columnas visibles")
    columnOrder: list[str] = Field(..., description="Orden de columnas")
    filters: Optional[Dict[str, Any]] = Field(None, description="Filtros aplicados")
    pageSize: Optional[int] = Field(None, description="Tamaño de página")


class SavePreferencesRequest(BaseModel):
    """Modelo para el request de guardar preferencias."""
    
    preferences: TablePreferencesDto


class PreferencesResponse(BaseModel):
    """Modelo de respuesta para obtener preferencias de una tabla."""
    
    preferences: Optional[TablePreferencesDto] = None


class AllPreferencesResponse(BaseModel):
    """Modelo de respuesta para obtener todas las preferencias."""
    
    preferences: Dict[str, TablePreferencesDto]


# ============================================================================
# Modelos para Preferencias del Sidebar
# ============================================================================

class SidebarPreferencesDto(BaseModel):
    """Modelo para las preferencias del sidebar."""
    
    collapsed: bool = Field(..., description="Estado colapsado del sidebar")
    
    @field_validator('collapsed', mode='before')
    @classmethod
    def convert_collapsed(cls, v):
        """
        Convierte diferentes formatos a boolean para mayor flexibilidad.
        
        Acepta:
        - boolean: True/False
        - string: "true", "false", "1", "0", "yes", "no", "on", "off"
        - int: 1 (True), 0 (False)
        
        Args:
            v: Valor a convertir
            
        Returns:
            bool: Valor convertido a boolean
        """
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            # Convertir strings comunes a boolean
            v_lower = v.lower().strip()
            if v_lower in ('true', '1', 'yes', 'on', 'si', 'sí'):
                return True
            if v_lower in ('false', '0', 'no', 'off'):
                return False
            # Si no coincide, intentar convertir directamente
            try:
                return bool(int(v))
            except (ValueError, TypeError):
                pass
        if isinstance(v, int):
            return bool(v)
        # Si no se puede convertir, retornar el valor original
        # Pydantic validará si es boolean después
        return v


class SaveSidebarPreferencesRequest(BaseModel):
    """
    Modelo para el request de guardar preferencias del sidebar.
    
    Acepta dos formatos:
    1. Formato estándar: {"preferences": {"collapsed": true}}
    2. Formato alternativo: {"collapsed": true}
    """
    
    preferences: Optional[Union[Dict[str, Any], 'SidebarPreferencesDto']] = None  # Puede ser dict o objeto validado
    collapsed: Optional[bool] = None  # Permitir formato alternativo: {collapsed: true}
    
    class Config:
        # Permitir campos adicionales para mayor flexibilidad
        extra = "allow"
    
    @model_validator(mode='after')
    def validate_and_normalize(self):
        """
        Valida y normaliza los datos después de la validación inicial.
        
        Convierte el formato alternativo al estándar y valida que
        preferences sea un SidebarPreferencesDto válido.
        """
        # Si viene con formato alternativo (collapsed directamente), convertirlo
        if self.preferences is None and self.collapsed is not None:
            self.preferences = {'collapsed': self.collapsed}
        
        # Si preferences es un dict, validarlo como SidebarPreferencesDto
        if isinstance(self.preferences, dict):
            # Validar que tenga collapsed
            if 'collapsed' not in self.preferences:
                raise ValueError("'preferences.collapsed' es requerido")
            # Convertir a SidebarPreferencesDto para validación
            try:
                # Crear instancia de SidebarPreferencesDto para validar
                sidebar_prefs = SidebarPreferencesDto(**self.preferences)
                # Reemplazar el dict con el objeto validado
                self.preferences = sidebar_prefs
            except Exception as e:
                raise ValueError(f"Error al validar preferences: {str(e)}")
        
        # Validar que al menos preferences o collapsed esté presente
        if self.preferences is None and self.collapsed is None:
            raise ValueError("Se requiere 'preferences' o 'collapsed' en el request")
        
        return self


class SidebarPreferencesResponse(BaseModel):
    """Modelo de respuesta para obtener preferencias del sidebar."""
    
    preferences: Optional[SidebarPreferencesDto] = None


# ============================================================================
# MODELOS PARA HOMOLOGACIONES SKU
# ============================================================================

class SkuHomologacion(BaseModel):
    """Modelo para una homologación SKU entre MBA3 y SAP."""
    
    homologacion_id: str = Field(..., description="ID único de la homologación")
    
    # Datos de MBA3
    sku_mba3: str = Field(..., description="SKU desde MBA3")
    nombre_producto_mba3: Optional[str] = Field(None, description="Nombre del producto desde MBA3")
    precio_unitario_mba3: Optional[float] = Field(None, description="Precio unitario desde MBA3")
    cantidad_docena_mba3: Optional[float] = Field(None, description="Cantidad en docenas desde MBA3")
    total_linea_mba3: Optional[float] = Field(None, description="Total de la línea desde MBA3")
    
    # Datos de SAP (pueden ser null)
    sku_sap: Optional[str] = Field(None, description="SKU en SAP")
    nombre_producto_sap: Optional[str] = Field(None, description="Nombre del producto en SAP")
    precio_unitario_sap: Optional[float] = Field(None, description="Precio unitario en SAP")
    cantidad_pack_sap: Optional[float] = Field(None, description="Cantidad por pack en SAP")
    unidad_sap: Optional[str] = Field(None, description="Unidad de medida en SAP")
    subtotal_sap: Optional[float] = Field(None, description="Subtotal en SAP")
    
    # Estado y flags
    estado: str = Field(..., description="Estado de la homologación (PENDIENTE, HOMOLOGADO, ERROR)")
    tiene_diferencias: bool = Field(..., description="Indica si hay diferencias entre MBA3 y SAP")
    tiene_datos_sap: bool = Field(..., description="Indica si tiene al menos un dato de SAP")
    
    # Relaciones
    detalle_id: Optional[str] = Field(None, description="ID del detalle del despacho relacionado")
    despacho_id: Optional[str] = Field(None, description="ID del despacho relacionado")
    
    # Metadatos
    created_at: Optional[str] = Field(None, description="Fecha de creación (ISO 8601)")
    updated_at: Optional[str] = Field(None, description="Fecha de actualización (ISO 8601)")
    ultima_modificacion: Optional[str] = Field(None, description="Última modificación (ISO 8601)")
    modificado_por: Optional[str] = Field(None, description="Usuario que modificó")
    
    class Config:
        json_schema_extra = {
            "example": {
                "homologacion_id": "uuid-123",
                "sku_mba3": "SKU001",
                "nombre_producto_mba3": "Producto Ejemplo",
                "precio_unitario_mba3": 100.50,
                "cantidad_docena_mba3": 12.0,
                "total_linea_mba3": 1206.00,
                "sku_sap": "SKU001-SAP",
                "nombre_producto_sap": "Producto SAP",
                "precio_unitario_sap": 100.00,
                "cantidad_pack_sap": 10.0,
                "unidad_sap": "UN",
                "subtotal_sap": 1000.00,
                "estado": "PENDIENTE",
                "tiene_diferencias": True,
                "tiene_datos_sap": True,
                "detalle_id": "detalle-123",
                "despacho_id": "despacho-456",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
        }


class HomologacionSkuUpdateRequest(BaseModel):
    """Modelo para actualizar una homologación SKU."""
    
    sku_sap: Optional[str] = Field(None, description="SKU en SAP")
    nombre_producto_sap: Optional[str] = Field(None, description="Nombre del producto en SAP")
    precio_unitario_sap: Optional[float] = Field(None, ge=0, description="Precio unitario en SAP (>= 0)")
    cantidad_pack_sap: Optional[float] = Field(None, ge=0, description="Cantidad por pack en SAP (>= 0)")
    unidad_sap: Optional[str] = Field(None, description="Unidad de medida en SAP")
    subtotal_sap: Optional[float] = Field(None, description="Subtotal en SAP")
    estado: Optional[str] = Field(None, description="Estado (PENDIENTE, HOMOLOGADO, ERROR)")
    
    @field_validator('estado')
    @classmethod
    def validate_estado(cls, v):
        if v is not None and v not in ['PENDIENTE', 'HOMOLOGADO', 'ERROR']:
            raise ValueError('Estado debe ser PENDIENTE, HOMOLOGADO o ERROR')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "sku_sap": "SKU001-SAP",
                "nombre_producto_sap": "Producto SAP Actualizado",
                "precio_unitario_sap": 105.00,
                "cantidad_pack_sap": 12.0,
                "unidad_sap": "UN",
                "subtotal_sap": 1260.00,
                "estado": "HOMOLOGADO"
            }
        }


class HomologacionSkuBulkUpdateItem(BaseModel):
    """Modelo para un item de actualización masiva."""
    
    homologacion_id: str = Field(..., description="ID de la homologación a actualizar")
    data: HomologacionSkuUpdateRequest = Field(..., description="Datos a actualizar")


class HomologacionSkuBulkUpdateRequest(BaseModel):
    """Modelo para actualización masiva de homologaciones."""
    
    updates: List[HomologacionSkuBulkUpdateItem] = Field(..., description="Lista de actualizaciones")
    
    class Config:
        json_schema_extra = {
            "example": {
                "updates": [
                    {
                        "homologacion_id": "uuid-123",
                        "data": {
                            "sku_sap": "SKU001-SAP",
                            "precio_unitario_sap": 105.00,
                            "estado": "HOMOLOGADO"
                        }
                    },
                    {
                        "homologacion_id": "uuid-456",
                        "data": {
                            "sku_sap": "SKU002-SAP",
                            "estado": "HOMOLOGADO"
                        }
                    }
                ]
            }
        }


class HomologacionesSkuListResponse(BaseModel):
    """Modelo de respuesta para listar homologaciones."""
    
    status: str = Field(..., description="Estado de la respuesta")
    data: List[SkuHomologacion] = Field(..., description="Lista de homologaciones")
    metadata: Dict[str, Any] = Field(..., description="Metadatos y estadísticas")
    total: int = Field(..., description="Total de registros")
    page: int = Field(..., description="Página actual")
    pageSize: int = Field(..., description="Tamaño de página")
    totalPages: int = Field(..., description="Total de páginas")


class HomologacionSkuResponse(BaseModel):
    """Modelo de respuesta para una homologación individual."""
    
    status: str = Field(..., description="Estado de la respuesta")
    data: Optional[SkuHomologacion] = Field(None, description="Datos de la homologación")
    message: Optional[str] = Field(None, description="Mensaje adicional")


class HomologacionSkuBulkUpdateResponse(BaseModel):
    """Modelo de respuesta para actualización masiva."""
    
    status: str = Field(..., description="Estado de la respuesta")
    data: Dict[str, Any] = Field(..., description="Resultados de la actualización")


class HomologacionSkuSincronizarResponse(BaseModel):
    """Modelo de respuesta para sincronización."""
    
    status: str = Field(..., description="Estado de la respuesta")
    data: Dict[str, Any] = Field(..., description="Resultados de la sincronización")

