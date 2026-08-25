# Walix — Prompt Utel KB: Carga completa de la Knowledge Base (87 documentos)
> Pegar completo en Claude Code. Adjuntar antes de ejecutar:
> `/add app/api/kb.py`, `/add app/models/knowledge.py`, `/add app/services/rag.py`,
> `/add app/ai/retrieval.py`, `/add app/services/config_loader.py`

**Tiempo estimado:** 2.5–3.5 horas (la mayor parte es la extracción normalizada de 79 PDFs)
**Riesgo de regresión:** Bajo — solo INSERTs de documentos en un tenant nuevo.
**Requiere:** Prompts Utel #1 y #2 ya mergeados a main. Los archivos fuente deben colocarse en
el repo ANTES de correr este prompt (ver "Archivos fuente" abajo).

---

## Archivos fuente — colocar en el repo antes de ejecutar

1. Los 8 documentos ya redactados por Claude (chat), colocarlos tal cual en:
   `scripts/admin/utel_kb_source/00_INDEX.md` ... `08_admision_y_becas.md`
   (Walix los provee — 00, 01, 02, 04, 05, 06, 07, 08. No hay "03" suelto: ese número lo
   ocupan las 79 fichas de licenciatura, generadas por este mismo prompt.)

2. Los 79 PDFs de fichas técnicas (deduplicados — el paquete original traía 82 archivos con
   3 duplicados exactos por hash, ya identificados), colocarlos en:
   `scripts/admin/utel_kb_source/licenciaturas_pdfs/`

```
Vamos a cargar la Knowledge Base completa de Universidad Utel: 8 documentos generales ya
redactados, más 79 fichas de licenciatura que hay que extraer y normalizar desde PDF, para un
total de 87 documentos cargados vía el pipeline real de embeddings (_embed_and_store).

CONTEXTO DEL PROYECTO:
El módulo de Knowledge Base ya está wireado al Copiloto (9 acciones, sesión anterior). Los
documentos se guardan en la tabla documents y se trocean/embeben en knowledge_chunks vía
_embed_and_store (OpenAI embeddings, síncrono). Existe un pipeline real de RAG
(app/services/rag.py, app/ai/retrieval.py) que el bot usa en conversación — no es solo
almacenamiento inerte.

PASO 0 — VERIFICACIÓN OBLIGATORIA ANTES DE CARGAR NADA:
Leer app/services/rag.py, app/ai/retrieval.py y cómo se invocan desde el flujo de mensajes
entrantes de WhatsApp (bot_engine o equivalente, buscar dónde se procesa un mensaje de
Utel/receive_whatsapp_webhook). Confirmar explícitamente que el RAG contra knowledge_chunks
SÍ se ejecuta como parte de generar la respuesta del bot para una branch cualquiera (no
verificar como featureflag opcional que podría estar apagado). Si encuentras que el RAG NO se
invoca automáticamente, o requiere alguna config adicional a nivel branch/tenant que Utel no
tiene activada, DETENTE y repórtalo antes de cargar los 87 documentos — de nada sirve cargar
contenido que el bot nunca va a consultar.

PASO 1 — NORMALIZACIÓN DE LAS 79 FICHAS DE LICENCIATURA

Los 79 PDFs vienen en DOS formatos distintos (confirmarlo tú mismo leyendo 3-4 de cada uno
antes de escribir el parser, no asumir que son idénticos):

- Familia A (~30 PDFs, nombre de archivo "Utel_Mx_Fichas_Tecnicas_..."): secciones "Sobre la
  Licenciatura", "Dónde podrás trabajar", "Lo que aprenderás", listado de "Asignaturas" +
  "Áreas de concentración", créditos totales, RVOE.
- Familia B (~46 PDFs, "Utel_Universidad_Editorial_Mx_..._FT_..." o
  "MX_Licenciatura_..._Nuevos_Programas_Bloque_..."): descripción corta, "Lo que aprenderás"
  (4 puntos), selector de 3 modalidades (en línea/ejecutiva/híbrida, con texto propio de
  modalidad híbrida por programa), Duración (Completa/Intensivo en meses), "Perfil de
  ingreso", "Perfil de egreso", RVOE.

Extraer texto con `pdftotext -layout` (o el método que prefieras, pero -layout preserva mejor
las dos columnas de estos PDFs). Para CADA una de las 79 fichas, generar UN documento markdown
normalizado en scripts/admin/utel_kb_source/03_licenciaturas/ con este esquema común
(independiente de qué familia sea el PDF origen):

```markdown
# Licenciatura en {Nombre}

## Sobre la licenciatura
{descripción, de "Sobre la Licenciatura" en Familia A, o el párrafo corto en Familia B}

## Lo que aprenderás
{lista de puntos/materias destacadas de la ficha}

## Perfil de ingreso
{si la ficha es Familia B, usar el contenido real. Si es Familia A (no tiene esta sección),
escribir: "No disponible en la ficha técnica original — no inventar contenido aquí."}

## Perfil de egreso / Dónde podrás trabajar
{contenido real de la ficha, sea cual sea la sección que lo cubra en cada familia}

## Duración
Programa base: 44 meses · Intensivo: 34 meses · Super intensivo: ~26 meses
(Usar SIEMPRE esta cifra fija confirmada por Walix — NO la cifra distinta que algunas fichas
Familia B traen en su propio PDF, ej. "36 meses". Esto es intencional, ya documentado en
00_INDEX.md como conflicto de fuente resuelto.)

## Modalidad híbrida
Disponible. Ver 02_modalidad_hibrida.md y 04_sedes_horarios.md para el detalle de Power
Skills, precio y sedes — no repetir ese contenido acá, solo confirmar que esta licenciatura
específica SÍ está disponible en modalidad híbrida (las 79 lo están, por decisión de Walix).

