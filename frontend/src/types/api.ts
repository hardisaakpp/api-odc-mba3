export interface ApiResponse<T> {
  status: string
  data?: T
  message?: string
  metadata?: Record<string, any>
}

export interface HealthResponse {
  status: string
  time: string
}

export interface ProcesoResponse {
  status: string
  data?: any
  metadata?: {
    query?: string
    save_status?: {
      status: string
      facturas_guardadas: number
      facturas_actualizadas: number
      total_detalles: number
    }
    oc_status?: {
      status: string
      oc_creadas: number
      oc_errores: number
      total_procesadas: number
      detalles: any[]
    }
  }
}

