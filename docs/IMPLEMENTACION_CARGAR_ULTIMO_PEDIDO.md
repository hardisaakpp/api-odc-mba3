# Implementación: Cargar Último Pedido al Entrar a "Cargar Plantillas"

## 🎯 Objetivo

Cuando el usuario entra a la pantalla de "Cargar Plantillas" (ya sea desde el botón o navegando), debe mostrarse automáticamente el último pedido creado, independientemente de si fue:
- ✅ Creado manualmente (`POST /api/pedidos`)
- ✅ Cargado desde Excel (`POST /api/plantillas/upload`)

## 📋 Comportamiento Esperado

### Escenario 1: Usuario sube Excel
1. Usuario sube Excel → Se guarda en BD → Se muestra inmediatamente ✅
2. Usuario sale de la pantalla
3. Usuario regresa haciendo clic en "Cargar Plantillas"
4. **Resultado esperado:** Se muestra el último Excel subido ✅ (Ya funciona)

### Escenario 2: Usuario crea pedido manual
1. Usuario crea pedido manual → Se guarda en BD → Se muestra inmediatamente ✅
2. Usuario sale de la pantalla
3. Usuario regresa haciendo clic en "Cargar Plantillas"
4. **Resultado esperado:** Se muestra el último pedido manual ❌ (NO funciona actualmente)

### Escenario 3: Usuario crea pedido manual, luego sube Excel
1. Usuario crea pedido manual → Se guarda en BD
2. Usuario sube Excel → Se guarda en BD
3. Usuario sale de la pantalla
4. Usuario regresa haciendo clic en "Cargar Plantillas"
5. **Resultado esperado:** Se muestra el Excel (más reciente) ✅

### Escenario 4: Usuario sube Excel, luego crea pedido manual
1. Usuario sube Excel → Se guarda en BD
2. Usuario crea pedido manual → Se guarda en BD
3. Usuario sale de la pantalla
4. Usuario regresa haciendo clic en "Cargar Plantillas"
5. **Resultado esperado:** Se muestra el pedido manual (más reciente) ❌ (NO funciona actualmente)

---

## 🔌 Endpoint del Backend

### `GET /api/plantillas/ultimo`

**Características:**
- ✅ Funciona para pedidos manuales Y Excel
- ✅ Filtrado por usuario (cada usuario ve solo sus pedidos)
- ✅ Ordena por `creado_en DESC` (más reciente primero)
- ✅ Devuelve el mismo formato que `GET /api/plantillas/{identificador}`

**Respuesta exitosa (200):**
Formato directo, igual que `GET /api/plantillas/{identificador}`:

```json
{
  "cabecera": {
    "pedido_id": "...",
    "numero_pedido": "P-12.56 - 12 - 2025",
    "fecha_pedido": "2025-12-25",
    "archivo_nombre": "CREACION_MANUAL",  // o "nombre_archivo.xlsx"
    "creado_por": "user@example.com",
    "creado_en": "2025-12-25T10:30:00",
    ...
  },
  "detalles": [...]
}
```

**Respuesta sin pedidos (404):**
```json
{
  "detail": "No hay pedidos cargados para este usuario"
}
```

**Nota importante:** La respuesta es **directa** (`{cabecera, detalles}`), NO está envuelta. Esto permite usar el mismo código del frontend que procesa `GET /api/plantillas/{identificador}`.

---

## 💻 Implementación en Frontend

### Paso 1: Detectar cuando el usuario entra a "Cargar Plantillas"

El componente debe detectar cuando se monta o cuando el usuario navega a esta pantalla.

**Ejemplo con Vue 3 (Composition API):**
```typescript
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const pedidoCargado = ref(false)

onMounted(async () => {
  // Solo cargar si no hay datos ya cargados
  if (!pedidoCargado.value) {
    await cargarUltimoPedido()
  }
})

// También detectar cuando se navega a esta ruta
watch(() => route.path, async (newPath) => {
  if (newPath === '/mba3-consultas/cargar-plantillas' && !pedidoCargado.value) {
    await cargarUltimoPedido()
  }
})
```

