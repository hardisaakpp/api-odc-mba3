<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-content">
        <div class="modal-header">
        <h2>Detalle de Pre-Factura</h2>
        <button @click="$emit('close')" class="btn-close">&times;</button>
      </div>
      
      <div class="modal-body">
        <div v-if="factura" class="factura-info">
          <h3>Información General</h3>
          <div class="info-grid">
            <div class="info-item">
              <label>Código Pre-Factura:</label>
              <span>{{ factura.CODIGO_FACTURA || '-' }}</span>
            </div>
            <div class="info-item">
              <label>Empresa:</label>
              <span>{{ factura.EMPRESA || '-' }}</span>
            </div>
            <div class="info-item">
              <label>Cliente:</label>
              <span>{{ factura.CODIGO_CLIENTE || '-' }}</span>
            </div>
            <div class="info-item">
              <label>Fecha:</label>
              <span>{{ formatDate(factura.FECHA_FACTURA) }}</span>
            </div>
            <div class="info-item">
              <label>Tipo:</label>
              <span>{{ factura.TIPO_DOCUMENTO || '-' }}</span>
            </div>
            <div class="info-item">
              <label>N° Pedido Sistema:</label>
              <span>{{ factura.NUMERO_PEDIDO_SISTEMA ?? '-' }}</span>
            </div>
            <div class="info-item">
              <label>N° Orden:</label>
              <span>{{ factura.NUMERO_ORDEN ?? '-' }}</span>
            </div>
            <div class="info-item">
              <label>N° Factura:</label>
              <span>{{ factura.NUMERO_FACTURA ?? '-' }}</span>
            </div>
            <div class="info-item">
              <label>Código Bodega:</label>
              <span>{{ factura.CODIGO_BODEGA || '-' }}</span>
            </div>
            <div class="info-item">
              <label>Código Despacho:</label>
              <span>{{ factura.CODIGO_DESPACHO ?? '-' }}</span>
            </div>
            <div class="info-item">
              <label>Orden Compra:</label>
              <span>{{ factura.ORDEN_COMPRA || '-' }}</span>
            </div>
            <div class="info-item">
              <label>Estado:</label>
              <span>
                <span v-if="factura.ANULADA" class="badge badge-danger">Anulada</span>
                <span v-else-if="factura.CONFIRMADO" class="badge badge-success">Confirmada</span>
                <span v-else class="badge badge-warning">Pendiente</span>
              </span>
            </div>
          </div>
        </div>
        
        <div v-if="factura && factura.ObjDatosFactura" class="lineas-section">
          <h3>Líneas de Pre-Factura</h3>
          <LineasList :objDatosFactura="factura.ObjDatosFactura" />
        </div>
        <div v-else-if="factura" class="no-lineas">
          <p>No hay líneas de detalle disponibles</p>
        </div>
        <div v-else class="no-lineas">
          <p>Cargando información...</p>
        </div>
      </div>
      
        <div class="modal-footer">
          <button @click="$emit('close')" class="btn-close-modal">Cerrar</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { watch, onUnmounted } from 'vue'
import type { Factura } from '@/types/factura'
import LineasList from './LineasList.vue'

const props = defineProps<{
  factura: Factura | null
}>()

const emit = defineEmits<{
  close: []
}>()

function formatDate(dateString?: string): string {
  if (!dateString) return '-'
  try {
    return new Date(dateString).toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  } catch {
    return dateString || '-'
  }
}

// Manejar escape key para cerrar el modal
function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    emit('close')
  }
}

// Agregar listener cuando el modal se monta
watch(() => props.factura, (newValue) => {
  if (newValue) {
    // Agregar listener de escape cuando el modal está abierto
    window.addEventListener('keydown', handleEscape)
  } else {
    // Remover listener cuando el modal está cerrado
    window.removeEventListener('keydown', handleEscape)
  }
}, { immediate: true })

// Limpiar listener cuando el componente se desmonta
onUnmounted(() => {
  window.removeEventListener('keydown', handleEscape)
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.modal-content {
  background: var(--bg-secondary);
  border-radius: 8px;
  max-width: 1000px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 6px var(--shadow);
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
  animation: slideUp 0.3s ease;
  position: relative;
}

@keyframes slideUp {
  from {
    transform: translateY(20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-color);
  background-color: #34495e;
  color: white;
  flex-shrink: 0;
}

.dark .modal-header {
  background-color: var(--bg-tertiary);
  border-bottom-color: var(--border-color);
}

.modal-header h2 {
  margin: 0;
}

.btn-close {
  background: none;
  border: none;
  font-size: 2rem;
  color: white;
  cursor: pointer;
  line-height: 1;
  padding: 0;
  width: 30px;
  height: 30px;
}

.btn-close:hover {
  opacity: 0.7;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
  color: var(--text-primary);
  min-height: 200px;
}

.factura-info h3,
.lineas-section h3 {
  margin: 0 0 1rem 0;
  color: var(--text-primary);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.info-item label {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.info-item span {
  color: var(--text-primary);
  min-height: 1.2rem;
  display: block;
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
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

.no-lineas {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

.modal-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.btn-close-modal {
  padding: 0.75rem 1.5rem;
  background-color: #95a5a6;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.btn-close-modal:hover {
  background-color: #7f8c8d;
}
</style>

