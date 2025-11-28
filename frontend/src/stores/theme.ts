import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref<boolean>(() => {
    const saved = localStorage.getItem('theme')
    if (saved) {
      return saved === 'dark'
    }
    // Detectar preferencia del sistema
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  function toggleTheme() {
    isDark.value = !isDark.value
  }

  function setTheme(theme: 'light' | 'dark') {
    isDark.value = theme === 'dark'
  }

  // Aplicar tema al documento
  watch(isDark, (dark) => {
    if (dark) {
      document.documentElement.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, { immediate: true })

  return {
    isDark,
    toggleTheme,
    setTheme,
  }
})

