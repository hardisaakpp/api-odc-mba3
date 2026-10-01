# Manual de Usuario — Sistema SCNexus

## Módulo Gestión ODC SAP — SCNexus

**MABEL TRADING S. A.**
**DEPARTAMENTO DE TECNOLOGÍA**
**ÁREA DE DESARROLLO**

Autor: Carlos Ortiz
Fecha: 18/02/2026 — **Actualizado:** 01/10/2026 (segunda fase del módulo y mejoras de septiembre de 2026)

---

## 1. Introducción

Este manual describe el uso del módulo **Gestión ODC SAP** dentro del Sistema SCNexus. Este módulo permite gestionar pedidos, cargar plantillas Excel, distribuir cantidades por tienda o bodega, generar órdenes de compra (ODC), generar y confirmar solicitudes de traslado (ST) hacia tiendas, y enviarlo todo a SAP.

Esta versión del manual cubre la **segunda fase** del módulo: incorpora el perfil de **Producción El Rayo**, el flujo de **pedidos parciales / Producción Pospuesta**, nuevas validaciones de carga de Excel, el **Análisis de Margen**, la **exportación de traslados a Excel** y la **reconciliación automática diaria** de traslados con SAP.

### 1.1 Tipos de usuario

Existen **tres perfiles** que interactúan con el módulo, más un permiso transversal y un rol administrativo:

