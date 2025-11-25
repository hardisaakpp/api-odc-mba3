# MBA3 Frontend

Frontend Vue.js para la gestión de pre-facturas MBA3.

## Setup

```bash
# Instalar dependencias
npm install

# Servidor de desarrollo
npm run dev

# Build para producción
npm run build

# Preview del build
npm run preview
```

## Configuración

Crea un archivo `.env.local` en la raíz del frontend:

```env
VITE_API_URL=http://localhost:8000
```

## Estructura

```
frontend/
├── src/
│   ├── main.ts              # Punto de entrada
│   ├── App.vue              # Componente raíz
│   ├── router/              # Rutas
│   ├── stores/              # Estado (Pinia)
│   ├── views/               # Vistas principales
│   ├── components/          # Componentes reutilizables
│   ├── services/            # Servicios API
│   └── types/               # Tipos TypeScript
```

