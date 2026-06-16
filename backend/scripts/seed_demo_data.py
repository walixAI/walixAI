"""seed_demo_data.py — Genera datos de prueba realistas para la clínica beta.

Crea:
  - Pipeline stages de salud para todas las branches
  - 45 leads con nombres mexicanos, distribuidos en los últimos 30 días
  - Conversaciones y mensajes WhatsApp simulados (bot + paciente)
  - Lead scores con factores positivos/negativos
  - Agent suggestions de los 4 tipos (follow_up, closing, pipeline, reactivation)
  - Daily metrics (30 días de historial)
  - Sentiment snapshots (30 días)
  - Revenue configurado: $850 MXN por conversión

Uso:
  cd backend
  .venv/bin/python scripts/seed_demo_data.py

Es idempotente: detecta lo existente y omite duplicados.
"""

from __future__ import annotations

import asyncio
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.agent import AgentSuggestion
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.metrics import DailyMetric, SentimentSnapshot
from app.models.pipeline import PipelineStage
from app.models.scoring import LeadScore
from app.models.tenant import Branch, Tenant
from app.models.user import User, UserRole

random.seed(42)

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()

# ── Pipeline stages ───────────────────────────────────────────────────────────

HEALTH_STAGES = [
    {"key": "consulta_inicial",   "label": "Consulta Inicial",   "order": 0, "color": "#3B82F6", "is_won": False, "is_lost": False},
    {"key": "primera_cita",       "label": "Primera Cita",        "order": 1, "color": "#8B5CF6", "is_won": False, "is_lost": False},
    {"key": "estudios",           "label": "Estudios / Labs",     "order": 2, "color": "#F59E0B", "is_won": False, "is_lost": False},
    {"key": "seguimiento",        "label": "Seguimiento",         "order": 3, "color": "#10B981", "is_won": False, "is_lost": False},
    {"key": "tratamiento_activo", "label": "Tratamiento Activo",  "order": 4, "color": "#06B6D4", "is_won": False, "is_lost": False},
    {"key": "alta",               "label": "Alta Médica",         "order": 5, "color": "#22C55E", "is_won": True,  "is_lost": False},
    {"key": "no_continuo",        "label": "No continuó",         "order": 6, "color": "#EF4444", "is_won": False, "is_lost": True},
]

# ── Pacientes ficticios ───────────────────────────────────────────────────────

