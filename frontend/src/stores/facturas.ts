import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { facturasApi } from '@/services/api'
import type { Factura, FacturaFilters, FacturasResponse } from '@/types/factura'

export const useFacturasStore = defineStore('facturas', () => {
  // State
  const facturas = ref<Factura[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const filters = ref<FacturaFilters>({
    anulada: false,
    confirmado: true,
    remision_facturada: false,
    include_obj_datos: true,
    save_to_db: true
  })
  const metadata = ref<FacturasResponse['metadata'] | null>(null)

  // Getters
  const totalFacturas = computed(() => facturas.value.length)
  
  const hasFacturas = computed(() => facturas.value.length > 0)
  
  const facturasPorEmpresa = computed(() => {
    const grupos: Record<string, number> = {}
    facturas.value.forEach(factura => {
      const empresa = factura.EMPRESA || 'Sin empresa'
      grupos[empresa] = (grupos[empresa] || 0) + 1
    })
    return grupos
  })

  // Actions
  async function fetchFacturas(customFilters?: FacturaFilters) {
    loading.value = true
    error.value = null
    
    try {
      const filtersToUse = customFilters || filters.value
      
      const response = await facturasApi.getFacturas(filtersToUse)
      
      // Log solo si hay datos para evitar spam en consola
      if (Array.isArray(response.data) && response.data.length > 0) {
        console.log('🔵 Primera factura recibida - Campos:', Object.keys(response.data[0]))
        if (Object.keys(response.data[0]).length === 1) {
          console.warn('⚠️ SOLO HAY 1 CAMPO EN LA FACTURA:', response.data[0])
        }
      }
      
      facturas.value = response.data
      metadata.value = response.metadata
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || 'Error al cargar pre-facturas'
      console.error('❌ Error fetching facturas:', err)
    } finally {
      loading.value = false
    }
  }

  function updateFilters(newFilters: Partial<FacturaFilters>) {
    filters.value = { ...filters.value, ...newFilters }
  }

  function resetFilters() {
    filters.value = {
      anulada: false,
      confirmado: true,
      remision_facturada: false,
      include_obj_datos: true,
      save_to_db: true
    }
  }

  return {
    // State
    facturas,
    loading,
    error,
    filters,
    metadata,
    // Getters
    totalFacturas,
    hasFacturas,
    facturasPorEmpresa,
    // Actions
    fetchFacturas,
    updateFilters,
    resetFilters
  }
})

