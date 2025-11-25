<template>
  <div class="lineas-container">
    <div v-for="(lineas, tipo) in lineasAgrupadas" :key="tipo" class="lineas-group">
      <h4 class="tipo-header">{{ formatTipo(tipo) }}</h4>
      <table class="lineas-table">
        <thead>
          <tr>
            <th>Código</th>
            <th>Nombre</th>
            <th>Cantidad</th>
            <th>Precio Unit.</th>
            <th>Descuento</th>
            <th>Impuesto</th>
            <th>Total Línea</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(linea, index) in lineas" :key="index">
            <td>{{ linea.Codigo || '-' }}</td>
            <td>{{ linea.Nombre || '-' }}</td>
            <td>{{ formatNumber(linea.Cantidad) }}</td>
            <td>${{ formatNumber(linea.PrecioUnitario) }}</td>
            <td>${{ formatNumber(linea.Descuento) }}</td>
            <td>${{ formatNumber(linea.Impuesto) }}</td>
            <td><strong>${{ formatNumber(linea.TotalLinea) }}</strong></td>
          </tr>
        </tbody>
        <tfoot v-if="lineas.length > 0">
          <tr>
            <td colspan="6" class="total-label">Total {{ formatTipo(tipo) }}:</td>
            <td class="total-amount">
              <strong>${{ formatNumber(getTotal(lineas)) }}</strong>
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ObjDatosFactura, LineaFactura } from '@/types/factura'

const props = defineProps<{
  objDatosFactura: ObjDatosFactura
}>()

const lineasAgrupadas = computed(() => {
  const grupos: Record<string, LineaFactura[]> = {}
  
  // Recorrer todos los tipos de líneas
  const tipos = [
    'GrabarLineasProd',
    'Lineas',
    'CtrlEliminados1',
    'CtrlEliminados2',
    'CtrlEliminados3',
    'CtrlEliminados4',
    'CtrlEliminados5',
    'CtrlEliminados6',
    'CtrlEliminados7',
    'CtrlEliminados8',
    'CtrlEliminadosA',
    'CtrlEliminadosB'
  ]
  
  tipos.forEach(tipo => {
    const lineas = props.objDatosFactura[tipo as keyof ObjDatosFactura]
    if (lineas && Array.isArray(lineas) && lineas.length > 0) {
      grupos[tipo] = lineas
    }
  })
  
  return grupos
})

function formatTipo(tipo: string): string {
  const nombres: Record<string, string> = {
    'GrabarLineasProd': 'Productos',
    'Lineas': 'Líneas',
    'CtrlEliminados1': 'Control Eliminados 1',
    'CtrlEliminados2': 'Control Eliminados 2',
    'CtrlEliminados3': 'Control Eliminados 3',
    'CtrlEliminados4': 'Control Eliminados 4',
    'CtrlEliminados5': 'Control Eliminados 5',
    'CtrlEliminados6': 'Control Eliminados 6',
    'CtrlEliminados7': 'Control Eliminados 7',
    'CtrlEliminados8': 'Control Eliminados 8',
    'CtrlEliminadosA': 'Control Eliminados A',
    'CtrlEliminadosB': 'Control Eliminados B'
  }
  return nombres[tipo] || tipo
}

function formatNumber(value?: number): string {
  if (value === undefined || value === null) return '0.00'
  return value.toLocaleString('es-ES', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function getTotal(lineas: LineaFactura[]): number {
  return lineas.reduce((sum, linea) => sum + (linea.TotalLinea || 0), 0)
}
</script>

<style scoped>
.lineas-container {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.lineas-group {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.tipo-header {
  background-color: #34495e;
  color: white;
  margin: 0;
  padding: 0.75rem 1rem;
  font-size: 1rem;
  font-weight: 600;
}

.dark .tipo-header {
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
}

.lineas-table {
  width: 100%;
  border-collapse: collapse;
}

.lineas-table thead {
  background-color: var(--bg-tertiary);
}

.lineas-table th {
  padding: 0.75rem;
  text-align: left;
  font-weight: 600;
  font-size: 0.875rem;
  border-bottom: 2px solid var(--border-color);
  color: var(--text-primary);
}

.lineas-table tbody tr {
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.lineas-table tbody tr:hover {
  background-color: var(--bg-tertiary);
}

.lineas-table td {
  padding: 0.75rem;
}

.lineas-table tfoot {
  background-color: var(--bg-tertiary);
  font-weight: 600;
  color: var(--text-primary);
}

.total-label {
  text-align: right;
}

.total-amount {
  text-align: right;
  color: #27ae60;
}
</style>

