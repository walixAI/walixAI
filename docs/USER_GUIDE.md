# Walix — Guía de Usuario

**Para:** Asesores de ventas, Gerentes, Owners de PyME  
**Versión:** Sprint 13A · Julio 2026

---

## Cómo funciona Walix (visión general)

1. Un cliente te escribe por WhatsApp (o llena un formulario de Meta Ads)
2. El bot de Walix responde automáticamente, le hace preguntas de calificación y recopila datos
3. Cuando el lead está listo (o pide hablar con alguien), el bot te avisa y te entrega el lead
4. Tú continúas la conversación desde el CRM, mueves al lead por el pipeline y cierras
5. Los agentes de IA monitorean tu pipeline en background y te avisan qué hacer a continuación

---

## Roles

| Rol | Qué puede hacer |
|-----|----------------|
| **Asesor** | Ver sus leads asignados, conversar, mover por pipeline, crear actividades |
| **Gerente** | Todo lo del asesor + ver equipo completo, asignar leads, reportes de equipo |
| **Owner** | Todo + configurar el negocio, gestionar billing, ver todos los dashboards |
| **IT** | Acceso técnico a configuración y logs |
| **Platform Owner** | Vista global de todos los tenants (admin Walix) |

---

## 1. Dashboard

Al entrar, ves el dashboard adaptado a tu rol.

### Dashboard de Asesor
- **Mis leads hoy** — cuántos leads tienes activos, cuántos respondieron hoy
- **Actividad pendiente** — tareas y seguimientos que tienes pendientes
- **Sugerencias de IA** — qué recomienda el sistema hacer hoy
- **Chat recientes** — últimas conversaciones activas

### Dashboard de Gerente / Owner
- **KPIs del equipo** — leads creados, calificados, ganados, perdidos (hoy / semana / mes)
- **Performance por asesor** — tabla comparativa del equipo
- **Sentimiento del pipeline** — temperatura general de los leads (interesado, neutral, urgente, negativo)
- **Pipeline health** — % de leads en cada etapa; qué está atascado
- **Sugerencias de IA** — alertas y recomendaciones priorizadas

---

## 2. Contactos (CRM)

Ruta: `/contacts`

### Ver y buscar leads
- La lista muestra todos los leads de tu sucursal
- Usa la **barra de búsqueda** para buscar por nombre, empresa o teléfono
- **Filtros:** status (nuevo, calificado, escalado…), etiqueta, asesor asignado, fechas
- **Ordenar:** por fecha de creación, última actividad, score
- **Vistas guardadas:** guarda combinaciones de filtros que usas frecuentemente

### Detalle de un lead
Haz clic en cualquier lead para abrir su perfil completo:

- **Info básica** — nombre, empresa, teléfono, status, sentimiento, score de calificación
- **Chat** — historial completo de mensajes WhatsApp
- **Timeline** — todas las actividades (notas, llamadas, reuniones, cambios de status)
- **Oportunidades** — deals activos vinculados a este lead
- **Etiquetas** — categorías custom

### Crear una actividad (nota, llamada, tarea)
1. Abre el detalle de un lead
2. En la sección Timeline, haz clic en "+"
3. Elige el tipo (nota, llamada, reunión, email, tarea)
4. Escribe el contenido y guarda
5. Las tareas tienen fecha de vencimiento y se pueden marcar como completadas

### Enviar un mensaje manual
1. Abre el chat del lead
2. Escribe en el campo de texto y envía
3. El mensaje sale por WhatsApp Business directamente

### Cambiar el status de un lead
- En el detalle del lead, haz clic en el badge de status
- Opciones: nuevo → en_calificacion → calificado → escalado → perdido

### Importar leads desde CSV
1. Ve a Contactos → botón "Importar"
2. Descarga la plantilla CSV
3. Llena los datos (nombre, teléfono, empresa, status)
4. Sube el archivo (máx. 1,000 filas)

### Exportar leads
- Botón "Exportar" en la lista de contactos
- Descarga CSV con todos los leads y filtros aplicados

---

## 3. Pipeline

Ruta: `/pipeline` (o `/app/pipeline`)

El pipeline es el tablero Kanban donde mueves leads por las etapas de tu proceso de ventas.

