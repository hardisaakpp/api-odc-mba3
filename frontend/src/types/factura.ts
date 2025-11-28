export interface LineaFactura {
  Codigo?: string
  Nombre?: string
  Cantidad?: number
  PrecioUnitario?: number
  TotalLinea?: number
  Descuento?: number
  Impuesto?: number
  RegNum?: number
}

export interface ObjDatosFactura {
  Lineas?: LineaFactura[]
  CtrlEliminados1?: LineaFactura[]
  CtrlEliminados2?: LineaFactura[]
  CtrlEliminados3?: LineaFactura[]
  CtrlEliminados4?: LineaFactura[]
  CtrlEliminados5?: LineaFactura[]
  CtrlEliminados6?: LineaFactura[]
  CtrlEliminados7?: LineaFactura[]
  CtrlEliminados8?: LineaFactura[]
  CtrlEliminadosA?: LineaFactura[]
  CtrlEliminadosB?: LineaFactura[]
  GrabarLineasProd?: LineaFactura[]
}

export interface Factura {
  CODIGO_FACTURA?: string
  NUMERO_FACTURA?: number
  EMPRESA?: string
  CODIGO_CLIENTE?: string
  FECHA_FACTURA?: string
  NUMERO_ORDEN?: number
  ANULADA?: boolean
  CODIGO_DESPACHO?: number
  TIPO_DOCUMENTO?: string
  NUMERO_PEDIDO_SISTEMA?: number
  ORDEN_COMPRA?: string
  ORDEN_COMPRA_CLIENTE?: string
  Remision_Facturada?: boolean
  NumIDFacturaRelacionada?: number
  CONFIRMADO?: boolean
  CODIGO_BODEGA?: string
  ObjDatosFactura?: ObjDatosFactura
}

export interface FacturaFilters {
  anulada?: boolean
  confirmado?: boolean
  remision_facturada?: boolean
  include_obj_datos?: boolean
  save_to_db?: boolean
}

export interface FacturasResponse {
  status: string
  data: Factura[]
  metadata: {
    count: number
    filters: FacturaFilters
    save_status?: {
      status: string
      facturas_guardadas?: number
      facturas_actualizadas?: number
      total_detalles?: number
    }
  }
}









