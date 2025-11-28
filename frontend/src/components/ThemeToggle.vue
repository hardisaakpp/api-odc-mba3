<template>
  <button 
    @click="toggleTheme" 
    class="theme-toggle"
    :title="themeStore.isDark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'"
  >
    <span v-if="themeStore.isDark" class="theme-icon">☀️</span>
    <span v-else class="theme-icon">🌙</span>
  </button>
</template>

<script setup lang="ts">
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()

function toggleTheme() {
  themeStore.toggleTheme()
}
</script>

<style scoped>
.theme-toggle {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
}

.theme-toggle:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: scale(1.05);
}

.theme-icon {
  font-size: 1.25rem;
  line-height: 1;
}

/* Modo oscuro */
:global(.dark) .theme-toggle {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
}

:global(.dark) .theme-toggle:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>
