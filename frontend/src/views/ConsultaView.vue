<template>
  <div class="consulta-view">
    <div class="header">
      <h1>Consulta SQL Dinámica</h1>
      <p class="subtitle">Ejecuta consultas SQL personalizadas contra MBA3</p>
    </div>

    <div class="query-section">
      <div class="query-header">
        <label for="sql-query">Consulta SQL:</label>
        <div class="query-actions">
          <button @click="loadExample" class="btn-example">Cargar Ejemplo</button>
          <button @click="clearQuery" class="btn-clear">Limpiar</button>
        </div>
      </div>
      <textarea
        id="sql-query"
        v-model="query"
        class="query-input"
        placeholder="Ejemplo: SELECT * FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"
        rows="6"
      ></textarea>
      <div class="query-footer">
        <button @click="executeQuery" :disabled="!query.trim() || store.loading" class="btn-execute">
          {{ store.loading ? 'Ejecutando...' : 'Ejecutar Consulta' }}
        </button>
        <span v-if="store.error" class="error-message">{{ store.error }}</span>
      </div>
    </div>

    <div v-if="store.loading" class="loading">
      <p>Ejecutando consulta...</p>
    </div>

    <div v-else-if="store.error" class="error">
      <p>Error: {{ store.error }}</p>
      <button @click="executeQuery" class="btn-retry">Reintentar</button>
    </div>

    <div v-else-if="store.hasFacturas" class="results-section">
      <div class="stats">
        <div class="stat-card">
          <h3>Resultados</h3>
          <p class="stat-number">{{ store.totalFacturas }}</p>
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

    <div v-else-if="queryExecuted && !store.hasFacturas" class="no-results">
      <p>La consulta se ejecutó correctamente pero no se encontraron resultados.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useFacturasStore } from '@/stores/facturas'
import FacturaTable from '@/components/FacturaTable.vue'
import Pagination from '@/components/Pagination.vue'

const store = useFacturasStore()

// Estado de la consulta
const query = ref('')
const queryExecuted = ref(false)

// Estado de paginación
const currentPage = ref(1)
const itemsPerPage = ref(10)

// Facturas paginadas
const paginatedFacturas = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value
  const end = start + itemsPerPage.value
  return store.facturas.slice(start, end)
})

// Ejecutar consulta
async function executeQuery() {
  if (!query.value.trim()) return
  
  queryExecuted.value = true
  currentPage.value = 1 // Resetear a primera página
  await store.executeQuery(query.value.trim())
}

// Cargar ejemplo
function loadExample() {
  query.value = `SELECT * FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'`
}

// Limpiar consulta
function clearQuery() {
  query.value = ''
  queryExecuted.value = false
  store.facturas = []
  store.error = null
}

// Manejar cambio de página
function handlePageChange(page: number) {
  currentPage.value = page
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// Manejar cambio de items por página
function handleItemsPerPageChange(items: number) {
  itemsPerPage.value = items
  currentPage.value = 1
}
</script>

<style scoped>
.consulta-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.header {
  margin-bottom: 2rem;
}

.header h1 {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  color: var(--text-primary);
}

.subtitle {
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.query-section {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.query-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.query-header label {
  font-weight: 600;
  color: var(--text-primary);
}

.query-actions {
  display: flex;
  gap: 0.5rem;
}

.btn-example,
.btn-clear {
  padding: 0.5rem 1rem;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  color: var(--text-primary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.btn-example:hover,
.btn-clear:hover {
  background: var(--bg-hover);
}

.query-input {
  width: 100%;
  padding: 1rem;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.9rem;
  background: var(--bg-primary);
  color: var(--text-primary);
  resize: vertical;
  margin-bottom: 1rem;
}

.query-input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
}

.query-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-execute {
  padding: 0.75rem 2rem;
  background: var(--primary-color, #3b82f6);
  color: white;
  border: none;
  border-radius: 4px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-execute:hover:not(:disabled) {
  background: var(--primary-color-hover, #2563eb);
}

.btn-execute:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-message {
  color: var(--error-color, #ef4444);
  font-size: 0.9rem;
}

.loading,
.error,
.no-results {
  text-align: center;
  padding: 3rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  margin-bottom: 2rem;
}

.error {
  color: var(--error-color, #ef4444);
}

.btn-retry {
  margin-top: 1rem;
  padding: 0.5rem 1.5rem;
  background: var(--primary-color, #3b82f6);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.results-section {
  margin-top: 2rem;
}

.stats {
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: var(--bg-secondary);
  padding: 1.5rem;
  border-radius: 8px;
  flex: 1;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.stat-card h3 {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.stat-number {
  font-size: 2rem;
  font-weight: bold;
  color: var(--text-primary);
}
</style>


