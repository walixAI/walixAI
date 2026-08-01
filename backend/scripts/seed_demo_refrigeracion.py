"""seed_demo_refrigeracion.py — Genera datos demo para Frigo Industrial MX.

Empresa mexicana de venta y mantenimiento de equipo de refrigeración industrial.

Crea:
  - Tenant "Frigo Industrial MX" + Company + 2 sucursales (CDMX, Monterrey)
  - 8 usuarios con jerarquía completa (sin platform_owner)
  - FinancePermission: owner tenant-wide, gerentes solo su sucursal
  - 2 pipelines por sucursal (Ventas de Equipo + Mantenimiento y Servicio)
  - 6 categorías de producto (ProductCategory)
  - ~75 leads + ~50 deals (mix Venta/Servicio, ganados/perdidos/abiertos)
  - ExpenseCategories (fijas + variables) + ExpenseRule + ~40 Expenses
  - MonthlyGoals (global, deal_type, product_category) + Assignments
  - 3-5 turnos de Copiloto por usuario AGENT_ROLES
  - 2 CopilotCapabilities (recetas Walix Builder activas)
  - 1 SupportSession ya expirada (Karla Nieto Ibarra)

Uso:
  cd backend
  .venv/bin/python scripts/seed_demo_refrigeracion.py

Es idempotente: detecta lo existente y omite duplicados.
Contraseña de prueba: Demo2026!
"""
from __future__ import annotations

import asyncio
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.ai_memory import AIConversationMessage, CopilotCapability
from app.models.deal import Deal
from app.models.finance import Expense, ExpenseCategory, ExpenseRule, FinancePermission
from app.models.goals import MonthlyGoal, MonthlyGoalAssignment, ProductCategory
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import Pipeline
from app.models.support import SupportSession
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole

random.seed(2026)

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
DEMO_PASSWORD = "Demo2026!"
TENANT_EMAIL = "admin@frigomx.com"


def ts(days_back: int, hour: int = 10, minute: int = 0) -> datetime:
    return (NOW - timedelta(days=days_back)).replace(
        hour=hour, minute=minute, second=0, microsecond=0, tzinfo=timezone.utc
    )


# ── Pipeline stage specs ──────────────────────────────────────────────────────

VENTAS_STAGES = [
    {"key": "v_prospecto",    "label": "Prospecto",            "order": 0, "color": "#3B82F6", "is_won": False, "is_lost": False, "prob": 10},
    {"key": "v_diagnostico",  "label": "Diagnóstico y Cotiz.", "order": 1, "color": "#8B5CF6", "is_won": False, "is_lost": False, "prob": 25},
    {"key": "v_propuesta",    "label": "Propuesta Enviada",    "order": 2, "color": "#F59E0B", "is_won": False, "is_lost": False, "prob": 45},
    {"key": "v_negociacion",  "label": "Negociación",          "order": 3, "color": "#F97316", "is_won": False, "is_lost": False, "prob": 65},
    {"key": "v_orden_compra", "label": "Orden de Compra",      "order": 4, "color": "#22C55E", "is_won": True,  "is_lost": False, "prob": 100},
    {"key": "v_perdido",      "label": "Perdido",              "order": 5, "color": "#EF4444", "is_won": False, "is_lost": True,  "prob": 0},
]

SERVICIO_STAGES = [
    {"key": "s_solicitud",  "label": "Solicitud de Servicio",     "order": 0, "color": "#06B6D4", "is_won": False, "is_lost": False, "prob": 80},
    {"key": "s_visita",     "label": "Visita Técnica Programada", "order": 1, "color": "#3B82F6", "is_won": False, "is_lost": False, "prob": 85},
    {"key": "s_ejecucion",  "label": "En Ejecución",              "order": 2, "color": "#8B5CF6", "is_won": False, "is_lost": False, "prob": 90},
    {"key": "s_concluido",  "label": "Servicio Concluido",        "order": 3, "color": "#22C55E", "is_won": True,  "is_lost": False, "prob": 100},
    {"key": "s_cancelado",  "label": "Cancelado",                 "order": 4, "color": "#EF4444", "is_won": False, "is_lost": True,  "prob": 0},
]

# ── Clientes simulados ────────────────────────────────────────────────────────

CLIENTES_CDMX = [
    ("Grupo Bachoco CDMX",        "interesado",  "meta_ads",        "Cámara frigorífica planta procesadora, budget confirmado Q3"),
    ("Walmart Iztapalapa",        "urgente",     "whatsapp_inbound","Sistema congelación para piso de venta — urgente"),
    ("Lab. Pisa Distribución",    "interesado",  "manual",          "Cuarto frío farmacéutico 2-8°C con certificación"),
    ("Hotel Camino Real CDMX",    "neutral",     "whatsapp_inbound","Mantenimiento preventivo semestral walk-in"),
    ("Sorianas CDMX Norte",       "interesado",  "meta_ads",        "Renovación vitrinas refrigeradas piso de ventas"),
    ("Distribuidora Bimbo CD",    "urgente",     "whatsapp_inbound","Falla compresor cámara distribución — parado"),
    ("Hospital Ángeles CDMX",     "interesado",  "manual",          "Cuarto frío farmacia hospitalaria"),
    ("Alpura Planta DF",          "urgente",     "meta_ads",        "Sistema enfriamiento producción láctea"),
    ("Walmart Tlalpan",           "neutral",     "whatsapp_inbound","Revisión semestral refrigeración"),
    ("Sukarne Distribución",      "urgente",     "meta_ads",        "Cámara maduración carne res 500 m³"),
    ("Costco Perisur",            "interesado",  "meta_ads",        "Instalación freezers industriales"),
    ("Chilchota CDMX",            "interesado",  "manual",          "Mantenimiento correctivo 3 cámaras"),
    ("Pharmex Distribuciones",    "interesado",  "meta_ads",        "Cuarto frío 2-8°C medicamentos controlados"),
    ("Yza Farmacias CDMX",        "neutral",     "whatsapp_inbound","Mantenimiento preventivo anual"),
    ("McDonald's Franquicias",    "urgente",     "meta_ads",        "Reparación urgente sistema congelación"),
    ("Sigma Alimentos CDMX",      "interesado",  "meta_ads",        "Ampliación cámara frigorífica +300 m³"),
    ("Chedraui Santa Fe",         "interesado",  "whatsapp_inbound","Sistema display refrigerado lácteos"),
    ("Sears Perisur",             "neutral",     "manual",          "Chequeo anual equipos instalados"),
    ("Cafés Bola de Oro",         "interesado",  "meta_ads",        "Cuarto frío para granos y roasting"),
    ("Benavides Farmacias",       "negativo",    "whatsapp_inbound","Segunda cotización — precio alto"),
    ("Marinela CDMX",             "interesado",  "meta_ads",        "Renovación sistema enfriamiento masas"),
    ("Sam's Club Insurgentes",    "urgente",     "whatsapp_inbound","Falla compresor urgente zona congelados"),
    ("Liverpool Centro Médico",   "neutral",     "manual",          "Consulta mantenimiento preventivo"),
    ("Vitafil Laboratorios",      "interesado",  "meta_ads",        "Cuarto frío biofarmacéutico estricto"),
    ("Pollo Feliz Franquicia",    "urgente",     "whatsapp_inbound","Compresor dañado — reemplazo urgente"),
    ("Lala CDMX Distribución",    "interesado",  "meta_ads",        "Cámara satélite refrigerada móvil"),
    ("Farmacias del Ahorro",      "interesado",  "whatsapp_inbound","Preventivo 2 sucursales CDMX"),
    ("Pepsico Distribución CD",   "urgente",     "meta_ads",        "Sistema agua helada planta CDMX"),
    ("La Castellana Carnes",      "interesado",  "manual",          "Vitrina exhibición carnes premium"),
    ("Frigorífico Nacional",      "urgente",     "meta_ads",        "Cámara bodega 500 m²"),
    ("Supermercados City",        "neutral",     "whatsapp_inbound","Cotización display refrigerado"),
    ("Nutrisa CDMX",              "interesado",  "meta_ads",        "Cuarto frío helados artesanales"),
    ("Torres Médicas Farmacia",   "interesado",  "manual",          "Refrigerador medicamentos cadena de frío"),
    ("Domino's Logística",        "urgente",     "whatsapp_inbound","Reparación urgente cámara central"),
    ("Yakult CDMX",               "interesado",  "meta_ads",        "Expansión cámara distribución bebidas"),
    ("Starbucks Abasto CDMX",     "neutral",     "manual",          "Mantenimiento preventivo anual"),
    ("La Michoacana Plus",        "urgente",     "whatsapp_inbound","Compresor parado, helados derritiéndose"),
    ("BioLab México",             "interesado",  "meta_ads",        "Freezer -80°C muestras biológicas"),
]

