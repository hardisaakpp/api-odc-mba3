import axios, { type AxiosInstance } from 'axios'
import type { 
  FacturaResponse, 
  FacturaFilters 
} from '@/types/factura'
import type { OrdenCompraResponse } from '@/types/ordenCompra'
import type { HealthResponse, ProcesoResponse } from '@/types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

class ApiService {
  private api: AxiosInstance

  constructor() {
    this.api = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 30000,
    })

    // Interceptor para errores
    this.api.interceptors.response.use(
      (response) => response,
      (error) => {
        console.error('API Error:', error)
        const message = error.response?.data?.message || error.message || 'Error desconocido'
        return Promise.reject(new Error(message))
      }
    )
  }

  // Health check
  async healthCheck(): Promise<HealthResponse> {
    const response = await this.api.get<HealthResponse>('/health')
    return response.data
  }

  // Facturas
  async getFacturas(filters?: FacturaFilters): Promise<FacturaResponse> {
    const params = new URLSearchParams()
    if (filters?.anulada !== undefined && filters.anulada !== null) {
      params.append('anulada', String(filters.anulada))
    }
    if (filters?.confirmado !== undefined && filters.confirmado !== null) {
      params.append('confirmado', String(filters.confirmado))
    }
    if (filters?.remision_facturada !== undefined && filters.remision_facturada !== null) {
      params.append('remision_facturada', String(filters.remision_facturada))
    }
    if (filters?.include_obj_datos !== undefined) {
      params.append('include_obj_datos', String(filters.include_obj_datos))
    }
    if (filters?.save_to_db !== undefined) {
      params.append('save_to_db', String(filters.save_to_db))
    }

    const queryString = params.toString()
    const url = queryString ? `/facturas?${queryString}` : '/facturas'
    const response = await this.api.get<FacturaResponse>(url)
    return response.data
  }

  // Consultar (solo lectura)
  async consultar(): Promise<any> {
    const response = await this.api.get('/consultar')
    return response.data
  }

  // Migrar
  async migrar(): Promise<ProcesoResponse> {
    const response = await this.api.get<ProcesoResponse>('/migrar')
    return response.data
  }

  // Procesar OC
  async procesarOC(): Promise<any> {
    const response = await this.api.get('/procesar-oc')
    return response.data
  }

  // Integrar SAP
  async integrarSAP(referenciaDespacho?: string): Promise<any> {
    const params = referenciaDespacho 
      ? `?referencia_despacho=${referenciaDespacho}`
      : ''
    const response = await this.api.post(`/integrar-sap${params}`)
    return response.data
  }

  // Órdenes de compra
  async getOrdenesCompra(estado?: string): Promise<OrdenCompraResponse> {
    const params = estado ? `?estado=${estado}` : ''
    const response = await this.api.get<OrdenCompraResponse>(`/ordenes-compra${params}`)
    return response.data
  }

  // Pruebas (endpoint completo)
  async pruebas(): Promise<ProcesoResponse> {
    const response = await this.api.get<ProcesoResponse>('/pruebas')
    return response.data
  }
}

export default new ApiService()
