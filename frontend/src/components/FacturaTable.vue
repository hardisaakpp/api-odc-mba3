<template>
  <div class="table-container">
    <div class="table-header">
      <h2>Facturas Encontradas</h2>
      <div class="table-info">
        <span class="count-badge">{{ facturas.length }} facturas</span>
        <span v-if="metadata?.save_status" class="save-status">
          Guardadas: {{ metadata.save_status.facturas_guardadas || 0 }} | 
          Actualizadas: {{ metadata.save_status.facturas_actualizadas || 0 }}
        </span>
      </div>
    </div>

    <div v-if="facturas.length === 0" class="empty-state">
      <p>No se encontraron facturas con los filtros seleccionados</p>
    </div>

    <div v-else class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>Código Factura</th>
            <th>Número Factura</th>
            <th>Empresa</th>
            <th>Cliente</th>
            <th>Fecha</th>
            <th>Estado</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="factura in facturas" :key="factura.CODIGO_FACTURA" class="table-row">
            <td class="font-mono">{{ factura.CODIGO_FACTURA }}</td>
            <td>{{ factura.NUMERO_FACTURA }}</td>
            <td>{{ factura.EMPRESA }}</td>
            <td>{{ factura.CODIGO_CLIENTE }}</td>
            <td>{{ formatDate(factura.FECHA_FACTURA) }}</td>
            <td>
              <span :class="getStatusClass(factura)">
                {{ getStatusText(factura) }}
              </span>
            </td>
            <td>
              <button 
                @click="openModal(factura)" 
                class="btn-view"
              >
                Ver Detalles
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <FacturaModal 
      v-if="selectedFactura"
      :factura="selectedFactura"
      @close="closeModal"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { Factura } from '@/types/factura'
import FacturaModal from './FacturaModal.vue'

defineProps<{
  facturas: Factura[]
  metadata?: any
}>()

const selectedFactura = ref<Factura | null>(null)

function formatDate(dateString: string): string {
  if (!dateString) return '-'
  try {
    const date = new Date(dateString)
    return date.toLocaleDateString('es-ES')
  } catch {
    return dateString
  }
}

function getStatusClass(factura: Factura): string {
  if (factura.ANULADA === 'true') return 'status-badge status-error'
  if (factura.CONFIRMADO === 'true') return 'status-badge status-success'
  return 'status-badge status-warning'
}

function getStatusText(factura: Factura): string {
  if (factura.ANULADA === 'true') return 'Anulada'
  if (factura.CONFIRMADO === 'true') return 'Confirmada'
  return 'Pendiente'
}

function openModal(factura: Factura) {
  selectedFactura.value = factura
}

function closeModal() {
  selectedFactura.value = null
}
</script>

<style scoped>
.table-container {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-color);
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 2px solid var(--border-color);
}

.table-header h2 {
  margin: 0;
  font-size: 1.5rem;
  color: var(--text-primary);
}

.table-info {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.count-badge {
  background: #3498db;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.875rem;
  font-weight: 500;
}

.save-status {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.empty-state {
  text-align: center;
  padding: 3rem;
  color: var(--text-light);
}

.table-wrapper {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table thead {
  background: var(--bg-secondary);
}

.data-table th {
  padding: 1rem;
  text-align: left;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.875rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.data-table td {
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
}

.table-row:hover {
  background: var(--bg-secondary);
}

.font-mono {
  font-family: 'Courier New', monospace;
  font-size: 0.9rem;
}

.status-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 500;
}

.status-success {
  background: #d4edda;
  color: #155724;
}

.status-warning {
  background: #fff3cd;
  color: #856404;
}

.status-error {
  background: #f8d7da;
  color: #721c24;
}

.btn-view {
  background: #3498db;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
  transition: background 0.2s;
}

.btn-view:hover {
  background: #2980b9;
}
</style>
