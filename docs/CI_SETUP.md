# CI/CD Setup — GitHub Actions + Railway

## Resumen de pipelines

| Workflow | Trigger | Qué hace |
|---|---|---|
| `ci.yml` | Push/PR a `main` o `develop` | Tests backend, lint+build frontend, E2E en PRs |
| `deploy-staging.yml` | Push a `develop` | Deploy a Railway Staging |
| `deploy-production.yml` | Push a `main` | Deploy a Railway Production (requiere aprobación manual) |

---

## 1. GitHub Secrets

Ir a **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Descripción |
|---|---|
| `RAILWAY_TOKEN_STAGING` | Token de Railway para el entorno de staging (ver §3) |
| `RAILWAY_TOKEN_PRODUCTION` | Token de Railway para el entorno de producción |
| `ANTHROPIC_API_KEY_TEST` | API key de Anthropic para CI (puede ser la misma de dev) |
| `STAGING_URL` | URL pública del backend de staging, e.g. `https://walix-staging.up.railway.app` |
| `PRODUCTION_URL` | URL pública del backend de producción |

---

## 2. GitHub Environments

Los deploys usan **GitHub Environments** para proteger producción con aprobación manual.

### Crear entornos

Ir a **Settings → Environments → New environment**.

#### `staging`
- Nombre: `staging`
- No requiere protección adicional.
- Añadir la variable `url` con la URL de staging (opcional, mejora el link en el PR).

#### `production`
- Nombre: `production`
- **Activar "Required reviewers"** y añadir el usuario/equipo aprobador.
- Esto bloquea el job de deploy hasta que alguien apruebe en la UI de GitHub.

---

## 3. Obtener Railway Tokens

1. Ir a [railway.app](https://railway.app) → tu proyecto.
2. **Settings → Tokens → New Token**.
3. Crear un token **por entorno** (staging y production en proyectos separados o usando environments de Railway).
4. Copiar el token y añadirlo como secret en GitHub (ver §1).

---

## 4. Configurar Railway Services

El `Procfile` define tres servicios que deben existir en Railway:

```
web:    alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: celery -A app.celery_app worker --loglevel=info --concurrency=2
beat:   celery -A app.celery_app beat --loglevel=info --scheduler celery.beat:PersistentScheduler
```

En Railway, crear tres servicios con el mismo repo:
- **web** — comando del Procfile `web`
- **worker** — comando del Procfile `worker`
- **beat** — comando del Procfile `beat`

Los tres servicios comparten las mismas variables de entorno (ver `backend/.env.example`).

---

## 5. Variables de entorno en Railway

Copiar todas las variables de `backend/.env.example` a cada servicio de Railway (o usar la funcionalidad de "Shared Variables" del proyecto).

Variables críticas:
- `DATABASE_URL` — URL interna de PostgreSQL (`.railway.internal`)
- `REDIS_URL` — Upstash Redis con `rediss://`
- `SECRET_KEY` — generado con `python -c "import secrets; print(secrets.token_hex(32))"`
- `ANTHROPIC_API_KEY`
- `META_VERIFY_TOKEN`, `META_APP_SECRET`

---

## 6. Mock de Anthropic en tests

Para evitar llamadas reales a la API de Anthropic en CI, el conftest de tests debe parchear el cliente de Anthropic. Ejemplo en `backend/tests/conftest.py`:

```python
from unittest.mock import AsyncMock, patch

@pytest.fixture(autouse=True)
def mock_anthropic():
    with patch("anthropic.AsyncAnthropic") as mock_cls:
        instance = mock_cls.return_value
        instance.messages.create = AsyncMock(return_value=...)
        yield instance
```

Si `ANTHROPIC_API_KEY_TEST` es una key real, los tests que la necesitan pueden usarla directamente. En ese caso, asegurarse de que el secret esté configurado en GitHub (ver §1).

---

## 7. Verificar el pipeline

Una vez configurado:

1. Hacer un push a `develop` → debe disparar `ci.yml` y `deploy-staging.yml`.
2. Abrir un PR de `develop` a `main` → `ci.yml` ejecuta los tests + E2E.
3. Hacer merge a `main` → `deploy-production.yml` pausa esperando aprobación.
4. Aprobar el deploy en **Actions → el workflow run → Review deployments**.
5. El health check final confirma que `/health` responde `{"status": "ok"}`.