CLIENTES_MTY = [
    ("Gruma Monterrey",           "urgente",     "meta_ads",        "Cámara frigorífica tortillas empacadas"),
    ("Soriana Obispado",          "interesado",  "whatsapp_inbound","Mantenimiento preventivo cadena de frío"),
    ("HEB Monterrey Sur",         "urgente",     "meta_ads",        "Renovación vitrinas refrigeradas piso"),
    ("FEMSA Logística MTY",       "interesado",  "meta_ads",        "Cuarto frío distribución bebidas"),
    ("Vitacilina Laboratorios",   "interesado",  "manual",          "Cuarto frío farmacéutico 2-8°C"),
    ("TGI Fridays Monterrey",     "neutral",     "whatsapp_inbound","Revisión preventiva cocinas"),
    ("Liverpool MTY Valle",       "neutral",     "manual",          "Chequeo semestral equipos"),
    ("Chedraui Contry",           "interesado",  "meta_ads",        "Display refrigerado sección lácteos"),
    ("Marinela Planta MTY",       "urgente",     "whatsapp_inbound","Falla urgente sistema frío producción"),
    ("Sancor Lácteos MTY",        "interesado",  "meta_ads",        "Cámara maduración quesos"),
    ("Farmacia San Pablo MTY",    "interesado",  "whatsapp_inbound","Refrigerador vacunas cadena de frío"),
    ("Costco Monterrey",          "interesado",  "meta_ads",        "Instalación freezers industriales"),
    ("Arca Continental MTY",      "urgente",     "meta_ads",        "Enfriadores planta embotelladora"),
    ("Hospital San José MTY",     "interesado",  "manual",          "Cuarto frío farmacia hospitalaria"),
    ("Sigma Alimentos MTY",       "interesado",  "meta_ads",        "Ampliación cámara materia prima"),
    ("Walmart Cumbres",           "urgente",     "whatsapp_inbound","Compresor zona congelados dañado"),
    ("La Única Carnicería",       "interesado",  "manual",          "Vitrina exhibición y cámara maduración"),
    ("Gasolineras Oxxo MTY",      "neutral",     "whatsapp_inbound","Enfriadoras bebidas mantenimiento"),
    ("Bepensa Bebidas MTY",       "interesado",  "meta_ads",        "Cuarto frío 1,200 m³ distribución"),
    ("Pharmex Noreste",           "interesado",  "meta_ads",        "Ampliación cadena de frío"),
    ("Pizza Hut Franquicias MTY", "neutral",     "manual",          "Preventivo equipos instalados"),
    ("Steak House El Patrón",     "urgente",     "whatsapp_inbound","Cámara carne res parada fin de semana"),
    ("Congelados del Norte",      "urgente",     "meta_ads",        "Cámara congelación -25°C industrial"),
    ("Bachoco Noreste",           "interesado",  "meta_ads",        "Sistema enfriamiento línea producción"),
    ("KidneyBio Laboratorio",     "interesado",  "manual",          "Freezer ultra-bajo -80°C muestras"),
    ("Panadería La Fe MTY",       "neutral",     "whatsapp_inbound","Cámara fermentación pan"),
    ("McDonald's MTY Central",    "urgente",     "whatsapp_inbound","Falla sistema frío cocina — urgente"),
    ("Farmacias Benavides MTY",   "interesado",  "meta_ads",        "Preventivo 5 sucursales zona MTY"),
    ("Supermercados González",    "interesado",  "whatsapp_inbound","Cotización sistema display refrigerado"),
    ("Gatorade Distribución MTY", "urgente",     "meta_ads",        "Enfriadores distribución bebidas isotónicas"),
    ("Restaurante La Única MTY",  "interesado",  "manual",          "Cuarto frío restaurante fino"),
    ("Frigoríficos del Norte",    "interesado",  "meta_ads",        "Cámara 800 m² carne de cerdo"),
    ("Lala MTY Distribución",     "interesado",  "meta_ads",        "Cámara satélite refrigerada"),
    ("Hotel Fiesta Inn MTY",      "neutral",     "whatsapp_inbound","Mantenimiento preventivo anual"),
    ("Bio Science MTY",           "interesado",  "meta_ads",        "Equipos temperatura controlada biofarm"),
    ("Nutri-Mex MTY",             "neutral",     "manual",          "Revisión anual vitrinas"),
    ("Cárnica Los Pinos MTY",     "urgente",     "whatsapp_inbound","Compresor parado cámara principal"),
    ("Cemex Cafetería Industrial","neutral",     "manual",          "Mantenimiento equipos cocina industrial"),
]

