# Correo al hacer "Enviar" pedido (EL RAYO)

## Resumen según logs (2026-02-24)

Los logs del backend confirman que **el correo de "Plantilla procesada" sí se envía** cuando se hace clic en "Enviar" en cargar-plantilla:

- **Destinatarios (OPERACIONES / EL RAYO):** `asiscomercial@elrayo.com.ec`, `desarrollopdv@elrayo.com.ec`
- **Momento:** al llamar a `POST /api/pedidos/{pedido_id}/enviar` (botón "Enviar").
- **Log esperado:**  
  `✅ Notificación de plantilla procesada enviada a asiscomercial@elrayo.com.ec, desarrollopdv@elrayo.com.ec (Pedido: PREG-02.08.2026)`

Ejemplos en tus logs:

1. **10:24:55** – Pedido `87E652DB-3898-4AE4-BE4C-78F8A92B998E` (PREG-02.08.2026)  
   → Notificación enviada a asiscomercial@elrayo.com.ec, desarrollopdv@elrayo.com.ec  
   → Estado actualizado a NUEVO_PEDIDO (estado_id=2).

2. **10:32:16** – Pedido `7F31C8F5-C7C8-4C5A-BEFD-C9E71BC610F0` (PREG-02.08.2026)  
   → Mismo mensaje de notificación enviada a los mismos destinatarios.

Conclusión: el flujo de "Enviar" y el envío del correo están funcionando en backend; no hace falta cambiar código para que se dispare el correo.

---

## Si "no llega" el correo

Ese correo va **a EL RAYO** (OPERACIONES), no a MABEL TRADING:

- Quien debe recibirlo: buzones de **asiscomercial@elrayo.com.ec** y **desarrollopdv@elrayo.com.ec**.
- Si quien prueba es MABEL (p. ej. cortiz@mabeltrading.com.ec), ese usuario **no** recibirá este correo, porque no está en la lista de destinatarios de "plantilla procesada".

Qué revisar:

1. **Buzón correcto**  
   Revisar en **asiscomercial@elrayo.com.ec** y **desarrollopdv@elrayo.com.ec** (y spam/carpetas de operaciones).

2. **Entrega tras el relay**  
   El backend usa `mabeltrading-com-ec.mail.protection.outlook.com:25`. El log "Notificación de plantilla procesada enviada a…" indica que el envío SMTP fue aceptado. Si no llega a EL RAYO, puede ser filtrado, retraso o reglas en el dominio @elrayo.com.ec.

3. **Destinatarios en BD**  
   Los destinatarios de cada correo salen de `notificacion_persona_correo` (interfaz "Personas y Correos" en `/mba3-consultas/admin/destinatarios`), filtrando por el correo específico del catálogo (`notificacion_tipo_correo`). Si nadie está vinculado a ese correo, no se envía a nadie.

---

## Desarrollo vs producción: override de destinatarios

Para que en **desarrollo** solo el desarrollador reciba todos los correos (y en **producción** sigan yendo a los destinatarios reales de la BD), se implementó el override por entorno:

- **Variable:** `EMAIL_DEV_OVERRIDE` en `.env`.
- **Comportamiento:**  
  Si `ENVIRONMENT=development` **y** `EMAIL_DEV_OVERRIDE` tiene al menos un correo, **todos** los tipos de notificación (OPERACIONES, MABEL_TRADING, HOMOLOGACIONES, TECNICOS, PRODUCCION_ELRAYO) envían a ese(s) correo(s). `notificacion_persona_correo` **no** se consulta en ese caso.
- **Producción:** con `ENVIRONMENT=production` no se usa `EMAIL_DEV_OVERRIDE`; se usa siempre `notificacion_persona_correo` (sin fallback a `.env`).

**Ejemplo .env desarrollo (local):**
```env
ENVIRONMENT=development
EMAIL_DEV_OVERRIDE=cortiz@mabeltrading.com.ec
```

**Producción:** no definir `EMAIL_DEV_OVERRIDE` (o dejarlo vacío) y mantener `ENVIRONMENT=production`; los destinatarios salen de `notificacion_persona_correo` ("Personas y Correos" en el admin).

---

## Flujo resumido

| Paso | Acción | Correo |
|------|--------|--------|
| 1 | Carga plantilla (sync o async) | No se envía correo. Pedido en BORRADOR. |
| 2 | Usuario hace clic en **"Enviar"** | `POST /api/pedidos/{pedido_id}/enviar` → se envía correo a OPERACIONES (EL RAYO) y estado pasa a NUEVO_PEDIDO. |
| 3 | EL RAYO confirma / Despachar y facturar | Otros correos (confirmación, etc.) según flujo. |

El "correo de confirmación de EL RAYO" que sí recibes es **otro** flujo (p. ej. cuando EL RAYO confirma o cuando MABEL finaliza); ese va a otros destinatarios (p. ej. MABEL_TRADING o OPERACIONES según el caso).

---

## Nota sobre GET resultado 400 en carga async

En los logs aparece algo como:

- `GET resultado plantilla-7b8188a71825: enviando validacion_sap con detalle_validacion`
- `GET /api/plantillas/resultado/plantilla-7b... - [400]`

El **400** en `GET /api/plantillas/resultado/{process_id}` es esperado cuando el procesamiento en Celery terminó con **error** (p. ej. validación SAP). El backend devuelve 400 con el detalle del error para que la UI muestre el mensaje y, si aplica, las sugerencias de corrección. No indica fallo del envío de correo; el correo solo se envía al hacer "Enviar" (paso 2 arriba).
