import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

// Inicializar Pinia antes de crear la app para que los stores se inicialicen
const pinia = createPinia()

const app = createApp(App)

app.use(pinia)
app.use(router)

// Inicializar el tema después de montar la app
import { useThemeStore } from './stores/theme'
const themeStore = useThemeStore()

// Filtrar errores conocidos de extensiones del navegador
window.addEventListener('error', (event) => {
  const errorMessage = event.message || event.error?.message || ''
  
  // Ignorar errores comunes de extensiones del navegador
  if (
    errorMessage.includes('message channel closed') ||
    errorMessage.includes('Extension context invalidated') ||
    errorMessage.includes('Receiving end does not exist')
  ) {
    event.preventDefault()
    event.stopPropagation()
    return false
  }
})

// Filtrar promesas rechazadas no capturadas (especialmente de extensiones)
window.addEventListener('unhandledrejection', (event) => {
  const errorMessage = event.reason?.message || String(event.reason) || ''
  
  // Ignorar errores comunes de extensiones del navegador
  if (
    errorMessage.includes('message channel closed') ||
    errorMessage.includes('Extension context invalidated') ||
    errorMessage.includes('Receiving end does not exist') ||
    errorMessage.includes('listener indicated an asynchronous response')
  ) {
    event.preventDefault()
    return false
  }
})

app.mount('#app')

