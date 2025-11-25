# Setup del Frontend Vue

## Instalación

1. **Instalar dependencias:**
   ```bash
   cd frontend
   npm install
   ```

2. **Configurar variables de entorno:**
   Crea un archivo `.env.local` en la raíz del directorio `frontend`:
   ```env
   VITE_API_URL=http://localhost:8000
   ```

## Desarrollo

1. **Iniciar servidor de desarrollo:**
   ```bash
   npm run dev
   ```
   
   El frontend estará disponible en: `http://localhost:5173`

2. **Asegúrate de que el backend esté corriendo:**
   ```bash
   # En otra terminal
   cd src
   python api_server.py
   ```
   
   El backend debe estar en: `http://localhost:8000`

## Estructura del Proyecto

```
frontend/
├── src/
│   ├── main.ts                 # Punto de entrada
│   ├── App.vue                 # Componente raíz
│   ├── router/                 # Rutas (Vue Router)
│   │   └── index.ts
│   ├── stores/                 # Estado global (Pinia)
│   │   └── facturas.ts
│   ├── views/                  # Vistas principales
│   │   └── FacturasView.vue
│   ├── components/             # Componentes reutilizables
│   │   ├── FacturaFilters.vue
│   │   ├── FacturaTable.vue
│   │   ├── FacturaModal.vue
│   │   └── LineasList.vue
│   ├── services/               # Servicios API
│   │   └── api.ts
│   ├── types/                  # Tipos TypeScript
│   │   └── factura.ts
│   └── assets/                 # Estilos y recursos
│       └── main.css
├── public/                     # Archivos públicos
└── package.json
```

## Scripts Disponibles

- `npm run dev` - Inicia servidor de desarrollo
- `npm run build` - Compila para producción
- `npm run preview` - Previsualiza el build de producción
- `npm run lint` - Ejecuta el linter

## Características

✅ Listado de pre-facturas con tabla
✅ Filtros configurables (anulada, confirmado, remisión facturada)
✅ Modal con detalles completos de pre-factura
✅ Visualización de líneas de pre-factura agrupadas por tipo
✅ Estadísticas básicas
✅ Integración completa con API backend
✅ TypeScript para type safety
✅ Vue Router para navegación
✅ Pinia para gestión de estado

## Próximos Pasos

- ✅ Paginación implementada
- Agregar búsqueda y ordenamiento
- Mejorar estilos con framework CSS (Tailwind, Vuetify, etc.)
- Agregar gráficos y estadísticas avanzadas
- Implementar exportación a Excel/PDF

