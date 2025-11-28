<template>
  <div id="app">
    <nav class="navbar">
      <div class="container">
        <h1 class="navbar-brand">MBA3 - Gestión de Pre-Facturas</h1>
        <div class="navbar-actions">
          <nav class="nav-links">
            <RouterLink to="/" class="nav-link">Facturas</RouterLink>
          </nav>
          <ThemeToggle />
        </div>
      </div>
    </nav>
    
    <main class="container">
      <RouterView />
    </main>
    
    <footer class="footer">
      <div class="container">
        <p>&copy; 2025 MBA3 Consultas</p>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { RouterView, RouterLink } from 'vue-router'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { useThemeStore } from '@/stores/theme'

// Inicializar el tema
const themeStore = useThemeStore()
</script>

<style scoped>
#app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  transition: background-color 0.3s ease, color 0.3s ease;
}

.navbar {
  background-color: #2c3e50;
  color: white;
  padding: 1rem 0;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.navbar .container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.navbar-actions {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.nav-links {
  display: flex;
  gap: 1rem;
}

.nav-link {
  color: white;
  text-decoration: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.nav-link:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.nav-link.router-link-active {
  background-color: rgba(255, 255, 255, 0.2);
  font-weight: 600;
}

.navbar-brand {
  margin: 0;
  font-size: 1.5rem;
}

:global(.dark) .navbar {
  background-color: #1a1a1a;
  border-bottom: 1px solid #333;
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1rem;
  flex: 1;
}

main.container {
  padding: 2rem 1rem;
}

.footer {
  background-color: #34495e;
  color: white;
  padding: 1rem 0;
  margin-top: auto;
}

:global(.dark) .footer {
  background-color: #1a1a1a;
  border-top: 1px solid #333;
}

.footer p {
  margin: 0;
  text-align: center;
}
</style>

