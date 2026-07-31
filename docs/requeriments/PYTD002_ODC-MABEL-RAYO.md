# Control de Cambios Orden de Compra entre Mabel Trading y El Rayo

**Código:** SIS-PYTD-0002

| Campo | Valor |
|---|---|
| Nombre del requerimiento | Control de Cambios Módulo Gestión ODC Mabel-Rayo v1.2 |
| Área solicitante | Compras Mabel Trading – Administración El Rayo |
| Empresa | Mabel Trading / Textiles El Rayo |
| Herramienta utilizada | SCNexus, MBA3, SAP Business One |
| Fecha de levantamiento | 01/07/2026 |
| Responsable del requerimiento | Paola Cháfuel |
| Solicitante | Andrea Vaca |

## 1. Descripción del proyecto

Se solicita una mejora evolutiva al módulo de Gestión de Órdenes de Compra de SCNexus
con el objetivo de optimizar el proceso de compras entre Mabel Trading y El Rayo,
incorporando nuevas funcionalidades que faciliten la gestión de pedidos, redistribución,
traslados, validaciones y seguimiento de la producción.

Los cambios solicitados son los siguientes:

### 1.1 Mejoras de usabilidad

#### 1.1.1 Inmovilización de columnas

En las opciones:

- Redistribución de Productos
- Revisar Redistribución de Productos (El Rayo)

Se requiere que el encabezado permanezca fijo al desplazarse verticalmente. Desde la
columna N° hasta la columna Precio permanezcan inmovilizadas durante el
desplazamiento horizontal. Esto permitirá revisar grandes cantidades de productos sin
perder la referencia de la información principal.

#### 1.1.2 Ajuste del formato PDF

Modificar el formato de impresión de las Órdenes de Compra para que:

- Se adapte automáticamente a la cantidad de productos.
- Evite espacios en blanco innecesarios.
- Reduzca el número de páginas cuando la orden contiene pocos ítems.

### 1.2 Gestión de pedidos parciales

Actualmente un pedido solo puede continuar cuando El Rayo dispone del total o parcial
solicitado. Se requiere modificar el proceso para permitir pedidos parciales o a la vez
cerrar el pedido porque no habrá producción.

El nuevo flujo será:

- El Rayo confirma únicamente las cantidades disponibles del pedido.
- El usuario de Compras de Mabel Trading podrá redistribuir inmediatamente
  dichas cantidades entre las tiendas.

Para las cantidades faltantes, el usuario administrativo de El Rayo dispondrá de dos
opciones:

- **Opción 1. Finalizar Pedido:** Indica que las cantidades restantes no serán
  producidas. En este caso el pedido se cerrará definitivamente.
- **Opción 2. Programar Producción:** Permite indicar:
  - Número de pedidos futuros y cantidades por pedido
  - Fecha estimada de entrega de cada pedido restante

El usuario de Compras de Mabel Trading decidirá si:

- Acepta la programación, o
- Finaliza definitivamente el pedido.

Si acepta:

SCNexus deberá generar automáticamente una Orden de Compra por cada entrega
programada cumpliendo el proceso ya establecido. En cada nueva orden el usuario podrá
redistribuir las cantidades correspondientes a las tiendas.

### 1.3 Validación de carga de Excel

Durante la carga del archivo Excel del pedido, el sistema deberá validar la información
contra SAP Business One. Los siguientes campos deberán coincidir:

- Pack
- PVP

Si existe alguna diferencia, informar el error y sugerir los valores existentes en SAP para
facilitar la corrección.

### 1.4 Inclusión del costo en la plantilla Excel

Agregar una nueva columna denominada **Costo**, en la plantilla utilizada para cargar
pedidos de Mabel. Este campo únicamente servirá para calcular el margen; no modificará
el proceso actual de carga; no actualizará costos en SAP; no afectará las órdenes de
compra.

El sistema mediante un botón permitirá descargar el análisis completo del margen.

### 1.5 Análisis de margen de rentabilidad

Se requiere incorporar un análisis del margen por producto. Cambios solicitados:

