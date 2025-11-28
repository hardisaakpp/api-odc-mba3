<template>
  <div class="ordenes-compra-view">
    <div class="view-header">
      <h1 class="page-title">Órdenes de Compra</h1>
      <div class="header-actions">
        <select 
          v-model="estadoFilter" 
          @change="handleFilterChange"
          class="filter-select"
        >
          <option value="">Todos los estados</option>
          <option value="PENDIENTE">Pendientes</option>
          <option value="ENVIADA">Enviadas</option>
          <option value="ERROR">Con Error</option>
        </select>
        <button 
          @click="refreshOrdenes" 
          class="btn btn-primary"
          :disabled="ordenesCompraStore.loading"
        >
          {{ ordenesCompraStore.loading ? 'Cargando...' : 'Actualizar' }}
        </button>
      </div>
    </div>

    <div v-if="ordenesCompraStore.error" class="error-alert">
      <strong>Error:</strong> {{ ordenesCompraStore.error }}
    </div>

    <LoadingSpinner v-if="ordenesCompraStore.loading" message="Cargando órdenes de compra..." />

    <OrdenCompraTable 
      v-else
      :ordenes-compra="ordenesCompraStore.ordenesCompra"
      :loading="ordenesCompraStore.loading"
      @integrar="handleIntegrar"
    />

    <div v-if="integrationResult" class="result-alert" :class="integrationResult.status === 'success' ? 'success' : 'error'">
      <strong>{{ integrationResult.status === 'success' ? '✓ Éxito' : '✗ Error' }}:</strong>
      {{ integrationResult.message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useOrdenesCompraStore } from '@/stores/ordenesCompra'
import OrdenCompraTable from '@/components/OrdenCompraTable.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'

const ordenesCompraStore = useOrdenesCompraStore()
const estadoFilter = ref<string>('')
const integrationResult = ref<{ status: string; message: string } | null>(null)

onMounted(() => {
  ordenesCompraStore.fetchOrdenesCompra()
})

function handleFilterChange() {
  ordenesCompraStore.fetchOrdenesCompra(estadoFilter.value || undefined)
}

function refreshOrdenes() {
  ordenesCompraStore.fetchOrdenesCompra(estadoFilter.value || undefined)
}

async function handleIntegrar(referenciaDespacho: string) {
  integrationResult.value = null
  try {
    const result = await ordenesCompraStore.integrarSAP(referenciaDespacho)
    integrationResult.value = {
      status: 'success',
      message: result.message || 'Orden de compra enviada exitosamente a SAP'
    }
    setTimeout(() => {
      integrationResult.value = null
    }, 5000)
  } catch (error: any) {
    integrationResult.value = {
      status: 'error',
      message: error.message || 'Error al enviar orden de compra a SAP'
    }
    setTimeout(() => {
      integrationResult.value = null
    }, 5000)
  }
}
</script>

<style scoped>
.ordenes-compra-view {
  padding: 2rem 0;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.page-title {
  font-size: 2rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.filter-select {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 0.9rem;
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
  transition: background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease;
}

.btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #3498db;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #2980b9;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-alert {
  background: #fee;
  color: #c33;
  padding: 1rem;
  border-radius: 6px;
  margin-bottom: 1.5rem;
  border-left: 4px solid #e74c3c;
}

.result-alert {
  padding: 1rem;
  border-radius: 6px;
  margin-top: 1.5rem;
  border-left: 4px solid;
}

.result-alert.success {
  background: #d4edda;
  color: #155724;
  border-color: #27ae60;
}

.result-alert.error {
  background: #fee;
  color: #c33;
  border-color: #e74c3c;
}
</style>
