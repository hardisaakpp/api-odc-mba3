# Frontend Vue.js

Frontend moderno desarrollado con Vue.js 3, TypeScript, Pinia y Vue Router.

## 🚀 Inicio Rápido

```bash
# Instalar dependencias
npm install

# Configurar API (opcional)
echo "VITE_API_URL=http://localhost:8000" > .env.local

# Iniciar desarrollo
npm run dev
```

Frontend disponible en: http://localhost:5173

## 📁 Estructura

```
frontend/
├── src/
│   ├── views/          # Vistas principales
│   │   ├── FacturasView.vue
│   │   └── ConsultaView.vue
│   ├── components/     # Componentes reutilizables
│   │   ├── FacturaTable.vue
│   │   ├── FacturaFilters.vue
│   │   ├── FacturaModal.vue
│   │   └── Pagination.vue
│   ├── stores/         # Estado global (Pinia)
│   │   ├── facturas.ts
│   │   └── theme.ts
│   ├── services/       # Servicios API
│   │   └── api.ts
│   └── types/         # Tipos TypeScript
│       └── factura.ts
```

## 🎯 Funcionalidades

- ✅ Vista de facturas con filtros configurables
- ✅ Consulta SQL dinámica
- ✅ Tabla interactiva con paginación
- ✅ Modal de detalles completos
- ✅ Tema claro/oscuro
- ✅ Visualización de líneas agrupadas

## 📝 Scripts

- `npm run dev` - Servidor de desarrollo
- `npm run build` - Compilar para producción
- `npm run preview` - Previsualizar build
- `npm run lint` - Ejecutar linter

## ⚙️ Configuración

Crear `.env.local`:

```env
VITE_API_URL=http://localhost:8000
```

## 🔗 Integración con Backend

El frontend consume:
- **GET `/facturas`** - Obtener facturas con filtros
- **GET `/consulta?query=...`** - Ejecutar consulta SQL

Ver [docs/ENDPOINTS.md](../docs/ENDPOINTS.md) para más detalles.