# ── Deal templates (title, base_amount, base_cost) ───────────────────────────

VENTA_TMPLS = [
    ("Instalación cámara frigorífica walk-in",          380000, 220000),
    ("Sistema de congelación industrial -20°C",          560000, 310000),
    ("Cuarto frío farmacéutico temperatura controlada",  420000, 240000),
    ("Compresor Copeland + condensador Güntner",         180000,  95000),
    ("Renovación vitrinas refrigeradas piso ventas",     285000, 155000),
    ("Cámara frigorífica 500 m³ con automatización",     850000, 490000),
    ("Sistema agua helada planta industrial",            620000, 360000),
    ("Display refrigerado lineal 12 metros",             220000, 120000),
    ("Freezer -80°C laboratorio biofarmacéutico",       195000, 110000),
    ("Cuarto frío bodega distribución 300 m²",           340000, 190000),
    ("Sistema congelación IQF alimentos procesados",     920000, 530000),
    ("Cámara frigorífica 200 m³ restaurante",            260000, 140000),
    ("Pack compresor + evaporador Danfoss",              145000,  80000),
    ("Sistema enfriamiento masas panadería industrial",  210000, 115000),
    ("Expansión cámara frigorífica existente +300 m³",   310000, 170000),
]

SERVICIO_TMPLS = [
    ("Mantenimiento preventivo semestral 2 cámaras",     14500,  4800),
    ("Reparación compresor parado emergencia",            32000, 12000),
    ("Recarga refrigerante R-404A",                       8500,  2800),
    ("Mantenimiento correctivo evaporador",               18000,  7200),
    ("Sustitución válvula de expansión",                   9500,  3200),
    ("Revisión y ajuste sistema de control",               6800,  2100),
    ("Mantenimiento preventivo anual contrato",           28000,  9500),
    ("Reparación fuga refrigerante R-134a",               12500,  4300),
    ("Cambio motor ventilador condensador",                7200,  2600),
    ("Limpieza y mantenimiento condensadores",             5800,  1900),
    ("Sustitución termostato y controles",                11000,  3800),
    ("Mantenimiento preventivo cadena frío 5 puntos",     35000, 12000),
    ("Diagnóstico y reparación sistema compresor",        22000,  8500),
    ("Mantenimiento preventivo vitrinas 10 unidades",     16000,  5500),
    ("Revisión anual contrato mantenimiento integral",    42000, 14500),
]

# ── Copiloto conversations ────────────────────────────────────────────────────

COPILOT_TURNS: dict[str, list[tuple[str, str]]] = {
    "jorge": [
        ("user",      "¿Cómo vamos contra la meta de ventas de este mes en CDMX?"),
        ("assistant", "**Meta del mes (CDMX):** $1,200,000 MXN\n**Vendido hasta hoy:** $847,000 (70.6%)\n\nFaltan ~8 días hábiles. Para cerrar en meta necesitas $353K adicionales (~$44K/día).\n\n**Deals más cercanos al cierre:**\n- Sigma Alimentos CDMX ($310K) — Negociación\n- Frigorífico Nacional ($380K) — Propuesta Enviada"),
        ("user",      "¿Cuál es la rentabilidad del mes en CDMX?"),
        ("assistant", "**Rentabilidad CDMX (mes actual):**\n- Ingresos: $847,000\n- Gastos: $198,400\n- **Utilidad bruta: $648,600 (76.6%)**\n\nGastos variables ($134K) dominan — principalmente refrigerante y mano de obra subcontratada. Gastos fijos ($64K) en presupuesto."),
    ],
    "alejandra": [
        ("user",      "Muéstrame el run rate de Monterrey este mes"),
        ("assistant", "**Run Rate — Monterrey**\n\n📊 Vendido: $612,000 MXN\n🎯 Meta: $900,000 MXN\n📈 Proyectado: $780,000 (87% de meta)\n\nVan 16 días del mes. A este ritmo cerrarían ~13% bajo meta. 3 deals de servicio urgente podrían mejorar el cierre esta semana."),
        ("user",      "¿Cuántos deals abiertos hay en Monterrey?"),
        ("assistant", "**Deals abiertos — Monterrey:** 14 deals\n\n**Por tipo:**\n- Venta de equipo: 8 deals ($2.1M en pipeline)\n- Servicio/mantenimiento: 6 deals ($198K)\n\n**Por etapa:** Propuesta enviada: 4 · Negociación: 3 · Diagnóstico: 7"),
        ("user",      "¿Cómo está el rendimiento del equipo en MTY?"),
        ("assistant", "**Rendimiento equipo Monterrey (mes actual):**\n\n| Vendedor | Cerrado | Meta | % |\n|---|---|---|---|\n| Lucía Bermúdez | $280K | $350K | 80% |\n| Alejandra Cortés | $332K | $550K | 60% |\n\nLucía va bien en servicio. El pipeline de ventas grandes necesita acelerar cierre."),
    ],
    "felipe": [
        ("user",      "¿Cuáles son mis tareas pendientes de hoy?"),
        ("assistant", "**Tareas pendientes — Ing. Felipe Nájera:**\n\n🔧 Supervisión visita técnica · Arca Continental · Hoy 09:00\n📋 Revisión cotización agua helada · Pepsico CD · Vence hoy\n📞 Seguimiento cierre · Sigma Alimentos · Prioridad alta\n\n3 tareas. ¿Preparo mensaje de seguimiento para algún cliente?"),
        ("user",      "Prepárame un mensaje de WhatsApp para Sigma Alimentos CDMX sobre el status de su propuesta de expansión de cámara"),
        ("assistant", "Aquí tienes el borrador:\n\n---\nBuenos días estimado equipo Sigma Alimentos 👋\n\nLes escribo para dar seguimiento a la propuesta de ampliación de su cámara frigorífica (+300 m³) que les enviamos la semana pasada.\n\nQuedo a sus órdenes para resolver cualquier duda técnica o ajustar la propuesta.\n\n¿Tienen disponibilidad para una llamada breve mañana?\n\nSaludos,\n*Ing. Felipe Nájera Ochoa*\nSupervisor Técnico Senior — Frigo Industrial MX\n---\n\n⚠️ Revisa el borrador antes de enviarlo."),
        ("user",      "¿Cuántos deals tengo asignados a mí?"),
        ("assistant", "**Deals asignados a Ing. Felipe Nájera:**\n\n📂 Total: 7 deals\n- 4 abiertos · $1.24M en pipeline\n- 2 ganados este mes · $560K + $420K\n- 1 perdido · precio\n\nTu deal más grande pendiente: Sistema agua helada Pepsico CD ($620K) en Negociación."),
    ],
    "diego": [
        ("user",      "¿Cómo voy contra mi meta del mes?"),
        ("assistant", "**Tu avance — Diego Armendáriz:**\n\n🎯 Meta asignada: $699,930 (33.3% de meta global)\n💰 Cerrado: $285,000 (40.7%)\n\nFaltan ~8 días hábiles. Tienes 3 deals en Propuesta Enviada por $580K total. Si cierras uno más este mes llegarías a la meta.\n\n**Deal más caliente:** La Michoacana Plus ($145K) — Negociación, 70% probabilidad."),
        ("user",      "Busca a Grupo Bachoco CDMX"),
        ("assistant", "**Grupo Bachoco CDMX**\n\n📋 Status: Calificado · Fuente: Meta Ads\n💬 Interés: Cámara frigorífica planta procesadora\n📊 Etapa deal: Diagnóstico y Cotización · $380,000 MXN\n\nÚltimo contacto: hace 3 días. Budget confirmado para Q3. Requieren certificación HACCP en instalación."),
    ],
    "lucia": [
        ("user",      "¿Cuál es la rentabilidad de los servicios de mantenimiento este mes en MTY?"),
        ("assistant", "**Rentabilidad — Mantenimiento Monterrey:**\n\n💵 Ingresos mantenimiento: $198,000 MXN\n🏭 Costo directo: $68,500 MXN\n**Margen: $129,500 (65.4%)**\n\nEl mantenimiento tiene mejor margen que venta de equipo este mes. Contratos de preventivo anual son los más rentables."),
        ("user",      "¿Cómo van los deals de Soriana Obispado?"),
        ("assistant", "**Soriana Obispado**\n\n📋 Deal activo: Mantenimiento preventivo cadena de frío\n💰 Monto: $35,000 MXN · Etapa: Visita Técnica Programada\n⏳ Cierre esperado: ~15 días\n\nNota del Supervisor Felipe: *\"Cliente requiere acceso nocturno para no interferir con operación.\"*"),
        ("user",      "¿Cuáles son mis sugerencias del Copiloto?"),
        ("assistant", "**Sugerencias para ti — Lucía Bermúdez:**\n\n1. 🔁 **Seguimiento pendiente** · HEB Monterrey Sur · 5 días sin contacto tras cotización $340K\n2. ⚡ **Cierre urgente** · Walmart Cumbres · Cliente esperando tu llamada para aprobar reparación\n3. 📅 **Renovación contrato** · Gruma Monterrey · Contrato mantenimiento vence próximo mes"),
    ],
}


