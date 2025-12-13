"""
Modelos Pydantic para la API de consultas MBA3.

Define los esquemas de request y response para los endpoints.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


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


class SaveSidebarPreferencesRequest(BaseModel):
    """Modelo para el request de guardar preferencias del sidebar."""
    
    preferences: SidebarPreferencesDto


class SidebarPreferencesResponse(BaseModel):
    """Modelo de respuesta para obtener preferencias del sidebar."""
    
    preferences: Optional[SidebarPreferencesDto] = None