## Validez académica
{RVOE número y fecha, tal cual aparece en la ficha — extraerlo exacto, no aproximar}

## Áreas de concentración / especialización
{si la ficha las trae (típico de Familia A), listarlas. Si no aplica, omitir esta sección
completa en vez de dejarla vacía}
```

Reglas para la normalización:
- NO inventar contenido que no esté en el PDF origen. Si una sección no tiene datos, omitirla
  o marcarla como "no disponible" según el caso — nunca rellenar con texto genérico.
- El nombre del archivo de salida debe ser slug del nombre de la licenciatura, ej.
  `03_licenciaturas/mercadotecnia.md`, `03_licenciaturas/ingenieria-robotica.md`.
- Si encuentras alguna ficha con RVOE vencido, sin RVOE, o con algún dato que se vea
  claramente incompleto/roto en la extracción de texto, NO la descartes — cárgala igual pero
  deja un comentario HTML `<!-- REVISAR: ... -->` al inicio del archivo explicando el problema,
  para que Walix lo revise después.
- Título del documento (campo `title` al cargar, máx 255 caracteres): "Licenciatura en
  {Nombre}". Confirmar que ningún nombre de licenciatura + prefijo excede 255 caracteres
  antes de cargar (no debería pasar, pero verificar en vez de asumir).
- Contenido máximo 20,000 caracteres por documento (límite real de create_document,
  confirmado). Ninguna ficha individual debería acercarse a ese límite, pero verificarlo
  programáticamente antes de cargar cada una y reportar si alguna lo excede.

PASO 2 — CARGA DE LOS 87 DOCUMENTOS

SCRIPT: scripts/admin/load_utel_kb.py

Idempotente: si ya existen documentos cargados para el tenant Utel con is_auto_generated=False
y algún filename que coincida con los que este script va a crear, preguntar/abortar antes de
duplicar.

Para cada uno de los 8 documentos generales (00 a 08, sin el 03 suelto) y cada una de las 79
fichas normalizadas de 03_licenciaturas/:
- Llamar directamente a la función de servicio real que create_document usa internamente
  (_embed_and_store + creación de la fila Document) — NO pasar por HTTP, es un script admin
  con acceso directo a DB, igual que los scripts anteriores de Utel.
- title = el H1 del markdown (o "Índice de Knowledge Base — Universidad Utel" para el 00).
- content = el archivo completo.
- tenant_id = tenant de Utel. branch_id = branch principal de Utel (o None si el modelo de
  Document no lo requiere a nivel branch — confirmar leyendo el modelo antes de asumir).
- is_auto_generated = False (contenido curado por Walix, no generado por IA de onboarding).

Imprimir progreso cada 10 documentos (son 87, puede tardar por los embeddings síncronos).
Al final, imprimir resumen: cuántos documentos cargados, cuántos chunks totales generados,
cuántos con el comentario `<!-- REVISAR -->` pendiente de revisión manual.

PASO 3 — TEST: scripts/test_utel_kb.py
a) Confirmar 87 documentos para el tenant Utel (8 + 79), ninguno duplicado por filename.
b) Confirmar que cada uno tiene chunk_count > 0 (se generaron embeddings reales).
c) Confirmar que ningún documento excede los límites de title(255)/content(20000).
d) Hacer una búsqueda RAG real de prueba (usando la función real de app/services/rag.py, no
   un mock) con una query tipo "modalidad híbrida sede Monterrey" y confirmar que el resultado
   incluye contenido de 04_sedes_horarios.md o de la ficha de alguna licenciatura — prueba de
   que el pipeline de principio a fin funciona, no solo que las filas existen en la tabla.
e) Listar cuántas fichas quedaron con el comentario `<!-- REVISAR -->` (si hay, no es un FAIL,
   pero reportarlo explícitamente para que Walix las revise).
f) PASS/FAIL por cada verificación (d es más una prueba funcional que un PASS/FAIL estricto —
   reportar el resultado real de la búsqueda para que Walix lo evalúe).

NOTAS IMPORTANTES:
- Este prompt NO modifica el pipeline de bot ni webhooks — solo carga contenido. Si el Paso 0
  revela que el RAG no está conectado al flujo real de conversación, ESO es un hallazgo para
  reportar y decidir un prompt de fix aparte — no lo arregles silenciosamente acá.
- Los 6 ProductCategory / carrera placeholder de los Demos A y B (Administración de Empresas,
  Mercadotecnia Digital, Psicología, Derecho, Ingeniería Industrial, Contaduría Pública) NO
  coinciden con los nombres reales de este catálogo de 79. Esto ya estaba identificado como
  pendiente — NO lo arregles en este prompt, es un prompt de remediación aparte.
- No commitear los 79 PDFs originales al repo (son pesados y no aportan valor versionado más
  allá de este prompt) — sí commitear los 87 .md normalizados/redactados, que son el contenido
  real que quedó cargado y sirven de fuente de verdad legible.

ORDEN DE EJECUCIÓN:
1. Colocar los 8 .md y los 79 PDFs en scripts/admin/utel_kb_source/ (ver arriba)
2. Ejecutar el Paso 0 (verificación de RAG) y reportar el resultado ANTES de continuar
3. python scripts/admin/normalize_licenciaturas.py (o el nombre que le des al paso 1) →
   revisar cuántas fichas quedaron con REVISAR
4. python scripts/admin/load_utel_kb.py
5. python scripts/test_utel_kb.py → revisar todos los PASS y el resultado de la prueba RAG (d)
6. python scripts/test_webhook.py → confirmar que nada se rompió
7. Commit y push a review/utel-kb-completa — pegar rama + hash al final.
```
