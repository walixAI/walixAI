"""seed_utel_demo_a.py — Prompt Utel Demo A: usuarios + prospectos + conversaciones.

Puebla el tenant "Universidad Utel" (creado por create_tenant_utel.py, Prompt #1)
con datos simulados para una demo interna del CRM: 1 GERENTE + 3 ASESOR, 160
Leads distribuidos en las 8 stages del funnel de admisiones, Conversations +
Messages reflejando el perfilamiento del bot, y LeadActivity por lead.

SEGURIDAD — confirmado leyendo el código antes de escribir este script (no
asumido):
  - app/agents/follow_up_agent.py, pipeline_agent.py, config_agent.py y
    closing_agent.py SOLO notifican a staff (target_user.wa_phone /
    gerente.wa_phone / owner.wa_phone), nunca directo al lead — y el envío
    está gateado por `if user and user.wa_phone: ...` en los 4. Por eso los
    4 usuarios demo creados acá SIEMPRE llevan wa_phone=None.
  - El único call-site que manda un mensaje directo a lead.wa_phone es
    app/agents/executor.py (_exec_follow_up / _exec_closing), y solo corre
    vía execute_suggestion(), que requiere una AgentSuggestion existente con
    status en ("suggested","accepted","confirmed"). Este script NO crea
    ningún AgentSuggestion (eso es el Prompt Demo C) — así que sembrar
    Leads/Conversations/Messages acá no puede disparar ese path.
  - Grep de todos los call-sites de WhatsAppService.send_text_message en
    app/ confirma que el resto (app/ai/bot_engine.py, app/ai/qualifier.py,
    app/api/internal_wa.py, app/api/leads.py, app/api/support.py,
    app/api/webhooks.py, app/services/alert_generator.py) solo se disparan
    por un mensaje entrante real vía webhook o una acción HTTP explícita del
    dashboard — ninguno se activa por la sola existencia de filas en BD.
  - Conclusión: con wa_phone=None en los 4 usuarios demo Y cero
    AgentSuggestion creados, no hay ningún path de código que pueda mandar
    un WhatsApp saliente real a partir de lo que este script inserta.

Idempotente respecto al tag "Demo — Borrable": si ya existe para el tenant
Utel, no crea nada — imprime cuántos leads ya tiene y sale con código 0.

Uso:
    .venv/Scripts/python.exe scripts/admin/seed_utel_demo_a.py
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.activity import ActivityType, LeadActivity
from app.models.conversation import Conversation, ConversationHandler, ConversationStatus, Message, MessageRole
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.tag import Tag, lead_tags_table
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.tenant_setup import _find_principal_branch

UTEL_EMAIL = "admin@utel.walix.mx"
TAG_NAME = "Demo — Borrable"
TAG_COLOR = "#F59E0B"
DEMO_PASSWORD = "utel2026"

MANIFEST_PATH = Path(__file__).resolve().parent / ".utel_demo_manifest.json"

# ── Nombres — Faker con locale es_MX NO está en requirements.txt (confirmado
# por grep antes de escribir esto) — no se agrega una dependencia nueva solo
# para un script de seed. Lista propia de nombres/apellidos comunes en México.
FIRST_NAMES = [
    "María", "José", "Juan", "Ana", "Luis", "Guadalupe", "Carlos", "Laura",
    "Miguel", "Fernanda", "Alejandro", "Daniela", "Jorge", "Paola", "Ricardo",
    "Karla", "Roberto", "Andrea", "Francisco", "Valeria", "Diego", "Cynthia",
    "Sergio", "Mariana", "Eduardo", "Alejandra", "Antonio", "Gabriela",
    "Manuel", "Itzel", "Raúl", "Ximena", "Arturo", "Jimena", "Emilio",
    "Renata", "Iván", "Perla", "Mauricio", "Montserrat",
]
LAST_NAMES = [
    "García", "Hernández", "Martínez", "López", "González", "Rodríguez",
    "Pérez", "Sánchez", "Ramírez", "Torres", "Flores", "Vázquez", "Morales",
    "Ortiz", "Gutiérrez", "Reyes", "Cruz", "Jiménez", "Mendoza", "Ruiz",
    "Chávez", "Romero", "Álvarez", "Castillo", "Herrera", "Medina", "Aguilar",
    "Vargas", "Guzmán", "Contreras",
]

# NOTA IMPORTANTE — dato ficticio de demo, PENDIENTE de reemplazar por el
# catálogo real de licenciaturas de Utel (viene en el Prompt de Knowledge
# Base). Estas 6 son placeholders genéricos, no necesariamente lo que Utel
# ofrece en su modalidad híbrida real.
CARRERAS_PLACEHOLDER_DEMO = [
    "Administración de Empresas", "Mercadotecnia Digital", "Psicología",
    "Derecho", "Ingeniería Industrial", "Contaduría Pública",
]
SITUACIONES_LABORALES = ["tiempo_completo", "medio_tiempo", "estudiante", "sin_empleo"]
SEDES = ["CDMX", "en_linea"]

# stage_key -> cantidad de leads
STAGE_DISTRIBUTION: dict[str, int] = {
    "new": 40, "profiling": 30, "profiled": 25, "appointment": 20,
    "follow_up": 15, "docs": 12, "enrolled": 10, "lost": 8,
}
assert sum(STAGE_DISTRIBUTION.values()) == 160

# status coherente con la etapa — mapeo explícito pedido por el prompt.
# NOTA: "new" mapea a EN_CALIFICACION, no a LeadStatus.NUEVO — así lo pidió
# el prompt explícitamente (no es un descuido: se sigue el mapeo tal cual
# se especificó, no el que parecería más obvio por el nombre del status).
# "enrolled" también mapea a CALIFICADO — LeadStatus no tiene un valor tipo
# GANADO/INSCRITO, así que se usa CALIFICADO ahí también (documentado acá
# porque el mapeo 1:1 no es obvio).
STAGE_TO_STATUS: dict[str, LeadStatus] = {
    "new": LeadStatus.EN_CALIFICACION,
    "profiling": LeadStatus.EN_CALIFICACION,
    "profiled": LeadStatus.CALIFICADO,
    "appointment": LeadStatus.CALIFICADO,
    "follow_up": LeadStatus.CALIFICADO,
    "docs": LeadStatus.CALIFICADO,
    "enrolled": LeadStatus.CALIFICADO,
    "lost": LeadStatus.PERDIDO,
}

# stages con conversación: todas menos "new" ("profiling o posterior", por
# order_index — new es la única con order_index menor al de profiling).
CONVERSATION_STAGES = {"profiling", "profiled", "appointment", "follow_up", "docs", "enrolled", "lost"}
# stages con qualification_data completo: "profiled" o posterior por
# order_index (incluye "lost" — se interpreta como leads que sí llegaron a
# perfilarse antes de finalmente no inscribirse, más realista que asumir
# que todo lost se cayó a medio perfilamiento).
QUALIFIED_STAGES = {"profiled", "appointment", "follow_up", "docs", "enrolled", "lost"}
# stages con asesor asignado.
ASSIGNED_STAGES = {"appointment", "follow_up", "docs", "enrolled"}
# handler=BOT si stage <= profiled, HUMAN si appointment o posterior.
HUMAN_HANDLER_STAGES = {"appointment", "follow_up", "docs", "enrolled", "lost"}
# conversation CLOSED si enrolled/lost, ACTIVE en cualquier otro caso (de las que tienen conversación).
CLOSED_CONVERSATION_STAGES = {"enrolled", "lost"}


def _full_name(rng: random.Random) -> tuple[str, str]:
    first = rng.choice(FIRST_NAMES)
    last = f"{rng.choice(LAST_NAMES)} {rng.choice(LAST_NAMES)}"
    return first, last


def _biased_created_at(rng: random.Random, now: datetime) -> datetime:
    """Más leads en días recientes, menos en los antiguos (últimos 60 días)."""
    days_ago = int(60 * (rng.random() ** 2))
    return now - timedelta(
        days=days_ago, hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
    )


def _build_qualification_data(rng: random.Random) -> dict:
    return {
        "carrera_interes": rng.choice(CARRERAS_PLACEHOLDER_DEMO),
        "situacion_laboral": rng.choice(SITUACIONES_LABORALES),
        "disponibilidad_fin_de_semana": rng.choice([True, False]),
        "sede_preferida": rng.choice(SEDES),
    }


def _situacion_text(situacion: str) -> str:
    return {
        "tiempo_completo": "Trabajo tiempo completo",
        "medio_tiempo": "Trabajo medio tiempo",
        "estudiante": "Soy estudiante todavía",
        "sin_empleo": "Ahorita no estoy trabajando",
    }[situacion]


def _disponibilidad_text(disponible: bool) -> str:
    return "Sí, sin problema" if disponible else "Los fines de semana se me complica un poco, pero puedo hacer el esfuerzo"


def _sede_text(sede: str) -> str:
    return "CDMX, si se puede presencial" if sede == "CDMX" else "Prefiero la modalidad en línea"


def _build_messages(
    rng: random.Random,
    stage_key: str,
    lead_first_name: str,
    qual: dict | None,
    lead_created_at: datetime,
    asesor_name: str | None,
) -> list[dict]:
    """Retorna una lista de dicts {role, content, sent_by_user_id, created_at}
    (sent_by_user_id se resuelve afuera, acá solo marca True/False)."""
    t = lead_created_at
    msgs: list[dict] = []

    def _bump(minutes_range: tuple[int, int]) -> datetime:
        nonlocal t
        t = t + timedelta(minutes=rng.randint(*minutes_range))
        return t

    msgs.append({
        "role": MessageRole.ASSISTANT, "human": False, "created_at": _bump((1, 3)),
        "content": (
            f"¡Hola {lead_first_name}! 👋 Soy el asistente virtual de Universidad Utel. "
            "Gracias por tu interés en nuestras licenciaturas híbridas. Para conocerte mejor, "
            "¿qué licenciatura te interesa estudiar?"
        ),
    })

    if qual is None:
        # "profiling": perfilamiento incompleto a propósito — 2 de 4 preguntas
        # respondidas, sin llegar a disponibilidad/sede. Coherente con que no
        # tenga qualification_data todavía (sigue "Perfilando").
        carrera = rng.choice(CARRERAS_PLACEHOLDER_DEMO)
        situacion = rng.choice(SITUACIONES_LABORALES)
        msgs.append({"role": MessageRole.USER, "human": False, "created_at": _bump((1, 8)), "content": f"Me interesa {carrera}"})
        msgs.append({
            "role": MessageRole.ASSISTANT, "human": False, "created_at": _bump((1, 3)),
            "content": "¡Excelente elección! Cuéntame, ¿actualmente trabajas tiempo completo, medio tiempo, o eres estudiante?",
        })
        msgs.append({"role": MessageRole.USER, "human": False, "created_at": _bump((2, 15)), "content": _situacion_text(situacion)})
        return msgs

    carrera = qual["carrera_interes"]
    situacion = qual["situacion_laboral"]
    disponible = qual["disponibilidad_fin_de_semana"]
    sede = qual["sede_preferida"]

    msgs.append({"role": MessageRole.USER, "human": False, "created_at": _bump((1, 8)), "content": f"Me interesa {carrera}"})
    msgs.append({
        "role": MessageRole.ASSISTANT, "human": False, "created_at": _bump((1, 3)),
        "content": "¡Excelente elección! Cuéntame, ¿actualmente trabajas tiempo completo, medio tiempo, o eres estudiante?",
    })
    msgs.append({"role": MessageRole.USER, "human": False, "created_at": _bump((2, 15)), "content": _situacion_text(situacion)})
    msgs.append({
        "role": MessageRole.ASSISTANT, "human": False, "created_at": _bump((1, 3)),
        "content": (
            "Perfecto. Nuestro modelo es híbrido: clases en línea entre semana y una sesión "
            "presencial los fines de semana para power skills. ¿Tienes disponibilidad los fines de semana?"
        ),
    })
    msgs.append({"role": MessageRole.USER, "human": False, "created_at": _bump((2, 20)), "content": _disponibilidad_text(disponible)})
    msgs.append({
        "role": MessageRole.ASSISTANT, "human": False, "created_at": _bump((1, 3)),
        "content": "Genial. Por último, ¿prefieres la sede presencial en CDMX o la modalidad 100% en línea?",
    })
    msgs.append({"role": MessageRole.USER, "human": False, "created_at": _bump((2, 30)), "content": _sede_text(sede)})

    if stage_key in ASSIGNED_STAGES and asesor_name:
        extra_count = rng.choice([1, 2])
        fecha = (t + timedelta(days=rng.randint(1, 5))).strftime("%A %d de %B")
        hora = rng.choice(["10:00", "11:30", "13:00", "16:00", "17:30"])
        msgs.append({
            "role": MessageRole.ASSISTANT, "human": False, "created_at": _bump((5, 90)),
            "content": "¡Perfecto! Te voy a conectar con uno de nuestros asesores para resolver tus dudas y ayudarte con la inscripción.",
        })
        if extra_count == 2:
            msgs.append({
                "role": MessageRole.ASSISTANT, "human": True, "created_at": _bump((10, 180)),
                "content": (
                    f"¡Hola {lead_first_name}! Soy {asesor_name}, tu asesor de admisiones en Utel 😊 "
                    f"Quedamos en platicar el {fecha} a las {hora} hrs, ¿te funciona ese horario?"
                ),
            })

    return msgs


async def main() -> int:
    print("=" * 70)
    print("  seed_utel_demo_a.py — Usuarios + Prospectos + Conversaciones (Utel)")
    print("=" * 70)

    rng = random.Random(20260824)
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.email == UTEL_EMAIL))).scalar_one_or_none()
        if tenant is None:
            print(f"\nNo existe el tenant Utel ({UTEL_EMAIL!r}). Correr primero create_tenant_utel.py.")
            return 1

        branch = await _find_principal_branch(tenant.id, db)
        if branch is None:
            print(f"\nEl tenant Utel (id={tenant.id}) no tiene ninguna branch activa.")
            return 1

        # ── Idempotencia respecto al tag ─────────────────────────────────────
        existing_tag = (await db.execute(
            select(Tag).where(Tag.tenant_id == tenant.id, Tag.name == TAG_NAME)
        )).scalar_one_or_none()
        if existing_tag is not None:
            count = (await db.execute(
                select(func.count()).select_from(lead_tags_table).where(
                    lead_tags_table.c.tag_id == existing_tag.id
                )
            )).scalar_one()
            print(
                f"\nEl tag {TAG_NAME!r} ya existe para Utel (tag_id={existing_tag.id}) con "
                f"{count} lead(s) — no se crea nada de nuevo. Correr purge_utel_demo_data.py "
                "primero si querés regenerar la demo."
            )
            return 0

        # ── Stages reales del tenant (no hardcodear IDs) ─────────────────────
        stage_rows = (await db.execute(
            select(PipelineStage).where(
                PipelineStage.tenant_id == tenant.id,
                PipelineStage.is_archived.is_(False),
            )
        )).scalars().all()
        stages_by_key = {s.stage_key: s for s in stage_rows}
        missing = set(STAGE_DISTRIBUTION) - set(stages_by_key)
        if missing:
            print(f"\nFaltan stages esperadas en Utel: {missing}. ¿Se corrió Prompt #1 completo?")
            return 1

        # ── a) Usuarios ───────────────────────────────────────────────────────
        hashed = hash_password(DEMO_PASSWORD)
        gerente = User(
            tenant_id=tenant.id, branch_id=branch.id,
            email="supervisor.utel@walix.mx", name="Supervisor de Admisiones",
            hashed_password=hashed, role=UserRole.GERENTE, wa_phone=None, is_active=True,
        )
        asesores = [
            User(
                tenant_id=tenant.id, branch_id=branch.id,
                email=f"asesor{i}.utel@walix.mx", name=f"Asesor Admisiones {i}",
                hashed_password=hashed, role=UserRole.ASESOR, wa_phone=None, is_active=True,
            )
            for i in (1, 2, 3)
        ]
        new_users = [gerente, *asesores]
        db.add_all(new_users)
        await db.flush()

        # ── Tag ───────────────────────────────────────────────────────────────
        tag = Tag(tenant_id=tenant.id, name=TAG_NAME, color=TAG_COLOR)
        db.add(tag)
        await db.flush()

        # ── Rango de wa_phone reservado — confirmar que no colisiona ─────────
        # Rango completo +5215500000XXX a +5215500001XXX (2000 números) — se
        # consulta cuáles ya están en uso por CUALQUIER lead existente (no
        # solo de Utel) y se seleccionan los primeros 160 libres, en vez de
        # asumir que el bloque entero está disponible.
        full_range = [f"5215500000{i:03d}" for i in range(1000)] + [f"5215500001{i:03d}" for i in range(1000)]
        existing_phones = set((await db.execute(
            select(Lead.wa_phone).where(Lead.wa_phone.in_(full_range))
        )).scalars().all())
        candidate_phones = [p for p in full_range if p not in existing_phones][:160]
        if len(candidate_phones) < 160:
            print(f"\nSolo hay {len(candidate_phones)} números libres en el rango reservado — abortando.")
            return 1
        if existing_phones:
            print(
                f"\nNota: {len(existing_phones)} número(s) del rango reservado ya estaban en uso "
                f"por otro(s) lead(s) existente(s) — se omitieron: {sorted(existing_phones)}"
            )

        # ── b) Leads ──────────────────────────────────────────────────────────
        phone_iter = iter(candidate_phones)
        leads: list[Lead] = []
        lead_meta: dict[int, dict] = {}  # id(lead) -> {stage_key, qual, first_name, asesor, created_at}

        for stage_key, qty in STAGE_DISTRIBUTION.items():
            stage = stages_by_key[stage_key]
            for _ in range(qty):
                first, last = _full_name(rng)
                is_meta = rng.random() < 0.60
                created_at = _biased_created_at(rng, now)

                qual = _build_qualification_data(rng) if stage_key in QUALIFIED_STAGES else None
                asesor = rng.choice(asesores) if stage_key in ASSIGNED_STAGES else None

                lead = Lead(
                    branch_id=branch.id,
                    tenant_id=tenant.id,
                    wa_phone=next(phone_iter),
                    name=first,
                    last_name=last,
                    # prospection_source tiene un CHECK constraint en BD
                    # (ck_leads_prospection_source) que solo permite
                    # whatsapp_inbound/form/referral/manual — "meta_ads" (lo
                    # que pedía el prompt literalmente) NO es un valor válido
                    # ahí, confirmado corriendo el script y leyendo el
                    # constraint real. "form" es el valor correcto para un
                    # lead capturado vía un formulario de ads (Meta Lead Ads
                    # es justamente eso), distinto de `source` (columna
                    # separada, un enum LeadSource que SÍ tiene META_ADS).
                    prospection_source="form" if is_meta else "manual",
                    source=LeadSource.META_ADS if is_meta else LeadSource.MANUAL,
                    status=STAGE_TO_STATUS[stage_key],
                    qualification_data=qual or {},
                    assigned_to=asesor.id if asesor else None,
                    pipeline_stage_id=stage.id,
                    # No hay columna `notes` en Lead (confirmado leyendo el modelo) —
                    # qualification_notes es el campo de texto libre más cercano,
                    # se usa acá solo para marcar el placeholder de canal.
                    qualification_notes="(demo Google Ads)" if not is_meta else None,
                    created_at=created_at,
                )
                leads.append(lead)
                lead_meta[id(lead)] = {
                    "stage_key": stage_key, "qual": qual, "first_name": first, "asesor": asesor,
                    "created_at": created_at,
                }

        db.add_all(leads)
        await db.flush()

        # lead_tags — bulk insert
        await db.execute(
            lead_tags_table.insert(),
            [{"lead_id": lead.id, "tag_id": tag.id} for lead in leads],
        )

        # ── c) Conversations + Messages ──────────────────────────────────────
        conversations: list[Conversation] = []
        conv_meta: dict[int, Lead] = {}  # id(conversation) -> Lead
        for lead in leads:
            meta = lead_meta[id(lead)]
            stage_key = meta["stage_key"]
            if stage_key not in CONVERSATION_STAGES:
                continue
            conv = Conversation(
                lead_id=lead.id,
                branch_id=branch.id,
                status=ConversationStatus.CLOSED if stage_key in CLOSED_CONVERSATION_STAGES else ConversationStatus.ACTIVE,
                current_handler=ConversationHandler.HUMAN if stage_key in HUMAN_HANDLER_STAGES else ConversationHandler.BOT,
                started_at=meta["created_at"],
            )
            conversations.append(conv)
            conv_meta[id(conv)] = lead

        db.add_all(conversations)
        await db.flush()

        messages: list[Message] = []
        for conv in conversations:
            lead = conv_meta[id(conv)]
            meta = lead_meta[id(lead)]
            asesor = meta["asesor"]
            built = _build_messages(
                rng, meta["stage_key"], meta["first_name"], meta["qual"],
                meta["created_at"], asesor.name if asesor else None,
            )
            last_ts = meta["created_at"]
            for m in built:
                messages.append(Message(
                    conversation_id=conv.id,
                    role=m["role"],
                    content=m["content"],
                    sent_by_user_id=asesor.id if (m["human"] and asesor) else None,
                    created_at=m["created_at"],
                ))
                last_ts = m["created_at"]
            conv.last_message_at = last_ts

        db.add_all(messages)

        # ── d) LeadActivity ───────────────────────────────────────────────────
        activities: list[LeadActivity] = []
        for lead in leads:
            meta = lead_meta[id(lead)]
            stage_key = meta["stage_key"]
            source_label = "Meta Ads" if lead.source == LeadSource.META_ADS else "Google Ads (demo)"
            activities.append(LeadActivity(
                lead_id=lead.id, tenant_id=tenant.id, actor_id=None,
                activity_type=ActivityType.NOTE,
                payload={"text": f"Lead capturado vía {source_label}", "source": lead.source.value},
                created_at=meta["created_at"],
            ))
            if stage_key in QUALIFIED_STAGES:
                activities.append(LeadActivity(
                    lead_id=lead.id, tenant_id=tenant.id, actor_id=None,
                    activity_type=ActivityType.STAGE_CHANGE,
                    payload={"text": "Bot completó el perfilamiento del prospecto", "to_stage": "profiled"},
                    created_at=meta["created_at"] + timedelta(hours=rng.randint(1, 6)),
                ))
            asesor = meta["asesor"]
            if stage_key in ASSIGNED_STAGES and asesor:
                activities.append(LeadActivity(
                    lead_id=lead.id, tenant_id=tenant.id, actor_id=asesor.id,
                    activity_type=ActivityType.CALL,
                    payload={"text": "Cita agendada con asesor", "asesor_id": str(asesor.id)},
                    created_at=meta["created_at"] + timedelta(hours=rng.randint(6, 48)),
                ))
        db.add_all(activities)

        await db.flush()

        # ── Seguridad: releer wa_phone de TODOS los usuarios de Utel ─────────
        all_users = (await db.execute(select(User).where(User.tenant_id == tenant.id))).scalars().all()
        no_wa_phone_confirmed = all(u.wa_phone is None for u in all_users)

        # ── e) Manifiesto ────────────────────────────────────────────────────
        manifest = {
            "created_at": now.isoformat(),
            "tenant_id": str(tenant.id),
            "tag_id": str(tag.id),
            "user_ids": [str(u.id) for u in new_users],
            "lead_ids": [str(l.id) for l in leads],
            "conversation_ids": [str(c.id) for c in conversations],
            "message_ids": [str(m.id) for m in messages],
            "activity_ids": [str(a.id) for a in activities],
        }

        await db.commit()

        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # ── f) Resumen ────────────────────────────────────────────────────────
        print("\n✓ Demo sembrada exitosamente\n")
        print(f"  tenant_id = {tenant.id}  branch_id = {branch.id}")
        print(f"  Usuarios creados: 1 GERENTE + 3 ASESOR (password compartido: {DEMO_PASSWORD!r})")
        for u in new_users:
            print(f"    - {u.email:<28} role={u.role.value}")
        print(f"\n  Leads creados: {len(leads)} (tag={TAG_NAME!r}, tag_id={tag.id})")
        for stage_key, qty in STAGE_DISTRIBUTION.items():
            print(f"    {stage_key:<12} {qty}")
        print(f"\n  Conversations: {len(conversations)}")
        print(f"  Messages:      {len(messages)}")
        print(f"  LeadActivity:  {len(activities)}")
        print(f"\n  Manifiesto escrito en: {MANIFEST_PATH}")
        print()
        if no_wa_phone_confirmed:
            print(
                "  ✓ Ningún wa_phone de usuario fue configurado — cero riesgo de "
                "notificaciones salientes reales por agentes proactivos."
            )
        else:
            offenders = [u.email for u in all_users if u.wa_phone is not None]
            print(
                f"  ⚠ ADVERTENCIA: {len(offenders)} usuario(s) de Utel SÍ tienen wa_phone "
                f"configurado (no creados por este script): {offenders}. Esto es una "
                "condición preexistente, no algo que este script haya introducido — "
                "revisar antes de correr agentes proactivos sobre este tenant."
            )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