PACIENTES = [
    ("María López Hernández",     8,  "Mi hijo no está creciendo bien",              "interesado", "whatsapp_inbound"),
    ("Ana Martínez García",       5,  "Mi niña tiene hipotiroidismo congénito",      "urgente",    "whatsapp_inbound"),
    ("Carlos Rodríguez Sánchez",  12, "Mi hijo tiene diabetes tipo 1",               "urgente",    "meta_ads"),
    ("Laura González Pérez",      7,  "Revisión anual de hormona de crecimiento",    "interesado", "whatsapp_inbound"),
    ("Roberto Jiménez Torres",    10, "Pubertad precoz en mi hija",                  "urgente",    "whatsapp_inbound"),
    ("Sofía Ramírez Cruz",        3,  "Hipotiroidismo neonatal detectado",           "urgente",    "meta_ads"),
    ("Miguel Flores Díaz",        9,  "Obesidad infantil con resistencia insulina",  "interesado", "whatsapp_inbound"),
    ("Patricia Morales Vega",     6,  "Retraso en el desarrollo puberal",            "interesado", "whatsapp_inbound"),
    ("Jorge Herrera Castillo",    11, "Control de diabetes mellitus tipo 1",         "urgente",    "meta_ads"),
    ("Carmen Reyes Núñez",        4,  "Mi niña no sube de peso",                    "interesado", "whatsapp_inbound"),
    ("Eduardo Vargas Ríos",       8,  "Hipoglucemia recurrente",                     "urgente",    "whatsapp_inbound"),
    ("Isabel Mendoza Luna",       13, "Síndrome de ovario poliquístico",             "interesado", "whatsapp_inbound"),
    ("Alejandro Castro Medina",   7,  "Talla baja familiar",                         "neutral",    "whatsapp_inbound"),
    ("Guadalupe Ortiz Salinas",   5,  "Hipotiroidismo subclínico",                   "interesado", "meta_ads"),
    ("Fernando Ruiz Espinoza",    10, "Ginecomastia puberal",                        "neutral",    "whatsapp_inbound"),
    ("Valentina Guzmán Paredes",  6,  "Retraso de crecimiento intrauterino",         "interesado", "whatsapp_inbound"),
    ("Héctor Moreno Aguilar",     9,  "Hipercortisolismo sospechado",                "urgente",    "meta_ads"),
    ("Adriana Soto Leal",         11, "Amenorrea primaria",                          "interesado", "whatsapp_inbound"),
    ("Ricardo Peña Sandoval",     4,  "Micropene detectado en control pediátrico",   "urgente",    "whatsapp_inbound"),
    ("Daniela Fuentes Barrera",   8,  "Hipertiroidismo en niña de 8 años",          "urgente",    "meta_ads"),
    ("José Guerrero Contreras",   12, "Control de insulina con bomba",               "interesado", "whatsapp_inbound"),
    ("Rosa Delgado Miranda",      6,  "Hipoglucemia neonatal tardía",                "urgente",    "whatsapp_inbound"),
    ("Andrés León Campos",        10, "Acromegalia pediátrica evaluación",           "neutral",    "whatsapp_inbound"),
    ("Esperanza Ríos Velasco",    7,  "Segunda opinión crecimiento",                 "negativo",   "meta_ads"),
    ("Marco Serrano Alvarado",    5,  "Criptorquidia con evaluación hormonal",       "interesado", "whatsapp_inbound"),
    ("Diana Torres Iglesias",     9,  "Hiperprolactinemia en adolescente",           "interesado", "meta_ads"),
    ("Luis Ramos Pedraza",        11, "Diabetes mellitus tipo 2 en adolescente",     "urgente",    "whatsapp_inbound"),
    ("Mónica Cervantes Palma",    8,  "Deficiencia de hormona de crecimiento",       "interesado", "whatsapp_inbound"),
    ("Raúl Acosta Villanueva",    6,  "Hipotiroidismo autoinmune Hashimoto",         "neutral",    "whatsapp_inbound"),
    ("Ximena Romero Jiménez",     13, "PCOS con hiperandrogenismo",                  "interesado", "meta_ads"),
    ("Pablo Medina Espino",       7,  "Talla baja grave, percentil < 3",            "urgente",    "whatsapp_inbound"),
    ("Natalia Vázquez Téllez",    4,  "Bocio neonatal detectado en tamiz",           "urgente",    "whatsapp_inbound"),
    ("Alberto Muñoz Coronel",     10, "Seguimiento tiroides con ultrasonido",        "neutral",    "whatsapp_inbound"),
    ("Claudia Aguilar Zamora",    12, "Hirsutismo en adolescente",                   "interesado", "meta_ads"),
    ("Ernesto Silva Pacheco",     8,  "Obesidad mórbida con alteración glucosa",     "urgente",    "whatsapp_inbound"),
    ("Sandra Ibáñez Montoya",     5,  "Insuficiencia suprarrenal en niña",          "urgente",    "whatsapp_inbound"),
    ("Rodrigo Cabrera Ochoa",     9,  "Hipotiroidismo post quirúrgico",              "interesado", "meta_ads"),
    ("Verónica Pedraza Garza",    7,  "Retraso de menarca",                          "interesado", "whatsapp_inbound"),
    ("Sergio Núñez Padilla",      11, "Diabetes insípida central",                   "urgente",    "whatsapp_inbound"),
    ("Alicia Flores Benítez",     6,  "Deficiencia vitamina D con raquitismo",      "interesado", "whatsapp_inbound"),
    ("Tomás Ávila Bermúdez",      13, "Ginecomastia patológica evaluación",          "neutral",    "meta_ads"),
    ("Marisol Guerrero Téllez",   8,  "Hiperinsulinismo congénito",                  "urgente",    "whatsapp_inbound"),
    ("Gustavo Herrera Montiel",   10, "Segunda cita hormona crecimiento",            "interesado", "whatsapp_inbound"),
    ("Beatriz Sáenz Villanueva",  5,  "Hiperplasia suprarrenal congénita",           "urgente",    "meta_ads"),
    ("Enrique Ponce Medrano",     12, "Obesidad con síndrome metabólico",            "interesado", "whatsapp_inbound"),
]