### Vistas disponibles
- **Kanban** (default) — columnas por etapa, cards drag & drop
- **Lista** — tabla con todos los leads/deals ordenados

### Etapas del pipeline
Las etapas son configurables por sucursal. Un ejemplo típico:
```
Nuevo contacto → Calificado → Propuesta enviada → Negociación → Cerrado ganado
                                                              → Cerrado perdido
```

### Mover un lead de etapa
- **Drag & drop** — arrastra el card a la columna destino
- **Desde el detalle** — abre el deal y cambia la etapa desde el dropdown

### Crear un deal / oportunidad
1. Haz clic en "+" en cualquier columna del Kanban
2. Llena: título, monto ($), probabilidad (%), fecha esperada de cierre
3. Vincula a un lead existente
4. El deal aparece en el Kanban

### Health badges (indicadores de salud)
Los cards tienen badges visuales automáticos:
- 🔥 **Hot** — lead muy activo / alta probabilidad
- ⚠️ **Stale** — sin movimiento en más de X días
- ❗ **At-risk** — en riesgo de perderse (score bajó, sin actividad)

### Cerrar una oportunidad
- **Ganado:** Botón "Marcar como ganado" → registra el ingreso
- **Perdido:** Botón "Marcar como perdido" → pide razón de pérdida

### Forecast
Ruta: `/forecast`
- Proyección de revenue para el período seleccionado
- Revenue esperado = suma(monto × probabilidad) por deal abierto
- Filtros: por período, por asesor, por sucursal

---

## 4. WhatsApp y el bot

### Cómo funciona el bot
1. El bot recibe el mensaje del cliente en WhatsApp
2. Saluda y empieza a hacer las preguntas de calificación configuradas en onboarding
3. Va acumulando el perfil del lead (nombre, empresa, necesidad, urgencia)
4. Si detecta que el lead quiere hablar con alguien (dice "quiero hablar con un asesor", "cuánto cuesta", etc.) → **handoff**

### Handoff (entrega al asesor)
- El bot notifica al equipo que hay un lead listo
- El lead aparece marcado como "escalado" en el CRM
- El asesor asignado puede ver el historial completo de la conversación
- El asesor responde desde el CRM; el mensaje llega por WhatsApp al cliente

### Devolver al bot
Si el cliente tiene preguntas simples que el bot puede resolver:
1. Abre el chat del lead
2. Botón "Devolver al bot"
3. El bot retoma la conversación

---

## 5. Sugerencias de IA (Agentes)

Los agentes de IA corren en background durante el día y generan sugerencias para ti.

### Dónde ver las sugerencias
- **Dashboard** — sección de sugerencias activas
- **Agentes** — página dedicada con todas las sugerencias

### Tipos de sugerencias

| Agente | Qué sugiere |
|--------|-------------|
| **Follow-up** | "El lead Juan García lleva 26 horas sin respuesta. Te sugiero enviarle: _[mensaje exacto]_" |
| **Pipeline** | "5 leads llevan más de 7 días en Propuesta enviada. Considera moverlos o cerrarlos." |
| **Closing** | "María López tiene score 82/100. Es buen momento para enviarle propuesta de precio." |
| **Reactivation** | "Carlos Ruiz estuvo interesado hace 45 días. Te sugiero reactivarlo con: _[mensaje]_" |
| **Config** | "Tu etapa Negociación tiene el 40% de los leads. Considera dividirla en pasos más claros." |
| **Enrichment** | "A 8 leads les falta empresa registrada. Pregúntales durante la próxima conversación." |

### Qué hacer con una sugerencia
- **Aceptar** → el sistema ejecuta la acción (envía el mensaje, cambia el status)
- **Descartar** → ignorar esta sugerencia
- Las sugerencias expiran automáticamente después de 24–48h

---

## 6. Knowledge Base

Ruta: Settings → Knowledge Base

La KB es donde subes documentación sobre tu negocio para que el bot pueda responder preguntas específicas.

### Qué subir
- Catálogos de productos o servicios
- Precios y paquetes
- FAQs del negocio
- Políticas de servicio
- Horarios y ubicaciones

### Cómo subirla
1. Ve a Settings → Knowledge Base
2. Botón "Subir documento"
3. Sube PDF, DOCX o TXT
4. El sistema indexa automáticamente (puede tardar 1-2 minutos)

