import { createRouter, createWebHistory } from 'vue-router'
import FacturasView from '@/views/FacturasView.vue'
import ConsultaView from '@/views/ConsultaView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'facturas',
      component: FacturasView
    },
    {
      path: '/consulta',
      name: 'consulta',
      component: ConsultaView
    }
  ]
})

export default router

