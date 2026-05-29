# Walix

CRM conversacional sobre WhatsApp para PyMEs mexicanas. Sprint 1: bot para una clínica de endocrinología pediátrica.

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 async (asyncpg) + Alembic
- **Frontend**: Next.js 14 (App Router) + Tailwind
- **Infra**: Postgres en Railway, Redis en Upstash, Claude Haiku para el bot, Langfuse para observabilidad, Meta WhatsApp Business API

## Flujo de trabajo

```
desarrollo local con test_webhook.py  →  git push main  →  Railway deploy automático  →  WhatsApp real apuntando a Railway
```

- **Local** no recibe mensajes reales de WhatsApp. Se prueba con `scripts/test_webhook.py` que firma un POST con HMAC válido.
- **Railway** es el único host que ve a Meta. El webhook de Meta apunta a la URL pública de Railway, no a localhost ni a ngrok.

## Correrlo en local

Requisitos: Python 3.13, Node 20+, `backend/.env` con las credenciales.

```bash
# backend (terminal 1)
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py                # crea tenant + 3 sucursales + 4 users
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend (terminal 2)
cd frontend
npm install
npm run dev                                     # http://localhost:3000
```

Login de prueba (creado por `seed.py`):

| email | role | password |
|---|---|---|
| `owner@clinica.com` | owner | `walix2026` |
| `asesor.mty@clinica.com` | asesor (Monterrey) | `walix2026` |
| `asesor.sf@clinica.com` | asesor (Santa Fe CDMX) | `walix2026` |
| `asesor.con@clinica.com` | asesor (Condesa CDMX) | `walix2026` |

### Probar el bot localmente sin Meta

```bash
cd backend
.venv/bin/python scripts/test_webhook.py
```

El script construye un payload con formato Meta, lo firma con HMAC-SHA256 usando `META_APP_SECRET` del `.env`, y POSTea a `localhost:8000/api/webhooks/whatsapp`. Dispara el flujo completo: HMAC verify → resolve branch → crear lead → llamar a Claude → guardar mensajes → intentar send a WhatsApp (fallará si `branches.wa_token` está vacío, no afecta al test).

Vas iterando en local hasta que el bot responda como quieres, sin gastar mensajes de la cuota gratuita de Meta.

## Variables de entorno del backend

| Variable | Donde se usa | Notas |
|---|---|---|
| `DATABASE_URL` | conexión interna a Postgres | En Railway lo enchufas con `${{Postgres.DATABASE_URL}}`. En local, ignorado en favor de `DATABASE_PUBLIC_URL` cuando `APP_ENV=development`. |
| `DATABASE_PUBLIC_URL` | conexión externa a Postgres | Solo necesario en local (la URL interna `.railway.internal` no resuelve fuera de Railway). |
| `REDIS_URL` | cache, dedup de webhooks, historial de conversación | Upstash con esquema `rediss://`. |
| `ANTHROPIC_API_KEY` | llamadas al modelo | console.anthropic.com → API Keys. |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | traces del bot | langfuse.com → Project → Settings → API Keys. |
| `META_VERIFY_TOKEN` | webhook handshake GET (Meta envía `hub.verify_token`, comparas con esto) | String arbitrario que tú eliges. Lo escribes en el campo "Verify Token" de Meta y aquí. |
| `META_APP_SECRET` | firma HMAC-SHA256 de cada POST entrante de Meta | Meta → Settings → Basic → **App Secret** → Show. |
| `APP_ENV` | `development` o `production` | En dev fuerza `DATABASE_PUBLIC_URL` y `echo=True` en SQLAlchemy. |
| `SECRET_KEY` | firma JWT del login | En prod: `openssl rand -hex 32`. |
| `OPENAI_API_KEY` | embeddings para RAG | platform.openai.com → API Keys. Solo necesario si se usa la KB (Sprint 2+). |
| `FRONTEND_URL` | CORS | En prod = tu URL de Vercel. |

## Configurar WhatsApp Business API contra Railway

Meta necesita una URL pública HTTPS. La nuestra es la de Railway directamente — no se usa ngrok.

**Conceptos rápidos:**

| Concepto | Vive en | Para qué sirve |
|---|---|---|
| `META_VERIFY_TOKEN` | env var (.env + Railway Variables) | string que tú eliges; Meta lo manda en el GET de verificación. |
| `META_APP_SECRET` | env var | string que Meta generó para tu app; valida HMAC de los POST. |
| `wa_phone_number_id` | columna `branches` | ID del número (`+15551907107` → un número de 15 dígitos). |
| `wa_token` | columna `branches` | bearer token para enviar mensajes salientes. |

### Pasos (una sola vez)

**1. App + WhatsApp en developers.facebook.com**

