<template>
  <div class="filters-card">
    <h2>Filtros</h2>
    <form @submit.prevent="applyFilters" class="filters-form">
      <div class="filter-group">
        <label>
          <input
            type="checkbox"
            v-model="onlyNotAnuladas"
          />
          Solo no anuladas
        </label>
      </div>
      
      <div class="filter-group">
        <label>
          <input
            type="checkbox"
            v-model="onlyConfirmadas"
          />
          Solo confirmadas
        </label>
      </div>
      
      <div class="filter-group">
        <label>
          <input
            type="checkbox"
            v-model="onlySinRemision"
          />
          Sin remisión facturada
        </label>
      </div>
      
      <div class="filter-group">
        <label>
          <input
            type="checkbox"
            v-model="localFilters.include_obj_datos"
          />
          Solo con ObjDatosFactura
        </label>
      </div>
      
      <div class="filter-actions">
        <button type="submit" class="btn-primary">Aplicar Filtros</button>
        <button type="button" @click="resetFilters" class="btn-secondary">Restablecer</button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { FacturaFilters } from '@/types/factura'

const emit = defineEmits<{
  filter: [filters: FacturaFilters]
}>()

const onlyNotAnuladas = ref(true)
const onlyConfirmadas = ref(true)
const onlySinRemision = ref(true)

const localFilters = ref<FacturaFilters>({
  anulada: false,
  confirmado: true,
  remision_facturada: false,
  include_obj_datos: true,
  save_to_db: true
})

const computedFilters = computed<FacturaFilters>(() => ({
  anulada: onlyNotAnuladas.value ? false : undefined,
  confirmado: onlyConfirmadas.value ? true : undefined,
  remision_facturada: onlySinRemision.value ? false : undefined,
  include_obj_datos: localFilters.value.include_obj_datos,
  save_to_db: localFilters.value.save_to_db
}))

function applyFilters() {
  emit('filter', computedFilters.value)
}

function resetFilters() {
  onlyNotAnuladas.value = true
  onlyConfirmadas.value = true
  onlySinRemision.value = true
  localFilters.value.include_obj_datos = true
  localFilters.value.save_to_db = true
  applyFilters()
}
</script>

<style scoped>
.filters-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
  box-shadow: 0 2px 4px var(--shadow);
  transition: all 0.3s ease;
}

.filters-card h2 {
  margin: 0 0 1rem 0;
  color: var(--text-primary);
  font-size: 1.2rem;
}

.filters-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.filter-group {
  display: flex;
  align-items: center;
}

.filter-group label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.filter-group input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.filter-actions {
  grid-column: 1 / -1;
  display: flex;
  gap: 1rem;
  margin-top: 1rem;
}

.btn-primary, .btn-secondary {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  transition: background-color 0.2s;
}

.btn-primary {
  background-color: #3498db;
  color: white;
}

.btn-primary:hover {
  background-color: #2980b9;
}

.btn-secondary {
  background-color: #95a5a6;
  color: white;
}

.btn-secondary:hover {
  background-color: #7f8c8d;
}
</style>

