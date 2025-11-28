<template>
  <div class="dashboard">
    <h1 class="page-title">Dashboard</h1>
    
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon stat-blue">
          <span>📋</span>
        </div>
        <div class="stat-content">
          <h3 class="stat-value">{{ facturasCount }}</h3>
          <p class="stat-label">Facturas</p>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon stat-orange">
          <span>⏳</span>
        </div>
        <div class="stat-content">
          <h3 class="stat-value">{{ ordenesCompraStore.pendientes }}</h3>
          <p class="stat-label">OCs Pendientes</p>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon stat-green">
          <span>✅</span>
        </div>
        <div class="stat-content">
          <h3 class="stat-value">{{ ordenesCompraStore.enviadas }}</h3>
          <p class="stat-label">OCs Enviadas</p>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon stat-red">
          <span>❌</span>
        </div>
        <div class="stat-content">
          <h3 class="stat-value">{{ ordenesCompraStore.errores }}</h3>
          <p class="stat-label">OCs con Error</p>
        </div>
      </div>
    </div>

    <div class="actions-grid">
      <div class="action-card">
        <h3>Consultar Facturas</h3>
        <p>Consulta y filtra facturas desde MBA3</p>
        <router-link to="/facturas" class="btn btn-primary">
          Ir a Facturas
        </router-link>
      </div>

      <div class="action-card">
        <h3>Órdenes de Compra</h3>
        <p>Gestiona y envía órdenes de compra a SAP</p>
        <router-link to="/ordenes-compra" class="btn btn-primary">
          Ver Órdenes
        </router-link>
      </div>

      <div class="action-card">
        <h3>Proceso Completo</h3>
        <p>Ejecuta el flujo completo de procesamiento</p>
        <router-link to="/proceso" class="btn btn-success">
          Ejecutar Proceso
        </router-link>
      </div>
    </div>

    <div class="health-status">
      <h3>Estado del Sistema</h3>
      <div class="health-card">
        <div class="health-item">
          <span class="health-label">API Status:</span>
          <span :class="['health-value', healthStatus === 'ok' ? 'health-ok' : 'health-error']">
            {{ healthStatus === 'ok' ? '✓ Conectado' : '✗ Desconectado' }}
          </span>
        </div>
        <div v-if="healthTime" class="health-item">
          <span class="health-label">Última verificación:</span>
          <span class="health-value">{{ formatTime(healthTime) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useFacturasStore } from '@/stores/facturas'
import { useOrdenesCompraStore } from '@/stores/ordenesCompra'
import api from '@/services/api'

const facturasStore = useFacturasStore()
const ordenesCompraStore = useOrdenesCompraStore()

const healthStatus = ref<'ok' | 'error'>('error')
const healthTime = ref<string | null>(null)

const facturasCount = computed(() => facturasStore.count)

onMounted(async () => {
  await checkHealth()
  await ordenesCompraStore.fetchOrdenesCompra()
})

async function checkHealth() {
  try {
    const response = await api.healthCheck()
    healthStatus.value = response.status === 'ok' ? 'ok' : 'error'
    healthTime.value = response.time
  } catch {
    healthStatus.value = 'error'
  }
}

function formatTime(timeString: string): string {
  try {
    const date = new Date(timeString)
    return date.toLocaleString('es-ES')
  } catch {
    return timeString
  }
}
</script>

<style scoped>
.dashboard {
  padding: 2rem 0;
}

.page-title {
  font-size: 2rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  gap: 1.5rem;
  transition: transform 0.2s, box-shadow 0.2s, background-color 0.3s ease, border-color 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.stat-icon {
  width: 64px;
  height: 64px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
}

.stat-blue {
  background: #e3f2fd;
}

.stat-orange {
  background: #fff3e0;
}

.stat-green {
  background: #e8f5e9;
}

.stat-red {
  background: #ffebee;
}

.stat-content {
  flex: 1;
}

.stat-value {
  margin: 0;
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  margin: 0.25rem 0 0 0;
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.actions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.action-card {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 2rem;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-color);
  text-align: center;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.action-card h3 {
  margin: 0 0 0.5rem 0;
  font-size: 1.25rem;
  color: var(--text-primary);
}

.action-card p {
  margin: 0 0 1.5rem 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.btn {
  display: inline-block;
  padding: 0.75rem 1.5rem;
  border-radius: 6px;
  text-decoration: none;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary {
  background: #3498db;
  color: white;
}

.btn-primary:hover {
  background: #2980b9;
}

.btn-success {
  background: #27ae60;
  color: white;
}

.btn-success:hover {
  background: #229954;
}

.health-status {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-color);
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.health-status h3 {
  margin: 0 0 1rem 0;
  font-size: 1.25rem;
  color: var(--text-primary);
}

.health-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.health-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  background: var(--bg-secondary);
  border-radius: 6px;
  border: 1px solid var(--border-color);
}

.health-label {
  font-weight: 500;
  color: var(--text-secondary);
}

.health-value {
  font-weight: 600;
}

.health-ok {
  color: #27ae60;
}

.health-error {
  color: #e74c3c;
}
</style>