### Cómo usa el bot la KB
Cuando un cliente pregunta algo (ej: "¿qué servicios ofrecen?"), el bot:
1. Busca en la KB los documentos más relevantes
2. Usa esa información para responder con datos reales de tu negocio
3. Cita la información correcta sin inventar

---

## 7. Settings (Configuración)

Ruta: `/app/settings`

### Pestaña: Perfil del negocio
- Nombre de la empresa, industria, descripción
- Logo y configuración visual

### Pestaña: Bot
- **System prompt** — instrucciones del bot (qué es, cómo habla, qué puede y no puede decir)
- **Tono** — formal / amigable / profesional / empático
- **Preguntas de calificación** — qué pregunta el bot para calificar leads
  - Ejemplo clínica: "¿Para quién es la consulta?", "¿Tiene seguro médico?"
  - Ejemplo inmobiliaria: "¿Busca comprar o rentar?", "¿Cuál es su presupuesto?"

### Pestaña: Pipeline
- Nombres y colores de las etapas
- Probabilidad por defecto por etapa
- Marcar etapa como "ganado" o "perdido"

### Pestaña: Alertas
- **Threshold de horas** — después de cuántas horas sin respuesta se genera alerta
- **Horario de silencio** — no enviar alertas de X:00 a X:00 (ej: 20:00 a 08:00)
- **Horario de resumen diario** — a qué hora recibir el resumen del día

### Pestaña: Team
- Ver todos los usuarios de la sucursal
- Invitar nuevos usuarios (email + rol)
- Cambiar rol o desactivar usuario

### Pestaña: Sucursales
- Ver y gestionar sucursales del tenant
- Configurar WhatsApp Business API por sucursal (token + phone number ID)
- Modo de asignación: equitativa (round-robin) o pool

---

## 8. ROI Dashboard

Ruta: `/roi`

Métricas de retorno de inversión:
- **Revenue generado** — suma de deals ganados en el período
- **Revenue por conversión** — configurable en settings del tenant
- **Costo por lead** — si se tiene integración con Meta Ads
- **Tasa de conversión** — leads → calificados → ganados
- **Tiempo promedio de cierre** — desde creación hasta "ganado"

---

## 9. Billing

Ruta: `/billing`

### Ver tu plan actual
- Nombre del plan, fecha de renovación, estado de pago

### Cambiar de plan
1. Ve a `/billing`
2. Compara los planes disponibles
3. Haz clic en "Suscribirse" en el plan deseado
4. Paga con tarjeta via Stripe
5. El sistema activa inmediatamente el nuevo plan

### Gestionar suscripción
- Botón "Portal de suscripción" → abre Stripe Customer Portal
- Ahí puedes cambiar método de pago, ver facturas, cancelar

---

## 10. Alertas automáticas por WhatsApp

Si tu negocio tiene el número interno de WhatsApp configurado, recibes:

| Alerta | Cuándo | Contenido |
|--------|--------|-----------|
| **Lead sin respuesta** | Cuando un lead lleva N horas sin ser atendido | Nombre, teléfono, horas de espera |
| **Resumen diario** | Hora configurada en Settings | KPIs del día: leads creados, calificados, ganados, perdidos |
| **Resumen mensual** | Primero de cada mes, 09:00 | KPIs del mes + comparativa vs mes anterior |

---

## Preguntas frecuentes

**¿Qué pasa si el bot no sabe responder algo?**  
Responde que lo conectará con un asesor y hace el handoff automáticamente.

**¿Puedo ver quién cambió el status de un lead?**  
Sí, el timeline de actividades muestra todos los cambios con usuario y timestamp.

**¿El bot puede enviar imágenes o documentos?**  
Actualmente solo texto y templates de Meta (en desarrollo: media messages).

**¿Puedo tener más de una sucursal?**  
Sí, desde el plan Growth en adelante. Cada sucursal tiene su propio bot, pipeline y equipo.

**¿Qué pasa con mis datos si cancelo?**  
Los datos se conservan 90 días después de la cancelación para que puedas exportarlos.

**¿Los agentes de IA ejecutan acciones solos?**  
No. Los agentes sugieren acciones; tú decides aceptar o descartar cada sugerencia.
