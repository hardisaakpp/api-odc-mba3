import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  // State
  const isDark = ref<boolean>(() => {
    // Verificar si hay una preferencia guardada
    const saved = localStorage.getItem('theme')
    if (saved) {
      return saved === 'dark'
    }
    // Verificar preferencia del sistema
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  // Actions
  function toggleTheme() {
    isDark.value = !isDark.value
    updateTheme()
  }

  function setTheme(dark: boolean) {
    isDark.value = dark
    updateTheme()
  }

  function updateTheme() {
    // Guardar preferencia
    localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
    
    // Aplicar clase al documento
    if (isDark.value) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  // Inicializar tema al cargar
  updateTheme()

  // Observar cambios en la preferencia del sistema
  if (window.matchMedia) {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaQuery.addEventListener('change', (e) => {
      // Solo actualizar si no hay preferencia guardada
      if (!localStorage.getItem('theme')) {
        isDark.value = e.matches
        updateTheme()
      }
    })
  }

  return {
    isDark,
    toggleTheme,
    setTheme
  }
})


