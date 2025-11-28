<template>
  <div class="proceso-completo-view">
    <h1 class="page-title">Proceso Completo</h1>
    
    <ProcesoFlujo 
      :current-step="procesoStore.currentStep"
      :progress="procesoStore.progress"
    />

    <div class="actions-section">
      <h3>Acciones</h3>
      <div class="actions-buttons">
        <button 
          @click="ejecutarProcesoCompleto" 
          class="btn btn-success btn-large"
          :disabled="procesoStore.loading"
        >
          {{ procesoStore.loading ? 'Ejecutando...' : 'Ejecutar Proceso Completo' }}
        </button>
        <button 
          @click="ejecutarPasoAPaso" 
          class="btn btn-primary btn-large"
          :disabled="procesoStore.loading"
        >
          Ejecutar Paso a Paso
        </button>
        <button 
          @click="procesoStore.reset" 
          class="btn btn-secondary"
          :disabled="procesoStore.loading"
        >
          Limpiar
        </button>
      </div>
    </div>

    <div v-if="procesoStore.error" class="error-alert">
      <strong>Error:</strong> {{ procesoStore.error }}
    </div>

    <div v-if="procesoStore.resultados" class="resultados-section">
      <h3>Resultados</h3>
      <div class="resultados-card">
        <div v-if="procesoStore.resultados.metadata?.save_status" class="resultado-item">
          <h4>Guardado en Base de Datos</h4>
          <ul>
            <li>Facturas guardadas: {{ procesoStore.resultados.metadata.save_status.facturas_guardadas || 0 }}</li>
            <li>Facturas actualizadas: {{ procesoStore.resultados.metadata.save_status.facturas_actualizadas || 0 }}</li>
            <li>Total detalles: {{ procesoStore.resultados.metadata.save_status.total_detalles || 0 }}</li>
          </ul>
        </div>

        <div v-if="procesoStore.resultados.metadata?.oc_status" class="resultado-item">
          <h4>Órdenes de Compra</h4>
          <ul>
            <li>OCs creadas: {{ procesoStore.resultados.metadata.oc_status.oc_creadas || 0 }}</li>
            <li>Errores: {{ procesoStore.resultados.metadata.oc_status.oc_errores || 0 }}</li>
            <li>Total procesadas: {{ procesoStore.resultados.metadata.oc_status.total_procesadas || 0 }}</li>
          </ul>
        </div>

        <div class="resultado-item">
          <h4>Datos Completos</h4>
          <pre class="json-preview">{{ JSON.stringify(procesoStore.resultados, null, 2) }}</pre>
        </div>
      </div>
    </div>

    <div v-if="pasoAPasoMode" class="paso-a-paso-section">
      <h3>Ejecutar Paso a Paso</h3>
      <div class="paso-buttons">
        <button 
          @click="ejecutarConsultar" 
          class="btn btn-primary"
          :disabled="procesoStore.loading"
        >
          {{ procesoStore.loading && procesoStore.currentStep === 'consultar' ? 'Ejecutando...' : '1. Consultar' }}
        </button>
        <button 
          @click="ejecutarMigrar" 
          class="btn btn-primary"
          :disabled="procesoStore.loading"
        >
          {{ procesoStore.loading && procesoStore.currentStep === 'migrar' ? 'Ejecutando...' : '2. Migrar' }}
        </button>
        <button 
          @click="ejecutarProcesarOC" 
          class="btn btn-primary"
          :disabled="procesoStore.loading"
        >
          {{ procesoStore.loading && procesoStore.currentStep === 'procesar-oc' ? 'Ejecutando...' : '3. Procesar OC' }}
        </button>
        <button 
          @click="ejecutarIntegrarSAP" 
          class="btn btn-primary"
          :disabled="procesoStore.loading"
        >
          {{ procesoStore.loading && procesoStore.currentStep === 'integrar-sap' ? 'Ejecutando...' : '4. Integrar SAP' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useProcesoStore } from '@/stores/proceso'
import ProcesoFlujo from '@/components/ProcesoFlujo.vue'

const procesoStore = useProcesoStore()
const pasoAPasoMode = ref(false)

async function ejecutarProcesoCompleto() {
  try {
    await procesoStore.procesoCompleto()
  } catch (error) {
    console.error('Error en proceso completo:', error)
  }
}

function ejecutarPasoAPaso() {
  pasoAPasoMode.value = true
}

async function ejecutarConsultar() {
  try {
    await procesoStore.consultar()
  } catch (error) {
    console.error('Error al consultar:', error)
  }
}

async function ejecutarMigrar() {
  try {
    await procesoStore.migrar()
  } catch (error) {
    console.error('Error al migrar:', error)
  }
}

async function ejecutarProcesarOC() {
  try {
    await procesoStore.procesarOC()
  } catch (error) {
    console.error('Error al procesar OC:', error)
  }
}

async function ejecutarIntegrarSAP() {
  try {
    await procesoStore.integrarSAP()
  } catch (error) {
    console.error('Error al integrar SAP:', error)
  }
}
</script>

<style scoped>
.proceso-completo-view {
  padding: 2rem 0;
}

.page-title {
  font-size: 2rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2rem;
}

.actions-section {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-color);
  margin-bottom: 2rem;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.actions-section h3 {
  margin: 0 0 1rem 0;
  font-size: 1.25rem;
  color: var(--text-primary);
}

.actions-buttons {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
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

.btn-large {
  padding: 1rem 2rem;
  font-size: 1rem;
}

.btn-success {
  background: #27ae60;
  color: white;
}

.btn-success:hover:not(:disabled) {
  background: #229954;
}

.btn-primary {
  background: #3498db;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #2980b9;
}

.btn-secondary {
  background: #95a5a6;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #7f8c8d;
}

.btn:disabled {
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

.resultados-section {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-color);
  margin-bottom: 2rem;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.resultados-section h3 {
  margin: 0 0 1.5rem 0;
  font-size: 1.25rem;
  color: var(--text-primary);
}

.resultados-card {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.resultado-item {
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.resultado-item h4 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: var(--text-primary);
}

.resultado-item ul {
  margin: 0;
  padding-left: 1.5rem;
}

.resultado-item li {
  margin: 0.5rem 0;
  color: var(--text-secondary);
}

.json-preview {
  background: var(--bg-secondary);
  color: var(--text-primary);
  padding: 1rem;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 0.875rem;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--border-color);
  font-family: 'Courier New', monospace;
}

.paso-a-paso-section {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-color);
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.paso-a-paso-section h3 {
  margin: 0 0 1rem 0;
  font-size: 1.25rem;
  color: var(--text-primary);
}

.paso-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
}
</style>