BOT_MSGS = [
    "Hola, soy Mila, la asistente virtual de la Clínica de Endocrinología Pediátrica 👋 ¿En qué puedo ayudarte?",
    "Entiendo tu preocupación. El Dr. González atiende casos similares con excelentes resultados. ¿Cuál es la edad de tu hijo/a y el diagnóstico previo si tienen?",
    "Perfecto. Para agendar, necesito: nombre completo del paciente, fecha de nacimiento y tu nombre como tutor. ¿Tienes disponibilidad entre semana o prefieres sábado?",
    "Muchas gracias. He registrado tu solicitud. El equipo revisará tu caso y te confirmará la cita en máximo 2 horas. ¿Tienes estudios recientes que debas traer?",
    "¡Listo! Tu cita queda tentativa para el jueves a las 10:00 AM con el Dr. González. Recibirás confirmación por este medio. ¿Necesitas indicaciones para llegar?",
]

PATIENT_MSGS_HIGH = [
    "Muchas gracias. ¿Tienen disponibilidad esta semana?",
    "Sí, tengo resultados de laboratorio del mes pasado.",
    "Perfecto, los martes me vienen bien.",
    "Mi hijo fue diagnosticado y necesitamos cita urgente.",
    "¿Cuánto cuesta la primera consulta?",
    "Sí acepto la cita del jueves.",
]

PATIENT_MSGS_LOW = [
    "Hola, buenas tardes.",
    "Quiero información.",
    "¿Dónde están ubicados?",
    "¿Tienen doctora mujer?",
]

AGENT_SUGGESTIONS_DATA = [
    {
        "agent_type": "follow_up",
        "trigger": "Lead sin respuesta en más de 24 horas tras primera consulta del bot",
        "text": "María López no ha respondido desde ayer. Sugiero enviar mensaje de seguimiento recordando que su cita puede agendarse esta semana. Score de conversión: 82/100.",
        "role": "asesor", "status": "suggested",
    },
    {
        "agent_type": "closing",
        "trigger": "Lead con score alto estancado en Consulta Inicial por más de 5 días",
        "text": "Carlos Rodríguez (diabetes tipo 1, score 91) lleva 5 días en Consulta Inicial sin avanzar. Recomiendo moverlo directamente a Primera Cita y asignar al Dr. González.",
        "role": "gerente", "status": "suggested",
    },
    {
        "agent_type": "pipeline",
        "trigger": "Acumulación de leads en etapa Estudios/Labs > 7 días",
        "text": "8 pacientes llevan más de 7 días esperando resultados de laboratorio. ¿Deseas que envíe recordatorio automático para agilizar el proceso?",
        "role": "owner", "status": "accepted",
    },
    {
        "agent_type": "follow_up",
        "trigger": "Paciente urgente sin asignación a doctor hace más de 3 horas",
        "text": "Ana Martínez (hipotiroidismo congénito, 5 años) fue marcada como URGENTE hace 3 horas y aún no tiene doctor asignado. Asignar al Dr. González inmediatamente.",
        "role": "gerente", "status": "confirmed",
    },
    {
        "agent_type": "reactivation",
        "trigger": "Leads perdidos hace 45+ días con historial de consultas pagadas",
        "text": "Identifiqué 4 leads que no continuaron el mes pasado por razones económicas. Han pasado 45 días — buen momento para contactarlos con información sobre financiamiento de 6 meses sin intereses.",
        "role": "owner", "status": "suggested",
    },
    {
        "agent_type": "closing",
        "trigger": "Paciente en tratamiento activo sin próxima cita agendada > 21 días",
        "text": "Roberto Jiménez lleva 3 semanas en Tratamiento Activo sin próxima cita agendada. Riesgo de abandono: 67%. Sugerencia: agendar revisión mensual esta semana.",
        "role": "asesor", "status": "suggested",
    },
    {
        "agent_type": "pipeline",
        "trigger": "Tasa de conversión semanal por debajo del promedio histórico",
        "text": "Esta semana la tasa de conversión es 31% vs 42% del promedio mensual. Los leads de Meta Ads convierten menos (18%). ¿Reviso los criterios del anuncio activo?",
        "role": "owner", "status": "dismissed",
    },
    {
        "agent_type": "follow_up",
        "trigger": "Sentimiento negativo detectado en conversación activa",
        "text": "Detecté frustración en la conversación de Esperanza Ríos: 'ya fui a otra clínica y no me dieron resultados claros'. Intervención humana recomendada antes de perder el lead.",
        "role": "asesor", "status": "executed",
    },
]


