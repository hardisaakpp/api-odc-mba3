"""
Modelos Pydantic para la API de consultas MBA3.

Define los esquemas de request y response para los endpoints.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List, Union
from datetime import datetime
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


class HomologacionSkuCreateRequest(BaseModel):
    """Modelo para crear una nueva homologación SKU."""
    
    # Datos de MBA3 (requeridos)
    sku_mba3: str = Field(..., description="SKU desde MBA3 (requerido)")
    nombre_producto_mba3: Optional[str] = Field(None, description="Nombre del producto desde MBA3")
    precio_unitario_mba3: Optional[float] = Field(None, ge=0, description="Precio unitario desde MBA3 (>= 0)")
    cantidad_docena_mba3: Optional[float] = Field(None, ge=0, description="Cantidad en docenas desde MBA3 (>= 0)")
    total_linea_mba3: Optional[float] = Field(None, description="Total de la línea desde MBA3")
    
    # Datos de SAP (opcionales)
    sku_sap: Optional[str] = Field(None, description="SKU en SAP")
    nombre_producto_sap: Optional[str] = Field(None, description="Nombre del producto en SAP")
    precio_unitario_sap: Optional[float] = Field(None, ge=0, description="Precio unitario en SAP (>= 0)")
    cantidad_pack_sap: Optional[float] = Field(None, ge=0, description="Cantidad por pack en SAP (>= 0)")
    unidad_sap: Optional[str] = Field(None, description="Unidad de medida en SAP")
    subtotal_sap: Optional[float] = Field(None, description="Subtotal en SAP")
    
    # Estado (opcional, default PENDIENTE)
    estado: Optional[str] = Field(None, description="Estado (PENDIENTE, HOMOLOGADO, ERROR)")
    
    # Relaciones (opcionales)
    detalle_id: Optional[str] = Field(None, description="ID del detalle del despacho relacionado")
    despacho_id: Optional[str] = Field(None, description="ID del despacho relacionado")
    
    @field_validator('estado')
    @classmethod
    def validate_estado(cls, v):
        if v is not None and v not in ['PENDIENTE', 'HOMOLOGADO', 'ERROR']:
            raise ValueError('Estado debe ser PENDIENTE, HOMOLOGADO o ERROR')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "sku_mba3": "SKU001",
                "nombre_producto_mba3": "Producto Ejemplo MBA3",
                "precio_unitario_mba3": 100.50,
                "cantidad_docena_mba3": 12.0,
                "total_linea_mba3": 1206.00,
                "sku_sap": "SKU001-SAP",
                "nombre_producto_sap": "Producto SAP",
                "precio_unitario_sap": 100.00,
                "cantidad_pack_sap": 10.0,
                "unidad_sap": "UN",
                "subtotal_sap": 1000.00,
                "estado": "PENDIENTE"
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


# ============================================================================
# MODELOS PARA RESPUESTA DEL PROVEEDOR (FASE 3 - INTERFAZ WEB)
# ============================================================================

class TiendaRespuesta(BaseModel):
    """Modelo para respuesta por tienda (opcional, para distribución detallada)."""
    
    tienda_id: str = Field(..., description="ID de la tienda")
    cantidad_confirmada: Optional[int] = Field(None, ge=0, description="Cantidad confirmada para esta tienda específica")


class ProductoRespuesta(BaseModel):
    """Modelo para respuesta de un producto del proveedor."""
    
    pedido_detalle_id: str = Field(..., description="ID del detalle del pedido")
    codigo_producto: str = Field(..., description="Código del producto")
    cantidad_confirmada_total: int = Field(..., ge=0, description="Cantidad confirmada total (consolidado por producto)")
    costo_unitario_ajustado: Optional[float] = Field(None, ge=0, description="Costo unitario ajustado (opcional)")
    descuento_ajustado: Optional[float] = Field(None, ge=0, le=100, description="Descuento % ajustado (opcional, 0-100)")
    observaciones: Optional[str] = Field(None, max_length=1000, description="Observaciones del proveedor para este producto")
    distribucion_tiendas: Optional[List[TiendaRespuesta]] = Field(None, description="Distribución detallada por tienda (opcional)")


class RespuestaProveedorRequest(BaseModel):
    """Modelo para el request completo de respuesta del proveedor desde formulario web."""
    
    productos: List[ProductoRespuesta] = Field(..., min_length=1, description="Lista de productos con sus respuestas")
    observaciones_generales: Optional[str] = Field(None, max_length=2000, description="Observaciones generales de la respuesta")
    estado: str = Field("borrador", description="Estado de la respuesta: 'borrador' o 'confirmado'")
    
    @field_validator('estado')
    @classmethod
    def validate_estado(cls, v):
        if v not in ['borrador', 'confirmado']:
            raise ValueError("Estado debe ser 'borrador' o 'confirmado'")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "productos": [
                    {
                        "pedido_detalle_id": "uuid-123",
                        "codigo_producto": "PROD001",
                        "cantidad_confirmada_total": 100,
                        "costo_unitario_ajustado": 50.00,
                        "descuento_ajustado": 5.0,
                        "observaciones": "Disponible en 2 semanas",
                        "distribucion_tiendas": [
                            {"tienda_id": "uuid-tienda-1", "cantidad_confirmada": 60},
                            {"tienda_id": "uuid-tienda-2", "cantidad_confirmada": 40}
                        ]
                    }
                ],
                "observaciones_generales": "Todos los productos disponibles",
                "estado": "confirmado"
            }
        }


class TiendaFormulario(BaseModel):
    """Modelo para mostrar tienda en el formulario."""
    
    tienda_id: str
    codigo: str
    nombre: Optional[str] = None
    cantidad_solicitada: int = Field(..., ge=0)


class ProductoFormulario(BaseModel):
    """Modelo para mostrar producto en el formulario del proveedor."""
    
    pedido_detalle_id: str
    codigo_producto: str
    descripcion: Optional[str] = None
    marca: Optional[str] = None
    cantidad_total_solicitada: int = Field(..., ge=0)
    costo_unitario_original: Optional[float] = None
    descuento_original: Optional[float] = None
    tiendas: List[TiendaFormulario] = Field(default_factory=list)
    # Campos de respuesta existente (si ya respondió)
    cantidad_confirmada_total: Optional[int] = None
    costo_unitario_ajustado: Optional[float] = None
    descuento_ajustado: Optional[float] = None
    observaciones: Optional[str] = None


class FormularioProveedorResponse(BaseModel):
    """Modelo de respuesta para el GET del formulario del proveedor."""
    
    pedido_id: str
    numero_pedido: str
    fecha_pedido: Optional[str] = None
    fecha_entrega: Optional[str] = None
    proveedor_nombre: Optional[str] = None
    estado_pedido: str = Field(..., description="Estado actual del pedido")
    puede_responder: bool = Field(..., description="Si el proveedor puede responder (no está cerrado/bloqueado)")
    tiene_respuesta: bool = Field(..., description="Si ya existe una respuesta previa")
    respuesta_id: Optional[str] = None
    version_respuesta: Optional[int] = None
    estado_respuesta: Optional[str] = None
    productos: List[ProductoFormulario] = Field(..., min_length=1)
    mensaje_estado: Optional[str] = Field(None, description="Mensaje explicativo del estado actual")


class RespuestaProveedorResponse(BaseModel):
    """Modelo de respuesta para el POST de respuesta del proveedor."""
    
    status: str = Field(..., description="Estado del procesamiento: 'success', 'validation_error', 'error'")
    message: str = Field(..., description="Mensaje descriptivo")
    respuesta_id: Optional[str] = None
    validacion: Dict[str, Any] = Field(..., description="Resultado de validaciones")
    cantidades_guardadas: Optional[int] = None
    precios_guardados: Optional[int] = None
    pedido_id: str
    estado_guardado: Optional[str] = Field(None, description="Estado en que se guardó: 'BORRADOR' o 'PENDIENTE_REVISION'")


class ActualizarCostoRequest(BaseModel):
    """Modelo para el request de actualizar costo de un detalle de pedido."""
    
    costo_doc_sin_iva: float = Field(..., ge=0, description="Nuevo costo unitario sin IVA (DECIMAL, debe ser >= 0)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "costo_doc_sin_iva": 25.50
            }
        }


class ActualizarTotalRequest(BaseModel):
    """Modelo para el request de actualizar total de un detalle de pedido."""
    
    total: int = Field(..., ge=0, description="Nuevo total del detalle (ENTERO, debe ser >= 0, incluye 0)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total": 510
            }
        }


class ActualizarComentarioRequest(BaseModel):
    """Modelo para el request de actualizar comentario de un detalle de pedido."""
    
    comentario: Optional[str] = Field(None, max_length=2000, description="Nuevo comentario del detalle (máximo 2000 caracteres)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "comentario": "Producto con descuento especial"
            }
        }


class ColumnaModificadaItem(BaseModel):
    """Modelo para un item de modificación de columna."""
    
    pedido_detalle_id: str = Field(..., description="UUID del detalle del pedido")
    columna_key: str = Field(..., description="Clave de la columna modificada (costo_doc_sin_iva, total, comentario)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "pedido_detalle_id": "550e8400-e29b-41d4-a716-446655440000",
                "columna_key": "costo_doc_sin_iva"
            }
        }


class GuardarModificacionesColumnasRequest(BaseModel):
    """Modelo para el request de guardar modificaciones de columnas."""
    
    numero_pedido: str = Field(..., description="Número del pedido")
    modificaciones: List[ColumnaModificadaItem] = Field(..., description="Lista de modificaciones de columnas")
    
    class Config:
        json_schema_extra = {
            "example": {
                "numero_pedido": "P-12.48 - 12 - 2025",
                "modificaciones": [
                    {
                        "pedido_detalle_id": "550e8400-e29b-41d4-a716-446655440000",
                        "columna_key": "costo_doc_sin_iva"
                    },
                    {
                        "pedido_detalle_id": "550e8400-e29b-41d4-a716-446655440001",
                        "columna_key": "total"
                    }
                ]
            }
        }


class GuardarModificacionesColumnasResponse(BaseModel):
    """Modelo para la respuesta de guardar modificaciones de columnas."""
    
    status: str = Field(default="success", description="Estado de la operación")
    message: str = Field(..., description="Mensaje descriptivo")
    numero_pedido: str = Field(..., description="Número del pedido")
    modificaciones_guardadas: int = Field(..., description="Número de modificaciones guardadas")


class ModificacionColumnaItem(BaseModel):
    """Modelo para un item de modificación obtenido."""
    
    pedido_detalle_id: str = Field(..., description="UUID del detalle del pedido")
    columna_key: str = Field(..., description="Clave de la columna modificada")
    modificado_por: Optional[str] = Field(None, description="Usuario que realizó la modificación")
    fecha_modificacion: str = Field(..., description="Fecha de modificación (ISO 8601)")


class ObtenerModificacionesColumnasResponse(BaseModel):
    """Modelo para la respuesta de obtener modificaciones de columnas."""
    
    status: str = Field(default="success", description="Estado de la operación")
    numero_pedido: str = Field(..., description="Número del pedido")
    modificaciones: List[ModificacionColumnaItem] = Field(default_factory=list, description="Lista de modificaciones")


class NotificarConfirmacionRequest(BaseModel):
    """Modelo para el request de notificar confirmación de pedido."""
    
    usuario_origen: str = Field(default="EL RAYO", description="Usuario que solicita la confirmación")
    usuario_destino: str = Field(default="MABEL TRADING", description="Usuario que debe confirmar")
    email_destino: Optional[str] = Field(None, description="Email del destinatario (opcional, usa EMAIL_MABEL_TRADING si no se proporciona)")
    url_confirmacion: Optional[str] = Field(None, description="URL directa para confirmar el pedido (opcional, se genera automáticamente si no se proporciona)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "usuario_origen": "EL RAYO",
                "usuario_destino": "MABEL TRADING",
                "url_confirmacion": "https://tu-dominio.com/mba3-consultas/pedidos/P-12.48%20-%2012%20-%202025?modo=confirmacion&usuario=mabel-trading"
            }
        }


# ============================================================================
# Modelos para FASE 4: Ajuste y Redistribución (MABEL TRADING)
# ============================================================================

class DistribucionTiendaItem(BaseModel):
    """Modelo para un item de redistribución por tienda."""
    
    tienda_id: str = Field(..., description="UUID de la tienda")
    cantidad_asignada: int = Field(..., ge=0, description="Cantidad asignada a esta tienda (debe ser >= 0)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tienda_id": "123e4567-e89b-12d3-a456-426614174000",
                "cantidad_asignada": 50
            }
        }


class RedistribucionProductoItem(BaseModel):
    """Modelo para redistribución de un producto específico."""
    
    pedido_detalle_id: str = Field(..., description="UUID del detalle del pedido (producto)")
    distribuciones: List[DistribucionTiendaItem] = Field(..., min_items=1, description="Lista de distribuciones por tienda")
    
    class Config:
        json_schema_extra = {
            "example": {
                "pedido_detalle_id": "123e4567-e89b-12d3-a456-426614174001",
                "distribuciones": [
                    {"tienda_id": "123e4567-e89b-12d3-a456-426614174000", "cantidad_asignada": 50},
                    {"tienda_id": "123e4567-e89b-12d3-a456-426614174002", "cantidad_asignada": 30}
                ]
            }
        }


class RedistribuirPedidoRequest(BaseModel):
    """Modelo para el request de redistribuir un pedido."""
    
    productos: List[RedistribucionProductoItem] = Field(..., min_items=1, description="Lista de productos con sus redistribuciones")
    observaciones: Optional[str] = Field(None, max_length=1000, description="Observaciones generales de la redistribución")
    
    class Config:
        json_schema_extra = {
            "example": {
                "productos": [
                    {
                        "pedido_detalle_id": "123e4567-e89b-12d3-a456-426614174001",
                        "distribuciones": [
                            {"tienda_id": "123e4567-e89b-12d3-a456-426614174000", "cantidad_asignada": 50},
                            {"tienda_id": "123e4567-e89b-12d3-a456-426614174002", "cantidad_asignada": 30}
                        ]
                    }
                ],
                "observaciones": "Ajuste por disponibilidad de stock"
            }
        }


class DistribucionConfirmadaItem(BaseModel):
    """Modelo para un item de distribución confirmada."""
    
    id: str = Field(..., description="UUID de la distribución confirmada")
    pedido_detalle_id: str = Field(..., description="UUID del detalle del pedido")
    tienda_id: str = Field(..., description="UUID de la tienda")
    tienda_codigo: Optional[str] = Field(None, description="Código de la tienda")
    tienda_nombre: Optional[str] = Field(None, description="Nombre de la tienda")
    cantidad_solicitada: int = Field(..., ge=0)
    cantidad_confirmada: int = Field(..., ge=0)
    cantidad_asignada: int = Field(..., ge=0)
    costo_unitario_original: Optional[float] = None
    costo_unitario_ajustado: Optional[float] = None
    subtotal_original: Optional[float] = None
    subtotal_ajustado: Optional[float] = None
    version: int = Field(..., ge=1)
    estado: str = Field(..., description="Estado de la distribución")
    fecha_creacion: Optional[datetime] = None
    fecha_modificacion: Optional[datetime] = None


class DistribucionProductoResponse(BaseModel):
    """Modelo para la distribución de un producto."""
    
    pedido_detalle_id: str = Field(..., description="UUID del detalle del pedido")
    codigo_interno: Optional[str] = None
    descripcion_sap: Optional[str] = None
    cantidad_solicitada_total: int = Field(..., ge=0)
    cantidad_confirmada_total: int = Field(..., ge=0)
    cantidad_asignada_total: int = Field(..., ge=0)
    distribuciones: List[DistribucionConfirmadaItem] = Field(default_factory=list)


class DistribucionPedidoResponse(BaseModel):
    """Modelo para la respuesta de obtener distribución de un pedido."""
    
    pedido_id: str = Field(..., description="UUID del pedido")
    numero_pedido: str = Field(..., description="Número del pedido")
    version_actual: int = Field(..., ge=1, description="Versión actual de la redistribución")
    estado_pedido: Optional[str] = None
    productos: List[DistribucionProductoResponse] = Field(default_factory=list)


class DiferenciaProductoItem(BaseModel):
    """Modelo para diferencia de un producto."""
    
    pedido_detalle_id: str = Field(..., description="UUID del detalle del pedido")
    codigo_interno: Optional[str] = None
    descripcion_sap: Optional[str] = None
    cantidad_solicitada: int = Field(..., ge=0)
    cantidad_confirmada: int = Field(..., ge=0)
    cantidad_asignada: int = Field(..., ge=0)
    diferencia_cantidad: int = Field(..., description="cantidad_asignada - cantidad_confirmada (puede ser negativa)")
    costo_unitario_original: Optional[float] = None
    costo_unitario_ajustado: Optional[float] = None
    subtotal_original: Optional[float] = None
    subtotal_ajustado: Optional[float] = None
    diferencia_costo: Optional[float] = Field(None, description="subtotal_ajustado - subtotal_original")


class DiferenciaTiendaItem(BaseModel):
    """Modelo para diferencia por tienda."""
    
    tienda_id: str = Field(..., description="UUID de la tienda")
    tienda_codigo: Optional[str] = None
    tienda_nombre: Optional[str] = None
    cantidad_solicitada: int = Field(..., ge=0)
    cantidad_confirmada: int = Field(..., ge=0)
    cantidad_asignada: int = Field(..., ge=0)
    diferencia_cantidad: int = Field(..., description="cantidad_asignada - cantidad_confirmada")


class ReporteDiferenciasResponse(BaseModel):
    """Modelo para el reporte de diferencias."""
    
    pedido_id: str = Field(..., description="UUID del pedido")
    numero_pedido: str = Field(..., description="Número del pedido")
    version: int = Field(..., ge=1)
    fecha_generacion: datetime = Field(default_factory=datetime.now)
    
    # Resumen total
    total_productos: int = Field(..., ge=0)
    total_cantidad_solicitada: int = Field(..., ge=0)
    total_cantidad_confirmada: int = Field(..., ge=0)
    total_cantidad_asignada: int = Field(..., ge=0)
    total_diferencia_cantidad: int = Field(..., description="Total diferencia de cantidad")
    total_costo_original: Optional[float] = None
    total_costo_ajustado: Optional[float] = None
    total_diferencia_costo: Optional[float] = Field(None, description="Total diferencia de costo")
    
    # Detalle por producto
    diferencias_productos: List[DiferenciaProductoItem] = Field(default_factory=list)
    
    # Detalle por tienda
    diferencias_tiendas: List[DiferenciaTiendaItem] = Field(default_factory=list)


class ConfirmarRedistribucionRequest(BaseModel):
    """Modelo para confirmar una redistribución."""
    
    version: Optional[int] = Field(None, ge=1, description="Versión a confirmar (si no se especifica, se confirma la última)")
    observaciones: Optional[str] = Field(None, max_length=1000, description="Observaciones de la confirmación")
    
    class Config:
        json_schema_extra = {
            "example": {
                "version": 1,
                "observaciones": "Redistribución validada y confirmada"
            }
        }


class ConfirmarRedistribucionResponse(BaseModel):
    """Modelo para la respuesta de confirmar redistribución."""
    
    pedido_id: str = Field(..., description="UUID del pedido")
    numero_pedido: str = Field(..., description="Número del pedido")
    version_confirmada: int = Field(..., ge=1)
    estado_anterior: str
    estado_nuevo: str
    fecha_confirmacion: datetime = Field(default_factory=datetime.now)
    mensaje: str = Field(..., description="Mensaje de confirmación")


# ============================================================================
# Modelos compatibles con Frontend (AjusteDetalle)
# ============================================================================

class DistribucionTiendaFrontend(BaseModel):
    """Modelo para distribución por tienda (compatible con frontend)."""
    
    tienda_codigo: str = Field(..., description="Código de la tienda")
    tienda_nombre: Optional[str] = Field(None, description="Nombre de la tienda")
    cantidad: int = Field(..., ge=0, description="Cantidad asignada a esta tienda")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tienda_codigo": "T001",
                "tienda_nombre": "Tienda Principal",
                "cantidad": 50
            }
        }


class AjusteDetalle(BaseModel):
    """Modelo para ajuste de un producto (compatible con frontend AjusteDetalle)."""
    
    codigo_producto: str = Field(..., description="Código del producto")
    descripcion: str = Field(..., description="Descripción del producto")
    cantidad_solicitada: int = Field(..., ge=0, description="Cantidad solicitada original")
    cantidad_confirmada: int = Field(..., ge=0, description="Cantidad confirmada por el proveedor")
    cantidad_ajustada: int = Field(..., ge=0, description="Cantidad ajustada/redistribuida")
    distribucion_tiendas: List[DistribucionTiendaFrontend] = Field(..., min_items=1, description="Distribución por tienda")
    costo_original: Optional[float] = Field(None, ge=0, description="Costo unitario original")
    costo_ajustado: Optional[float] = Field(None, ge=0, description="Costo unitario ajustado")
    cambio_precio: bool = Field(default=False, description="Indica si hubo cambio de precio")
    pedido_detalle_id: Optional[str] = Field(None, description="ID del detalle del pedido (para resaltado de filas)")
    costo_modificado_manual: Optional[bool] = Field(default=False, description="Indica si el costo fue modificado manualmente")
    total_modificado_manual: Optional[bool] = Field(default=False, description="Indica si el total fue modificado manualmente")
    
    class Config:
        json_schema_extra = {
            "example": {
                "codigo_producto": "R225.1012.BCO",
                "descripcion": "Producto ejemplo",
                "cantidad_solicitada": 100,
                "cantidad_confirmada": 80,
                "cantidad_ajustada": 75,
                "distribucion_tiendas": [
                    {"tienda_codigo": "T001", "tienda_nombre": "Tienda 1", "cantidad": 50},
                    {"tienda_codigo": "T002", "tienda_nombre": "Tienda 2", "cantidad": 25}
                ],
                "costo_original": 25.50,
                "costo_ajustado": 25.50,
                "cambio_precio": False
            }
        }


class RedistribucionConfirmarRequest(BaseModel):
    """Modelo para confirmar redistribución (compatible con frontend)."""
    
    ajustes_detalle: List[AjusteDetalle] = Field(..., min_items=1, description="Lista de ajustes por producto")
    
    class Config:
        json_schema_extra = {
            "example": {
                "ajustes_detalle": [
                    {
                        "codigo_producto": "R225.1012.BCO",
                        "descripcion": "Producto ejemplo",
                        "cantidad_solicitada": 100,
                        "cantidad_confirmada": 80,
                        "cantidad_ajustada": 75,
                        "distribucion_tiendas": [
                            {"tienda_codigo": "T001", "tienda_nombre": "Tienda 1", "cantidad": 50},
                            {"tienda_codigo": "T002", "tienda_nombre": "Tienda 2", "cantidad": 25}
                        ],
                        "costo_original": 25.50,
                        "costo_ajustado": 25.50,
                        "cambio_precio": False
                    }
                ]
            }
        }


class ResumenConfirmacion(BaseModel):
    """Modelo para resumen de confirmación."""
    
    total_productos: int = Field(..., ge=0)
    total_cantidad_solicitada: int = Field(..., ge=0)
    total_cantidad_confirmada: int = Field(..., ge=0)
    total_cantidad_ajustada: int = Field(..., ge=0)
    total_costo_original: Optional[float] = None
    total_costo_ajustado: Optional[float] = None
    diferencia_cantidad: int = Field(..., description="cantidad_ajustada - cantidad_confirmada")
    diferencia_costo: Optional[float] = Field(None, description="costo_ajustado - costo_original")


# ============================================================================
# Modelos para Historial de Confirmaciones de EL RAYO
# ============================================================================

class ConfirmacionRayoDetalleItem(BaseModel):
    """Modelo para un detalle de confirmación de EL RAYO."""
    
    confirmacion_detalle_id: str = Field(..., description="UUID del detalle de confirmación")
    pedido_detalle_id: str = Field(..., description="UUID del detalle del pedido")
    codigo_producto: Optional[str] = Field(None, description="Código del producto")
    
    # Valores anteriores
    costo_anterior: Optional[float] = None
    total_anterior: Optional[float] = None
    comentario_anterior: Optional[str] = None
    
    # Valores nuevos (confirmados)
    costo_nuevo: Optional[float] = None
    total_nuevo: Optional[float] = None
    comentario_nuevo: Optional[str] = None
    
    # Flags de cambios
    cambio_costo: bool = False
    cambio_total: bool = False
    cambio_comentario: bool = False


class ConfirmacionRayoItem(BaseModel):
    """Modelo para una confirmación de EL RAYO."""
    
    confirmacion_id: str = Field(..., description="UUID de la confirmación")
    pedido_id: str = Field(..., description="UUID del pedido")
    respuesta_id: Optional[str] = Field(None, description="UUID de la respuesta del proveedor")
    confirmado_por: str = Field(..., description="User ID de EL RAYO")
    fecha_confirmacion: str = Field(..., description="Fecha y hora de confirmación (ISO8601)")
    total_detalles_modificados: int = Field(..., ge=0, description="Número total de detalles modificados")
    detalles_modificados: Optional[Dict[str, Any]] = Field(None, description="Resumen JSON de cambios")
    observaciones_generales: Optional[str] = None
    detalles: List[ConfirmacionRayoDetalleItem] = Field(default_factory=list, description="Detalles de cambios")


class ConfirmacionRayoListResponse(BaseModel):
    """Modelo para la respuesta de obtener historial de confirmaciones."""
    
    pedido_id: str = Field(..., description="UUID del pedido")
    numero_pedido: Optional[str] = Field(None, description="Número del pedido")
    total_confirmaciones: int = Field(..., ge=0, description="Total de confirmaciones")
    confirmaciones: List[ConfirmacionRayoItem] = Field(default_factory=list, description="Lista de confirmaciones")


class ConfirmacionRayoDetailResponse(BaseModel):
    """Modelo para la respuesta de obtener detalle de una confirmación específica."""
    
    confirmacion: ConfirmacionRayoItem = Field(..., description="Detalle completo de la confirmación")


class ConfirmarRedistribucionResponseFrontend(BaseModel):
    """Modelo para respuesta de confirmar redistribución (compatible con frontend)."""
    
    status: str = Field(default="success")
    message: str = Field(..., description="Mensaje de confirmación")
    pedido_id: str = Field(..., description="UUID del pedido")
    numero_pedido: str = Field(..., description="Número del pedido")
    redistribucion_id: Optional[str] = Field(None, description="ID de la redistribución (si aplica)")
    fecha_confirmacion: datetime = Field(default_factory=datetime.now)
    resumen: ResumenConfirmacion
    ajustes_aplicados: int = Field(..., ge=0, description="Cantidad de productos ajustados")


class GuardarBorradorRequest(BaseModel):
    """Modelo para guardar borrador de redistribución."""
    
    ajustes_detalle: List[AjusteDetalle] = Field(..., min_items=1, description="Lista de ajustes por producto")
    
    class Config:
        json_schema_extra = {
            "example": {
                "ajustes_detalle": [
                    {
                        "codigo_producto": "R225.1012.BCO",
                        "descripcion": "Producto ejemplo",
                        "cantidad_solicitada": 100,
                        "cantidad_confirmada": 80,
                        "cantidad_ajustada": 75,
                        "distribucion_tiendas": [
                            {"tienda_codigo": "T001", "tienda_nombre": "Tienda 1", "cantidad": 50}
                        ],
                        "costo_original": 25.50,
                        "costo_ajustado": 25.50,
                        "cambio_precio": False
                    }
                ]
            }
        }


class GuardarBorradorResponse(BaseModel):
    """Modelo para respuesta de guardar borrador."""
    
    status: str = Field(default="success")
    message: str = Field(..., description="Mensaje de confirmación")
    pedido_id: str = Field(..., description="UUID del pedido")
    numero_pedido: str = Field(..., description="Número del pedido")
    fecha_guardado: datetime = Field(default_factory=datetime.now)


class BorradorResponse(BaseModel):
    """Modelo para obtener borrador guardado."""
    
    status: str = Field(default="success")
    ajustes_detalle: List[AjusteDetalle] = Field(..., description="Lista de ajustes guardados")
    fecha_guardado: datetime = Field(..., description="Fecha en que se guardó el borrador")


class ProductoSAPProcesamientoItem(BaseModel):
    """Modelo para un producto procesado con SAP."""
    
    procesamiento_detalle_id: str = Field(..., description="UUID del procesamiento")
    pedido_detalle_id: str = Field(..., description="UUID del detalle del pedido")
    codigo_interno: str = Field(..., description="Código interno del producto")
    descripcion_producto: Optional[str] = Field(None, description="Descripción del producto")
    item_code_sap: Optional[str] = Field(None, description="ItemCode de SAP")
    pack_sap: Optional[str] = Field(None, description="Pack SAP (X1, X2, X3, etc.)")
    unidad_conversion: Optional[float] = Field(None, description="Factor de conversión")
    unidad_sap: Optional[str] = Field(None, description="Unidad SAP")
    cantidad_original: Optional[float] = Field(None, description="Cantidad en unidades originales")
    cantidad_sap: Optional[float] = Field(None, description="Cantidad convertida a unidades SAP")
    precio_unitario_original: Optional[float] = Field(None, description="Precio por unidad original")
    precio_unitario_sap: Optional[float] = Field(None, description="Precio por unidad SAP")
    total_linea_original: Optional[float] = Field(None, description="Total en unidades originales")
    total_linea_sap: Optional[float] = Field(None, description="Total en unidades SAP")
    producto_homologado: bool = Field(default=True, description="Si el producto está homologado")
    tipo_problema: Optional[str] = Field(None, description="Tipo de problema: 'no_existe', 'mismatch', 'error'")
    item_code_sap_encontrado: Optional[str] = Field(None, description="ItemCode encontrado en SAP (para mismatch)")
    mensaje_error: Optional[str] = Field(None, description="Mensaje de error si hubo problema")
    fecha_procesamiento: Optional[datetime] = Field(None, description="Fecha de procesamiento")
    procesado_por: Optional[str] = Field(None, description="Usuario que procesó")


class EstadisticasProcesamientoSAP(BaseModel):
    """Estadísticas del procesamiento SAP."""
    
    total_productos: int = Field(..., ge=0, description="Total de productos procesados")
    productos_homologados: int = Field(..., ge=0, description="Productos homologados correctamente")
    productos_no_homologados: int = Field(..., ge=0, description="Productos no homologados")
    productos_con_error: int = Field(..., ge=0, description="Productos con error de procesamiento")
    total_cantidad_original: Optional[float] = Field(None, description="Suma total de cantidades originales")
    total_cantidad_sap: Optional[float] = Field(None, description="Suma total de cantidades SAP")
    total_precio_original: Optional[float] = Field(None, description="Suma total de precios originales")
    total_precio_sap: Optional[float] = Field(None, description="Suma total de precios SAP")


class ProcesamientoSAPResponse(BaseModel):
    """Modelo para respuesta de procesamiento SAP de un pedido."""
    
    status: str = Field(default="success")
    pedido_id: str = Field(..., description="UUID del pedido")
    numero_pedido: Optional[str] = Field(None, description="Número del pedido")
    productos: List[ProductoSAPProcesamientoItem] = Field(default_factory=list, description="Lista de productos procesados")
    estadisticas: EstadisticasProcesamientoSAP = Field(..., description="Estadísticas del procesamiento")
    fecha_procesamiento: Optional[datetime] = Field(None, description="Fecha del último procesamiento")


# ============================================================================
# MODELOS PARA CREAR PEDIDO MANUAL (HU-01)
# ============================================================================

class DistribucionTiendaRequest(BaseModel):
    """Modelo para distribución de un producto por tienda."""
    
    tienda_codigo: str = Field(..., description="Código de la tienda (ej: 'TRL-QSN', 'T001')")
    tienda_nombre: Optional[str] = Field(None, description="Nombre de la tienda (opcional, se crea si no existe)")
    cantidad: int = Field(..., ge=1, description="Cantidad a distribuir (debe ser >= 1)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tienda_codigo": "TRL-QSN",
                "tienda_nombre": "ROLAND QUITO SUR",
                "cantidad": 10
            }
        }


class ArticuloRequest(BaseModel):
    """Modelo para un artículo del pedido."""
    
    codigo_interno: str = Field(..., description="Código del producto (SKU)")
    descripcion_sap: Optional[str] = Field(None, description="Descripción del producto")
    marca: Optional[str] = Field(None, description="Marca del producto")
    codigo_barras: Optional[str] = Field(None, description="Código de barras")
    pack: Optional[str] = Field(None, description="Tipo de empaque/pack")
    costo_doc_sin_iva: Optional[float] = Field(None, ge=0, description="Costo sin IVA")
    descuento_1: Optional[float] = Field(None, ge=0, le=100, description="Descuento porcentual")
    pvp: Optional[float] = Field(None, ge=0, description="Precio de venta público")
    subtotal: Optional[float] = Field(None, ge=0, description="Subtotal del artículo")
    total: Optional[float] = Field(None, ge=0, description="Total del artículo")
    bodega: Optional[int] = Field(None, description="Código de bodega/almacén")
    comentario: Optional[str] = Field(None, description="Comentario o nota adicional del artículo")
    cantidad_total: Optional[int] = Field(None, ge=0, description="Cantidad total del artículo (solo para validación, no se guarda en BD)")
    distribuciones: List[DistribucionTiendaRequest] = Field(..., min_length=1, description="Lista de distribuciones por tienda")
    
    class Config:
        json_schema_extra = {
            "example": {
                "codigo_interno": "R225.1012.BCO",
                "descripcion_sap": "MEDIA TOBILLERA",
                "marca": "ROLAND",
                "costo_doc_sin_iva": 5.65,
                "descuento_1": 0.2,
                "pvp": 9.99,
                "distribuciones": [
                    {
                        "tienda_codigo": "TRL-QSN",
                        "tienda_nombre": "ROLAND QUITO SUR",
                        "cantidad": 10
                    },
                    {
                        "tienda_codigo": "TRL-SMA",
                        "cantidad": 5
                    }
                ]
            }
        }


class CrearPedidoRequest(BaseModel):
    """Modelo para crear un pedido manualmente desde la pantalla web."""
    
    # Campos de cabecera
    numero_pedido: str = Field(..., description="Número único del pedido")
    fecha_pedido: Optional[str] = Field(None, description="Fecha del pedido (YYYY-MM-DD)")
    fecha_entrega: Optional[str] = Field(None, description="Fecha de entrega (YYYY-MM-DD o 'INMEDIATO')")
    forma_pago: Optional[str] = Field(None, description="Forma de pago")
    odc: Optional[str] = Field(None, description="Orden de compra interna")
    proveedor_nombre: Optional[str] = Field(None, description="Nombre del proveedor")
    comprador_nombre: Optional[str] = Field(None, description="Nombre del comprador")
    comprador_codigo: Optional[str] = Field(None, description="Código del comprador")
    origen_traslado: Optional[str] = Field(None, description="Origen de traslado (bodega)")
    serie: Optional[str] = Field(None, description="Serie del documento")
    
    # Artículos
    articulos: List[ArticuloRequest] = Field(..., min_length=1, description="Lista de artículos del pedido")
    
    # Opciones de validación
    validar_productos: bool = Field(True, description="Validar que productos existan en catálogo")
    validar_tiendas: bool = Field(True, description="Validar que tiendas existan y estén activas")
    
    class Config:
        json_schema_extra = {
            "example": {
                "numero_pedido": "P-12.48 - 12 - 2025",
                "fecha_pedido": "2025-01-21",
                "fecha_entrega": "INMEDIATO",
                "forma_pago": "120 DIAS",
                "proveedor_nombre": "TEXTILES EL RAYO S.A.",
                "comprador_nombre": "VACA ANDREA",
                "comprador_codigo": "801",
                "origen_traslado": "RL-CD",
                "articulos": [
                    {
                        "codigo_interno": "R225.1012.BCO",
                        "descripcion_sap": "MEDIA TOBILLERA",
                        "marca": "ROLAND",
                        "costo_doc_sin_iva": 5.65,
                        "pvp": 9.99,
                        "distribuciones": [
                            {"tienda_codigo": "TRL-QSN", "cantidad": 10},
                            {"tienda_codigo": "TRL-SMA", "cantidad": 5}
                        ]
                    }
                ]
            }
        }


class CrearPedidoResponse(BaseModel):
    """Modelo para respuesta de creación de pedido manual."""
    
    status: str = Field(..., description="Estado del procesamiento: 'success', 'validation_error', 'error'")
    pedido_id: Optional[str] = Field(None, description="UUID del pedido creado")
    estado: Optional[str] = Field(None, description="Estado del pedido")
    validacion: Dict[str, Any] = Field(default_factory=dict, description="Resultados de validación")
    consolidacion: Dict[str, Any] = Field(default_factory=dict, description="Resumen de consolidación")
    articulos_cargados: int = Field(0, ge=0, description="Número de artículos cargados")
    distribuciones_cargadas: int = Field(0, ge=0, description="Número de distribuciones cargadas")
    errores: List[str] = Field(default_factory=list, description="Lista de errores encontrados")


# ============================================================================
# MODELOS PARA MODIFICAR PEDIDO (HU-03)
# ============================================================================

class ModificarPedidoCabeceraRequest(BaseModel):
    """Modelo para modificar la cabecera de un pedido."""
    
    fecha_pedido: Optional[str] = Field(None, description="Fecha del pedido (YYYY-MM-DD)")
    fecha_entrega: Optional[str] = Field(None, description="Fecha de entrega (YYYY-MM-DD o 'INMEDIATO')")
    forma_pago: Optional[str] = Field(None, description="Forma de pago")
    odc: Optional[str] = Field(None, description="Orden de compra interna")
    proveedor_nombre: Optional[str] = Field(None, description="Nombre del proveedor")
    comprador_nombre: Optional[str] = Field(None, description="Nombre del comprador")
    comprador_codigo: Optional[str] = Field(None, description="Código del comprador")
    origen_traslado: Optional[str] = Field(None, description="Origen de traslado (bodega)")
    serie: Optional[str] = Field(None, description="Serie del documento")
    estado: Optional[str] = Field(None, description="Estado del pedido")
    
    class Config:
        json_schema_extra = {
            "example": {
                "fecha_pedido": "2025-01-22",
                "fecha_entrega": "INMEDIATO",
                "forma_pago": "120 DIAS",
                "proveedor_nombre": "TEXTILES EL RAYO S.A.",
                "comprador_nombre": "VACA ANDREA",
                "comprador_codigo": "801",
                "origen_traslado": "RL-CD",
                "serie": "A"
            }
        }


class ModificarPedidoCabeceraResponse(BaseModel):
    """Modelo para respuesta de modificación de cabecera de pedido."""
    
    status: str = Field(default="success", description="Estado de la operación")
    message: str = Field(..., description="Mensaje descriptivo")
    pedido_id: str = Field(..., description="UUID del pedido modificado")
    campos_modificados: List[str] = Field(default_factory=list, description="Lista de campos que fueron modificados")

