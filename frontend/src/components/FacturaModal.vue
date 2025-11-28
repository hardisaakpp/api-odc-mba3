<template>
  <div class="modal-overlay" @click.self="close">
    <div class="modal-content">
      <div class="modal-header">
        <h2>Detalles de Factura</h2>
        <button @click="close" class="close-btn">&times;</button>
      </div>
      
      <div class="modal-body">
        <div class="detail-grid">
          <div class="detail-item">
            <label>Código Factura</label>
            <span class="font-mono">{{ factura.CODIGO_FACTURA }}</span>
          </div>
          
          <div class="detail-item">
            <label>Número Factura</label>
            <span>{{ factura.NUMERO_FACTURA }}</span>
          </div>
          
          <div class="detail-item">
            <label>Empresa</label>
            <span>{{ factura.EMPRESA }}</span>
          </div>
          
          <div class="detail-item">
            <label>Código Cliente</label>
            <span>{{ factura.CODIGO_CLIENTE }}</span>
          </div>
          
          <div class="detail-item">
            <label>Fecha Factura</label>
            <span>{{ formatDate(factura.FECHA_FACTURA) }}</span>
          </div>
          
          <div class="detail-item">
            <label>Tipo Documento</label>
            <span>{{ factura.TIPO_DOCUMENTO }}</span>
          </div>
          
          <div class="detail-item">
            <label>Número Orden</label>
            <span>{{ factura.NUMERO_ORDEN || '-' }}</span>
          </div>
          
          <div class="detail-item">
            <label>Número Pedido Sistema</label>
            <span>{{ factura.NUMERO_PEDIDO_SISTEMA || '-' }}</span>
          </div>
          
          <div class="detail-item">
            <label>Código Despacho</label>
            <span>{{ factura.CODIGO_DESPACHO || '0' }}</span>
          </div>
          
          <div class="detail-item">
            <label>Código Bodega</label>
            <span>{{ factura.CODIGO_BODEGA || '-' }}</span>
          </div>
          
          <div class="detail-item">
            <label>Orden Compra</label>
            <span>{{ factura.ORDEN_COMPRA || '-' }}</span>
          </div>
          
          <div class="detail-item">
            <label>Orden Compra Cliente</label>
            <span>{{ factura.ORDEN_COMPRA_CLIENTE || '-' }}</span>
          </div>
          
          <div class="detail-item">
            <label>Anulada</label>
            <span :class="factura.ANULADA === 'true' ? 'text-error' : 'text-success'">
              {{ factura.ANULADA === 'true' ? 'Sí' : 'No' }}
            </span>
          </div>
          
          <div class="detail-item">
            <label>Confirmado</label>
            <span :class="factura.CONFIRMADO === 'true' ? 'text-success' : 'text-warning'">
              {{ factura.CONFIRMADO === 'true' ? 'Sí' : 'No' }}
            </span>
          </div>
          
          <div class="detail-item">
            <label>Remisión Facturada</label>
            <span>{{ factura.Remision_Facturada === 'true' ? 'Sí' : 'No' }}</span>
          </div>
          
          <div class="detail-item full-width">
            <label>ObjDatosFactura</label>
            <span class="obj-datos">{{ factura.ObjDatosFactura || 'N/A' }}</span>
          </div>
        </div>
      </div>
      
      <div class="modal-footer">
        <button @click="close" class="btn btn-primary">Cerrar</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Factura } from '@/types/factura'

defineProps<{
  factura: Factura
}>()

const emit = defineEmits<{
  close: []
}>()

function close() {
  emit('close')
}

function formatDate(dateString: string): string {
  if (!dateString) return '-'
  try {
    const date = new Date(dateString)
    return date.toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  } catch {
    return dateString
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 2rem;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: var(--bg-primary);
  border-radius: 12px;
  max-width: 800px;
  width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--border-color);
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h2 {
  margin: 0;
  font-size: 1.5rem;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  font-size: 2rem;
  color: var(--text-light);
  cursor: pointer;
  line-height: 1;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.modal-body {
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.detail-item.full-width {
  grid-column: 1 / -1;
}

.detail-item label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-item span {
  font-size: 1rem;
  color: var(--text-primary);
  word-break: break-word;
}

.font-mono {
  font-family: 'Courier New', monospace;
}

.text-success {
  color: #27ae60;
  font-weight: 500;
}

.text-error {
  color: #e74c3c;
  font-weight: 500;
}

.text-warning {
  color: #f39c12;
  font-weight: 500;
}

.obj-datos {
  font-family: 'Courier New', monospace;
  font-size: 0.875rem;
  background: var(--bg-secondary);
  padding: 0.75rem;
  border-radius: 6px;
  word-break: break-all;
  border: 1px solid var(--border-color);
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: flex-end;
}

.btn {
  padding: 0.625rem 1.25rem;
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

.btn-primary:hover {
  background: #2980b9;
}
</style>

