# Seguimiento de Implementación — PYTD002 (Control de Cambios ODC Mabel-Rayo)

Complementa a [PYTD002_ODC-MABEL-RAYO.md](PYTD002_ODC-MABEL-RAYO.md) (documento oficial,
no se modifica). Este documento registra, por cada punto del requerimiento: qué se
implementó, en qué difiere de la letra del documento original y por qué — para que una
diferencia deliberada no se lea como un defecto en una futura revisión.

Última actualización: 2026-08-17.

## 1.1.1 Inmovilización de columnas — Implementado

Encabezado sticky + columnas N°→Precio congeladas en la vista "Excel" de
Redistribución/Revisar Redistribución (`ExcelLikeGridView.vue`). Sin desviaciones
relevantes.

## 1.1.2 Ajuste del formato PDF — Implementado

`src/utils/odc_pdf_generator.py`: anchos de columna dinámicos según contenido y
`KeepTogether` para evitar páginas casi vacías. Sin desviaciones.

## 1.2 Gestión de pedidos parciales — Implementado, con simplificación deliberada de alcance

**Adaptación acordada con el usuario (17/08/2026), más simple que el texto literal**: el
documento original pide, para la opción 2 ("Programar Producción"), poder indicar *N*
pedidos futuros con sus fechas estimadas de entrega. Se implementó una versión de una sola
iteración: un único pedido "hijo" por división, con una sola fecha de entrega. Si ese hijo
también termina con diferencia, puede volver a dividirse (mismo mecanismo, recursivo), pero
no hay UI para planificar varias entregas futuras de una sola vez. El botón "Finalizar
Pedido" que ya existía en el sistema sigue siendo una funcionalidad distinta (cierre
`DESPACHAR_Y_FACTURAR→FINALIZADO`, post-despacho) — no se confunde con la opción 1 de este
punto.

**Precondición — cantidad_solicitada_original**: `pedido_detalle.total` es sobrescrito en
secuencia por `produccion-elrayo.view` (estado GESTIONAR_PEDIDO) y `odcsap.view` (estado
CONFIRMADO_POR_PRODUCCION) vía el mismo PATCH `.../detalle/{id}/total` (req. 1.8) — no
quedaba registro del valor cargado originalmente en la plantilla Excel. Se agregó
`cantidad_solicitada_original` (migración 641, `pedido_detalle`; 642 espejo en
`pedido_detalle_tienda` para uso futuro) escrita **una sola vez** en
`PedidoDetalleRepository.insert()` y nunca tocada por ningún endpoint de edición
posterior. También se verificó que el mecanismo "maduro" preexistente
(`pedido_respuesta_proveedor_detalle`/`distribucion_confirmada`) no resolvía esto: cuando
el detalle no tiene tiendas asignadas (caso normal en este punto del flujo),
`_calcular_cantidad_solicitada` usaba como *fallback* el mismo `total` ya sobrescrito.

**Flujo implementado**: al hacer clic en "Confirmar" (`crear-respuesta-desde-pedido`),
el frontend consulta primero `GET .../diferencia-produccion`
(`calcular_diferencia_produccion` en `pedidos_crud_helpers.py`). Si algún producto tiene
`total < cantidad_solicitada_original`, se muestra un modal con 2 opciones:

- **"Diferencia no será entregada"**: continúa exactamente el flujo de confirmación ya
  existente, sin cambios.
