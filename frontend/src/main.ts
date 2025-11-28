import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/main.css'
import { useThemeStore } from './stores/theme'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// Inicializar tema antes de montar
const themeStore = useThemeStore()
themeStore.setTheme(themeStore.isDark ? 'dark' : 'light')

app.mount('#app')