def ts(days_back: int, hour: int = 10, minute: int = 0) -> datetime:
    return (NOW - timedelta(days=days_back)).replace(
        hour=hour, minute=minute, second=0, microsecond=0, tzinfo=timezone.utc
    )


async def main() -> None:
    print("\n" + "="*55)
    print("  Walix — Seed Demo Data para Clínica Beta")
    print("="*55 + "\n")

    async with AsyncSessionLocal() as db:
        await db.execute(text("SET LOCAL app.current_tenant_id = '00000000-0000-0000-0000-000000000000'"))

        # ── Tenant ─────────────────────────────────────────────────────────────
        tenant = (await db.execute(
            select(Tenant).where(Tenant.email == "admin@clinica.com")
        )).scalar_one_or_none()
        if tenant is None:
            print("✗ Tenant no encontrado. Ejecuta primero: .venv/bin/python scripts/seed.py")
            sys.exit(1)
        print(f"✓ Tenant: {tenant.name}")

        # ── Branches ───────────────────────────────────────────────────────────
        branches = (await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id, Branch.is_active.is_(True))
        )).scalars().all()
        mty = next((b for b in branches if "monterrey" in b.name.lower()), branches[0])
        print(f"✓ Branches: {[b.name for b in branches]}  →  usando '{mty.name}' como principal")

        # ── Usuarios ───────────────────────────────────────────────────────────
        users = (await db.execute(
            select(User).where(User.tenant_id == tenant.id, User.is_active.is_(True))
        )).scalars().all()
        asesores = [u for u in users if u.role in (UserRole.ASESOR, UserRole.DOCTOR) and u.branch_id == mty.id]
        owner    = next((u for u in users if u.role == UserRole.OWNER), None)
        print(f"✓ Usuarios: {len(users)} total")

        # ── Pipeline stages ────────────────────────────────────────────────────
        print("\n── Pipeline stages ──")
        existing_stages = (await db.execute(
            select(PipelineStage).where(
                PipelineStage.branch_id == mty.id,
                PipelineStage.tenant_id == tenant.id,
            )
        )).scalars().all()

        stage_map: dict[str, PipelineStage] = {}
        if existing_stages:
            print(f"  → Ya existen {len(existing_stages)} stages en '{mty.name}'")
            stage_map = {s.stage_key or s.slug: s for s in existing_stages}
            # Ensure our required keys exist
            for spec in HEALTH_STAGES:
                if spec["key"] not in stage_map:
                    sid = uuid.uuid4()
                    await db.execute(text("""
                        INSERT INTO pipeline_stages
                          (id, tenant_id, branch_id, name, slug, stage_key, order_index,
                           color, is_won, is_lost, is_active, created_at, updated_at)
                        VALUES (:id,:tid,:bid,:name,:slug,:sk,:oi,:col,:iw,:il,true,NOW(),NOW())
                        ON CONFLICT DO NOTHING
                    """), {
                        "id": sid, "tid": tenant.id, "bid": mty.id,
                        "name": spec["label"], "slug": spec["key"], "sk": spec["key"],
                        "oi": spec["order"], "col": spec["color"],
                        "iw": spec["is_won"], "il": spec["is_lost"],
                    })
                    # Reload
                    r = (await db.execute(
                        select(PipelineStage).where(
                            PipelineStage.branch_id == mty.id,
                            PipelineStage.stage_key == spec["key"],
                        )
                    )).scalar_one_or_none()
                    if r:
                        stage_map[spec["key"]] = r
        else:
            for spec in HEALTH_STAGES:
                sid = uuid.uuid4()
                s = PipelineStage(
                    id=sid,
                    tenant_id=tenant.id,
                    branch_id=mty.id,
                    name=spec["label"],
                    slug=spec["key"],
                    stage_key=spec["key"],
                    order_index=spec["order"],
                    color=spec["color"],
                    is_won=spec["is_won"],
                    is_lost=spec["is_lost"],
                    is_active=True,
                )
                db.add(s)
                stage_map[spec["key"]] = s
            await db.flush()
            print(f"  ✓ {len(HEALTH_STAGES)} stages creados para '{mty.name}'")

        # ── Revenue config ─────────────────────────────────────────────────────
        if tenant.roi_revenue_per_conversion is None:
            tenant.roi_revenue_per_conversion = 850
            print("✓ Revenue configurado: $850 MXN por conversión")

        # ── Leads ──────────────────────────────────────────────────────────────
        print("\n── Leads (pacientes) ──")
        existing_phones = {
            r[0] for r in (await db.execute(
                select(Lead.wa_phone).where(Lead.tenant_id == tenant.id, Lead.deleted_at.is_(None))
            )).fetchall()
        }
        print(f"  Existentes: {len(existing_phones)}")

        # Stage distribution for a realistic funnel
        stage_weights = [
            ("consulta_inicial",   16),
            ("primera_cita",       9),
            ("estudios",           7),
            ("seguimiento",        5),
            ("tratamiento_activo", 5),
            ("alta",               6),
            ("no_continuo",        3),
        ]
        stage_pool = [k for k, w in stage_weights for _ in range(w)]

        qual_map = {
            "consulta_inicial":   (None,  LeadStatus.NUEVO),
            "primera_cita":       (72.0,  LeadStatus.CALIFICADO),
            "estudios":           (81.0,  LeadStatus.CALIFICADO),
            "seguimiento":        (85.0,  LeadStatus.CALIFICADO),
            "tratamiento_activo": (88.0,  LeadStatus.CALIFICADO),
            "alta":               (92.0,  LeadStatus.CALIFICADO),
            "no_continuo":        (35.0,  LeadStatus.PERDIDO),
        }

        new_leads: list[Lead] = []
        for i, (nombre, edad, motivo, sent_str, src_str) in enumerate(PACIENTES):
            phone = f"521553{5600000 + i:07d}"
            if phone in existing_phones:
                continue

            days_back = random.randint(1, 28)
            created   = ts(days_back, hour=random.randint(8, 18), minute=random.randint(0, 59))
            sk        = random.choice(stage_pool)
            stage     = stage_map.get(sk)
            qual, status = qual_map[sk]
            if qual is not None:
                qual = round(qual + random.uniform(-8, 8), 1)

            handoff_at = None
            if sk not in ("consulta_inicial", "no_continuo") and qual and qual >= 60:
                handoff_at = created + timedelta(hours=random.randint(2, 18))

            assigned = random.choice(asesores) if asesores and sk != "consulta_inicial" else None
            cscore   = None
            if qual and qual >= 60:
                cscore = min(99, int(qual * 1.05) + random.randint(-5, 10))

            lid = uuid.uuid4()
            lead = Lead(
                id=lid,
                tenant_id=tenant.id,
                branch_id=mty.id,
                wa_phone=phone,
                name=nombre,
                status=status,
                sentiment=LeadSentiment(sent_str),
                source=LeadSource(src_str),
                qualification_score=qual,
                pipeline_stage_id=stage.id if stage else None,
                handoff_at=handoff_at,
                assigned_to=assigned.id if assigned else None,
                current_score=cscore,
                current_score_trend=random.choice(["up", "flat", "down"]),
                qualification_notes=f"Motivo consulta: {motivo}. Edad paciente: {edad} años.",
            )
            db.add(lead)
            new_leads.append(lead)

        await db.flush()

        # Backfill created_at for leads (raw SQL to bypass server_default)
        for i, lead in enumerate(new_leads):
            days_back = random.randint(1, 28)
            created = ts(days_back, hour=random.randint(8, 18), minute=random.randint(0, 59))
            await db.execute(
                text("UPDATE leads SET created_at = :ts WHERE id = :id"),
                {"ts": created, "id": lead.id},
            )

        print(f"  ✓ Leads creados: {len(new_leads)}")

        # ── Conversaciones y mensajes ──────────────────────────────────────────
        print("\n── Conversaciones y mensajes ──")
        conv_count = 0
        msg_total = 0

        for lead in new_leads:
            lead_created = (await db.execute(
                text("SELECT created_at FROM leads WHERE id = :id"), {"id": lead.id}
            )).scalar_one()
            if hasattr(lead_created, 'replace'):
                if lead_created.tzinfo is None:
                    lead_created = lead_created.replace(tzinfo=timezone.utc)

            is_handoff = lead.handoff_at is not None
            cid = uuid.uuid4()
            await db.execute(text("""
                INSERT INTO conversations
                  (id, lead_id, branch_id, status, current_handler, started_at, created_at, updated_at)
                VALUES
                  (:id, :lid, :bid, :status, :handler, :started, :started, :started)
            """), {
                "id": cid, "lid": lead.id, "bid": lead.branch_id,
                "status": "handoff" if is_handoff else "active",
                "handler": "human" if is_handoff else "bot",
                "started": lead_created,
            })
            conv_count += 1

            # Messages: 2-5 exchanges
            n_exchanges = random.randint(2, 4)
            msg_time = lead_created + timedelta(minutes=2)
            is_urgent = lead.sentiment in (LeadSentiment.URGENTE, LeadSentiment.INTERESADO)

            # Patient intro
            intro = f"Hola, {lead.qualification_notes.split('.')[0] if lead.qualification_notes else 'necesito información'}."
            mid = uuid.uuid4()
            await db.execute(text("""
                INSERT INTO messages (id, conversation_id, role, content, created_at, updated_at)
                VALUES (:id, :cid, 'user', :content, :ts, :ts)
            """), {"id": mid, "cid": cid, "content": intro, "ts": msg_time})
            msg_total += 1
            msg_time += timedelta(seconds=random.randint(20, 90))

            for j in range(n_exchanges):
                # Bot reply
                bot_text = BOT_MSGS[j % len(BOT_MSGS)]
                mid = uuid.uuid4()
                await db.execute(text("""
                    INSERT INTO messages
                      (id, conversation_id, role, content, tokens_used, latency_ms, created_at, updated_at)
                    VALUES (:id, :cid, 'assistant', :content, :tok, :lat, :ts, :ts)
                """), {
                    "id": mid, "cid": cid, "content": bot_text,
                    "tok": random.randint(80, 240), "lat": random.randint(800, 3200),
                    "ts": msg_time,
                })
                msg_total += 1
                msg_time += timedelta(seconds=random.randint(10, 60))

                if j < n_exchanges - 1:
                    patient_msgs = PATIENT_MSGS_HIGH if is_urgent else PATIENT_MSGS_LOW
                    mid = uuid.uuid4()
                    await db.execute(text("""
                        INSERT INTO messages (id, conversation_id, role, content, created_at, updated_at)
                        VALUES (:id, :cid, 'user', :content, :ts, :ts)
                    """), {"id": mid, "cid": cid, "content": random.choice(patient_msgs), "ts": msg_time})
                    msg_total += 1
                    msg_time += timedelta(minutes=random.randint(3, 40))

        print(f"  ✓ Conversaciones: {conv_count}")
        print(f"  ✓ Mensajes: {msg_total}")

        # ── Lead scores ────────────────────────────────────────────────────────
        print("\n── Lead scores ──")
        score_count = 0
        MAIN_REASONS = [
            "Urgencia médica confirmada y respuesta rápida al bot",
            "Paciente con diagnóstico previo y alta motivación",
            "Disposición para primera cita dentro de la semana",
            "Estudios recientes disponibles, facilita la consulta",
            "Referido por paciente satisfecho anterior",
        ]
        for lead in new_leads:
            if not lead.current_score:
                continue
            sid = uuid.uuid4()
            neg_json = '{"items": ["Sin confirmar horario"]}' if random.random() < 0.4 else '{"items": []}'
            await db.execute(text("""
                INSERT INTO lead_scores
                  (id, lead_id, tenant_id, score, main_reason, positive_factors, negative_factors, calculated_at, created_at, updated_at)
                VALUES
                  (:id, :lid, :tid, :score, :reason,
                   CAST(:pos AS jsonb), CAST(:neg AS jsonb),
                   :calc, :calc, :calc)
            """), {
                "id": sid, "lid": lead.id, "tid": tenant.id,
                "score": lead.current_score,
                "reason": random.choice(MAIN_REASONS),
                "pos": '{"items": ["Respondió al bot en < 5 min", "Tiene diagnóstico previo"]}',
                "neg": neg_json,
                "calc": NOW - timedelta(hours=random.randint(1, 72)),
            })
            score_count += 1

        print(f"  ✓ Scores: {score_count}")

        # ── Agent suggestions ──────────────────────────────────────────────────
        print("\n── Agent suggestions ──")
        existing_sugg_cnt = (await db.execute(
            text("SELECT count(*) FROM agent_suggestions WHERE tenant_id = :tid"),
            {"tid": tenant.id},
        )).scalar_one()

        if existing_sugg_cnt < 3:
            for spec in AGENT_SUGGESTIONS_DATA:
                target = None
                if spec["role"] == "asesor" and asesores:
                    target = random.choice(asesores).id
                elif spec["role"] == "owner" and owner:
                    target = owner.id

                sid = uuid.uuid4()
                days_ago_n = random.randint(0, 6)
                await db.execute(text("""
                    INSERT INTO agent_suggestions
                      (id, tenant_id, branch_id, agent_type, trigger_description,
                       suggestion_text, target_role, target_user_id, status,
                       expires_at, created_at, updated_at)
                    VALUES
                      (:id, :tid, :bid, :atype, :trigger,
                       :text, :role, :uid, :status,
                       NOW() + INTERVAL '48 hours', :created, :created)
                """), {
                    "id": sid, "tid": tenant.id, "bid": mty.id,
                    "atype": spec["agent_type"], "trigger": spec["trigger"],
                    "text": spec["text"], "role": spec["role"],
                    "uid": target, "status": spec["status"],
                    "created": NOW - timedelta(days=days_ago_n, hours=random.randint(1, 12)),
                })
            print(f"  ✓ {len(AGENT_SUGGESTIONS_DATA)} suggestions creadas")
        else:
            print(f"  → Ya existen {existing_sugg_cnt} suggestions, omitiendo")

        # ── Daily metrics (30 días) ────────────────────────────────────────────
        print("\n── Daily metrics (30 días) ──")
        metric_rows = 0
        for branch in branches:
            for days_back in range(29, -1, -1):
                d = TODAY - timedelta(days=days_back)
                existing = (await db.execute(
                    text("SELECT 1 FROM daily_metrics WHERE branch_id=:b AND metric_date=:d LIMIT 1"),
                    {"b": branch.id, "d": d},
                )).scalar_one_or_none()
                if existing:
                    continue
                is_weekend = d.weekday() >= 5
                m = 0.45 if is_weekend else 1.0
                mid2 = uuid.uuid4()
                await db.execute(text("""
                    INSERT INTO daily_metrics
                      (id, branch_id, tenant_id, metric_date,
                       leads_created, leads_qualified, leads_won, leads_lost,
                       messages_sent, messages_received, calls_logged,
                       tasks_completed, quotes_sent, avg_first_response_sec,
                       metrics_by_agent, created_at, updated_at)
                    VALUES
                      (:id, :bid, :tid, :d,
                       :lc, :lq, :lw, :ll,
                       :ms, :mr, :cl,
                       :tc, 0, :ars,
                       '{}', NOW(), NOW())
                """), {
                    "id": mid2, "bid": branch.id, "tid": tenant.id, "d": d,
                    "lc": max(0, int(random.gauss(3.2, 1.1) * m)),
                    "lq": max(0, int(random.gauss(2.0, 0.9) * m)),
                    "lw": max(0, int(random.gauss(0.9, 0.6) * m)),
                    "ll": max(0, int(random.gauss(0.3, 0.3) * m)),
                    "ms": max(0, int(random.gauss(19, 5) * m)),
                    "mr": max(0, int(random.gauss(23, 6) * m)),
                    "cl": max(0, int(random.gauss(1.5, 1.0) * m)),
                    "tc": max(0, int(random.gauss(2.2, 1.1) * m)),
                    "ars": max(60, int(random.gauss(680, 230))),
                })
                metric_rows += 1

        print(f"  ✓ Daily metrics: {metric_rows} filas ({len(branches)} branches × ~30 días)")

        # ── Sentiment snapshots (30 días) ─────────────────────────────────────
        print("\n── Sentiment snapshots ──")
        snap_rows = 0
        for branch in branches:
            for days_back in range(29, -1, -1):
                d = TODAY - timedelta(days=days_back)
                existing = (await db.execute(
                    text("SELECT 1 FROM sentiment_snapshots WHERE branch_id=:b AND snapshot_date=:d LIMIT 1"),
                    {"b": branch.id, "d": d},
                )).scalar_one_or_none()
                if existing:
                    continue
                # Score trends upward over time (improving clinic performance)
                base = 0.57 + (29 - days_back) * 0.006
                score = min(0.94, max(0.32, base + random.uniform(-0.07, 0.07)))
                n = random.randint(9, 22)
                ni = int(n * random.uniform(0.35, 0.50))
                nu = int(n * random.uniform(0.08, 0.18))
                nn = int(n * random.uniform(0.05, 0.14))
                ne = max(0, n - ni - nu - nn)
                sid2 = uuid.uuid4()
                dist_json = f'{{"interesado":{ni},"urgente":{nu},"neutral":{ne},"negativo":{nn}}}'
                await db.execute(text("""
                    INSERT INTO sentiment_snapshots
                      (id, branch_id, tenant_id, snapshot_date, overall_score,
                       distribution, by_stage, by_agent, created_at, updated_at)
                    VALUES
                      (:id, :bid, :tid, :d, :score,
                       CAST(:dist AS jsonb), CAST('{}' AS jsonb), CAST('{}' AS jsonb), NOW(), NOW())
                """), {
                    "id": sid2, "bid": branch.id, "tid": tenant.id, "d": d,
                    "score": round(score, 4),
                    "dist": dist_json,
                })
                snap_rows += 1

        print(f"  ✓ Sentiment snapshots: {snap_rows} filas")

        # ── Commit ─────────────────────────────────────────────────────────────
        await db.commit()

    print("\n" + "="*55)
    print("  ✓ SEED COMPLETO")
    print("="*55)
    print("""
Cuentas (password: walix2026):
  owner@clinica.com      → ROI, Dashboard owner, todas las sucursales
  doctor@clinica.com     → Dashboard doctor, Pipeline, ROI
  asistente@clinica.com  → Leads asignados, conversaciones
  asesor.sf@clinica.com  → Santa Fe CDMX
  it@clinica.com         → Dashboard IT, integraciones

Frontend: http://localhost:5173
  /dashboard   → KPIs por rol
  /pipeline    → Kanban con 45+ pacientes
  /contacts    → Lista con filtros y sentimiento
  /roi         → Dashboard ROI ($850 MXN/conversión)
  /forecast    → Scores de predicción
  /automations → 8 sugerencias de agentes IA
""")


if __name__ == "__main__":
    asyncio.run(main())
