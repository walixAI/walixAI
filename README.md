# Walix

CRM conversacional sobre WhatsApp para PyMEs mexicanas. Sprint 1: bot para una clínica de endocrinología pediátrica.

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 async (asyncpg) + Alembic
- **Frontend**: Next.js 14 (App Router) + Tailwind
- **Infra**: Postgres en Railway, Redis en Upstash, Claude Haiku para el bot, Langfuse para observabilidad, Meta WhatsApp Business API

## Cómo correrlo en local

Requisitos: Python 3.13, Node 20+, `backend/.env` con las credenciales (ver `Configurar WhatsApp Business API` más abajo para `META_*`).

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

## Scripts

- `backend/scripts/seed.py` — semilla de datos (idempotente)
- `backend/scripts/test_webhook.py` — simula un mensaje entrante de WhatsApp firmado con HMAC contra `localhost:8000`. Útil para probar el flujo bot → Claude → DB sin Meta real.

```bash
cd backend
.venv/bin/python scripts/test_webhook.py
```

## Configurar WhatsApp Business API

Esto vincula tu número de WhatsApp real con el backend. Hay 4 pasos. La primera vez toma ~30 minutos.

### a) Crear una app en developers.facebook.com

1. Entra a [developers.facebook.com](https://developers.facebook.com) con tu cuenta personal de Facebook.
2. Arriba a la derecha: **My Apps** → **Create App**.
3. *Use case*: **Other**. Continúa.
4. *App type*: **Business**. Continúa.
5. Ingresa nombre (ej. "Walix"), email de contacto y vincula (o crea) una **Business Account** en Meta Business Suite.
6. **Create App**.

### b) Agregar el producto WhatsApp

1. En el dashboard de la app, scroll abajo → **Add a product** → busca **WhatsApp** → **Set up**.
2. Meta crea automáticamente:
   - Un **número de prueba** (test number) que puedes usar gratis sin verificación.
   - Un **Phone Number ID** (string numérico, ej. `123456789012345`).
   - Una **WhatsApp Business Account (WABA)**.
   - Un **token temporal de 24 horas** para empezar a probar.

> Para producción necesitas tu propio número (no el de prueba). Eso se hace en **WhatsApp** → **API Setup** → **Add phone number**, y requiere verificación por SMS/llamada.

### c) Configurar el webhook apuntando a tu URL de Railway

1. Despliega el backend a Railway (`railway up` o conecta el repo en railway.app).
2. Tu URL queda como `https://walix-backend-production.up.railway.app` (o similar).
3. En la app de Meta: **WhatsApp** → **Configuration** (menú izquierdo) → sección **Webhook** → **Edit**.
4. Llena:
   - **Callback URL**: `https://TU-APP.up.railway.app/api/webhooks/whatsapp`
   - **Verify token**: el mismo string que pusiste en `backend/.env` como `META_WEBHOOK_SECRET`.
5. **Verify and save**. Meta hace `GET /api/webhooks/whatsapp?hub.verify_token=...&hub.challenge=...` — el backend compara el token con `META_WEBHOOK_SECRET` y echa el challenge. Si ves "Failed to validate callback URL" revisa logs del backend en Railway.
6. Una vez verificado, abajo **Webhook fields** → suscríbete a `messages`. (Opcionalmente también `message_status` si te interesan los read receipts.)

### d) Obtener `META_WHATSAPP_TOKEN` y `META_PHONE_NUMBER_ID`

1. **WhatsApp** → **API Setup**.
2. **Phone Number ID**: aparece arriba del número seleccionado en el dropdown "From". Cópialo a `backend/.env` como `META_PHONE_NUMBER_ID`.
3. **Access token**:
   - **Para desarrollo rápido (24h)**: en la misma página, sección **Temporary access token** → **Copy**.
   - **Para producción (token permanente)**:
     1. Entra a [business.facebook.com](https://business.facebook.com) → **Business Settings** → **Users** → **System Users** → **Add**.
     2. Crea un System User con rol *Admin*.
     3. **Add Assets** → selecciona tu **WhatsApp Account** → marca *Manage* y guarda.
     4. **Generate New Token** → elige la app, scopes `whatsapp_business_messaging` y `whatsapp_business_management` → **Generate**.
     5. Copia el token (no se vuelve a mostrar) a `backend/.env` como `META_WHATSAPP_TOKEN`.
4. Reinicia el backend en Railway para que cargue el nuevo `.env` (o agrega las vars en el panel de Variables de Railway).

### Vincular el número a una sucursal

El `Phone Number ID` también debe quedar en la columna `branches.wa_phone_number_id` para que el webhook resuelva qué sucursal responde. Lo más rápido:

```sql
UPDATE branches
SET wa_phone_number_id = '123456789012345',
    wa_token           = 'EAAxxxx_tu_token_permanente'
WHERE name = 'Monterrey';
```

`seed.py` deja placeholders (`PENDIENTE_MTY`, `PENDIENTE_SF`, `PENDIENTE_CON`) que se reemplazan con los IDs reales cuando configures cada número en Meta.

### Probar punta a punta

Después de configurar Meta y actualizar la fila de la sucursal, manda un WhatsApp **desde tu celular personal** al número de la WABA. Deberías ver en los logs del backend:

```
INFO ... bot_engine: Incoming msg from 521xxxxxxxxxx
INFO ... Claude latency_ms=...
INFO ... WhatsApp API 200
```

Si necesitas debuggear sin mandar mensajes reales, usa `scripts/test_webhook.py` — simula la llamada de Meta con HMAC válido contra tu backend local.
