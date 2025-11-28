export interface Factura {
  CODIGO_FACTURA: string
  ANULADA: string
  NUMERO_PEDIDO_SISTEMA: string
  NUMERO_ORDEN: string
  NUMERO_FACTURA: string
  CODIGO_DESPACHO: string
  EMPRESA: string
  CODIGO_CLIENTE: string
  FECHA_FACTURA: string
  TIPO_DOCUMENTO: string
  ObjDatosFactura: string | null
  ORDEN_COMPRA: string | null
  ORDEN_COMPRA_CLIENTE: string | null
  Remision_Facturada: string
  NumIDFacturaRelacionada: string | null
  CONFIRMADO: string
  CODIGO_BODEGA: string
}

export interface FacturaFilters {
  anulada?: boolean | null
  confirmado?: boolean | null
  remision_facturada?: boolean | null
  include_obj_datos?: boolean
  save_to_db?: boolean
}

export interface FacturaResponse {
  status: string
  data: Factura[]
  metadata: {
    count: number
    filters: FacturaFilters
    save_status?: {
      status: string
      facturas_guardadas: number
      facturas_actualizadas: number
      total_detalles: number
    }
  }
}