### Paso 2: Función para cargar el último pedido

```typescript
async function cargarUltimoPedido() {
  try {
    const response = await api.get('/api/plantillas/ultimo')
    
    // La respuesta es directa: {cabecera: {...}, detalles: [...]}
    // Mismo formato que GET /api/plantillas/{identificador}
    if (response.data && response.data.cabecera) {
      const pedido = response.data
      
      // Prellenar formulario con los datos del último pedido
      prellenarFormulario(pedido)
      
      // Marcar como cargado para evitar recargas innecesarias
      pedidoCargado.value = true
      
      // Mostrar notificación informativa
      mostrarNotificacion(
        `Se cargó el último pedido: ${pedido.cabecera.numero_pedido}`,
        'info'
      )
    } else {
      // Respuesta inesperada
      console.warn('Respuesta inesperada del endpoint /api/plantillas/ultimo:', response.data)
      pedidoCargado.value = true
    }
  } catch (error) {
    // Si es 404, no hay pedidos (es normal)
    if (error.response && error.response.status === 404) {
      mostrarNotificacion(
        'No hay pedidos cargados. Puedes crear uno nuevo o subir un Excel.',
        'info'
      )
    } else {
      console.error('Error al cargar último pedido:', error)
    }
    // No bloquear la interfaz si falla
    pedidoCargado.value = true
  }
}
```

### Paso 3: Función para prellenar el formulario

```typescript
function prellenarFormulario(pedido: any) {
  const cabecera = pedido.cabecera
  const detalles = pedido.detalles
  
  // Prellenar campos de cabecera (NO incluir numero_pedido porque debe ser único)
  formData.value.fecha_pedido = cabecera.fecha_pedido
  formData.value.fecha_entrega = cabecera.fecha_entrega
  formData.value.forma_pago = cabecera.forma_pago
  formData.value.proveedor_nombre = cabecera.proveedor_nombre
  formData.value.comprador_nombre = cabecera.comprador_nombre
  formData.value.comprador_codigo = cabecera.comprador_codigo
  formData.value.origen_traslado = cabecera.origen_traslado
  formData.value.serie = cabecera.serie
  
  // Prellenar artículos
  articulos.value = detalles.map((detalle: any) => ({
    codigo_interno: detalle.codigo_interno,
    descripcion_sap: detalle.descripcion_sap,
    marca: detalle.marca,
    codigo_barras: detalle.codigo_barras,
    pack: detalle.pack,
    costo_doc_sin_iva: detalle.costo_doc_sin_iva,
    descuento_1: detalle.descuento_1,
    pvp: detalle.pvp,
    subtotal: detalle.subtotal,
    total: detalle.total,
    distribuciones: detalle.tiendas.map((tienda: any) => ({
      tienda_codigo: tienda.codigo,
      tienda_nombre: tienda.nombre,
      cantidad: tienda.cantidad
    }))
  }))
}
```

### Paso 4: Resetear flag cuando se crea/actualiza un pedido

Cuando el usuario crea un nuevo pedido o sube un Excel, se debe resetear el flag para que al regresar se cargue el nuevo último pedido:

```typescript
async function crearPedidoManual() {
  try {
    const response = await api.post('/api/pedidos', requestBody)
    
    if (response.data.status === 'success') {
      // Mostrar mensaje de éxito
      mostrarNotificacion('Pedido creado exitosamente', 'success')
      
      // Resetear flag para que al regresar se cargue este nuevo pedido
      pedidoCargado.value = false
      
      // Opcional: Redirigir o actualizar la vista
      // ...
    }
  } catch (error) {
    // Manejar error
  }
}

async function subirExcel(file: File) {
  try {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await api.post('/api/plantillas/upload', formData)
    
    if (response.data.status === 'success') {
      // Mostrar mensaje de éxito
      mostrarNotificacion('Excel cargado exitosamente', 'success')
      
      // Resetear flag para que al regresar se cargue este nuevo pedido
      pedidoCargado.value = false
      
      // Opcional: Actualizar la vista con el nuevo pedido
      // ...
    }
  } catch (error) {
    // Manejar error
  }
}
```