Agregar una columna denominada **Margen de Rentabilidad**, calculada mediante la fórmula:

```
Margen = 1 - (Costo / (PVP / 1.15))
```

Además, mostrar el margen dentro de la pantalla de carga por producto; permitir
exportarlo a Excel.

### 1.6 Traslados entre bodega

Ampliar la funcionalidad de Traslados para permitir solicitudes entre:

- CEDI Roland → Regions
- Regions → CEDI Roland

Manteniendo el mismo flujo actual.

### 1.7 Generación del archivo TXT para MBA3

Cuando una Orden de Compra se encuentre en el estado **"Confirmado por El Rayo"**, el
sistema SCNexus deberá habilitar un botón denominado **"Generar TXT MBA3"**, el cual
permitirá generar un archivo de texto (.txt) compatible con el sistema MBA3 para su
posterior importación.

**Consideraciones funcionales:**

El botón únicamente estará disponible cuando la Orden de Compra tenga el estado
Confirmado por El Rayo.

El archivo deberá respetar exactamente la estructura y formato de la plantilla
proporcionada por El Rayo.

El sistema tomará la información del archivo Excel generado por SCNexus para
completar automáticamente los campos correspondientes del archivo TXT.

Los siguientes campos se completarán en el txt en conjunto con el formato del punto
anterior:

| Campo del archivo TXT | Origen de la información |
|---|---|
| Vendedor | Columna I del archivo Excel generado por SCNexus |
| Cantidad Pedido | Columna V del archivo Excel generado por SCNexus |
| Código Producto | Columna U del archivo Excel generado por SCNexus |
| Precio Final | Columna X del archivo Excel generado por SCNexus |

