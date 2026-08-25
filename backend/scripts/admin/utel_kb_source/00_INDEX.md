# Knowledge Base — Universidad Utel (Licenciaturas Híbridas)
## Índice de documentos

| Archivo | Contenido | Prioridad |
|---------|-----------|-----------|
| 01_protocolo_perfilamiento.md | Preguntas de precalificación y flujo hasta agendar con asesor | Alta |
| 02_modalidad_hibrida.md | Qué es la modalidad híbrida, Power Skills, Platzi, precio, líneas de cierre | Alta |
| 03_licenciaturas/*.md | Una ficha por licenciatura (79 programas) | Alta |
| 04_sedes_horarios.md | Las 8 sedes reales, direcciones, días/horarios, reglas de asignación | Alta |
| 05_manejo_objeciones.md | Objeciones típicas del modelo híbrido y cómo responderlas | Media |
| 06_mensajes_tipo.md | Conversaciones ejemplo correctas e incorrectas | Media |
| 07_preguntas_frecuentes.md | FAQ general sobre Utel y sus licenciaturas | Baja |
| 08_admision_y_becas.md | Requisitos de inscripción, becas, revalidación, titulación directa | Media |

## Instrucciones para el bot

1. El objetivo del bot es **perfilar y agendar cita con un asesor** — no cerrar la inscripción por WhatsApp. No existe un flujo de pago/inscripción dentro de la conversación.
2. Los documentos de prioridad Alta son los más importantes para precalificar al prospecto.
3. El precio SOLO se menciona si el prospecto pregunta directamente, y siempre como "desde", nunca como cifra cerrada — ver protocolo en 02_modalidad_hibrida.md.
4. Nunca prometer empleo garantizado, porcentaje de beca no confirmado, ni fecha de titulación garantizada — ver sección "Temas que el bot nunca debe responder" en 02_modalidad_hibrida.md.
5. Ante cualquier duda que no esté cubierta en esta KB, o que el prospecto insista después de 2 respuestas del bot, escalar al asesor.
6. Esta KB fue construida a partir de material oficial de Utel (pptx de capacitación comercial, speech de ventas, fichas técnicas por licenciatura, y utel.edu.mx) — con dos conflictos de fuente resueltos explícitamente por decisión de Walix, documentados abajo.

## Conflictos de fuente resueltos (para trazabilidad, no para que el bot los mencione)

- **Licenciaturas disponibles en híbrida:** utel.edu.mx/licenciaturas-hibridas solo lista 24 programas, pero las 79 fichas técnicas en PDF (más recientes, algunas con RVOE de abril 2026) incluyen su propio selector de modalidad híbrida por programa. **Se usa el catálogo de 79** — decisión confirmada por Walix el 25 de agosto de 2026.
- **Duración del programa:** las fichas técnicas en PDF dicen "Base: 44 meses / Intensivo: 36 meses"; la página web dice "Base: 44 / Intensivo: 34 / Super intensivo: ~26 meses". **Se usa la cifra de la página web (44/34/26)** — decisión confirmada por Walix.
- El banner de utel.edu.mx/licenciaturas-hibridas dice "disponible únicamente en CDMX", pero la misma página lista sedes en varios estados. Se trata como texto desactualizado del sitio; **se usan las sedes reales**.
- **Sede Guadalajara (PLAi):** aparecía en el mapa del pptx de capacitación pero no en el listado de utel.edu.mx/licenciaturas-hibridas — quedó marcada como no confirmada. **Walix confirmó el 25 de agosto de 2026 que sigue activa** (C. Independencia 55, Zona Centro, sábados 9am-11am). Ya está incluida en 04_sedes_horarios.md con sus reglas de asignación.

## Pendiente de validación por Utel
- [ ] Confirmar si el WhatsApp de Ventas del pptx (55 4440 9491) es el mismo equipo de asesores conectado a Walix, o un canal humano paralelo.
- [ ] Nombre/persona del bot (la clínica usa "Wali"; Utel no tiene nombre de bot definido todavía — placeholder usado: "[Nombre del bot]").
- [ ] Confirmar vigencia de los datos de sedes (días/horarios) — tomados de utel.edu.mx el 25 de agosto de 2026, pueden cambiar por temporada.
