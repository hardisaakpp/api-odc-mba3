import axios from 'axios'
import type { Factura, FacturaFilters, FacturasResponse } from '@/types/factura'

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
    
    const url = `/facturas?${params.toString()}`
    const response = await apiClient.get<FacturasResponse>(url)
    
    // Log detallado de la primera factura para debugging
    if (response.data?.data && Array.isArray(response.data.data) && response.data.data.length > 0) {
      const firstFactura = response.data.data[0]
      const campos = Object.keys(firstFactura)
      console.log('🌐 GET /facturas - Total facturas:', response.data.data.length)
      console.log('🌐 GET /facturas - Campos recibidos:', campos.length, 'campos')
      console.log('🌐 GET /facturas - Lista de campos:', campos)
      console.log('🌐 GET /facturas - Primera factura completa:', firstFactura)
      console.log('🌐 GET /facturas - JSON completo:', JSON.stringify(firstFactura, null, 2))
      
      if (campos.length === 1) {
        console.error('❌ PROBLEMA CRÍTICO: Solo se recibió 1 campo desde el backend')
        console.error('❌ Campo recibido:', campos[0])
        console.error('❌ Esto significa que el backend solo está devolviendo CODIGO_FACTURA')
      } else {
        console.log('✅ Se recibieron múltiples campos desde el backend')
      }
    }
    
    return response.data
  },

}

export default apiClient