[developers.facebook.com](https://developers.facebook.com) → **My Apps** → **Create App** → tipo **Business**. Después en el dashboard de la app: **Add a product** → **WhatsApp** → **Set up**. Meta te asigna automáticamente:
- Número de prueba (en este caso `+15551907107`)
- Su Phone Number ID
- Un token temporal (24h)

**2. Sacar el App Secret**

Meta dashboard → **Settings** → **Basic** → **App Secret** → **Show** → copia. Este es el valor de `META_APP_SECRET`.

**3. Setear env vars en Railway**

En el panel de Railway → tu servicio backend → **Variables**:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=rediss://default:...@allowed-jaguar-70088.upstash.io:6379
ANTHROPIC_API_KEY=sk-ant-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com
META_VERIFY_TOKEN=walix_webhook_secret_2026
META_APP_SECRET=<App Secret de Meta>
APP_ENV=production
SECRET_KEY=<openssl rand -hex 32>
FRONTEND_URL=https://<tu-proyecto>.vercel.app
```

**Importante**: `DATABASE_PUBLIC_URL` **NO** se pone en Railway (sólo en local). `META_VERIFY_TOKEN` tiene que ser exactamente el mismo string que pongas en el UI de Meta.

**4. Push a GitHub → Railway redeploya**

```bash
git push origin main
```

Railway detecta el push, instala deps, corre `alembic upgrade head` y arranca uvicorn (definido en `backend/Procfile`). Espera unos 60s y revisa el log en el panel de Railway: tiene que llegar a `Uvicorn running on http://0.0.0.0:PORT`.

Tu URL queda como `https://<servicio>-production.up.railway.app`. Anótala.

**5. Configurar el webhook en Meta apuntando a Railway**

Meta → **WhatsApp** → **Configuration** → sección **Webhook** → **Edit**:

- **Callback URL**: `https://<servicio>-production.up.railway.app/api/webhooks/whatsapp`
- **Verify token**: el mismo valor que pusiste en `META_VERIFY_TOKEN` en Railway Variables.

Click **Verify and save**. Meta hace un GET al webhook con `hub.verify_token` y `hub.challenge`. Tu backend en Railway lo verifica y devuelve el challenge. Si dice "Failed to validate callback URL":
- Revisa los logs de Railway — `META_VERIFY_TOKEN` mal escrito es la causa más común.
- Confirma que `/health` responde 200 abriendo `https://<servicio>.up.railway.app/health` en el browser.

Una vez verificado, abajo en **Webhook fields** → suscríbete a `messages`.

**6. Vincular el número a una sucursal (DB update)**

El **Phone Number ID** y el **access token** van en la fila de `branches` que vaya a manejar ese número. Saca ambos de Meta → **WhatsApp** → **API Setup**:

- Phone Number ID: arriba del dropdown "From".
- Access token: copia el "Temporary access token" (24h), o genera uno permanente vía System User en Business Manager.

Luego conecta al Postgres con tu `DATABASE_PUBLIC_URL` y corre:

```sql
UPDATE branches
SET wa_phone_number_id = '<phone_number_id_de_meta>',
    wa_token           = '<access_token_de_meta>'
WHERE name = 'Monterrey';
```

El seed dejó placeholders `PENDIENTE_MTY`, `PENDIENTE_SF`, `PENDIENTE_CON`. Sólo `Monterrey` quedará respondiendo hasta que asignes el resto de números.

**7. Probar de verdad**

Desde tu celular (`+5215535637687`) manda un WhatsApp al número de prueba (`+15551907107`). En los logs de Railway debería aparecer:

```
INFO app.api.webhooks: POST /api/webhooks/whatsapp 200 OK
INFO app.ai.bot_engine: Claude latency_ms=... tokens_used=...
INFO app.services.whatsapp: WhatsApp API 200
```

Y la respuesta de Wali llega a tu chat.

## Frontend en Vercel

En Vercel → tu proyecto → **Settings** → **Environment Variables**:

```
NEXT_PUBLIC_API_URL=https://<servicio>-production.up.railway.app
```

Aplica para Production, Preview y Development. Después del primer set, fuerza un redeploy desde el dashboard.

## Flujo de release

```
git push origin main
    ↓
Railway: alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
Vercel:  npm run build
```

Ambos hacen build automáticamente al detectar el push. Si rompes algo, Railway/Vercel mantienen el último deploy bueno hasta que el nuevo pase build.

## Sprint 2 — Setup (RAG + Calificación automática)

### Variables de entorno adicionales

Agrega en `backend/.env` y en Railway Variables:

```
OPENAI_API_KEY=sk-proj-...
```

### Pasos (una sola vez por entorno)

```bash
# 1. Aplicar migraciones nuevas (pgvector, knowledge_chunks, contact_phone, doctor role)
cd backend
.venv/bin/alembic upgrade head

# 2. Indexar la knowledge base en pgvector
.venv/bin/python scripts/ingest_kb.py
# Output esperado:
#   ✓ 00_INDEX.md: 3 chunks indexados
#   ✓ 01_protocolo_calificacion.md: 12 chunks indexados
#   ...
#   Total: 7 documento(s) indexado(s), 98 chunks, estimado $0.0009 USD

# 3. Verificar que el retrieval funciona
.venv/bin/python scripts/test_rag.py
# Debe mostrar fragmentos relevantes para las 5 queries de prueba

# 4. Crear usuarios de prueba (asistente, doctor, IT) si no existen
.venv/bin/python scripts/add_test_users.py
```

### Probar la calificación automática end-to-end

Con el backend corriendo (`uvicorn app.main:app --reload --port 8000`):

```bash
.venv/bin/python scripts/test_qualification.py
```

Envía 4 mensajes al webhook local simulando a una mamá que llega por el anuncio. Al final muestra el lead creado con su `qualification_data` y `qualification_score`.

### Re-indexar la KB desde el dashboard (producción)

Llama a `POST /api/kb/reindex` con un token de usuario `owner` o `it`.
Consulta el estado con `GET /api/kb/status`.

## Scripts útiles

```bash
backend/scripts/seed.py               # crea tenant + 3 sucursales + users (idempotente)
backend/scripts/add_test_users.py     # agrega asistente/doctor/it a tenant existente
backend/scripts/test_webhook.py       # un mensaje de prueba firmado contra localhost:8000
backend/scripts/test_rag.py           # verifica retrieval híbrido con 5 queries
backend/scripts/test_qualification.py # conversación completa de calificación end-to-end
backend/scripts/ingest_kb.py          # indexa backend/scripts/walix_kb/*.md en pgvector
```
