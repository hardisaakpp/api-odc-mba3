import axios from 'axios'
import type { FacturaFilters, FacturasResponse } from '@/types/factura'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json'
  }
})

export const facturasApi = {
  /**
   * Obtiene facturas desde el backend con filtros opcionales
   */
  async getFacturas(filters: FacturaFilters = {}): Promise<FacturasResponse> {
    const params = new URLSearchParams()
    
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        params.append(key, String(value))
      }
    })
    
    const response = await apiClient.get<FacturasResponse>(`/facturas?${params.toString()}`)
    return response.data
  },

  /**
   * Ejecuta una consulta SQL dinámica contra MBA3
   */
  async executeQuery(query: string): Promise<Factura[]> {
    const params = new URLSearchParams()
    params.append('query', query)
    
    const response = await apiClient.get<Factura[]>(`/consulta?${params.toString()}`)
    return response.data
  }
}

export default apiClient

