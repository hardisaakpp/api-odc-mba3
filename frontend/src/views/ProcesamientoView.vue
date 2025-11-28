<template>
  <div class="procesamiento-view">
    <h1>Procesamiento de Despachos</h1>
    <p class="subtitle">Gestiona el flujo completo de procesamiento de despachos desde MBA3 hasta SAP</p>

    <!-- Estado del servidor -->
    <div class="health-status" :class="{ 'online': serverOnline, 'offline': !serverOnline }">
      <span class="status-indicator"></span>
      <span>{{ serverOnline ? 'Servidor en línea' : 'Servidor desconectado' }}</span>
    </div>

    <!-- Pasos del flujo -->
    <div class="flujo-container">
      <div class="step-card" :class="{ 'completed': stepStatus.consultar, 'active': currentStep === 'consultar' }">
        <div class="step-header">
          <div class="step-number">1</div>
          <h3>Consultar</h3>
        </div>
        <p>Consulta despachos desde MBA3 (solo lectura)</p>
        <button 
          @click="ejecutarConsultar" 
          :disabled="loading"
          class="btn-step"
        >
          {{ loading && currentStep === 'consultar' ? 'Consultando...' : 'Consultar' }}
        </button>
        <div v-if="stepStatus.consultar" class="step-result">
          <span class="success-icon">✓</span>
          <span>{{ consultarResult?.length || 0 }} despachos encontrados</span>
        </div>
      </div>

      <div class="step-card" :class="{ 'completed': stepStatus.migrar, 'active': currentStep === 'migrar' }">
        <div class="step-header">
          <div class="step-number">2</div>
          <h3>Migrar</h3>
        </div>
        <p>Consulta y guarda en base de datos (despacho_cabecera/detalle)</p>
        <button 
          @click="ejecutarMigrar" 
          :disabled="loading || !stepStatus.consultar"
          class="btn-step"
        >
          {{ loading && currentStep === 'migrar' ? 'Migrando...' : 'Migrar' }}
        </button>
        <div v-if="stepStatus.migrar && migrarResult" class="step-result">
          <span class="success-icon">✓</span>
          <span>
            {{ migrarResult.metadata?.save_status?.facturas_guardadas || 0 }} facturas guardadas
          </span>
        </div>
      </div>

      <div class="step-card" :class="{ 'completed': stepStatus.procesarOC, 'active': currentStep === 'procesar-oc' }">
        <div class="step-header">
          <div class="step-number">3</div>
          <h3>Procesar OC</h3>
        </div>
        <p>Copia despachos a orden_compra_cabecera/detalle (estado: PENDIENTE)</p>
        <button 
          @click="ejecutarProcesarOC" 
          :disabled="loading || !stepStatus.migrar"
          class="btn-step"
        >
          {{ loading && currentStep === 'procesar-oc' ? 'Procesando...' : 'Procesar OC' }}
        </button>
        <div v-if="stepStatus.procesarOC && procesarOCResult" class="step-result">
          <span class="success-icon">✓</span>
          <span>
            {{ procesarOCResult.metadata?.oc_creadas || 0 }} OCs creadas
          </span>
        </div>
      </div>

      <div class="step-card" :class="{ 'completed': stepStatus.integrarSAP, 'active': currentStep === 'integrar-sap' }">
        <div class="step-header">
          <div class="step-number">4</div>
          <h3>Integrar SAP</h3>
        </div>
        <p>Envía ODCs pendientes a SAP Service Layer</p>
        <div class="sap-actions">
          <input 
            v-model="referenciaDespacho" 
            type="text" 
            placeholder="Referencia despacho (opcional)"
            class="input-referencia"
          />
          <button 
            @click="ejecutarIntegrarSAP" 
            :disabled="loading || !stepStatus.procesarOC"
            class="btn-step"
          >
            {{ loading && currentStep === 'integrar-sap' ? 'Enviando...' : 'Enviar a SAP' }}
          </button>
        </div>
        <div v-if="stepStatus.integrarSAP && integrarSAPResult" class="step-result">
          <span class="success-icon">✓</span>
          <span>
            {{ integrarSAPResult.metadata?.enviadas || 0 }} ODCs enviadas
            <span v-if="integrarSAPResult.metadata?.errores">, {{ integrarSAPResult.metadata.errores }} errores</span>
          </span>
        </div>
      </div>
    </div>

    <!-- Botón de proceso completo -->
    <div class="proceso-completo">
      <button 
        @click="ejecutarProcesoCompleto" 
        :disabled="loading"
        class="btn-completo"
      >
        {{ loading && currentStep === 'completo' ? 'Ejecutando proceso completo...' : 'Ejecutar Proceso Completo (Pruebas)' }}
      </button>
      <p class="hint">Ejecuta los pasos 1, 2 y 3 en una sola operación</p>
    </div>

    <!-- Mensajes de error -->
    <div v-if="error" class="error-message">
      <strong>Error:</strong> {{ error }}
      <button @click="error = null" class="btn-close-error">×</button>
    </div>

    <!-- Resultados detallados -->
    <div v-if="resultadoCompleto" class="resultado-detallado">
      <h3>Resultado del Proceso</h3>
      <pre>{{ JSON.stringify(resultadoCompleto, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import facturasApi from '@/services/api'
import type { ProcesoResponse } from '@/types/api'

const serverOnline = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const currentStep = ref<string | null>(null)
const referenciaDespacho = ref('')

const stepStatus = ref({
  consultar: false,
  migrar: false,
  procesarOC: false,
  integrarSAP: false
})

const consultarResult = ref<any>(null)
const migrarResult = ref<ProcesoResponse | null>(null)
const procesarOCResult = ref<ProcesoResponse | null>(null)
const integrarSAPResult = ref<ProcesoResponse | null>(null)
const resultadoCompleto = ref<any>(null)

async function checkHealth() {
  try {
    await facturasApi.healthCheck()
    serverOnline.value = true
  } catch {
    serverOnline.value = false
  }
}

async function ejecutarConsultar() {
  loading.value = true
  currentStep.value = 'consultar'
  error.value = null
  
  try {
    const result = await facturasApi.consultar()
    consultarResult.value = Array.isArray(result) ? result : [result]
    stepStatus.value.consultar = true
    resultadoCompleto.value = result
  } catch (err: any) {
    error.value = err.response?.data?.message || err.message || 'Error al consultar'
    stepStatus.value.consultar = false
  } finally {
    loading.value = false
    currentStep.value = null
  }
}

async function ejecutarMigrar() {
  loading.value = true
  currentStep.value = 'migrar'
  error.value = null
  
  try {
    const result = await facturasApi.migrar()
    migrarResult.value = result
    stepStatus.value.migrar = true
    resultadoCompleto.value = result
  } catch (err: any) {
    error.value = err.response?.data?.message || err.message || 'Error al migrar'
    stepStatus.value.migrar = false
  } finally {
    loading.value = false
    currentStep.value = null
  }
}

async function ejecutarProcesarOC() {
  loading.value = true
  currentStep.value = 'procesar-oc'
  error.value = null
  
  try {
    const result = await facturasApi.procesarOC()
    procesarOCResult.value = result
    stepStatus.value.procesarOC = true
    resultadoCompleto.value = result
  } catch (err: any) {
    error.value = err.response?.data?.message || err.message || 'Error al procesar OC'
    stepStatus.value.procesarOC = false
  } finally {
    loading.value = false
    currentStep.value = null
  }
}

async function ejecutarIntegrarSAP() {
  loading.value = true
  currentStep.value = 'integrar-sap'
  error.value = null
  
  try {
    const referencia = referenciaDespacho.value.trim() || undefined
    const result = await facturasApi.integrarSAP(referencia)
    integrarSAPResult.value = result
    stepStatus.value.integrarSAP = true
    resultadoCompleto.value = result
  } catch (err: any) {
    error.value = err.response?.data?.message || err.message || 'Error al integrar con SAP'
    stepStatus.value.integrarSAP = false
  } finally {
    loading.value = false
    currentStep.value = null
  }
}

async function ejecutarProcesoCompleto() {
  loading.value = true
  currentStep.value = 'completo'
  error.value = null
  
  try {
    const result = await facturasApi.pruebas()
    resultadoCompleto.value = result
    stepStatus.value.consultar = true
    stepStatus.value.migrar = true
    stepStatus.value.procesarOC = true
  } catch (err: any) {
    error.value = err.response?.data?.message || err.message || 'Error al ejecutar proceso completo'
  } finally {
    loading.value = false
    currentStep.value = null
  }
}

onMounted(() => {
  checkHealth()
  // Verificar salud cada 30 segundos
  setInterval(checkHealth, 30000)
})
</script>

<style scoped>
.procesamiento-view {
  max-width: 1400px;
  margin: 0 auto;
}

h1 {
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.subtitle {
  color: var(--text-secondary);
  margin-bottom: 2rem;
}

.health-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  margin-bottom: 2rem;
  font-weight: 500;
}

.health-status.online {
  background-color: rgba(39, 174, 96, 0.1);
  color: #27ae60;
  border: 1px solid rgba(39, 174, 96, 0.3);
}

.health-status.offline {
  background-color: rgba(231, 76, 60, 0.1);
  color: #e74c3c;
  border: 1px solid rgba(231, 76, 60, 0.3);
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background-color: currentColor;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.flujo-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.step-card {
  background: var(--bg-secondary);
  border: 2px solid var(--border-color);
  border-radius: 12px;
  padding: 1.5rem;
  transition: all 0.3s ease;
}

.step-card.active {
  border-color: #3498db;
  box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.1);
}

.step-card.completed {
  border-color: #27ae60;
  background: rgba(39, 174, 96, 0.05);
}

.step-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.step-number {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #34495e;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 1.2rem;
}

.step-card.completed .step-number {
  background: #27ae60;
}

.step-card.active .step-number {
  background: #3498db;
}

.step-header h3 {
  margin: 0;
  color: var(--text-primary);
}

.step-card p {
  color: var(--text-secondary);
  margin-bottom: 1rem;
  font-size: 0.9rem;
}

.btn-step {
  width: 100%;
  padding: 0.75rem 1rem;
  background-color: #3498db;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

.btn-step:hover:not(:disabled) {
  background-color: #2980b9;
}

.btn-step:disabled {
  background-color: #95a5a6;
  cursor: not-allowed;
  opacity: 0.6;
}

.step-result {
  margin-top: 1rem;
  padding: 0.75rem;
  background: rgba(39, 174, 96, 0.1);
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #27ae60;
  font-size: 0.9rem;
}

.success-icon {
  font-weight: bold;
  font-size: 1.2rem;
}

.sap-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.input-referencia {
  padding: 0.5rem;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 0.9rem;
}

.proceso-completo {
  margin-top: 2rem;
  padding: 1.5rem;
  background: var(--bg-secondary);
  border-radius: 12px;
  text-align: center;
  border: 2px dashed var(--border-color);
}

.btn-completo {
  padding: 1rem 2rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.1rem;
  font-weight: 600;
  transition: transform 0.2s, box-shadow 0.2s;
}

.btn-completo:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-completo:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.hint {
  margin-top: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.error-message {
  margin-top: 2rem;
  padding: 1rem;
  background: rgba(231, 76, 60, 0.1);
  border: 1px solid rgba(231, 76, 60, 0.3);
  border-radius: 8px;
  color: #e74c3c;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-close-error {
  background: none;
  border: none;
  color: #e74c3c;
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  line-height: 1;
}

.resultado-detallado {
  margin-top: 2rem;
  padding: 1.5rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.resultado-detallado h3 {
  margin-top: 0;
  color: var(--text-primary);
}

.resultado-detallado pre {
  background: var(--bg-primary);
  padding: 1rem;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 0.85rem;
  color: var(--text-primary);
  max-height: 400px;
  overflow-y: auto;
}
</style>

