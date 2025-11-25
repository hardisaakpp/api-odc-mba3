# Instrucciones para usar el Frontend Vue

## ✅ Instalación completada

Las dependencias ya están instaladas. El proyecto está listo para usarse.

## 🚀 Iniciar el desarrollo

### 1. Configurar la URL de la API (opcional)

Si tu backend no está en `http://localhost:8000`, crea el archivo `.env.local` en la raíz del frontend:

```env
VITE_API_URL=http://localhost:8000
```

**Nota:** Si no creas este archivo, el frontend usará `http://localhost:8000` por defecto.

### 2. Iniciar el servidor de desarrollo del frontend

```bash
cd frontend
npm run dev
```

El frontend estará disponible en: **http://localhost:5173**

### 3. Asegúrate de que el backend esté corriendo

En otra terminal:

```bash
cd src
python api_server.py
```

El backend debe estar en: **http://localhost:8000**

## 📋 Verificar que todo funcione

1. Abre tu navegador en: `http://localhost:5173`
2. Deberías ver la página de "Consulta de Pre-Facturas"
3. Los filtros están preconfigurados con valores por defecto
4. Haz clic en "Aplicar Filtros" para cargar las pre-facturas
5. Haz clic en "Ver Detalles" en cualquier pre-factura para ver el modal con información completa

## 🎨 Características incluidas

✅ **Listado de pre-facturas** - Tabla con información básica  
✅ **Filtros configurables** - Anulada, Confirmado, Remisión Facturada  
✅ **Modal de detalles** - Información completa de cada pre-factura  
✅ **Líneas agrupadas** - Visualización de líneas por tipo (GrabarLineasProd, CtrlEliminados1-8, etc.)  
✅ **Estadísticas** - Total de pre-facturas y estado de guardado en DB  
✅ **Responsive** - Diseño adaptable a diferentes tamaños de pantalla  

## 🔧 Scripts disponibles

- `npm run dev` - Inicia servidor de desarrollo (puerto 5173)
- `npm run build` - Compila para producción
- `npm run preview` - Previsualiza el build de producción
- `npm run lint` - Ejecuta el linter

## 📁 Estructura del código

- `src/views/FacturasView.vue` - Vista principal
- `src/components/FacturaTable.vue` - Tabla de facturas
- `src/components/FacturaFilters.vue` - Componente de filtros
- `src/components/FacturaModal.vue` - Modal de detalles
- `src/components/LineasList.vue` - Lista de líneas agrupadas
- `src/stores/facturas.ts` - Estado global (Pinia)
- `src/services/api.ts` - Cliente API para comunicarse con el backend

## 🐛 Solución de problemas

### Error: "Cannot GET /"
- Asegúrate de que el servidor de desarrollo esté corriendo con `npm run dev`

### Error: "Failed to fetch"
- Verifica que el backend esté corriendo en `http://localhost:8000`
- Revisa la consola del navegador para ver el error específico

### Las pre-facturas no se cargan
- Verifica que el backend responda en `http://localhost:8000/facturas`
- Revisa la pestaña Network en las herramientas de desarrollador

## 📝 Próximos pasos (opcionales)

- ✅ Paginación implementada
- Implementar búsqueda y ordenamiento
- Agregar un framework CSS (Tailwind, Vuetify, etc.)
- Implementar gráficos y estadísticas avanzadas
- Agregar exportación a Excel/PDF

