import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'
import type { Factura, FacturaFilters } from '@/types/factura'

export const useFacturasStore = defineStore('facturas', () => {
  const facturas = ref<Factura[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const filters = ref<FacturaFilters>({
    anulada: false,
    confirmado: true,
    remision_facturada: false,
    include_obj_datos: true,
    save_to_db: true,
  })
  const metadata = ref<any>(null)

  const count = computed(() => facturas.value.length)

  async function fetchFacturas(customFilters?: FacturaFilters) {
    loading.value = true
    error.value = null
    try {
      const response = await api.getFacturas(customFilters || filters.value)
      facturas.value = response.data
      metadata.value = response.metadata
    } catch (err: any) {
      error.value = err.message || 'Error al obtener facturas'
      console.error('Error fetching facturas:', err)
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
      save_to_db: true,
    }
  }

  return {
    facturas,
    loading,
    error,
    filters,
    metadata,
    count,
    fetchFacturas,
    updateFilters,
    resetFilters,
  }
})