---

## 🔄 Flujo Completo

```
1. Usuario entra a "Cargar Plantillas"
   ↓
2. Frontend llama a GET /api/plantillas/ultimo
   ↓
3. Backend devuelve último pedido (manual o Excel)
   ↓
4. Frontend prellena formulario con los datos
   ↓
5. Usuario puede:
   - Modificar y crear nuevo pedido
   - Subir nuevo Excel
   - Salir de la pantalla
   ↓
6. Si usuario sale y regresa:
   - Frontend vuelve a llamar a GET /api/plantillas/ultimo
   - Se muestra el pedido más reciente (puede ser diferente al anterior)
```

---

## ⚠️ Consideraciones Importantes

### 1. No precargar `numero_pedido`
El campo `numero_pedido` debe ser único, por lo que NO se debe precargar del último pedido. El usuario debe ingresar uno nuevo.

### 2. Prioridad de datos
Si el usuario tiene datos guardados en localStorage o en el estado del componente, se debe respetar esa prioridad:
```typescript
onMounted(async () => {
  // Primero: Verificar si hay datos guardados localmente
  const datosGuardados = localStorage.getItem('pedido_draft')
  
  if (datosGuardados) {
    // Usar datos guardados
    cargarDesdeLocalStorage(datosGuardados)
  } else {
    // Segundo: Cargar último pedido del backend
    await cargarUltimoPedido()
  }
})
```

### 3. Evitar recargas innecesarias
Usar un flag para evitar llamar al endpoint múltiples veces:
```typescript
const pedidoCargado = ref(false)

// Solo cargar si no se ha cargado ya
if (!pedidoCargado.value) {
  await cargarUltimoPedido()
}
```

### 4. Manejo de errores
Si el endpoint falla, no debe bloquear la interfaz. El usuario debe poder seguir trabajando:
```typescript
try {
  await cargarUltimoPedido()
} catch (error) {
  console.error('Error al cargar último pedido:', error)
  // No bloquear, permitir que el usuario continúe
  pedidoCargado.value = true
}
```

---

## ✅ Checklist de Implementación

### Frontend
- [ ] Detectar cuando el usuario entra a "Cargar Plantillas"
- [ ] Llamar a `GET /api/plantillas/ultimo` al montar el componente
- [ ] Prellenar formulario con los datos del último pedido
- [ ] NO precargar `numero_pedido` (debe ser único)
- [ ] Mostrar notificación informativa cuando se carga el último pedido
- [ ] Resetear flag cuando se crea un nuevo pedido o se sube un Excel
- [ ] Manejar caso cuando no hay pedidos (mostrar mensaje informativo)
- [ ] Manejar errores sin bloquear la interfaz

### Pruebas
- [ ] Crear pedido manual → Salir → Regresar → Debe mostrar el pedido manual
- [ ] Subir Excel → Salir → Regresar → Debe mostrar el Excel
- [ ] Crear manual → Subir Excel → Salir → Regresar → Debe mostrar el Excel (más reciente)
- [ ] Subir Excel → Crear manual → Salir → Regresar → Debe mostrar el manual (más reciente)
- [ ] Usuario sin pedidos → Debe mostrar mensaje informativo
- [ ] Verificar que `numero_pedido` NO se precarga

---

## 📚 Referencias

- **Endpoint:** `GET /api/plantillas/ultimo`
- **Documentación:** `docs/archivo/ENDPOINT_ULTIMO_PEDIDO.md`
- **Modelo de respuesta:** Mismo formato que `GET /api/plantillas/{identificador}`

---

**Última actualización:** 25 de Diciembre de 2025
