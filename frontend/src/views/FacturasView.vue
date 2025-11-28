<template>
  <div class="facturas-view">
    <div class="view-header">
      <h1 class="page-title">Facturas</h1>
      <button 
        @click="refreshFacturas" 
        class="btn btn-primary"
        :disabled="facturasStore.loading"
      >
        {{ facturasStore.loading ? 'Cargando...' : 'Actualizar' }}
      </button>
    </div>
    
    <FacturaFilters 
      :filters="facturasStore.filters"
      @update-filters="handleUpdateFilters"
      @reset="handleResetFilters"
    />

    <div v-if="facturasStore.error" class="error-alert">
      <strong>Error:</strong> {{ facturasStore.error }}
    </div>

    <LoadingSpinner v-if="facturasStore.loading" message="Cargando facturas..." />

    <FacturaTable 
      v-else
      :facturas="facturasStore.facturas"
      :metadata="facturasStore.metadata"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useFacturasStore } from '@/stores/facturas'
import FacturaFilters from '@/components/FacturaFilters.vue'
import FacturaTable from '@/components/FacturaTable.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import type { FacturaFilters as IFacturaFilters } from '@/types/factura'

const facturasStore = useFacturasStore()

onMounted(() => {
  facturasStore.fetchFacturas()
})

function handleUpdateFilters(filters: Partial<IFacturaFilters>) {
  facturasStore.updateFilters(filters)
  facturasStore.fetchFacturas()
}

function handleResetFilters() {
  facturasStore.resetFilters()
  facturasStore.fetchFacturas()
}

function refreshFacturas() {
  facturasStore.fetchFacturas()
}
</script>

<style scoped>
.facturas-view {
  padding: 2rem 0;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.page-title {
  font-size: 2rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
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
</style>