- **"Confirmar pedido, generar nuevo pedido con la diferencia"**: `POST
  .../confirmar-con-diferencia` (body: `nueva_fecha_entrega`). Confirma el pedido padre
  (misma lógica que la opción anterior) y crea un pedido "hijo"
  (`PedidoService.crear_pedido_hijo_diferencia`): `numero_pedido = "<padre>.NN"` (NN =
  hijos ya generados de ese padre + 1), `pedido_padre_id` enlaza al padre (migración 643,
  columna nueva en `pedido`, trazabilidad), `estado_id = ESTADO_PRODUCCION_POSPUESTA` (22
  — sembrado en la migración 620 para exactamente este propósito, pero nunca antes usado
  por ningún endpoint), `fecha_facturacion = NULL` (se define en su propio ciclo, como
  cualquier pedido nuevo). Cada línea del hijo copia atributos de producto/precio del
  padre; `total` = la diferencia; `subtotal` se escala proporcionalmente al subtotal
  original del padre (no lo toca ningún PATCH de "Total", sigue reflejando la cantidad
  completa original). Se notifica por correo a `mabel.view` (nuevo tipo "Diferencia en
  Pedido" en el catálogo de Destinatarios de Notificaciones, migración 644).

**Retomar el pedido pospuesto**: `POST .../gestionar` (mismo botón "Ver Detalle" de
siempre) ahora también transiciona `PRODUCCION_POSPUESTA (22) → GESTIONAR_PEDIDO (3)`
cuando El Rayo abre el pedido hijo — antes no existía ningún camino de salida de ese
estado.

**Mabel Trading puede cancelar el pedido hijo pospuesto**: el endpoint `/cancelar`
(y el flag `puede_cancelar_pedido` que gatilla el botón en el frontend) rechazaban
cualquier `estado_id >= ESTADO_LIMITE_CANCELAR_PEDIDO` (10); como 22 es numéricamente
mayor a ese límite pero anterior en el flujo real (mismo motivo por el que ya se excluye
de `_filtro_redistribucion`), se agregó una excepción explícita para
`ESTADO_PRODUCCION_POSPUESTA` en ambos lados (backend y el flag que expone al frontend).
Botón nuevo en `PedidoDetalleView.vue`, visible solo con `mabel.view` y estado 22.

**Endurecimiento del lado servidor (2026-08-17, mismo día)**: el control de diferencia
descrito arriba vivía solo como gate de UI — el frontend consultaba
`GET .../diferencia-produccion` y decidía si mostrar el modal, pero
`POST .../crear-respuesta-desde-pedido` (el que de verdad confirma) no verificaba nada por
su cuenta. Cualquier llamada directa a ese endpoint (otro cliente, un bug futuro del
frontend, o simplemente la migración 641 pendiente de aplicar, que fue exactamente lo que
pasó ese mismo día) se saltaba el control por completo. Se repitió la misma verificación
(`calcular_diferencia_produccion`) dentro de `_handle_crear_respuesta_desde_pedido`: si hay
diferencia y el body no envía `diferencia_reconocida=true`, rechaza con 400
(`diferencia_produccion_no_reconocida`). El body del POST ahora acepta ese campo opcional
(`ConfirmarRespuestaRequest`, default `false`); el frontend lo manda en `true` únicamente
al confirmar desde la opción "Diferencia no será entregada" del modal
(`handleDiferenciaNoEntregada` → `ejecutarConfirmacion(true)`, `PedidoDetalleView.vue`).

**Aclaración de alcance — `CargarPlantillaView.vue` NO confirma pedidos**: esa pantalla
(ruta `/mba3-consultas/cargar-plantilla/:id`, exclusiva de `mabel.view`) también llama a
`crear-respuesta-desde-pedido` desde un botón llamado "Confirmar", pero pese al nombre
**no es una confirmación real** en el sentido de este punto — es el paso "Fase 3" de Mabel
Trading: guarda cambios y crea la respuesta del proveedor, y de ahí redirige a
Redistribución (Fase 4), que es donde ocurre la confirmación real del flujo de El Rayo. En
este punto del proceso nadie ha tocado aún `total` (ni Producción ni Administración El Rayo
han editado nada todavía), así que `cantidad_solicitada_original` y `total` siempre
coinciden y el endurecimiento de arriba nunca bloquea esta pantalla en uso normal. No se le
agregó el modal de diferencia de producción — confirmado explícitamente por el usuario
(17/08/2026) que en Cargar Plantilla nunca se confirman pedidos, solo se envían
previamente. Queda documentado aquí para que la ambigüedad del nombre del botón no se lea
como una omisión en una futura revisión.

## 1.3 Validación de carga de Excel (Pack/PVP vs. SAP) — Implementado

`pedido_service.py` bloquea la carga si Pack o PVP no coinciden con SAP y sugiere el
valor correcto (RN-02). Sin desviaciones.

## 1.4 Costo en la plantilla Excel — Implementado

Columna `costo_margen` (migración 618): puramente informativa, no llega a SAP ni a la OC
(RN-05). El botón "Descargar Análisis de Margen" (que este punto pide) se implementó como
parte del punto 1.5 — ver abajo.

## 1.5 Margen de Rentabilidad — Implementado

- Fórmula `1 - (Costo Unitario / (PVP / 1.15))` en `pedido_utils.calcular_margen_rentabilidad`.
- **Decisión de diseño**: el insumo real del cálculo es `costo_unitario`
  (`costo_doc_sin_iva / unidad_conversion`, vía `pack_conversion`, migración 619), no
  `costo_margen` (la columna manual del Excel de 1.4). Se prefirió un costo ya conectado al
  pack resuelto por SAP en vez de un valor de entrada manual sin validar. `costo_margen`
  se sigue guardando y mostrando (es parte de 1.4), pero no alimenta el Margen.
- Se muestra en la pantalla de carga por producto (columna "Margen", `CargarPlantillaView.vue`).
- **2026-08-17**: se agregó el botón **"Descargar Análisis de Margen"** en esa misma
  pantalla (cubre el punto pendiente de 1.4 y 1.5: "permitir exportarlo a Excel").
  - Backend: `src/endpoints/pedidos/_excel_margen.py` (nuevo) +
    `GET /api/pedidos/{pedido_id}/margen/exportar-excel` en `pedidos_exportacion.py`.
    Permiso: `mabel.view` u `odcsap.view` — **deliberadamente sin** `produccion-elrayo.view`
    (RN-03).
  - Frontend: botón junto a "Descartar"/"Enviar" en `CargarPlantillaView.vue`, servicio
    `exportarAnalisisMargen` en `services/domains/pedidos.ts`.
  - Exporta: Código, Descripción, Código de Barras, Pack, PVP, Costo (Excel), Costo
    Unitario, Margen de Rentabilidad, Total.
  - **Pendiente de verificar**: que la migración 619 (`costo_unitario`) esté aplicada en
    el ambiente de desarrollo — no se pudo confirmar el 17/08 porque el servidor de BD de
    desarrollo (210.17.1.54) estaba temporalmente apagado. El código tolera la ausencia de
    la columna (degrada `margen=None` sin error), pero hay que confirmarlo cuando el
    servidor esté disponible.

## 1.6 Traslados entre bodega (CEDI Roland ↔ Regions) — Implementado

Allowlist `BODEGAS_TRASLADO_CRUZADO_PERMITIDO` en `stock_transfer_service.py`. Sin
desviaciones; verificado que ningún filtro previo de tienda-por-bodega lo bloquea.

## 1.7 Generación del archivo TXT para MBA3 — Implementado, con una corrección respecto al documento

**Corrección realizada vs. lo solicitado**: el documento (RN-01) pide habilitar el botón
"Generar TXT MBA3" cuando el pedido esté en estado **"Confirmado por El Rayo"**
(`ESTADO_REDISTRIBUCION`, id 4). La primera versión (commit `b40b357`, 04/08) se implementó
así. El commit `8844d8c` (12/08) la corrigió para exigir en su lugar
**`ESTADO_CONFIRMADO_ENVIADO`** (id 12, "CONFIRMADO Y ENVIADO"):

> Motivo: la columna "Orden Compra Cliente" (12) del TXT depende del **DocNum de la Orden
> de Compra en SAP**, y ese DocNum solo existe una vez que la OC fue enviada y aceptada por
> SAP — es decir, en el estado 12, dos pasos después del 4. Generar el archivo en el
> estado 4 (como pide la letra del documento) produciría un TXT con esa columna
> sistemáticamente vacía.

Esta corrección está en el código desde el 12/08 (frontend y backend alineados,
`estado_id === 12`), pero no había quedado documentada como un cambio de alcance aprobado
frente al documento original — este seguimiento cierra ese registro.

**2026-08-17 — reconexión de código muerto**: el flag `pedido["puede_generar_txt_mba3"]`
(`pedidos_crud_helpers.py`) había quedado apuntando al estado viejo (4) tras la corrección
de arriba, y el frontend (`PedidoDetalleView.vue`) dejó de usarlo, duplicando la condición
localmente (`estado_id === 12`) para no romper nada. Se corrigió el flag del backend para
que use `ESTADO_CONFIRMADO_ENVIADO` (ahora es la fuente de verdad real) y se reconectó el
frontend a `pedido.puede_generar_txt_mba3`, con la condición local como respaldo si el
campo no viniera en la respuesta. Sin cambio de comportamiento observable: ambos cálculos
ya daban el mismo resultado, esto solo elimina la duplicación y la desactualización futura.

Otras notas menores (no acciones, solo trazabilidad): "Vendedor" (columna I) no se lee de
una celda del Excel sino de una tabla fija por `origen_traslado`
(`_VENDEDOR_POR_ORIGEN`); no hay truncado explícito de longitud de campo si un valor
excede el máximo documentado en la plantilla MBA3.

## 1.8 Nuevo perfil Producción El Rayo — Implementado, con dos decisiones de alcance

### a) Columna "Cantidad a producir" — decisión deliberada de negocio, no una brecha

El documento pide una columna nueva y separada "Cantidad a producir" para que Producción
registre la cantidad realmente fabricada, distinta de la cantidad solicitada. **Esta
simplificación (reutilizar el campo "Total" existente en vez de crear una columna nueva)
fue analizada y solicitada expresamente por la persona encargada de Administración El
Rayo**, no es una omisión de la implementación. Queda documentado aquí para que no se
reporte como pendiente en una futura auditoría de cobertura.

Detalle técnico de cómo quedó: `produccion-elrayo.view` edita el campo "Total" vía PATCH
(`pedidos_edicion.py`), habilitado por el estado del pedido
(`_ESTADOS_EDITABLES_COSTO_TOTAL_COMENTARIO`). La migración `add_rol_modificador_...sql`
agrega `rol_modificador` para que el resaltado de la celda en pantalla (morado/ámbar)
refleje qué rol hizo la última edición.

### b) Botón "Confirmar Producción" y RN-03 — interpretación revisada

Lectura literal de RN-03 ("el perfil Producción El Rayo no tendrá acceso a ... gestión de
estados del pedido") y del punto 1.8 ("únicamente el usuario administrativo tendrá
permisos para confirmar el pedido y modificar su estado"): un botón que Producción puede
pulsar y que cambia `estado_id` del pedido contradice el texto tal cual está escrito.

Mecánica real verificada en `pedidos_detalle_endpoints.py`
(`_validar_acceso_produccion_el_rayo` / `_validar_acceso_estados_permitidos_produccion_el_rayo`):
un usuario que **solo** tiene `produccion-elrayo.view` (sin `odcsap.view`) únicamente puede
ver/actuar sobre un pedido mientras está en **Nuevo Pedido** o **Gestionar Pedido**. Su
único botón disponible en ese rango es "Confirmar Producción", que transiciona
`GESTIONAR_PEDIDO (3) → CONFIRMADO_POR_PRODUCCION (23)`. En cuanto ocurre esa transición,
ese mismo usuario **pierde el acceso al pedido** — no puede volver a verlo ni tocarlo.

Con ese alcance verificado, la interpretación que se adopta es: RN-03 y el texto de 1.8
apuntan a excluir a Producción de la **gestión operativa** de estados (cancelar,
redistribuir, confirmar hacia SAP, despachar, finalizar, cambiar fechas) — el terreno que
sigue siendo exclusivo de Administración El Rayo / Compras Mabel en todo el flujo restante.
La transición Producción→Confirmado-por-Producción no es gestión abierta de estados: es
una única transición hacia adelante, de un solo uso, que es la forma en que el sistema
recibe la señal "Producción ya registró sus cantidades" que el propio punto 1.8 pide
capturar — sin ella, Administración no tendría manera de saber que el pedido está listo
para su revisión sin una consulta manual. Administración conserva el control real: validar
cantidades, confirmar hacia Mabel, actualizar fecha comprometida y todo cambio de estado
posterior.

Se documenta como interpretación adoptada, no como pendiente de corrección.

### c) Ocultamiento de costos/precios en la API — Implementado (2026-08-17)

RN-03 también dice que Producción "no tendrá acceso a información de costos, precios [ni]
márgenes". Hasta el 17/08 esa restricción era **únicamente de presentación**:
`PedidoDetalleView.vue` ocultaba la columna "Costo Unit." si el usuario era
`produccion-elrayo.view`, pero el JSON de `GET /api/pedidos/{id}` seguía incluyendo
`costo_doc_sin_iva`, `pvp`, `costo_margen`, `costo_unitario` y `margen` sin filtrar por
rol — visible con las herramientas de desarrollador del navegador (pestaña Network).

Se agregó `ocultar_costos_para_produccion_el_rayo()` en `pedidos_crud_helpers.py`: si el
usuario autenticado tiene `produccion-elrayo.view` pero **no** `odcsap.view` ni
`mabel.view`, anula (deja en `None`, no elimina la clave) `costo_doc_sin_iva`,
`descuento_1`, `subtotal`, `costo_margen`, `costo_unitario` y `margen` en cada
`detalle`, y `total_costo_unitario`/`total_subtotal` en `totales`. Deliberadamente **no**
toca `total`/`total_total` (son cantidad, no costo — 1.8 los declara visibles). Se aplica
justo antes de serializar la respuesta HTTP, después de que la lógica interna de la misma
petición ya haya usado el valor real (nunca antes: SAP/OC, notificaciones y auditoría
siguen necesitando el costo verdadero).

**Corrección (2026-08-17, mismo día):** `pvp` se incluyó inicialmente en la lista de campos
redactados por una lectura demasiado amplia de "costos/precios/márgenes" en RN-03. El
usuario aclaró que no corresponde ocultar específicamente el PVP a Producción El Rayo — es
precio de venta al público, no costo ni margen de Mabel — y pidió revertir solo ese campo.
Se sacó `pvp` de `_CAMPOS_COSTO_DETALLE`; el resto de campos (costo, descuento, margen)
sigue redactado sin cambios.

Puntos donde se aplicó (los únicos dos que de verdad exponían estos campos a este rol,
verificado por grep antes de tocar nada — el listado y la respuesta de
`confirmar-produccion` no incluyen costos):
- `pedidos_detalle_endpoints.py` → `GET /api/plantillas/{identificador}` (detalle completo).
- `pedidos_edicion.py` → `PATCH .../detalle/{id}/total`: este es el endpoint que
  Producción usa a diario para registrar cantidades (sustituto de "Cantidad a producir",
  ver punto (a)); sin este fix, el costo total agregado del pedido y el
  `costo_actualizado` (costo individual del detalle, no un booleano) le llegaban en cada
  guardado aunque nunca los pidiera ni los viera en pantalla.

Verificado con pruebas unitarias directas del helper (produccion-elrayo puro → redactado;
odcsap.view, mabel.view, o ambos permisos a la vez → sin cambios; cantidad nunca se
redacta) y con la suite de tests existente (`test_pedidos_edicion.py`,
`test_pedidos_crud_endpoints.py`) sin regresiones nuevas.

**Hallazgo relacionado, fuera de este alcance — pendiente de decisión**: el PATCH
`.../detalle/{id}/costo` no exige ningún permiso además de estar autenticado (el propio
docstring dice "Cualquier usuario autenticado puede editar"), solo valida el estado del
pedido. La UI nunca ofrece ese botón a Producción (la columna "Costo" no existe en su
lista de columnas), pero un usuario `produccion-elrayo.view` con un token válido podría
llamarlo directo por API y **modificar** el costo — RN-03 tampoco lo permite. No se
corrigió en esta sesión (es un cambio de autorización, no de forma de respuesta); queda
pendiente de decidir si se le agrega `require_permission` explícito que excluya
`produccion-elrayo.view`.

## 1.9 Exportación de solicitudes de traslado a Excel — Implementado

Hoja "Traslados (Detalle)" con exactamente las columnas mínimas pedidas, más una matriz
por tienda adicional. Reutiliza los estilos de `_excel_generators.py` (RN-06).

## 1.10 Negociación de Precios MBA3 — Fuera de alcance (explícito en el documento original)

No evaluado; el propio documento lo marca como funcionalidad futura fuera de este ciclo.
