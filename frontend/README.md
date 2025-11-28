# MBA3 Consultas - Frontend

Frontend moderno desarrollado con Vue.js 3 + TypeScript para la gestión de facturas y órdenes de compra desde MBA3.

## 🚀 Inicio Rápido

### Instalación

```bash
npm install
```

### Desarrollo

```bash
npm run dev
```

La aplicación estará disponible en `http://localhost:5173`

### Build para Producción

```bash
npm run build
```

### Preview de Producción

```bash
npm run preview
```

## 📁 Estructura del Proyecto

```
frontend/
├── src/
│   ├── assets/          # Estilos globales
│   ├── components/      # Componentes reutilizables
│   ├── views/           # Vistas principales
│   ├── services/        # Servicios API
│   ├── stores/          # Stores de Pinia
│   ├── types/           # Tipos TypeScript
│   ├── router/          # Configuración de rutas
│   ├── App.vue          # Componente raíz
│   └── main.ts          # Punto de entrada
```

## 🎨 Características

- ✅ Vue.js 3 con Composition API
- ✅ TypeScript para type safety
- ✅ Pinia para gestión de estado
- ✅ Vue Router para navegación
- ✅ Diseño moderno y responsive
- ✅ Integración completa con API FastAPI

## 🔌 Configuración

Crea un archivo `.env` en la raíz del proyecto:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## 📚 Tecnologías

- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- Axios

