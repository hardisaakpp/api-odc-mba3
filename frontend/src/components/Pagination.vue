<template>
  <div class="pagination-container">
    <div class="pagination-info">
      <span>Mostrando {{ startItem }} - {{ endItem }} de {{ totalItems }}</span>
    </div>
    
    <div class="pagination-controls">
      <button 
        @click="goToPage(currentPage - 1)" 
        :disabled="currentPage === 1"
        class="pagination-btn"
        :class="{ disabled: currentPage === 1 }"
      >
        Anterior
      </button>
      
      <div class="page-numbers">
        <button
          v-for="page in visiblePages"
          :key="page"
          @click="goToPage(page)"
          class="page-btn"
          :class="{ active: page === currentPage, ellipsis: page === '...' }"
          :disabled="page === '...'"
        >
          {{ page }}
        </button>
      </div>
      
      <button 
        @click="goToPage(currentPage + 1)" 
        :disabled="currentPage === totalPages"
        class="pagination-btn"
        :class="{ disabled: currentPage === totalPages }"
      >
        Siguiente
      </button>
    </div>
    
    <div class="pagination-size">
      <label>
        Por página:
        <select v-model="localItemsPerPage" @change="changeItemsPerPage">
          <option :value="10">10</option>
          <option :value="25">25</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface Props {
  currentPage: number
  totalItems: number
  itemsPerPage: number
}

interface Emits {
  (e: 'page-change', page: number): void
  (e: 'items-per-page-change', items: number): void
}

const props = withDefaults(defineProps<Props>(), {
  currentPage: 1,
  totalItems: 0,
  itemsPerPage: 10
})

const emit = defineEmits<Emits>()

const localItemsPerPage = ref(props.itemsPerPage)

const totalPages = computed(() => {
  return Math.ceil(props.totalItems / props.itemsPerPage)
})

const startItem = computed(() => {
  if (props.totalItems === 0) return 0
  return (props.currentPage - 1) * props.itemsPerPage + 1
})

const endItem = computed(() => {
  const end = props.currentPage * props.itemsPerPage
  return Math.min(end, props.totalItems)
})

const visiblePages = computed(() => {
  const pages: (number | string)[] = []
  const total = totalPages.value
  const current = props.currentPage
  
  if (total <= 7) {
    // Mostrar todas las páginas si son 7 o menos
    for (let i = 1; i <= total; i++) {
      pages.push(i)
    }
  } else {
    // Siempre mostrar primera página
    pages.push(1)
    
    if (current > 3) {
      pages.push('...')
    }
    
    // Mostrar páginas alrededor de la actual
    const start = Math.max(2, current - 1)
    const end = Math.min(total - 1, current + 1)
    
    for (let i = start; i <= end; i++) {
      pages.push(i)
    }
    
    if (current < total - 2) {
      pages.push('...')
    }
    
    // Siempre mostrar última página
    pages.push(total)
  }
  
  return pages
})

function goToPage(page: number) {
  if (page >= 1 && page <= totalPages.value && page !== props.currentPage) {
    emit('page-change', page)
  }
}

function changeItemsPerPage() {
  emit('items-per-page-change', localItemsPerPage.value)
  // Volver a la primera página al cambiar el tamaño
  emit('page-change', 1)
}

watch(() => props.itemsPerPage, (newValue) => {
  localItemsPerPage.value = newValue
})
</script>

<style scoped>
.pagination-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  margin-top: 1rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.pagination-info {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.pagination-btn,
.page-btn {
  padding: 0.5rem 1rem;
  border: 1px solid var(--border-color);
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.2s ease;
  min-width: 40px;
}

.pagination-btn:hover:not(.disabled),
.page-btn:hover:not(.disabled):not(.ellipsis) {
  background-color: var(--bg-tertiary);
  border-color: #3498db;
}

.pagination-btn.disabled,
.page-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-btn.ellipsis {
  cursor: default;
  border: none;
  background: transparent;
}

.page-btn.active {
  background-color: #3498db;
  color: white;
  border-color: #3498db;
  font-weight: 600;
}

.page-numbers {
  display: flex;
  gap: 0.25rem;
}

.pagination-size {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.pagination-size select {
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 0.875rem;
}

.pagination-size select:hover {
  border-color: #3498db;
}

@media (max-width: 768px) {
  .pagination-container {
    flex-direction: column;
    align-items: stretch;
  }
  
  .pagination-controls {
    justify-content: center;
  }
  
  .pagination-info,
  .pagination-size {
    text-align: center;
  }
}
</style>

