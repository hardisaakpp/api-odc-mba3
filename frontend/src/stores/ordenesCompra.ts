import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'
import type { OrdenCompra } from '@/types/ordenCompra'

export const useOrdenesCompraStore = defineStore('ordenesCompra', () => {
  const ordenesCompra = ref<OrdenCompra[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const estadoFilter = ref<string | undefined>(undefined)
  const metadata = ref<any>(null)

  const count = computed(() => ordenesCompra.value.length)
  
  const pendientes = computed(() => 
    ordenesCompra.value.filter(oc => oc.estado === 'PENDIENTE').length
  )
  
  const enviadas = computed(() => 
    ordenesCompra.value.filter(oc => oc.estado === 'ENVIADA').length
  )
  
  const errores = computed(() => 
    ordenesCompra.value.filter(oc => oc.estado === 'ERROR').length
  )

  async function fetchOrdenesCompra(estado?: string) {
    loading.value = true
    error.value = null
    estadoFilter.value = estado
    try {
      const response = await api.getOrdenesCompra(estado)
      ordenesCompra.value = response.data
      metadata.value = response.metadata
    } catch (err: any) {
      error.value = err.message || 'Error al obtener órdenes de compra'
      console.error('Error fetching ordenes compra:', err)
    } finally {
      loading.value = false
    }
  }

  async function integrarSAP(referenciaDespacho?: string) {
    loading.value = true
    error.value = null
    try {
      const response = await api.integrarSAP(referenciaDespacho)
      // Refrescar la lista después de integrar
      await fetchOrdenesCompra(estadoFilter.value)
      return response
    } catch (err: any) {
      error.value = err.message || 'Error al integrar con SAP'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    ordenesCompra,
    loading,
    error,
    estadoFilter,
    metadata,
    count,
    pendientes,
    enviadas,
    errores,
    fetchOrdenesCompra,
    integrarSAP,
  }
})

