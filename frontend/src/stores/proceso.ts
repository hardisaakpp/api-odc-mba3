import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export const useProcesoStore = defineStore('proceso', () => {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const currentStep = ref<string | null>(null)
  const resultados = ref<any>(null)
  const progress = ref(0)

  async function consultar() {
    loading.value = true
    error.value = null
    currentStep.value = 'consultar'
    progress.value = 25
    try {
      const data = await api.consultar()
      resultados.value = { consultar: data }
      return data
    } catch (err: any) {
      error.value = err.message || 'Error al consultar'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function migrar() {
    loading.value = true
    error.value = null
    currentStep.value = 'migrar'
    progress.value = 50
    try {
      const data = await api.migrar()
      resultados.value = { ...resultados.value, migrar: data }
      return data
    } catch (err: any) {
      error.value = err.message || 'Error al migrar'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function procesarOC() {
    loading.value = true
    error.value = null
    currentStep.value = 'procesar-oc'
    progress.value = 75
    try {
      const data = await api.procesarOC()
      resultados.value = { ...resultados.value, procesarOC: data }
      return data
    } catch (err: any) {
      error.value = err.message || 'Error al procesar OC'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function integrarSAP(referenciaDespacho?: string) {
    loading.value = true
    error.value = null
    currentStep.value = 'integrar-sap'
    progress.value = 100
    try {
      const data = await api.integrarSAP(referenciaDespacho)
      resultados.value = { ...resultados.value, integrarSAP: data }
      return data
    } catch (err: any) {
      error.value = err.message || 'Error al integrar con SAP'
      throw err
    } finally {
      loading.value = false
      currentStep.value = null
    }
  }

  async function procesoCompleto() {
    loading.value = true
    error.value = null
    progress.value = 0
    try {
      const data = await api.pruebas()
      resultados.value = data
      progress.value = 100
      return data
    } catch (err: any) {
      error.value = err.message || 'Error en proceso completo'
      throw err
    } finally {
      loading.value = false
      currentStep.value = null
    }
  }

  function reset() {
    resultados.value = null
    error.value = null
    currentStep.value = null
    progress.value = 0
  }

  return {
    loading,
    error,
    currentStep,
    resultados,
    progress,
    consultar,
    migrar,
    procesarOC,
    integrarSAP,
    procesoCompleto,
    reset,
  }
})