| Perfil | Permiso | Descripción |
|---|---|---|
| **EL RAYO** | `odcsap.view` | Gestiona los pedidos que envía MABEL TRADING: revisa, edita costos/comentarios, confirma la respuesta al proveedor, revisa la redistribución (solo lectura) y consulta las ODC enviadas a SAP. |
| **Producción El Rayo** | `produccion-elrayo.view` | Sub-perfil de EL RAYO pensado para personal de planta/producción. Solo ve pedidos mientras están en **Nuevo Pedido** o **Gestionar Pedido**; su única función es confirmar que un pedido puede producirse (botón **Confirmar Producción**). No ve costos, precios ni márgenes. Ver [sección 11](#11-producción-el-rayo-perfil-nuevo). |
| **MABEL TRADING** | `mabel.view` | Flujo completo: cargar plantillas Excel, redistribuir productos por tienda, generar ODC y solicitudes de traslado, procesamiento SAP, homologaciones de SKU, análisis de margen, exportación de traslados, etc. |

Adicionalmente:

- **`funcionalidades-admin.view`** no es un perfil, es un permiso extra que se suma a cualquiera de los tres anteriores. Habilita el panel **"Información Pedidos y ODC"** en el Dashboard (Órdenes de Compra, Procesamiento SAP, Homologaciones, Listado Pedidos Originales) y la **Vista Compacta** dentro de Redistribución.
- El **rol Admin** no pertenece al flujo de pedidos: administra los **Destinatarios de Notificaciones** y el **Catálogo de Correos** del sistema (ver [sección 17](#17-administración-de-notificaciones-rol-admin)).

### 1.2 Novedades desde la versión del 28/08/2026

- **Contadores "requiere acción":** el Dashboard muestra un círculo rojo con el total real de pendientes en cada botón, y los listados tienen un botón naranja "N pedidos requieren acción". Antes solo contaban los pedidos de la página cargada. Ver [sección 3.3](#33-qué-significa-requiere-acción).
- **Estados retirados:** nueve estados del flujo antiguo (por ejemplo Confirmado Proveedor, Redistribuido y Error Datos Maestros) ya no se usan, y *Pendiente Confirmación* es el nombre antiguo de **Borrador**. Ver [sección 4.1](#41-estados-retirados-y-nombres-antiguos).
- **Confirmar (EL RAYO)** exige una **fecha de entrega real**; mientras falte aparece el aviso "Seleccione una fecha de entrega para confirmar". Ver [sección 9.2](#92-acciones-en-el-detalle-del-pedido).
- **Un botón "Número OC SAP" por cada ODC** del pedido, también en Cargar Plantilla y Redistribución. Ver [sección 6.3](#63-pedidos-que-generan-más-de-una-orden-de-compra).
- **Redistribución:** en pedidos hijo se puede **agregar una tienda**, y su resaltado se conserva al recargar. Ver [sección 6.2](#62-pasos).
- **ODC a SAP:** botón "con reintento pendiente" y selector de tamaño de página. Ver [sección 7](#7-odc-a-sap-ambos-perfiles).
- **Destinatarios de Notificaciones** rediseñado: buscador, tarjetas por persona y catálogo de correos que se arrastra. Ver [sección 17](#17-administración-de-notificaciones-rol-admin).

## 2. Acceso al módulo

1. Inicie sesión en SCNexus con su usuario y contraseña de Active Directory.
2. En el menú lateral (sidebar), pulse **Gestión ODC SAP**.
3. Se mostrará el **Dashboard** del módulo.

## 3. Dashboard de Gestión ODC SAP

El dashboard es la pantalla principal con botones de acceso rápido a cada funcionalidad. Los botones que ve dependen de su(s) permiso(s).

### 3.1 Botones principales (visibles según permiso)

| Botón | Permiso | Descripción |
|---|---|---|
| **Cargar Plantilla** | `mabel.view` | MABEL TRADING — cargar plantillas Excel y ver/editar pedidos. |
| **Producción El Rayo** | `produccion-elrayo.view` | Listado restringido de pedidos (solo Nuevo Pedido / Gestionar Pedido) para confirmar producción. |
| **Listado de Pedidos** | `odcsap.view` | EL RAYO — ver todos los pedidos, editar, confirmar. |
| **Redistribución** | `mabel.view` | MABEL TRADING — distribuir cantidades por tienda/bodega, generar ODC. |
| **Revisar Redistribución** | `odcsap.view` | EL RAYO — ver la distribución por tienda (solo lectura). |
| **ODC a SAP** | `mabel.view` u `odcsap.view` | Visualizar órdenes de compra generadas y enviarlas/consultarlas en SAP. |

Cuando hay trabajo pendiente para usted, el botón muestra en su esquina superior derecha un **círculo rojo con el número** de pendientes (se muestra "99+" si son más de 99; con cero no aparece). Los botones con círculo son **Cargar Plantilla**, **Producción El Rayo**, **Listado de Pedidos**, **Redistribución** y **ODC a SAP**. El número es el total real, no solo lo que se ve en la primera página, y se conserva al volver al Dashboard.

### 3.2 Panel "Información Pedidos y ODC" (requiere `funcionalidades-admin.view`)

Al hacer clic se expande un grupo de opciones adicionales, disponible para cualquier perfil que tenga este permiso extra:

| Opción | Descripción |
|---|---|
| **Órdenes de Compra** | Historial completo de ODC generadas (pendientes, enviadas, con error). |
| **Listado Pedidos Originales** | Abre un modal con los archivos Excel originales cargados (storage). |
| **Procesamiento SAP** | Buscar un pedido y ver el detalle de su procesamiento en SAP. |
| **Homologaciones** | SKUs no homologados entre MBA3 y SAP. |
| **Destinatarios de Notificaciones** | Solo visible con rol **Admin**. Administración de correos de notificación. |

> **Nota:** las tarjetas **"ODC con Errores"** y **"Reporte de Diferencias"** que aparecían en versiones anteriores del panel están **ocultas en producción** (solo visibles en ambiente de desarrollo). Si su usuario no las ve, es el comportamiento esperado.

> **Nota:** la pantalla **"Crear Pedido Manual"** existe en el sistema pero actualmente **no tiene botón de acceso** en ninguna pantalla del módulo; no está disponible para uso normal.

### 3.3 ¿Qué significa «requiere acción»?

Cada pantalla cuenta algo distinto, según lo que le toca hacer a su perfil:

| Pantalla | Perfil | Cuenta los pedidos en estado… | Qué le toca hacer |
|---|---|---|---|
| Cargar Plantilla | MABEL TRADING | **Producción Pospuesta** y **Despachar y Facturar** | Aceptar o Rechazar la diferencia; Finalizar el pedido |
| Listado de Pedidos | EL RAYO | **Confirmado por Producción** y **Confirmado y Enviado** | Confirmar o Cancelar; Despachar y Facturar |
| Redistribución | MABEL TRADING | **Confirmado por El Rayo** y **Listo para Redistribución** | Redistribuir por tienda y enviar la ODC a SAP |
| Producción El Rayo | Producción El Rayo | **Nuevo Pedido** | Revisar y Confirmar Producción |
| ODC a SAP | ambos | (cuenta **órdenes de compra**, no pedidos) con **Reintentar** o **Reintentar ST** disponible | Reintentar el envío |

En los listados, el botón naranja **"N pedidos requieren acción"** (en el de EL RAYO dice "requieren tu acción") filtra solo esos pedidos y muestra el aviso "Mostrando solo pedidos que requieren acción". Púlselo de nuevo para volver a ver todos. Si no hay ninguno, el botón no aparece.

## 4. Estados del pedido (referencia)

Estados vigentes, agrupados por etapa del flujo (el orden de la tabla es el del flujo normal):

**Flujo normal**

| Estado | Significado |
|---|---|
| Borrador | Pedido en edición por MABEL TRADING, aún no enviado. Es el estado inicial al subir un Excel. |
| Nuevo Pedido | MABEL TRADING envió el pedido al proveedor (EL RAYO es notificado). |
| Gestionar Pedido | El pedido está en gestión por EL RAYO / Producción El Rayo, que pueden revisarlo y editarlo. Pasa a este estado al abrir su detalle desde el listado. |
| Confirmado por Producción | Producción El Rayo confirmó que el pedido puede producirse; ahora le toca a Administración El Rayo. |
| Confirmado por El Rayo | Administración El Rayo confirmó la respuesta; el pedido pasa a redistribución (MABEL TRADING). |
| Confirmado redistribución | MABEL TRADING confirmó la redistribución por tienda; sigue el envío de la ODC a SAP. |
| Confirmado y Enviado | La ODC y sus Solicitudes de Traslado (ST) se generaron y enviaron a SAP con éxito. |
| Despachar y Facturar | Listo para despacho; se marca manualmente desde Confirmado y Enviado. |
| Finalizado | Estado final del flujo. Solo se llega desde Despachar y Facturar. |

**Pedidos parciales (Producción Pospuesta)**

| Estado | Significado |
|---|---|
| Producción Pospuesta | Se generó un pedido "hijo" con la diferencia entre lo solicitado y lo que EL RAYO confirmó que puede entregar. Ver [sección 5.4](#54-pedidos-parciales-producción-pospuesta). |
| Listo para Redistribución | MABEL TRADING aceptó la Producción Pospuesta; la diferencia entra directo a la cola de redistribución. |
| Rechazado | MABEL TRADING rechazó la Producción Pospuesta. Estado final. |

**Excepciones en el envío a SAP**

| Estado | Significado |
|---|---|
| Error envío SAP (reintentar) | El envío de la ODC a SAP falló (típicamente por conexión u otra falla transitoria); permite reintentar. |
| Pendiente Logística | La ODC se envió bien, pero alguna Solicitud de Traslado quedó pendiente o con error. |

**Cancelaciones**

| Estado | Significado |
|---|---|
| Cancelado por El Rayo | Administración El Rayo canceló el pedido. Solo es posible desde Confirmado por Producción y debe hacerse únicamente a solicitud expresa de MABEL TRADING. |
| Cancelado | MABEL TRADING canceló el pedido desde Redistribución. Es definitivo (irreversible). |

### 4.1 Estados retirados y nombres antiguos

**Estados retirados en septiembre de 2026.** Ya no forman parte del flujo ni aparecen en los filtros, y ningún pedido real los tenía:

- *Respuesta Cargada* (en algunos ambientes se veía como "En revisión")
- *Confirmado Proveedor*
- *Rechazado Proveedor*
- *En Ajuste Mabel*
- *Redistribuido*
- *Procesado SAP*
- *Error Datos Maestros*
- *En Proceso*
- *Completado*

**Nombre antiguo.** *Pendiente Confirmación* (o "Pendiente Confirmación Proveedor") **no es un estado retirado: es el nombre antiguo de Borrador**, el estado inicial de todo pedido nuevo. Si en algún documento, correo o dato antiguo ve "Pendiente Confirmación", corresponde a Borrador.

**Respuesta del proveedor por Excel.** El flujo antiguo en que el proveedor respondía cargando un Excel fue reemplazado por la Redistribución; por eso esos estados intermedios dejaron de usarse.

## 5. Cargar Plantilla (MABEL TRADING)

**Ruta:** Dashboard → Cargar Plantilla

### 5.1 Descripción

Permite seleccionar un pedido para cargar una plantilla Excel, editarla o continuar el flujo. Incluye pedidos en estado Borrador y con plantilla ya cargada.

### 5.2 Pasos para cargar una plantilla

1. En el listado, haga clic en el botón verde "Cargar Plantillas Excel", aparecerá la ventana para buscar pedidos, seleccione una plantilla Excel.
2. Espere a que termine el proceso (barra de progreso con 3 fases: Subir → Validar → Guardar).
3. Una vez cargada la plantilla Excel, podrá:
   - Visualizar la cabecera y los detalles del pedido cargado, incluyendo el **Origen Traslado** (bodega/CD detectado automáticamente a partir de las tiendas del pedido).
   - Modificar fecha de entrega o seleccionar la opción "INMEDIATO" (si selecciona esta última opción ya no podrá modificar la fecha). Mientras se guarda una fecha (de pedido o de entrega) aparece un indicador de progreso y el campo se bloquea hasta terminar. Para que EL RAYO pueda **Confirmar** el pedido, la fecha de entrega debe ser una fecha real: con "INMEDIATO" o vacía, EL RAYO verá "Seleccione una fecha de entrega para confirmar".
   - Enviar el pedido al proveedor.
   - Descartar el pedido (lo elimina completamente del sistema; el botón se oculta si el pedido tiene una Producción Pospuesta pendiente de Aceptar/Rechazar).

> **Nota:** una vez que el pedido haya sido enviado al proveedor, ya no podrá ser descartado desde esta interfaz. Mientras el proveedor se encuentre gestionándolo, se le podrá solicitar su cancelación; sin embargo, el pedido no se eliminará del sistema, sino que su estado cambiará a **"Cancelado por EL RAYO"**.

### 5.3 Validaciones al cargar el Excel

Antes de guardar el pedido, el sistema valida la plantilla y **bloquea la carga** (con el detalle exacto de la fila/producto afectado) si encuentra alguna de estas inconsistencias:

1. **TOTAL/SUBTOTAL no coincide con las cantidades reales**: si la fórmula de TOTAL o SUBTOTAL de un producto no coincide con la suma real de las cantidades por tienda/bodega parseadas del Excel. El mensaje indica la fila y el producto afectado; corrija la fórmula en el Excel y vuelva a subirlo.
2. **Costo Unitario inconsistente**: la columna "Costo Unitario" debe coincidir con el resultado de dividir "Costo sin IVA" entre la unidad de conversión del Pack. Si no coincide, la carga se bloquea antes de validar contra SAP.
3. **Pack o PVP no coinciden con SAP**: si el Pack o el PVP de un producto en el Excel no coinciden con lo registrado en SAP, la carga se bloquea y el mensaje **sugiere el valor correcto** a usar (ej. "Use 'Y'").

> El **código de barras** no se valida ni bloquea la carga: el sistema lo sincroniza automáticamente desde SAP (fuente de verdad), aunque difiera del Excel.

### 5.4 Pedidos parciales (Producción Pospuesta)

Si al confirmar EL RAYO entrega una cantidad **menor** a la solicitada originalmente para algún producto, el sistema pregunta cómo proceder:

- **"Diferencia no será entregada"**: continúa el flujo normal solo con lo confirmado.
- **"Confirmar pedido, generar nuevo pedido con la diferencia"**: crea un pedido "hijo" (numerado `<pedido>.NN`) en estado **Producción Pospuesta**, con su propia fecha de entrega.

Ese pedido hijo aparece en el listado de Cargar Plantilla con dos botones exclusivos de MABEL TRADING:

- **Aceptar**: envía la diferencia directo a la cola de **Listo para Redistribución** (sin volver a pasar por confirmación del proveedor).
- **Rechazar**: cierra el pedido hijo de forma definitiva (estado **Rechazado**).

### 5.5 Análisis de Margen

En el detalle del pedido (Cargar Plantilla), la grilla de productos incluye dos columnas adicionales:

- **Costo**: valor informativo tomado de la columna "Costo" del Excel original.
- **Margen**: porcentaje de margen de rentabilidad, calculado por el sistema a partir del **Costo Unitario** (Costo sin IVA ÷ unidad de conversión del Pack) y el **PVP**.

El botón **"Descargar Análisis de Margen"** exporta un Excel (`analisis_margen_{pedido}_{fecha}.xlsx`) con Código, Descripción, Código de Barras, Pack, PVP, Costo, Costo Unitario, Margen de Rentabilidad y Total.

### 5.6 Filtros de Búsqueda

Permite buscar un pedido por medio de filtros:

- **Botón "N pedidos requieren acción"**: filtra los pedidos en estado **Producción Pospuesta** (para Aceptar/Rechazar) o **Despachar y Facturar** (para Finalizar). Ver [sección 3.3](#33-qué-significa-requiere-acción).
- **Estado / Fecha Desde / Fecha Hasta / Proveedor / Número de Pedido / Creado Por.** La lista de Estados incluye únicamente los estados en los que existen pedidos realmente.

### 5.7 Uso de filtros

1. Haga clic en **Filtros de Búsqueda** para expandir.
2. Use **Actualizar** para refrescar los resultados, o **Auto-actualizar** para que la lista se recargue periódicamente.
3. El tamaño de página que seleccione en la paginación **se recuerda** la próxima vez que visite este listado.

### 5.8 Tabla Pedidos (MABEL TRADING)

Muestra todos los pedidos previamente cargados. **Para ver detalle**: clic en el pedido para abrir el detalle completo.

Si un pedido se encuentra en estado **"Gestionar Pedido"**, significa que el proveedor (EL RAYO, o Producción El Rayo) está revisándolo o realizando alguna modificación. En este estado, el usuario puede visualizar los comentarios o cambios efectuados y, si corresponde, solicitar la cancelación del pedido.

> Las celdas de Costo/Total/Comentario que fueron modificadas se resaltan en **color** para identificar quién hizo el último cambio: **púrpura** si fue EL RAYO, **naranja** si fue Producción El Rayo. El color depende de quién editó la celda, no de quién la esté viendo.

## 6. Redistribución (MABEL TRADING)

**Ruta:** Dashboard → Redistribución

### 6.1 Descripción

Distribuir las cantidades de productos por tienda a partir de la respuesta del proveedor. El pedido debe estar en estado **Confirmado por El Rayo**.

### 6.2 Pasos

1. En la pantalla de redistribución verá la cabecera del pedido y la tabla de productos con columnas por tienda.
2. Hay 2 vistas disponibles (la **Vista Compacta** solo aparece si su usuario tiene el permiso `funcionalidades-admin.view`):
   - **Vista Matriz (por defecto)**: editar cantidades por tienda manualmente. La barra superior indica los totales de la distribución; la columna DIFERENCIA y los mensajes en rojo debajo de la tabla ayudan a completar la distribución.
   - **Vista Compacta**: **Distribuir proporcionalmente** (reparte automáticamente según la plantilla original) y **Resetear distribución** (vuelve al estado inicial).
3. Haga clic en **Guardar Borrador** para guardar los cambios sin enviar aún.
4. Al colocar el mouse sobre **Enviar ODC a SAP** aparece un tooltip que explica que este botón generará la Orden de Compra en SAP, creará las Solicitudes de Traslado por tienda, realizará validaciones y conversiones de unidades, y notificará al personal de El Rayo.
5. **Cancelar Pedido**: cambia el estado de Confirmado por el Rayo a Cancelado. Este cambio es **irreversible**.
6. **Agregar tienda** (solo en pedidos hijo, es decir, la diferencia de una Producción Pospuesta): el botón **"Agregar tienda a la redistribución"**, en el encabezado de la matriz, permite redistribuir hacia una tienda que no estaba en el Excel original. La tienda agregada queda **resaltada**, y el resaltado se conserva aunque recargue la página o confirme la redistribución.

### 6.3 Pedidos que generan más de una Orden de Compra

Si el pedido mezcla tiendas de más de una marca/bodega (por ejemplo ROLAND y REGIONS), el sistema genera **automáticamente dos Órdenes de Compra**, una por bodega, cada una con sus propias Solicitudes de Traslado. Ambas se envían a SAP en paralelo. El correo de confirmación se envía una sola vez, solo si ambas ODC tuvieron éxito.

Cada ODC tiene su propio botón en el campo **"Número OC SAP"** de la cabecera del pedido: con dos ODC verá dos botones (antes solo se veía el del número más antiguo). Al pulsar uno se abre la ventana **"Integración con SAP Completada"** de esa ODC, con sus Solicitudes de Traslado por tienda; la tabla incluye la columna **"Nombre de Tienda"**, entre DocNum y Tienda. Este botón funciona en el detalle del pedido, en Cargar Plantilla y en Redistribución (incluida la vista de solo lectura de EL RAYO). Junto al número hay un ícono para **copiarlo**.

### 6.4 Envío confiable a SAP

Al enviar la ODC a SAP, si alguna Solicitud de Traslado queda pendiente de confirmación por parte de SAP, el proceso **no se marca como completado de inmediato**: la pantalla sigue esperando (consultando cada pocos segundos, hasta varios minutos) a que SAP resuelva, en vez de mostrar un "completado" prematuro que no refleje la realidad. Cada traslado se guarda apenas SAP lo resuelve, tienda por tienda, para no perder avance si el proceso se interrumpe.

### 6.5 Exportar Traslados a Excel

Disponible tanto para MABEL TRADING como para EL RAYO desde el estado **Confirmado y Enviado** en adelante (antes de enviar la ODC a SAP no existen traslados que exportar). El botón **"Exportar a Excel"** descarga un archivo `traslados_{numero_pedido}_v{version}_{fecha_hora}.xlsx` con 3 hojas:

- **Información del Pedido**: cabecera y notas de alcance.
- **Matriz por Tienda**: una fila por producto, una columna por tienda con la cantidad solicitada; totales generales con columnas Sol./Conf.
- **Traslados (Detalle)**: una fila por combinación producto + tienda, con número de traslado, cantidad solicitada, confirmada y asignada.

> El número de traslado es por **tienda**, no por producto (se repite en todas las líneas de esa tienda). Las bodegas centrales aparecen como "No aplica" en vez de número de traslado.

## 7. ODC a SAP (ambos perfiles)

**Ruta:** Dashboard → ODC a SAP

### 7.1 Descripción

Esta pantalla muestra las ODC generadas y enviadas a SAP, además de un botón para Descargar PDF.

- Al hacer clic en la flecha de la columna **DETALLES**, se despliega la información completa de la ODC.
- Se visualizan los números de pedido, la fecha y hora de creación, y el estado actual de la ODC.
- La columna **RESPUESTA SAP** muestra un mensaje descriptivo con la respuesta emitida por SAP.

### 7.2 Buscar, filtrar y paginar

- **Buscar:** el banner **"Procesar ODC"**, en la parte superior de la pantalla, busca en el servidor (no solo en la página que ve).
- **Con reintento pendiente:** si alguna ODC tiene disponible **Reintentar** o **Reintentar ST**, aparece el botón naranja **"N pedidos con reintento pendiente"** (aunque diga "pedidos", cuenta órdenes de compra). Púlselo para ver solo esas ODC y púlselo de nuevo para volver a ver todas. El mismo número aparece en el círculo rojo del botón **ODC a SAP** del Dashboard.
- **Reintentar ST:** muestra en un círculo cuántas tiendas quedan pendientes sobre el total (por ejemplo "2/5"). Para reintentos automáticos, ver la [sección 15](#15-reconciliación-automática-diaria-de-traslados).
- **Columnas:** el selector de columnas, a la derecha del filtro, permite mostrar u ocultar columnas y restablecerlas.
- **Paginación:** cuando hay más de una página, el pie indica "Mostrando X–Y de N órdenes (página P de T)" y permite **elegir cuántas filas ver por página (10, 20 o 50)**.

## 8. Procesamiento SAP (MABEL TRADING)

**Ruta:** Dashboard → Información Pedidos y ODC → Procesamiento SAP

### 8.1 Descripción

Búsqueda de un pedido por número para ver su procesamiento SAP. En la cabecera se ve información importante del pedido; en el detalle, la cantidad original, pack, cantidad en unidades SAP, precio unitario, y una comparación lado a lado de **"Subtotal Pedido" (Excel)** vs. **"Subtotal SAP"**.

### 8.2 Pasos

1. Haga clic en **Procesamiento SAP** en el dashboard.
2. Ingrese el número de pedido (ej: `P-12.48 - 12 - 2025`).
3. Presione **Enter** o **Buscar**.

## 9. Listado de Pedidos y Detalle (EL RAYO)

**Ruta:** Dashboard → Listado de Pedidos

### 9.1 Descripción

Muestra todos los pedidos con filtros por estado, fechas, proveedor, número de pedido y creado por. El botón naranja **"N pedidos requieren tu acción"** filtra los pedidos que esperan algo de usted: los que están en **Confirmado por Producción** (para Confirmar o Cancelar) o en **Confirmado y Enviado** (para Despachar y Facturar). El tamaño de página elegido se recuerda entre visitas.

Al hacer clic en un pedido, este pasa automáticamente a estado **Gestionar Pedido** y se abre el detalle.

> También existe el acceso directo **Dashboard → Gestionar Pedido**, que permite buscar un pedido por número (con historial de búsquedas) y recuerda el último pedido gestionado por el usuario.

### 9.2 Acciones en el Detalle del Pedido

Dentro del detalle, usted puede:

- **Descargar Pedido Original**: archivo Excel basado en el pedido cargado por MABEL TRADING.
- **Editar Costo Unitario, Total o Comentario** (campos editables mientras el pedido está en Gestionar Pedido).
- **Modificar fecha** de entrega. La **Fecha Facturación** es exclusiva de EL RAYO y solo se puede elegir con el pedido en **Confirmado y Enviado**; hasta que se elija, el botón **Despachar y Facturar** permanece deshabilitado.
- **Confirmar**, para crear la respuesta del proveedor. Solo está disponible con el pedido en **Confirmado por Producción** y exige una **fecha de entrega real**: si falta, el botón queda deshabilitado y aparece el aviso "Seleccione una fecha de entrega para confirmar".
- **Cancelar Pedido** (parte inferior del detalle, solo en Confirmado por Producción): cambia el pedido a **Cancelado por El Rayo**. Úselo únicamente cuando MABEL TRADING lo solicite expresamente.
- **Generar TXT MBA3**: si el pedido generó más de una ODC (por mezclar tiendas de distintas bodegas), aparece un botón de descarga independiente por cada ODC.
- **Volver** al listado de pedidos.

Las celdas que usted modifique se resaltan en **púrpura** para diferenciarlas de las que edite Producción El Rayo (resaltadas en naranja).

## 10. Revisar Redistribución (EL RAYO)

**Ruta:** Dashboard → Revisar Redistribución

### 10.1 Descripción

Lista pedidos con redistribución confirmada, para revisar la distribución por tienda en **modo solo lectura**. No se pueden editar cantidades.

### 10.2 Pasos

1. Use los filtros (fechas, proveedor, número de pedido) para localizar el pedido.
2. Haga clic en el pedido para ver su **redistribución por tienda**.
3. Verá las cantidades asignadas a cada tienda sin posibilidad de modificación. Desde estado Confirmado y Enviado en adelante, también puede usar **Exportar a Excel** para descargar los traslados (ver [sección 6.5](#65-exportar-traslados-a-excel)).

## 11. Producción El Rayo (perfil nuevo)

**Ruta:** Dashboard → Producción El Rayo (`/mba3-consultas/produccion/pedidos`)

### 11.1 Descripción

Perfil pensado para el personal de planta/producción, con visión reducida frente a EL RAYO. Su función es confirmar si un pedido puede producirse, **sin ver costos, precios ni márgenes**.

### 11.2 Alcance y restricciones

- El listado solo muestra pedidos en estado **Nuevo Pedido** o **Gestionar Pedido**. En cuanto el pedido avanza (por ejemplo al confirmarlo), deja de ser visible para este perfil.
- En el detalle del pedido, **no se muestran** Costo sin IVA, Descuento, Subtotal, Costo, Costo Unitario ni Margen. Sí se ve el PVP y las cantidades.
- **No** ve el campo "Fecha Facturación" (exclusivo de EL RAYO), pero sí puede editar la **fecha de entrega**.
- Puede editar el campo **Total** para registrar la cantidad que efectivamente se puede producir.

### 11.3 Botón "Confirmar Producción"

Reemplaza al botón "Confirmar" de EL RAYO. Disponible mientras el pedido está en **Gestionar Pedido**. Al confirmarlo:

- El pedido pasa al estado **Confirmado por Producción**.
- Se notifica por correo a Administración El Rayo (perfil `odcsap.view`).
- Como Producción ya no tiene acceso a ese estado, la pantalla lo redirige automáticamente de vuelta al listado.

También recibe una notificación por correo cuando MABEL TRADING envía un nuevo pedido, y cuando Administración El Rayo cancela un pedido que Producción ya había confirmado.

## 12. Homologaciones (MABEL TRADING)

**Ruta:** Dashboard → Información Pedidos y ODC → Homologaciones

### 12.1 Descripción

Administra las homologaciones de SKU que no coinciden entre MBA3 y SAP. Permite vincular un SKU MBA3 con un SKU SAP.

### 12.2 Pasos

1. Use **Buscar SKU** para localizar un SKU específico.
2. Use los filtros: **Estado** (Pendiente, Homologado, Error), **Tiene Diferencias**, **Tiene Datos SAP**.
3. En la tabla verá: SKU MBA3, SKU SAP (si existe), Estado, y acciones para homologar o editar.
4. El botón **"Cruce MBA3/SAP"** ejecuta un cruce masivo con barra de progreso.

## 13. Órdenes de Compra (MABEL TRADING)

**Ruta:** Dashboard → Información Pedidos y ODC → Órdenes de Compra

### 13.1 Descripción

Historial completo de órdenes de compra generadas: pendientes, enviadas y con error.

### 13.2 Uso

- Filtro por estado: **Todos**, **Pendientes**, **Enviadas**, **Con Error**.
- **Exportar CSV** para descargar los datos.
- **Actualizar** para refrescar. Paginación para navegar por las páginas.

## 14. Listado Pedidos Originales

**Ruta:** Dashboard → Información Pedidos y ODC → Listado Pedidos Originales (se abre como ventana emergente)

### 14.1 Descripción

Muestra los archivos Excel originales cargados en el sistema (storage).

### 14.2 Acciones

- Ver la lista de archivos, descargar, eliminar (según permisos).

## 15. Reconciliación automática diaria de traslados

Este proceso corre **solo, en segundo plano**, sin que ningún usuario deba iniciarlo. Automatiza lo que antes exigía usar manualmente el botón "Reintentar ST".

- **Qué hace:** revisa ODC ya enviadas a SAP que quedaron con Solicitudes de Traslado pendientes por una falla transitoria (incluyendo tiendas que nunca llegaron a intentarse), y reintenta enviarlas.
- **Cuándo corre:** una vez al día, en la noche. De lunes a sábado revisa solo lo de los últimos 2 días; los domingos hace un barrido más amplio de los últimos 7 días.
- **Si el problema no es transitorio** (por ejemplo, un artículo no habilitado en la bodega), se avisa de inmediato por correo al equipo técnico, ya que un reintento automático no lo va a resolver.
- **Si el problema persiste** tras varios intentos sin resolverse, deja de reintentarse automáticamente, pero ya se generó el correo de aviso correspondiente. El botón manual **"Reintentar ST"** sigue disponible en cualquier momento.

> Para el usuario final esto significa que un pedido que quedó con un traslado en error no necesariamente requiere que usted reintente manualmente: el sistema reintenta solo antes de que usted tenga que actuar.

## 16. Acciones — Referencia de botones

En el detalle de un pedido encontrará, según su perfil y el estado del pedido:

| Botón | Cuándo aparece | Acción |
|---|---|---|
| Confirmar | EL RAYO, pedido en Confirmado por Producción (requiere fecha de entrega real) | Crear respuesta del proveedor |
| Cancelar Pedido (EL RAYO) | EL RAYO, pedido en Confirmado por Producción | Pasa a Cancelado por El Rayo; solo a solicitud expresa de MABEL TRADING |
| Número OC SAP (uno por ODC) | Pedido con ODC generadas | Abre "Integración con SAP Completada" de esa ODC |
| Reintentar / Reintentar ST | ODC a SAP: **Reintentar** en una ODC Pendiente o con Error; **Reintentar ST** en una ODC Enviada con tiendas pendientes | Reintenta el envío de la ODC o los traslados pendientes |
| Confirmar Producción | Producción El Rayo, en Gestionar Pedido | Pasa a Confirmado por Producción, notifica a EL RAYO |
| Aceptar / Rechazar | MABEL TRADING, pedido en Producción Pospuesta | Envía la diferencia a redistribución, o la cierra como Rechazado |
| Generar ODC / Enviar ODC a SAP | Pedido con redistribución confirmada | Genera orden de compra y solicitudes de traslado |
| Confirmar Redistribución | MABEL, pedido con redistribución editable | Guardar redistribución |
| Exportar a Excel | Desde Confirmado y Enviado en adelante | Descarga los traslados (matriz + detalle) |
| Descargar Análisis de Margen | Cargar Plantilla, MABEL/EL RAYO | Descarga el Excel de márgenes |
| Despachar y Facturar | EL RAYO, pedido en Confirmado y Enviado y con **Fecha Facturación** elegida | Marcar para despacho |
| Finalizar | Pedido en Despachar y Facturar | Marcar como finalizado |
| Generar TXT MBA3 | Según ODC generadas (una por bodega si aplica) | Descargar archivo de exportación |
| Descargar Pedido / Pedido Original | Según permisos | Descargar datos del pedido |
| Cancelar Pedido (MABEL) | Confirmado por el Rayo en adelante, antes de Confirmado redistribución | Cambia a Cancelado (irreversible) |

### 16.1 Información mostrada

- **Cabecera**: número de pedido, proveedor, fechas, estado, marca/bodega (Origen Traslado).
- **Productos**: SKU, descripción, cantidades, costos (ocultos para Producción El Rayo), margen.
- **Redistribución por tienda**: cantidades por tienda (editable para MABEL, solo lectura para EL RAYO).

## 17. Administración de notificaciones (rol Admin)

**Ruta:** Dashboard → Información Pedidos y ODC → Destinatarios de Notificaciones (solo visible con rol `Admin`)

### 17.1 Destinatarios de Notificaciones

**Ruta:** `/mba3-consultas/admin/destinatarios`. Define qué personas reciben qué correos del sistema. **Cada persona recibe solo los correos que aparecen en su tarjeta.**

La pantalla tiene dos zonas: a la izquierda las **tarjetas de personas** y a la derecha el **Catálogo de correos**.

**Para agregar a alguien y asignarle correos:**

1. En el buscador superior, **"Buscar usuario o escribir un correo externo"**, escriba el nombre. Elija una sugerencia de usuario interno o, si es una persona externa, escriba su correo y presione **Enter** (si no hay coincidencias internas verá "Sin coincidencias internas — presiona Enter para agregar este correo externo").
2. Se crea una **tarjeta "pendiente"**: avatar gris y sin correos. Todavía no está guardada en el sistema. El Catálogo de correos se resalta un momento para indicarle el siguiente paso.
3. En el **Catálogo de correos**, **arrastre** el correo que le corresponde hasta la tarjeta, o **toque el correo y luego toque la tarjeta** (útil en pantallas táctiles). En cuanto la persona recibe su primer correo, queda **guardada**.
4. Repita con los demás correos. Si intenta soltar un correo que la persona ya tiene, la tarjeta se marca en rojo y no se permite.

**Para quitar correos o personas:**

- **"Quitar este correo"** (en cada correo de la tarjeta). Si quita el último, la tarjeta **no desaparece**: queda como pendiente (gris), igual que una persona nueva.
- **"Eliminar persona"** (ícono de la tarjeta): si la tarjeta está pendiente (sin correos) simplemente se descarta; si ya estaba guardada, el sistema pregunta "¿Eliminar a … y todos sus correos asignados?" y, al aceptar, la elimina junto con todos sus correos.

**Otras ayudas:**

- El catálogo tiene su propio buscador (**"Buscar correo o tipo"**), muestra los correos agrupados y coloreados por tipo, y un contador "X de Y".
- Sobre las tarjetas, los botones **"Todos los equipos"** y uno por cada equipo permiten ver solo las personas de ese equipo.
- El enlace **"→ Gestionar catálogo"** lleva al Catálogo de Correos.

### 17.2 Catálogo de Correos

**Ruta:** `/mba3-consultas/admin/catalogo-correos`. Catálogo de tipos de correo/notificación que envía el módulo.

## 18. Consejos y buenas prácticas

1. **Auto-actualizar**: actívelo en listados largos para mantener la información actualizada.
2. **Pendientes**: use el botón naranja "N pedidos requieren acción" (y los círculos rojos del Dashboard) para centrarse en lo que le toca.
3. **Número de pedido**: el formato típico es `P-12.48 - 12 - 2025`; respete espacios y guiones al buscar.
4. **Homologaciones**: revise periódicamente los SKUs pendientes para evitar bloqueos en el envío a SAP.
5. **Redistribución**: confirme la redistribución solo cuando las cantidades por tienda estén correctas.
6. **Validaciones de Excel**: si la carga se bloquea por Costo Unitario, Pack/PVP o TOTAL/SUBTOTAL, revise las fórmulas de la plantilla antes de volver a subirla — el mensaje siempre indica la fila y el producto exactos.
7. **Traslados pendientes**: si un traslado queda en error, no es necesario reintentarlo de inmediato; la reconciliación automática lo intentará esa misma noche.

## 19. Resolución de problemas

| Problema | Posible solución |
|---|---|
| No veo el botón X | Verifique que su usuario tiene el permiso adecuado (EL RAYO, Producción El Rayo, MABEL TRADING, o `funcionalidades-admin.view` si es una función del panel "Información Pedidos y ODC"). |
| Error al cargar plantilla: "Discrepancias de Costo Unitario" | La columna Costo Unitario no coincide con Costo sin IVA ÷ Pack. Corrija la fórmula en el Excel. |
| Error al cargar plantilla: "Discrepancias de Pack/PVP" | El Pack o PVP del Excel no coincide con SAP. Use el valor que el mensaje sugiere. |
| Error al cargar plantilla por TOTAL/SUBTOTAL | La fórmula de TOTAL o SUBTOTAL de algún producto no cuadra con las cantidades reales por tienda/bodega; revise el mensaje para identificar la fila. |
| ODC con error de SKU | Vaya a Homologaciones y complete la homologación del SKU. |
| Pedido no aparece en listado | Revise filtros (estado, fechas). Si activó el botón "N pedidos requieren acción", púlselo de nuevo para quitar el filtro. |
| Botón Confirmar / Confirmar Producción deshabilitado | **Confirmar** (EL RAYO) solo funciona en Confirmado por Producción y con una fecha de entrega real: si ve "Seleccione una fecha de entrega para confirmar", elija la fecha. **Confirmar Producción** solo funciona en Gestionar Pedido. Revise también el estado del pedido. |
| El pedido queda en Pendiente Logística o en Error envío SAP (reintentar) | Son estados de excepción durante el envío; la reconciliación automática reintentará esa noche, o puede usar "Reintentar" / "Reintentar ST" manualmente en ODC a SAP. |
| El botón "Número OC SAP" no abre nada | En versiones anteriores no respondía en Cargar Plantilla ni en Redistribución; ya funciona en las tres pantallas. Si su pedido generó dos ODC verá un botón por cada una. |
| El proceso de "Enviar ODC a SAP" sigue mostrando progreso tras varios minutos | Es esperado si SAP aún no confirma alguna Solicitud de Traslado; el sistema sigue consultando en vez de cerrar el proceso de forma prematura. |
| No encuentro "Crear Pedido Manual" | La pantalla existe pero no tiene botón de acceso habilitado actualmente; no está disponible para uso normal. |

## 20. Glosario

| Término | Definición |
|---|---|
| ODC | Orden de Compra |
| ST / ITR | Solicitud de Traslado (transferencia de mercadería hacia una tienda), generada tras enviar la ODC a SAP |
| SAP | Sistema ERP corporativo |
| MBA3 | Sistema de gestión de pedidos |
| SKU | Código único de producto |
| Homologación | Correspondencia entre un SKU MBA3 y un SKU SAP |
| Redistribución | Asignación de cantidades por tienda |
| Bodega / CD | Centro de distribución origen de un traslado (ej. RL-CD, RG-CD, OUT-CD) |
| Producción Pospuesta | Pedido "hijo" generado con la diferencia entre lo solicitado y lo confirmado por EL RAYO/Producción |
| Margen de Rentabilidad | Porcentaje calculado a partir del Costo Unitario y el PVP de cada producto |
| Reconciliación | Proceso automático diario que reintenta Solicitudes de Traslado pendientes con SAP |
| Requiere acción | Pedido (u ODC) que espera una acción de su perfil; el significado cambia según la pantalla (ver sección 3.3) |
| Pedido hijo | Pedido generado con la diferencia de una Producción Pospuesta; se numera `<pedido>.NN` |
| Tarjeta pendiente | En Destinatarios, persona recién agregada que aún no tiene ningún correo asignado (avatar gris) |

---

*Documento generado para el módulo MBA3-consultas de SCNexus. Consulte con el administrador del sistema ante dudas sobre permisos o configuración.*
