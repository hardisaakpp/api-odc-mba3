<template>
  <div class="table-container">
    <table class="factura-table">
      <thead>
        <tr>
          <th>Código Pre-Factura</th>
          <th>Empresa</th>
          <th>Cliente</th>
          <th>Fecha</th>
          <th>Tipo</th>
          <th>N° Pedido</th>
          <th>Estado</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="facturas.length === 0">
          <td colspan="8" class="no-data">No se encontraron pre-facturas</td>
        </tr>
        <tr v-for="factura in facturas" :key="factura.CODIGO_FACTURA" class="factura-row">
          <td>{{ factura.CODIGO_FACTURA }}</td>
          <td>{{ factura.EMPRESA }}</td>
          <td>{{ factura.CODIGO_CLIENTE }}</td>
          <td>{{ formatDate(factura.FECHA_FACTURA) }}</td>
          <td>
            <span :class="['badge', getTipoClass(factura.TIPO_DOCUMENTO)]">
              {{ factura.TIPO_DOCUMENTO }}
            </span>
          </td>
          <td>{{ factura.NUMERO_PEDIDO_SISTEMA }}</td>
          <td>
            <span v-if="factura.ANULADA" class="badge badge-danger">Anulada</span>
            <span v-else-if="factura.CONFIRMADO" class="badge badge-success">Confirmada</span>
            <span v-else class="badge badge-warning">Pendiente</span>
          </td>
          <td>
            <button @click="viewDetails(factura)" class="btn-view">Ver Detalles</button>
          </td>
        </tr>
      </tbody>
    </table>
    
    <FacturaModal
      v-if="selectedFactura"
      :factura="selectedFactura"
      @close="selectedFactura = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { Factura } from '@/types/factura'
import FacturaModal from './FacturaModal.vue'

defineProps<{
  facturas: Factura[]
}>()

const selectedFactura = ref<Factura | null>(null)

function formatDate(dateString?: string): string {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleDateString('es-ES')
}

function getTipoClass(tipo?: string): string {
  const tipos: Record<string, string> = {
    'FACT': 'badge-primary',
    'REM': 'badge-info'
  }
  return tipos[tipo || ''] || 'badge-secondary'
}

function viewDetails(factura: Factura) {
  selectedFactura.value = factura
}
</script>

<style scoped>
.table-container {
  background: var(--bg-secondary);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 4px var(--shadow);
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
}

.factura-table {
  width: 100%;
  border-collapse: collapse;
}

.factura-table thead {
  background-color: #34495e;
  color: white;
}

.dark .factura-table thead {
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
}

.factura-table th {
  padding: 1rem;
  text-align: left;
  font-weight: 600;
  text-transform: uppercase;
  font-size: 0.875rem;
}

.factura-table tbody tr {
  border-bottom: 1px solid var(--border-color);
  transition: background-color 0.2s;
  color: var(--text-primary);
}

.factura-table tbody tr:hover {
  background-color: var(--bg-tertiary);
}

.factura-table td {
  padding: 1rem;
}

.no-data {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.badge-primary {
  background-color: #3498db;
  color: white;
}

.badge-info {
  background-color: #17a2b8;
  color: white;
}

.badge-success {
  background-color: #27ae60;
  color: white;
}

.badge-danger {
  background-color: #e74c3c;
  color: white;
}

.badge-warning {
  background-color: #f39c12;
  color: white;
}

.badge-secondary {
  background-color: #95a5a6;
  color: white;
}

.btn-view {
  padding: 0.5rem 1rem;
  background-color: #3498db;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.875rem;
  transition: background-color 0.2s;
}

.btn-view:hover {
  background-color: #2980b9;
}
</style>