async def main() -> None:
    print("\n" + "=" * 60)
    print("  Walix — Seed Demo: Frigo Industrial MX")
    print("=" * 60 + "\n")

    async with AsyncSessionLocal() as db:
        await db.execute(text("SET LOCAL app.current_tenant_id = '00000000-0000-0000-0000-000000000000'"))
        hashed_pw = hash_password(DEMO_PASSWORD)

        # ── 1. Tenant ─────────────────────────────────────────────────────────
        print("── 1. Tenant ──")
        tenant = (await db.execute(select(Tenant).where(Tenant.email == TENANT_EMAIL))).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                name="Frigo Industrial MX",
                email=TENANT_EMAIL,
                plan=TenantPlan.BUSINESS,
                industry_key="generico",
                industry_label="Refrigeración Industrial",
                entity_name="Cliente",
                entity_plural="Clientes",
                deal_name="Oportunidad",
                deal_plural="Oportunidades",
                is_active=True,
                finance_scope="branch",
            )
            db.add(tenant)
            await db.flush()
            print(f"  ✓ Tenant creado: {tenant.name}")
        else:
            print(f"  → Tenant ya existe: {tenant.name}")

        # ── 2. Company + Branches ─────────────────────────────────────────────
        print("\n── 2. Company + Branches ──")
        company = (await db.execute(
            select(Company).where(Company.tenant_id == tenant.id)
        )).scalar_one_or_none()
        if company is None:
            company = Company(
                tenant_id=tenant.id,
                name="Frigo Industrial MX S.A. de C.V.",
                industry="Refrigeración Industrial",
            )
            db.add(company)
            await db.flush()
            print(f"  ✓ Company creada: {company.name}")
        else:
            print(f"  → Company ya existe: {company.name}")

        def get_or_make_branch(name: str, description: str) -> Branch:
            return Branch(
                company_id=company.id,
                tenant_id=tenant.id,
                name=name,
                is_active=True,
                onboarding_status="active",
                business_description=description,
            )

        branch_cdmx = (await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id, Branch.name == "CDMX")
        )).scalar_one_or_none()
        if branch_cdmx is None:
            branch_cdmx = get_or_make_branch("CDMX", "Sucursal CDMX — venta e instalación refrigeración industrial")
            db.add(branch_cdmx)
            print("  ✓ Branch CDMX creada")
        else:
            print("  → Branch CDMX ya existe")

        branch_mty = (await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id, Branch.name == "Monterrey")
        )).scalar_one_or_none()
        if branch_mty is None:
            branch_mty = get_or_make_branch("Monterrey", "Sucursal Monterrey — venta e instalación refrigeración industrial")
            db.add(branch_mty)
            print("  ✓ Branch Monterrey creada")
        else:
            print("  → Branch Monterrey ya existe")

        await db.flush()
        branches = {"CDMX": branch_cdmx, "Monterrey": branch_mty}

        # ── 3. Usuarios ───────────────────────────────────────────────────────
        print("\n── 3. Usuarios ──")
        USER_SPECS = [
            ("Ricardo Solano Vega",      "ricardo@frigomx.com",   UserRole.OWNER,   None),
            ("Mariana Castañeda Ruiz",   "mariana@frigomx.com",   UserRole.IT,      None),
            ("Jorge Peña Villareal",     "jorge@frigomx.com",     UserRole.GERENTE, "CDMX"),
            ("Alejandra Cortés Mijares", "alejandra@frigomx.com", UserRole.GERENTE, "Monterrey"),
            ("Ing. Felipe Nájera Ochoa", "felipe@frigomx.com",    UserRole.DOCTOR,  "CDMX"),
            ("Diego Armendáriz Solís",   "diego@frigomx.com",     UserRole.ASESOR,  "CDMX"),
            ("Lucía Bermúdez Träger",    "lucia@frigomx.com",     UserRole.ASESOR,  "Monterrey"),
            ("Karla Nieto Ibarra",       "karla@frigomx.com",     UserRole.SOPORTE, None),
        ]

        users: dict[str, User] = {}
        for name, email, role, branch_key in USER_SPECS:
            u = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if u is None:
                u = User(
                    tenant_id=tenant.id,
                    branch_id=branches[branch_key].id if branch_key else None,
                    email=email,
                    name=name,
                    hashed_password=hashed_pw,
                    role=role,
                    is_active=True,
                    email_verified_at=NOW,
                )
                db.add(u)
                print(f"  ✓ {name} ({role.value})")
            else:
                print(f"  → {name} ya existe")
            users[email] = u

        await db.flush()

        owner_u      = users["ricardo@frigomx.com"]
        gerente_cdmx = users["jorge@frigomx.com"]
        gerente_mty  = users["alejandra@frigomx.com"]
        supervisor   = users["felipe@frigomx.com"]
        asesor_cdmx  = users["diego@frigomx.com"]
        asesor_mty   = users["lucia@frigomx.com"]
        karla        = users["karla@frigomx.com"]

        agents_cdmx = [gerente_cdmx, supervisor, asesor_cdmx]
        agents_mty  = [gerente_mty, asesor_mty]

        # ── 4. FinancePermission ──────────────────────────────────────────────
        print("\n── 4. FinancePermission ──")
        fp_specs = [
            (owner_u.id,     None),
            (gerente_cdmx.id, branch_cdmx.id),
            (gerente_mty.id,  branch_mty.id),
        ]
        for user_id, branch_id in fp_specs:
            cond = [
                FinancePermission.tenant_id == tenant.id,
                FinancePermission.user_id == user_id,
                FinancePermission.branch_id.is_(None) if branch_id is None
                else FinancePermission.branch_id == branch_id,
            ]
            existing = (await db.execute(select(FinancePermission).where(*cond))).scalar_one_or_none()
            if existing is None:
                db.add(FinancePermission(
                    tenant_id=tenant.id,
                    user_id=user_id,
                    branch_id=branch_id,
                    granted_by=owner_u.id,
                ))
                label = "tenant-wide" if branch_id is None else ("CDMX" if branch_id == branch_cdmx.id else "Monterrey")
                print(f"  ✓ FinancePermission: {user_id} → {label}")
            else:
                print(f"  → FinancePermission ya existe para {user_id}")

        await db.flush()

        # ── 5. Pipelines + Stages ─────────────────────────────────────────────
        print("\n── 5. Pipelines + Stages ──")
        stage_map: dict[str, dict[str, PipelineStage]] = {}

        for branch_name, branch in branches.items():
            stage_map[branch_name] = {}
            for pipe_name, pipe_default, stages_spec in [
                ("Ventas de Equipo",         True,  VENTAS_STAGES),
                ("Mantenimiento y Servicio",  False, SERVICIO_STAGES),
            ]:
                pipe = (await db.execute(
                    select(Pipeline).where(
                        Pipeline.branch_id == branch.id,
                        Pipeline.name == pipe_name,
                    )
                )).scalar_one_or_none()
                if pipe is None:
                    pipe = Pipeline(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        name=pipe_name,
                        is_default=pipe_default,
                        position=0 if pipe_default else 1,
                    )
                    db.add(pipe)
                    await db.flush()
                    print(f"  ✓ Pipeline '{pipe_name}' — {branch_name}")
                else:
                    print(f"  → Pipeline '{pipe_name}' ya existe en {branch_name}")

                for spec in stages_spec:
                    stage = (await db.execute(
                        select(PipelineStage).where(
                            PipelineStage.branch_id == branch.id,
                            PipelineStage.slug == spec["key"],
                        )
                    )).scalar_one_or_none()
                    if stage is None:
                        stage = PipelineStage(
                            tenant_id=tenant.id,
                            branch_id=branch.id,
                            pipeline_id=pipe.id,
                            name=spec["label"],
                            slug=spec["key"],
                            stage_key=None,  # unique per tenant; leave NULL to avoid cross-branch conflict
                            order_index=spec["order"],
                            color=spec["color"],
                            is_won=spec["is_won"],
                            is_lost=spec["is_lost"],
                            is_active=True,
                            probability_default=spec["prob"],
                        )
                        db.add(stage)
                        await db.flush()
                    stage_map[branch_name][spec["key"]] = stage

        # ── 6. ProductCategories ──────────────────────────────────────────────
        print("\n── 6. ProductCategories ──")
        PROD_CAT_NAMES = [
            "Cámaras Frigoríficas",
            "Compresores y Condensadores",
            "Sistemas de Congelación",
            "Mantenimiento Preventivo",
            "Mantenimiento Correctivo / Emergencia",
            "Repuestos y Refacciones",
        ]
        prod_cats: dict[str, ProductCategory] = {}
        for i, cat_name in enumerate(PROD_CAT_NAMES):
            cat = (await db.execute(
                select(ProductCategory).where(
                    ProductCategory.tenant_id == tenant.id,
                    ProductCategory.name == cat_name,
                )
            )).scalar_one_or_none()
            if cat is None:
                cat = ProductCategory(tenant_id=tenant.id, name=cat_name, is_active=True, position=i)
                db.add(cat)
                print(f"  ✓ ProductCategory: {cat_name}")
            else:
                print(f"  → ProductCategory ya existe: {cat_name}")
            prod_cats[cat_name] = cat

        await db.flush()

        # ── 7. Leads ──────────────────────────────────────────────────────────
        print("\n── 7. Leads ──")
        existing_phones = {
            r[0] for r in (await db.execute(
                select(Lead.wa_phone).where(Lead.tenant_id == tenant.id, Lead.deleted_at.is_(None))
            )).fetchall()
        }

        VENTAS_OPEN = ["v_prospecto", "v_diagnostico", "v_propuesta", "v_negociacion"]
        SERVICIO_OPEN = ["s_solicitud", "s_visita", "s_ejecucion"]

        new_leads: list[Lead] = []
        leads_by_branch: dict[str, list[Lead]] = {"CDMX": [], "Monterrey": []}

        for branch_name, branch, clientes, agents, phone_base in [
            ("CDMX",      branch_cdmx, CLIENTES_CDMX, agents_cdmx, 5553000000),
            ("Monterrey", branch_mty,  CLIENTES_MTY,  agents_mty,  8183000000),
        ]:
            smap = stage_map[branch_name]
            for i, (name, sent_str, src_str, note) in enumerate(clientes):
                phone = f"52{phone_base + i}"
                if phone in existing_phones:
                    continue

                sent = LeadSentiment(sent_str)
                src  = LeadSource(src_str)

                if sent == LeadSentiment.NEGATIVO:
                    status = LeadStatus.PERDIDO
                    stage_key = "v_perdido"
                elif sent == LeadSentiment.URGENTE:
                    status = LeadStatus.ESCALADO
                    stage_key = random.choice(VENTAS_OPEN + SERVICIO_OPEN)
                else:
                    status = random.choice([LeadStatus.NUEVO, LeadStatus.EN_CALIFICACION, LeadStatus.CALIFICADO])
                    stage_key = random.choice(VENTAS_OPEN if random.random() < 0.7 else SERVICIO_OPEN)

                stage = smap.get(stage_key)
                assigned = random.choice(agents)

                lead = Lead(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    wa_phone=phone,
                    name=name,
                    status=status,
                    sentiment=sent,
                    source=src,
                    pipeline_stage_id=stage.id if stage else None,
                    assigned_to=assigned.id,
                    qualification_notes=note,
                )
                db.add(lead)
                new_leads.append(lead)
                leads_by_branch[branch_name].append(lead)

        await db.flush()

        for lead in new_leads:
            days_back = random.randint(1, 60)
            created = ts(days_back, hour=random.randint(8, 18), minute=random.randint(0, 59))
            await db.execute(
                text("UPDATE leads SET created_at = :ts WHERE id = :id"),
                {"ts": created, "id": lead.id},
            )

        print(f"  ✓ Leads: {len(new_leads)} ({len(leads_by_branch['CDMX'])} CDMX, {len(leads_by_branch['Monterrey'])} MTY)")

        # ── 8. Deals ──────────────────────────────────────────────────────────
        print("\n── 8. Deals ──")
        deal_count = 0

        for branch_name, branch, agents, leads in [
            ("CDMX",      branch_cdmx, agents_cdmx, leads_by_branch["CDMX"]),
            ("Monterrey", branch_mty,  agents_mty,  leads_by_branch["Monterrey"]),
        ]:
            existing_cnt = (await db.execute(
                text("""SELECT count(*) FROM deals
                        WHERE tenant_id=:tid
                        AND pipeline_stage_id IN (
                            SELECT id FROM pipeline_stages WHERE branch_id=:bid
                        )"""),
                {"tid": tenant.id, "bid": branch.id},
            )).scalar_one()
            if existing_cnt >= 20:
                print(f"  → Ya existen {existing_cnt} deals en {branch_name}, omitiendo")
                continue

            smap = stage_map[branch_name]
            deal_leads = random.sample(leads, min(25, len(leads)))

            for lead in deal_leads:
                is_venta = random.random() < 0.6
                if is_venta:
                    title_base, base_amt, base_cost = random.choice(VENTA_TMPLS)
                    deal_type = "Venta"
                    open_keys = ["v_prospecto", "v_diagnostico", "v_propuesta", "v_negociacion"]
                    won_key, lost_key = "v_orden_compra", "v_perdido"
                    cat_name = random.choice(["Cámaras Frigoríficas", "Compresores y Condensadores", "Sistemas de Congelación"])
                else:
                    title_base, base_amt, base_cost = random.choice(SERVICIO_TMPLS)
                    deal_type = "Servicio"
                    open_keys = ["s_solicitud", "s_visita", "s_ejecucion"]
                    won_key, lost_key = "s_concluido", "s_cancelado"
                    cat_name = random.choice(["Mantenimiento Preventivo", "Mantenimiento Correctivo / Emergencia", "Repuestos y Refacciones"])

                amount = Decimal(str(round(base_amt * random.uniform(0.85, 1.15), 2)))
                cost   = Decimal(str(round(base_cost * random.uniform(0.85, 1.15), 2)))
                if cost >= amount * Decimal("0.88"):
                    cost = amount * Decimal("0.60")
                cost = round(cost, 2)

                r = random.random()
                if r < 0.40:
                    sk = random.choice(open_keys)
                    is_won, is_lost = False, False
                    prob = smap[sk].probability_default if sk in smap else 50
                    lost_reason = None
                elif r < 0.80:
                    sk = won_key
                    is_won, is_lost, prob, lost_reason = True, False, 100, None
                else:
                    sk = lost_key
                    is_won, is_lost, prob = False, True, 0
                    lost_reason = random.choice(["precio", "competencia", "sin_presupuesto"])

                stage = smap.get(sk)
                if stage is None:
                    continue

                db.add(Deal(
                    tenant_id=tenant.id,
                    lead_id=lead.id,
                    pipeline_stage_id=stage.id,
                    title=f"{title_base} — {lead.name}",
                    amount=amount,
                    cost_amount=cost,
                    probability=prob,
                    expected_close_date=TODAY + timedelta(days=random.randint(-30, 60)),
                    is_won=is_won,
                    is_lost=is_lost,
                    deal_type=deal_type,
                    product_category_id=prod_cats[cat_name].id,
                    owner_id=random.choice(agents).id,
                    source=lead.source.value if lead.source else None,
                    lost_reason=lost_reason,
                ))
                deal_count += 1

        await db.flush()
        print(f"  ✓ Deals creados: {deal_count}")

        # ── 9. ExpenseCategories ──────────────────────────────────────────────
        print("\n── 9. ExpenseCategories ──")
        EXP_CAT_SPECS = [
            ("Renta bodega/taller",           "fijo"),
            ("Nómina técnicos",               "fijo"),
            ("Seguro unidades de servicio",   "fijo"),
            ("Refrigerante y gases",          "variable"),
            ("Refacciones y repuestos",       "variable"),
            ("Combustible y viáticos",        "variable"),
            ("Mano de obra subcontratada",    "variable"),
        ]
        exp_cats: dict[str, ExpenseCategory] = {}
        for cat_name, kind in EXP_CAT_SPECS:
            cat = (await db.execute(
                select(ExpenseCategory).where(
                    ExpenseCategory.tenant_id == tenant.id,
                    ExpenseCategory.name == cat_name,
                )
            )).scalar_one_or_none()
            if cat is None:
                cat = ExpenseCategory(tenant_id=tenant.id, name=cat_name, kind=kind, is_active=True)
                db.add(cat)
                print(f"  ✓ ExpenseCategory: {cat_name} ({kind})")
            else:
                print(f"  → ExpenseCategory ya existe: {cat_name}")
            exp_cats[cat_name] = cat

        await db.flush()

        # ── 10. ExpenseRule ───────────────────────────────────────────────────
        print("\n── 10. ExpenseRule ──")
        rule_name = "Comisión ventas 5%"
        rule_exists = (await db.execute(
            select(ExpenseRule).where(
                ExpenseRule.tenant_id == tenant.id,
                ExpenseRule.name == rule_name,
            )
        )).scalar_one_or_none()
        if rule_exists is None:
            mdo_cat = exp_cats.get("Mano de obra subcontratada")
            db.add(ExpenseRule(
                tenant_id=tenant.id,
                category_id=mdo_cat.id if mdo_cat else None,
                name=rule_name,
                rule_type="percent_of_deal",
                value=Decimal("5.00"),
                deal_type_filter="Venta",
                auto_confirm=False,
                is_active=True,
            ))
            print(f"  ✓ ExpenseRule: {rule_name}")
        else:
            print(f"  → ExpenseRule ya existe: {rule_name}")

        await db.flush()

        # ── 11. Expenses ──────────────────────────────────────────────────────
        print("\n── 11. Expenses ──")
        FIJO_BASE = {
            "CDMX":      {"Renta bodega/taller": 38000, "Nómina técnicos": 95000, "Seguro unidades de servicio": 8500},
            "Monterrey": {"Renta bodega/taller": 28000, "Nómina técnicos": 72000, "Seguro unidades de servicio": 6800},
        }
        VAR_RANGES = {
            "Refrigerante y gases":       (3000, 18000),
            "Refacciones y repuestos":    (2500, 35000),
            "Combustible y viáticos":     (1200, 6000),
            "Mano de obra subcontratada": (5000, 22000),
        }
        exp_count = 0

        for branch_name, branch, gerente in [
            ("CDMX",      branch_cdmx, gerente_cdmx),
            ("Monterrey", branch_mty,  gerente_mty),
        ]:
            existing_cnt = (await db.execute(
                text("SELECT count(*) FROM expenses WHERE tenant_id=:tid AND branch_id=:bid"),
                {"tid": tenant.id, "bid": branch.id},
            )).scalar_one()
            if existing_cnt >= 15:
                print(f"  → Ya existen {existing_cnt} gastos en {branch_name}, omitiendo")
                continue

            # Fixed expenses for last 2 months
            for month_offset in (0, 1):
                ref = TODAY.replace(day=1) - timedelta(days=month_offset * 28)
                for cat_name, base in FIJO_BASE[branch_name].items():
                    cat = exp_cats.get(cat_name)
                    if not cat:
                        continue
                    amt = Decimal(str(round(base * random.uniform(0.97, 1.03), 2)))
                    incurred = date(ref.year, ref.month, random.randint(1, 5))
                    db.add(Expense(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        category_id=cat.id,
                        owner_id=gerente.id,
                        amount=amt,
                        kind="fijo",
                        currency="MXN",
                        incurred_at=incurred,
                        status="confirmed",
                        source="manual",
                        description=f"{cat_name} — {incurred.strftime('%B %Y')}",
                    ))
                    exp_count += 1

            # Variable expenses last 60 days
            for _ in range(10):
                cat_name = random.choice(list(VAR_RANGES.keys()))
                cat = exp_cats.get(cat_name)
                if not cat:
                    continue
                lo, hi = VAR_RANGES[cat_name]
                amt = Decimal(str(round(random.uniform(lo, hi), 2)))
                incurred = TODAY - timedelta(days=random.randint(0, 60))
                db.add(Expense(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    category_id=cat.id,
                    owner_id=random.choice(agents_cdmx if branch_name == "CDMX" else agents_mty).id,
                    amount=amt,
                    kind="variable",
                    currency="MXN",
                    incurred_at=incurred,
                    status="confirmed",
                    source="manual",
                    description=f"{cat_name} — {branch_name}",
                ))
                exp_count += 1

        await db.flush()
        print(f"  ✓ Expenses creados: {exp_count}")

        # ── 12. MonthlyGoals ──────────────────────────────────────────────────
        print("\n── 12. MonthlyGoals ──")
        THIS_YEAR, THIS_MONTH = TODAY.year, TODAY.month
        PREV_MONTH = THIS_MONTH - 1 if THIS_MONTH > 1 else 12
        PREV_YEAR  = THIS_YEAR if THIS_MONTH > 1 else THIS_YEAR - 1

        async def upsert_goal(year: int, month: int, dimension: str,
                               amount: int, dim_text: str | None = None,
                               dim_uuid: uuid.UUID | None = None) -> MonthlyGoal:
            existing = (await db.execute(
                select(MonthlyGoal).where(
                    MonthlyGoal.tenant_id == tenant.id,
                    MonthlyGoal.period_year == year,
                    MonthlyGoal.period_month == month,
                    MonthlyGoal.dimension == dimension,
                    MonthlyGoal.dimension_value_text == dim_text,
                    MonthlyGoal.dimension_value_uuid == dim_uuid,
                )
            )).scalar_one_or_none()
            if existing is not None:
                print(f"  → Meta {dimension!r} {year}/{month} ya existe")
                return existing
            goal = MonthlyGoal(
                tenant_id=tenant.id,
                period_year=year,
                period_month=month,
                amount=Decimal(str(amount)),
                currency="MXN",
                dimension=dimension,
                dimension_value_text=dim_text,
                dimension_value_uuid=dim_uuid,
                is_draft=False,
                created_by=owner_u.id,
            )
            db.add(goal)
            await db.flush()
            print(f"  ✓ Meta {dimension!r} {year}/{month}: ${amount:,}")
            return goal

        goal_curr  = await upsert_goal(THIS_YEAR, THIS_MONTH, "global",         2_100_000)
        _goal_prev = await upsert_goal(PREV_YEAR, PREV_MONTH, "global",         1_900_000)
        _goal_venta = await upsert_goal(THIS_YEAR, THIS_MONTH, "deal_type",    1_500_000, dim_text="Venta")
        _goal_serv  = await upsert_goal(THIS_YEAR, THIS_MONTH, "deal_type",      600_000, dim_text="Servicio")

        cat_camara = prod_cats.get("Cámaras Frigoríficas")
        cat_mant   = prod_cats.get("Mantenimiento Preventivo")
        if cat_camara:
            await upsert_goal(THIS_YEAR, THIS_MONTH, "product_category", 800_000, dim_uuid=cat_camara.id)
        if cat_mant:
            await upsert_goal(THIS_YEAR, THIS_MONTH, "product_category", 350_000, dim_uuid=cat_mant.id)

        # ── 13. MonthlyGoalAssignments ────────────────────────────────────────
        print("\n── 13. GoalAssignments ──")
        ASSIGNMENTS = [
            (asesor_cdmx,  Decimal("33.333"), Decimal("699993")),
            (asesor_mty,   Decimal("33.333"), Decimal("699993")),
            (supervisor,   Decimal("33.334"), Decimal("700014")),
        ]
        for user_u, pct, amt in ASSIGNMENTS:
            existing = (await db.execute(
                select(MonthlyGoalAssignment).where(
                    MonthlyGoalAssignment.goal_id == goal_curr.id,
                    MonthlyGoalAssignment.user_id == user_u.id,
                )
            )).scalar_one_or_none()
            if existing is None:
                db.add(MonthlyGoalAssignment(
                    goal_id=goal_curr.id,
                    tenant_id=tenant.id,
                    user_id=user_u.id,
                    share_percent=pct,
                    amount=amt,
                ))
                print(f"  ✓ {user_u.name} → {pct}% (${amt:,})")
            else:
                print(f"  → Assignment ya existe para {user_u.name}")

        await db.flush()

        # ── 14. AI Conversation history ───────────────────────────────────────
        print("\n── 14. Copiloto AI conversations ──")
        CONV_SPECS = [
            (gerente_cdmx, "copiloto:frigo:gerente_cdmx",  COPILOT_TURNS["jorge"]),
            (gerente_mty,  "copiloto:frigo:gerente_mty",   COPILOT_TURNS["alejandra"]),
            (supervisor,   "copiloto:frigo:supervisor",     COPILOT_TURNS["felipe"]),
            (asesor_cdmx,  "copiloto:frigo:asesor_cdmx",   COPILOT_TURNS["diego"]),
            (asesor_mty,   "copiloto:frigo:asesor_mty",    COPILOT_TURNS["lucia"]),
        ]
        conv_rows = 0
        for user_u, session_id, turns in CONV_SPECS:
            existing_cnt = (await db.execute(
                text("SELECT count(*) FROM ai_conversation_history WHERE user_id=:uid AND session_id=:sid"),
                {"uid": user_u.id, "sid": session_id},
            )).scalar_one()
            if existing_cnt >= len(turns):
                print(f"  → Conversación {session_id} ya existe ({existing_cnt} turnos)")
                continue
            for role, content in turns:
                db.add(AIConversationMessage(
                    tenant_id=tenant.id,
                    user_id=user_u.id,
                    session_id=session_id,
                    role=role,
                    content=content,
                ))
                conv_rows += 1

        await db.flush()
        print(f"  ✓ Mensajes Copiloto: {conv_rows}")

        # ── 15. CopilotCapabilities ───────────────────────────────────────────
        print("\n── 15. CopilotCapabilities (Walix Builder) ──")
        CAP_SPECS = [
            {
                "name": "Recordatorio mantenimiento preventivo",
                "description": "Busca clientes con equipo instalado y prepara mensaje de seguimiento de mantenimiento semestral.",
                "trigger_phrases": ["recordatorio mantenimiento", "clientes equipo instalado", "seguimiento mantenimiento"],
                "steps": [
                    {"tool": "search_contacts", "note": "Buscar clientes con equipo instalado"},
                    {"tool": "prepare_whatsapp_message", "note": "Preparar recordatorio mantenimiento preventivo semestral"},
                ],
            },
            {
                "name": "Alerta visita técnica demorada",
                "description": "Muestra deals en etapa de servicio activo y permite agregar nota de seguimiento para visitas sin cerrar.",
                "trigger_phrases": ["visita sin cerrar", "servicio demorado", "técnico pendiente", "visita sin respuesta"],
                "steps": [
                    {"tool": "get_my_deals", "note": "Ver deals en etapa visita técnica o en ejecución"},
                    {"tool": "add_note", "note": "Agregar nota de seguimiento a deal demorado"},
                ],
            },
        ]
        for spec in CAP_SPECS:
            existing = (await db.execute(
                select(CopilotCapability).where(
                    CopilotCapability.tenant_id == tenant.id,
                    CopilotCapability.name == spec["name"],
                )
            )).scalar_one_or_none()
            if existing is None:
                db.add(CopilotCapability(
                    tenant_id=tenant.id,
                    name=spec["name"],
                    description=spec["description"],
                    kind="recipe",
                    recipe_json={"steps": spec["steps"]},
                    trigger_phrases=spec["trigger_phrases"],
                    scope_type="all",
                    scope_roles=[],
                    scope_user_ids=[],
                    channels=["web"],
                    require_confirmation=False,
                    daily_limit=None,
                    is_active=True,
                    created_by=owner_u.id,
                ))
                print(f"  ✓ Capability: {spec['name']}")
            else:
                print(f"  → Capability ya existe: {spec['name']}")

        await db.flush()

        # ── 16. SupportSession ────────────────────────────────────────────────
        print("\n── 16. SupportSession ──")
        existing_ss = (await db.execute(
            select(SupportSession).where(
                SupportSession.support_user_id == karla.id,
                SupportSession.tenant_id == tenant.id,
            )
        )).scalar_one_or_none()
        if existing_ss is None:
            db.add(SupportSession(
                support_user_id=karla.id,
                tenant_id=tenant.id,
                reason="Verificación configuración inicial tenant demo Frigo Industrial MX",
                access_code="789012",
                code_expires_at=NOW - timedelta(days=8),
                session_expires_at=NOW - timedelta(days=7),
                requested_duration_hours=4,
                scope="readonly",
                status="expired",
                authorized_by=owner_u.id,
                actions_log=[{"action": "login", "ts": str(NOW - timedelta(days=7, hours=3))}],
            ))
            print("  ✓ SupportSession creada (ya expirada)")
        else:
            print("  → SupportSession ya existe")

        # ── Commit ────────────────────────────────────────────────────────────
        await db.commit()

    print("\n" + "=" * 60)
    print("  ✓ SEED COMPLETO — Frigo Industrial MX")
    print("=" * 60)
    print(f"""
Cuentas (password: {DEMO_PASSWORD}):
  ricardo@frigomx.com   → Owner / Director General (finanzas tenant-wide)
  mariana@frigomx.com   → IT / Administradora de Sistemas
  jorge@frigomx.com     → Gerente CDMX (finanzas solo CDMX)
  alejandra@frigomx.com → Gerente Monterrey (finanzas solo MTY)
  felipe@frigomx.com    → Supervisor Técnico Senior (doctor, CDMX)
  diego@frigomx.com     → Asesor de Ventas CDMX
  lucia@frigomx.com     → Asesor de Ventas Monterrey
  karla@frigomx.com     → Soporte Walix (sesión ya expirada)

Frontend: http://localhost:5173
  /dashboard          → KPIs por rol y sucursal
  /pipeline           → Kanban Ventas + Servicio
  /contacts           → ~75 clientes industriales
  /finance            → Gastos + rentabilidad (acceso por rol/sucursal)
  /settings?tab=builder → 2 recetas Walix Builder activas
""")


if __name__ == "__main__":
    asyncio.run(main())
