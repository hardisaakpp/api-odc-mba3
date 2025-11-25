<template>
  <div class="facturas-view">
    <h1>Consulta de Pre-Facturas</h1>
    
    <FacturaFilters @filter="handleFilter" />
    
    <div v-if="store.loading" class="loading">
      <p>Cargando pre-facturas...</p>
    </div>
    
    <div v-else-if="store.error" class="error">
      <p>Error: {{ store.error }}</p>
      <button @click="handleFilter(store.filters)" class="btn-retry">Reintentar</button>
    </div>
    
    <div v-else>
      <div class="stats">
        <div class="stat-card">
          <h3>Total Pre-Facturas</h3>
          <p class="stat-number">{{ store.totalFacturas }}</p>
        </div>
        <div v-if="store.metadata?.save_status" class="stat-card">
          <h3>Guardadas en DB</h3>
          <p class="stat-number">{{ store.metadata.save_status.facturas_guardadas || 0 }}</p>
        </div>
      </div>
      
      <FacturaTable :facturas="paginatedFacturas" />
      
      <Pagination
        :current-page="currentPage"
        :total-items="store.totalFacturas"
        :items-per-page="itemsPerPage"
        @page-change="handlePageChange"
        @items-per-page-change="handleItemsPerPageChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useFacturasStore } from '@/stores/facturas'
import FacturaFilters from '@/components/FacturaFilters.vue'
import FacturaTable from '@/components/FacturaTable.vue'
import Pagination from '@/components/Pagination.vue'
import type { FacturaFilters as IFilters } from '@/types/factura'

const store = useFacturasStore()

// Estado de paginación
const currentPage = ref(1)
const itemsPerPage = ref(10)

// Facturas paginadas
const paginatedFacturas = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value
  const end = start + itemsPerPage.value
  return store.facturas.slice(start, end)
})

function handleFilter(filters: IFilters) {
  store.updateFilters(filters)
  currentPage.value = 1 // Resetear a primera página al filtrar
  store.fetchFacturas()
}

function handlePageChange(page: number) {
  currentPage.value = page
  // Scroll al inicio de la tabla
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function handleItemsPerPageChange(items: number) {
  itemsPerPage.value = items
  currentPage.value = 1
}

onMounted(() => {
  store.fetchFacturas()
})
</script>

<style scoped>
.facturas-view {
  max-width: 1400px;
  margin: 0 auto;
}

h1 {
  color: var(--text-primary);
  margin-bottom: 2rem;
}

.loading, .error {
  text-align: center;
  padding: 2rem;
  margin: 2rem 0;
  background-color: var(--bg-secondary);
  border-radius: 8px;
  color: var(--text-primary);
}

.error {
  background-color: rgba(231, 76, 60, 0.1);
  border: 1px solid rgba(231, 76, 60, 0.3);
  color: #e74c3c;
}

.dark .error {
  background-color: rgba(231, 76, 60, 0.2);
  border-color: rgba(231, 76, 60, 0.4);
}

.btn-retry {
  margin-top: 1rem;
  padding: 0.5rem 1rem;
  background-color: #3498db;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.btn-retry:hover {
  background-color: #2980b9;
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin: 2rem 0;
}

.stat-card {
  background: var(--bg-secondary);
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px var(--shadow);
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
}

.stat-card h3 {
  margin: 0 0 0.5rem 0;
  font-size: 0.9rem;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.stat-number {
  margin: 0;
  font-size: 2rem;
  font-weight: bold;
  color: var(--text-primary);
}
</style>

