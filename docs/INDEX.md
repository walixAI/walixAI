# Walix — Índice de Documentación

**Actualizado:** Julio 2026 · Sprint 13A

---

## Documentos disponibles

### Para evaluación del producto

| Documento | Descripción |
|-----------|-------------|
| [PRODUCT_STATE.md](PRODUCT_STATE.md) | **Qué se ha construido** — inventario completo de funcionalidades por módulo, arquitectura, métricas del producto y pendientes |
| [USER_GUIDE.md](USER_GUIDE.md) | **Guía de usuario** — cómo usan la plataforma asesores, gerentes y owners; flujos paso a paso |
| [AUTOMATIONS_AND_AI.md](AUTOMATIONS_AND_AI.md) | **Automatizaciones e IA** — los 6 agentes proactivos, el bot conversacional, tareas Celery, RAG, cronograma completo |

### Técnica

| Documento | Descripción |
|-----------|-------------|
| [TECHNICAL.md](TECHNICAL.md) | Stack técnico, modelos de datos, API, multi-tenancy, seguridad, sprints |
| [AI_AGENTS_INVENTORY.md](AI_AGENTS_INVENTORY.md) | Inventario detallado de agentes IA (shapes y payloads) |
| [API_AGENTS_SHAPE.md](API_AGENTS_SHAPE.md) | Shape de la API de agentes (request/response) |
| [OPPORTUNITY_VS_DEAL_AUDIT.md](OPPORTUNITY_VS_DEAL_AUDIT.md) | Auditoría: diferencia entre modelos Opportunity y Deal |
| [CI_SETUP.md](CI_SETUP.md) | Configuración de CI/CD |

---

## Mapa rápido del producto

```
WhatsApp → Bot (Claude Haiku) → CRM → Pipeline Kanban → Cierre
                ↑                         ↑
           Knowledge Base          6 Agentes IA
           (RAG + pgvector)     (Celery Beat, 11 tareas)
                                          ↑
                               Dashboard + Métricas + ROI
```

**Tech:** FastAPI · PostgreSQL+pgvector · Redis · React/Vite · Stripe · Meta WA API · Anthropic · Langfuse