> **Nota:** las páginas 5-6 del PDF original muestran capturas de pantalla de ejemplo (archivo
> generado en SCNexus con datos de PROL-07.01.2026 y una hoja de cálculo con el layout de
> campos del archivo TXT a generar: Fecha Pedido, Fecha Entrega, Moneda, Bodega, Vendedor,
> Pedido Manual, Contrato, Orden Compra, Cotización, Medio Capt., Transporte, Nombre Sol.
> Memo, Registro Edit., Confirmado, Sucursal, Código Producto, Cantidad Pedido, BackOrder,
> Precio Final, Aplica Impuesto, Depau, entre otros — son imágenes de ejemplo, no texto
> normativo del requerimiento.

El archivo generado deberá conservar el mismo orden, longitud de campos y formato
definido en la plantilla oficial de MBA3.

### 1.8 Nuevo perfil Producción El Rayo

Se requiere incorporar un nuevo perfil de usuario denominado **Producción El Rayo**,
destinado exclusivamente al personal encargado de la planificación y confirmación de la
producción. Este perfil únicamente tendrá acceso a ver la información cuando esté en
estado Gestionar Pedido.

**Información visible**

El usuario visualizará únicamente la siguiente información:

- Número de pedido
- Fecha del pedido
- Fecha de entrega
- Fecha de facturación
- Código Interno
- Marca
- Código de Barras
- Descripción SAP
- Pack
- Cantidad Total solicitada

El perfil no visualizará información relacionada con costos, precios o márgenes.

**Nueva funcionalidad:**

Se incorporará una nueva columna denominada **Cantidad a producir**.

En esta columna el usuario de Producción registrará la cantidad que realmente será
fabricada para cada producto del pedido.

La información registrada quedará almacenada y será utilizada posteriormente por el
usuario de Administración El Rayo, quien será responsable de:

- Validar las cantidades registradas;
- Confirmar las cantidades definitivas hacia Mabel Trading;
- Actualizar la fecha comprometida de entrega;
- Cambiar el estado del pedido.

Se considera que existirán dos usuarios del área de Producción que podrán registrar las
cantidades producidas sobre un mismo pedido; el usuario que registró las cantidades
quedará registrado en el pedido, mientras que únicamente el usuario administrativo tendrá
permisos para confirmar el pedido y modificar su estado.

### 1.9 Exportación de solicitudes de traslado

Incorporar la opción Exportar a Excel dentro del detalle de las Solicitudes de Traslado.

El archivo generado deberá contener como mínimo la siguiente información:

- Número de traslado
- Nombre de la tienda
- Código de barras
- Cantidad solicitada
- Cantidad confirmada

El formato de exportación deberá ser similar al utilizado actualmente en la sección
Redistribución, manteniendo el mismo estilo de presentación para facilitar su análisis.

> **Nota:** la página 7 del PDF original muestra tablas dinámicas de ejemplo (PROL-06.76.2026)
> con cantidades asignadas por tienda (Condado, Laguna Mall, Mall de los Andes, Mall del
> Alto, Portal Shopping, Quicentro Norte, Quicentro Sur, Recreo, San Luis, Scala) — son
> capturas de ejemplo, no texto normativo del requerimiento.

### 1.10 Negociación de precios MBA3 (funcionalidad futura)

Como mejora futura se plantea incorporar un nuevo módulo denominado **Negociación de
Precios MBA3**, cuyo objetivo será administrar listas de precios y descuentos comerciales
para el cliente Mabel Trading. La información será obtenida del análisis del Cubo MBA3 y
permitirá consultar el estado comercial de cada producto.

## 2. Actores y responsabilidades

| Rol / Área | Acción |
|---|---|
| Comprador Mabel Trading | Generar órdenes de compra, redistribuir productos, validar pedidos parciales y aprobar entregas programadas. |
| Administración El Rayo | Gestionar los estados de los pedidos, validar las cantidades confirmadas por Producción y confirmar los pedidos hacia Mabel Trading. |
| Producción El Rayo | Registrar las cantidades que serán producidas y la fecha estimada de entrega de cada pedido. |
| Sistema SCNexus | Validar información, generar órdenes de compra, generar archivos TXT, exportar información e integrarse con SAP Business One. |
| SAP Business One | Proveer información de productos, Pack y PVP para las validaciones del sistema. |
| MBA3 | Recibir los archivos TXT generados por SCNexus. |

## 3. Historias de Usuario

| Como | Quiero | Para |
|---|---|---|
| Comprador de Mabel Trading | Redistribuir las cantidades disponibles de un pedido parcial | Abastecer las tiendas sin esperar la producción total del pedido. |
| Comprador de Mabel Trading | Validar automáticamente el Pack y el PVP durante la carga del Excel | Evitar errores en la generación de órdenes de compra. |
| Comprador de Mabel Trading | Consultar el margen de rentabilidad por producto | Analizar la conveniencia comercial antes de confirmar un pedido. |
| Usuario Administrativo El Rayo | Programar la entrega de cantidades pendientes en varios pedidos | Informar oportunamente a Mabel Trading sobre el plan de producción. |
| Usuario Producción El Rayo | Registrar las cantidades que serán producidas | Facilitar la confirmación del pedido por parte del área administrativa. |
| Usuario Administrativo El Rayo | Generar el archivo TXT para MBA3 cuando el pedido esté confirmado | Importar la información al ERP sin realizar digitación manual. |
| Usuario Compras | Exportar las solicitudes de traslado a Excel | Realizar seguimiento y conciliación de los traslados entre bodegas y tiendas. |

### 3.1 Reglas para considerar

| ID | Descripción |
|---|---|
| RN-01 | El sistema únicamente permitirá generar el archivo TXT cuando la Orden de Compra tenga el estado Confirmado por El Rayo. |
| RN-02 | Durante la carga del archivo Excel se validarán obligatoriamente el Pack y el PVP contra la información registrada en SAP Business One. |
| RN-03 | El perfil Producción El Rayo no tendrá acceso a información de costos, precios, márgenes ni gestión de estados del pedido. |
| RN-04 | Cada entrega parcial aceptada generará una nueva Orden de Compra independiente para su redistribución. |
| RN-05 | El costo registrado en la plantilla Excel será únicamente informativo para el cálculo del margen de rentabilidad y no modificará información en SAP Business One. |
| RN-06 | Las exportaciones a Excel deberán respetar el formato estándar utilizado por SCNexus en los procesos de redistribución. |

## 4. Integraciones

Conexiones a otros sistemas, aplicativos y bases de datos:

| ID | Sistema / BDD | Descripción |
|---|---|---|
| IN-01 | SAP | Consulta de información maestra de productos (Pack, PVP y demás datos necesarios para las validaciones del proceso). |
| IN-02 | SCNexus | Generación de órdenes de compra, redistribuciones, exportaciones a Excel y administración del flujo operativo del proceso. |

## 5. Cronograma de Implementación (5 semanas)

**Inicio:** lunes 03/08/2026 · **Cierre:** viernes 04/09/2026 · **Horario:** laboral, lunes a viernes.

**Supuestos del cronograma:**

- 1 desarrollador, trabajo secuencial (un ítem a la vez, sin paralelización).
- Se excluye el punto 1.10 (Negociación de Precios MBA3) por estar definido en el propio
  requerimiento como funcionalidad futura, fuera del alcance de este ciclo.
- Feriado nacional considerado: **lunes 10/08/2026** (Primer Grito de la Independencia de
  Quito). No se identifican otros feriados nacionales entre el 03/08/2026 y el 04/09/2026.
- Fines de semana excluidos.
- Total de días laborables disponibles: **24**.
- No se reservan días de contingencia adicionales; cualquier bloqueo (p. ej. disponibilidad
  de ambiente de pruebas SAP, cambios de alcance) desplazaría la fecha de cierre.

### Semana 1 (03 – 07 ago)

| Fecha | Día | Actividad | Ref. |
|---|---|---|---|
| 03/08 | Lun | Kickoff y diseño técnico integral (incluye diseño del flujo de pedidos parciales y del nuevo perfil de Producción, para no rediseñar en semanas 4-5) | — |
| 04/08 | Mar | Inmovilización de columnas (Redistribución y Revisar Redistribución El Rayo) | 1.1.1 |
| 05/08 | Mié | Ajuste del formato PDF de Órdenes de Compra | 1.1.2 |
| 06/08 | Jue | Inclusión de columna Costo en plantilla Excel | 1.4 |
| 07/08 | Vie | Margen de Rentabilidad — fórmula y columna | 1.5 |

### Semana 2 (10 – 14 ago) — feriado 10/08

| Fecha | Día | Actividad | Ref. |
|---|---|---|---|
| 10/08 | Lun | **Feriado** (Primer Grito de la Independencia) | — |
| 11/08 | Mar | Margen de Rentabilidad — pantalla de carga y exportación a Excel | 1.5 |
| 12/08 | Mié | Validación de carga de Excel contra SAP (Pack, PVP) | 1.3 |
| 13/08 | Jue | Validación de carga de Excel contra SAP — mensajes de error y sugerencia de valores | 1.3 |
| 14/08 | Vie | Validación de carga de Excel contra SAP — pruebas y ajustes (RN-02) | 1.3 |

### Semana 3 (17 – 21 ago)

| Fecha | Día | Actividad | Ref. |
|---|---|---|---|
| 17/08 | Lun | Traslados entre bodega: CEDI Roland → Regions | 1.6 |
| 18/08 | Mar | Traslados entre bodega: Regions → CEDI Roland | 1.6 |
| 19/08 | Mié | Exportación a Excel de Solicitudes de Traslado (RN-06) | 1.9 |
| 20/08 | Jue | Pruebas funcionales de checkpoint (puntos 1.1 a 1.9) | — |
| 21/08 | Vie | Ajustes derivados de las pruebas de checkpoint | — |

### Semana 4 (24 – 28 ago)

| Fecha | Día | Actividad | Ref. |
|---|---|---|---|
| 24/08 | Lun | Gestión de pedidos parciales — confirmación de cantidades disponibles y redistribución inmediata | 1.2 |
| 25/08 | Mar | Gestión de pedidos parciales — opción "Finalizar Pedido" | 1.2 |
| 26/08 | Mié | Gestión de pedidos parciales — opción "Programar Producción" (pedidos futuros, fechas estimadas) | 1.2 |
| 27/08 | Jue | Gestión de pedidos parciales — generación automática de nueva OC por entrega programada (RN-04) | 1.2 |
| 28/08 | Vie | Gestión de pedidos parciales — pruebas del flujo completo | 1.2 |

### Semana 5 (31 ago – 04 sep)

| Fecha | Día | Actividad | Ref. |
|---|---|---|---|
| 31/08 | Lun | Generación de archivo TXT para MBA3 — botón condicional por estado (RN-01) | 1.7 |
| 01/09 | Mar | Generación de archivo TXT para MBA3 — mapeo de campos y formato de plantilla | 1.7 |
| 02/09 | Mié | Nuevo perfil Producción El Rayo — vista restringida y columna Cantidad a producir (RN-03) | 1.8 |
| 03/09 | Jue | Nuevo perfil Producción El Rayo — flujo de validación/confirmación con Administración El Rayo | 1.8 |
| 04/09 | Vie | Pruebas integrales finales, validación de reglas de negocio (RN-01 a RN-06) y preparación para entrega/UAT | — |

### Resumen por ítem del requerimiento

| Ref. | Ítem | Fechas | Días estimados |
|---|---|---|---|
| — | Kickoff y diseño técnico | 03/08 | 1 |
| 1.1.1 | Inmovilización de columnas | 04/08 | 1 |
| 1.1.2 | Ajuste de formato PDF | 05/08 | 1 |
| 1.4 | Columna Costo en plantilla Excel | 06/08 | 1 |
| 1.5 | Margen de Rentabilidad | 07/08, 11/08 | 2 |
| 1.3 | Validación de carga de Excel vs. SAP | 12/08 – 14/08 | 3 |
| 1.6 | Traslados entre bodega | 17/08 – 18/08 | 2 |
| 1.9 | Exportación de solicitudes de traslado | 19/08 | 1 |
| — | Checkpoint de pruebas semana 3 | 20/08 – 21/08 | 2 |
| 1.2 | Gestión de pedidos parciales | 24/08 – 28/08 | 5 |
| 1.7 | Generación de archivo TXT para MBA3 | 31/08 – 01/09 | 2 |
| 1.8 | Nuevo perfil Producción El Rayo | 02/09 – 03/09 | 2 |
| — | Pruebas integrales finales y UAT | 04/09 | 1 |
| 1.10 | Negociación de Precios MBA3 | Fuera de alcance | — |

### Riesgos y supuestos a validar

- El punto 1.2 (pedidos parciales) es el de mayor complejidad funcional (nuevos estados,
  decisión Mabel/Rayo, generación automática de OC) y concentra toda la semana 4 sin
  margen adicional; cualquier ajuste de alcance descubierto durante el diseño técnico
  del 03/08 impactaría directamente esta semana.
- El punto 1.8 (nuevo perfil) queda con un margen ajustado de 2 días; al implicar permisos
  transversales sobre varias pantallas, si el alcance real de restricciones es mayor al
  estimado podría requerir tiempo adicional de la semana 5.
- No se contempla explícitamente un pase a producción ni ventana de UAT con los usuarios
  finales (Andrea Vaca, Melissa Sigcha, Nicole Velásquez) más allá del 04/09; de requerirse,
  se recomienda planificarlo como una sexta semana.
- Se recomienda validar este cronograma con Alex Toasa (Líder Desarrollo) antes de
  compartirlo con el sponsor del requerimiento.

## 6. Responsables del Proyecto

| Nombre | Rol | Firma | Fecha |
|---|---|---|---|
| Andrea Vaca | Sponsor | | |
| Melissa Sigcha | Analista de Compras Mabel T. | | |
| Nicole Velásquez | Analista Administrativa El Rayo | | |
| Alex Toasa | Líder Desarrollo | | |
| Paola Cháfuel | Analista de Aplicaciones / Responsable de Requerimiento | | |
