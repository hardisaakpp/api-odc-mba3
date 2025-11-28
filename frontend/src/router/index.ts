import { createRouter, createWebHistory } from 'vue-router'
import FacturasView from '@/views/FacturasView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'facturas',
      component: FacturasView
    }
  ]
})

export default router

