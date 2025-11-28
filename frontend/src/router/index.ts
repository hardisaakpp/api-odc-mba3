import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import FacturasView from '@/views/FacturasView.vue'
import OrdenesCompraView from '@/views/OrdenesCompraView.vue'
import ProcesoCompletoView from '@/views/ProcesoCompletoView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
    },
    {
      path: '/facturas',
      name: 'facturas',
      component: FacturasView,
    },
    {
      path: '/ordenes-compra',
      name: 'ordenes-compra',
      component: OrdenesCompraView,
    },
    {
      path: '/proceso',
      name: 'proceso',
      component: ProcesoCompletoView,
    },
  ],
})

export default router
