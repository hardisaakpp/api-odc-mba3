export interface OrdenCompra {
  oc_id: string
  despacho_id: string
  proveedor: string
  fecha_generacion: string
  estado: 'PENDIENTE' | 'ENVIADA' | 'ERROR'
  numero_oc_sap: string | null
  referencia_despacho: string
  created_at: string
}

export interface OrdenCompraResponse {
  status: string
  data: OrdenCompra[]
  metadata: {
    count: number
    estado_filter?: string
  }
}

export interface OrdenCompraDetalle {
  oc_id: string
  proveedor: string
  detalles: any[]
}

