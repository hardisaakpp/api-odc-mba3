<template>
  <div class="proceso-flujo">
    <div class="steps-container">
      <div 
        v-for="(step, index) in steps" 
        :key="step.id"
        class="step-item"
        :class="getStepClass(step.id)"
      >
        <div class="step-icon">
          <span v-if="step.status === 'completed'">✓</span>
          <span v-else-if="step.status === 'active'">⟳</span>
          <span v-else>{{ index + 1 }}</span>
        </div>
        <div class="step-content">
          <h3 class="step-title">{{ step.title }}</h3>
          <p class="step-description">{{ step.description }}</p>
        </div>
      </div>
    </div>

    <div v-if="progress > 0" class="progress-bar">
      <div class="progress-fill" :style="{ width: `${progress}%` }"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  currentStep: string | null
  progress: number
}>()

const steps = computed(() => [
  {
    id: 'consultar',
    title: 'Consultar',
    description: 'Consulta datos desde MBA3',
    status: getStepStatus('consultar')
  },
  {
    id: 'migrar',
    title: 'Migrar',
    description: 'Guarda en base de datos',
    status: getStepStatus('migrar')
  },
  {
    id: 'procesar-oc',
    title: 'Procesar OC',
    description: 'Copia a órdenes de compra',
    status: getStepStatus('procesar-oc')
  },
  {
    id: 'integrar-sap',
    title: 'Integrar SAP',
    description: 'Envía a SAP Service Layer',
    status: getStepStatus('integrar-sap')
  }
])

function getStepStatus(stepId: string): 'pending' | 'active' | 'completed' {
  if (!props.currentStep) return 'pending'
  
  const stepOrder = ['consultar', 'migrar', 'procesar-oc', 'integrar-sap']
  const currentIndex = stepOrder.indexOf(props.currentStep)
  const stepIndex = stepOrder.indexOf(stepId)
  
  if (stepIndex < currentIndex) return 'completed'
  if (stepIndex === currentIndex) return 'active'
  return 'pending'
}

function getStepClass(stepId: string): string {
  const status = getStepStatus(stepId)
  return `step-${status}`
}
</script>

<style scoped>
.proceso-flujo {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 2rem;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-color);
  margin-bottom: 2rem;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.steps-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.step-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 1.5rem;
  border-radius: 8px;
  transition: all 0.3s;
}

.step-pending {
  background: var(--bg-secondary);
  color: var(--text-light);
  border: 1px solid var(--border-color);
}

.step-active {
  background: #e3f2fd;
  color: #1976d2;
  box-shadow: 0 4px 12px rgba(25, 118, 210, 0.2);
  transform: scale(1.05);
}

.step-completed {
  background: #e8f5e9;
  color: #2e7d32;
}

.step-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  font-weight: bold;
  margin-bottom: 1rem;
  background: var(--bg-primary);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border-color);
}

.step-pending .step-icon {
  background: var(--bg-secondary);
  color: var(--text-light);
}

.step-active .step-icon {
  background: #1976d2;
  color: white;
  animation: pulse 2s infinite;
}

.step-completed .step-icon {
  background: #2e7d32;
  color: white;
}

.step-content {
  flex: 1;
}

.step-title {
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.step-description {
  margin: 0;
  font-size: 0.875rem;
  opacity: 0.8;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--border-color);
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3498db, #2980b9);
  transition: width 0.3s ease;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.1);
  }
}
</style>

