<template>
  <div id="app">
    <nav class="navbar">
      <div class="nav-container">
        <div class="nav-brand">
          <h1 class="nav-title">MBA3 Consultas</h1>
        </div>
        <div class="nav-links">
          <router-link to="/" class="nav-link">
            <span>📊</span>
            Dashboard
          </router-link>
          <router-link to="/facturas" class="nav-link">
            <span>📋</span>
            Facturas
          </router-link>
          <router-link to="/ordenes-compra" class="nav-link">
            <span>🛒</span>
            Órdenes de Compra
          </router-link>
          <router-link to="/proceso" class="nav-link">
            <span>⚙️</span>
            Proceso Completo
          </router-link>
          <ThemeToggle />
        </div>
      </div>
    </nav>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import ThemeToggle from '@/components/ThemeToggle.vue'
</script>

<style scoped>
#app {
  min-height: 100vh;
  background: var(--bg-secondary);
  transition: background-color 0.3s ease;
}

.navbar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 1rem 0;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.nav-brand {
  display: flex;
  align-items: center;
}

.nav-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.nav-links {
  display: flex;
  gap: 0.5rem;
}

.nav-link {
  color: white;
  text-decoration: none;
  padding: 0.75rem 1.25rem;
  border-radius: 8px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  font-size: 0.95rem;
}

.nav-link:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.nav-link.router-link-active {
  background: rgba(255, 255, 255, 0.2);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.main-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem;
  min-height: calc(100vh - 80px);
}

@media (max-width: 768px) {
  .nav-container {
    flex-direction: column;
    gap: 1rem;
  }

  .nav-links {
    flex-wrap: wrap;
    justify-content: center;
  }

  .nav-link {
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
  }

  .main-content {
    padding: 1rem;
  }
}
</style>
