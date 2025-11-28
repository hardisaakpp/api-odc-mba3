<template>
  <div class="table-container">
    <div class="table-header">
      <h2>Órdenes de Compra</h2>
      <div class="table-info">
        <span class="count-badge">{{ ordenesCompra.length }} órdenes</span>
      </div>
    </div>

    <div v-if="ordenesCompra.length === 0" class="empty-state">
      <p>No se encontraron órdenes de compra</p>
    </div>

    <div v-else class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>OC ID</th>
            <th>Proveedor</th>
            <th>Referencia Despacho</th>
            <th>Fecha Generación</th>
            <th>Estado</th>
            <th>Número OC SAP</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr 
            v-for="oc in ordenesCompra" 
            :key="oc.oc_id" 
            class="table-row"
          >
            <td class="font-mono">{{ oc.oc_id.substring(0, 8) }}...</td>
            <td>{{ oc.proveedor }}</td>
            <td>{{ oc.referencia_despacho }}</td>
            <td>{{ formatDate(oc.fecha_generacion) }}</td>
            <td>
              <span :class="getEstadoClass(oc.estado)">
                {{ oc.estado }}
              </span>
            </td>
            <td>{{ oc.numero_oc_sap || '-' }}</td>
            <td>
              <button 
                v-if="oc.estado === 'PENDIENTE'"
                @click="handleIntegrar(oc.referencia_despacho)" 
                class="btn-integrate"
                :disabled="loading"
              >
                {{ loading ? 'Enviando...' : 'Enviar a SAP' }}
              </button>
              <span v-else class="no-action">-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { OrdenCompra } from '@/types/ordenCompra'

defineProps<{
  ordenesCompra: OrdenCompra[]
  loading?: boolean
}>()

const emit = defineEmits<{
  integrar: [referenciaDespacho: string]
}>()

function formatDate(dateString: string): string {
  if (!dateString) return '-'
  try {
    const date = new Date(dateString)
    return date.toLocaleDateString('es-ES')
  } catch {
    return dateString
  }
}

function getEstadoClass(estado: string): string {
  const classes: Record<string, string> = {
    'PENDIENTE': 'status-badge status-warning',
    'ENVIADA': 'status-badge status-success',
    'ERROR': 'status-badge status-error',
  }
  return classes[estado] || 'status-badge'
}

function handleIntegrar(referenciaDespacho: string) {
  emit('integrar', referenciaDespacho)
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

.count-badge {
  background: #3498db;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.875rem;
  font-weight: 500;
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

.btn-integrate {
  background: #27ae60;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
  transition: background 0.2s;
}

.btn-integrate:hover:not(:disabled) {
  background: #229954;
}

.btn-integrate:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.no-action {
  color: var(--text-light);
  font-style: italic;
}
</style>

