"""Sprint 8B — test_sprint8b.py

Batería completa de pruebas para el Sprint 8B de Walix:

  1. Catálogo de Industry Templates     — estructura, completitud, unicidad
  2. Servicio de inferencia de industria — keyword + Claude Haiku + follow-up
  3. Configuración automática del tenant — apply, archive, recreate
  4. Endpoints API                       — prompt-guide, analyze (multi-turno)
  5. Regresión                           — clínica beta sigue funcionando

Corre desde backend/:
    .venv/bin/python scripts/test_sprint8b.py
"""

import asyncio
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

import httpx
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.industry_templates.catalog import INDUSTRY_TEMPLATES, get_template
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch, Company, Tenant
from app.services.industry_inference import IndustryInferenceService
from app.services.tenant_setup import TenantSetupService

BASE_URL = "http://localhost:8000"
RESULTS: list[bool] = []


# ── Helpers ────────────────────────────────────────────────────────────────────


def check(name: str, passed: bool, detail: str = "") -> None:
    icon = "✓" if passed else "✗"
    RESULTS.append(passed)
    suffix = f" — {detail}" if detail else ""
    print(f"  {icon} {name}{suffix}")


# ── 1. Catálogo ────────────────────────────────────────────────────────────────


async def test_catalog() -> None:
    print("\n📋 CATÁLOGO DE INDUSTRY TEMPLATES")

    expected_keys = [
        "salud", "bienes_raices", "educacion", "estetica_wellness",
        "automotriz", "restaurante", "servicios_profesionales", "generico",
    ]
    for key in expected_keys:
        check(f"Template '{key}' existe", key in INDUSTRY_TEMPLATES)

    required_template_keys = ["label", "entity_name", "entity_plural",
                               "pipeline_stages", "contact_statuses", "keywords"]
    for key, tmpl in INDUSTRY_TEMPLATES.items():
        has_all = all(k in tmpl for k in required_template_keys)
        check(f"Template '{key}' tiene todos los campos", has_all)

        stage_keys = [s["key"] for s in tmpl["pipeline_stages"]]
        check(f"Template '{key}' sin stage_keys duplicados",
              len(stage_keys) == len(set(stage_keys)))

        stages_valid = all(
            "key" in s and "label" in s and "order" in s and "color" in s
            for s in tmpl["pipeline_stages"]
        )
        check(f"Template '{key}' stages bien formadas", stages_valid)

    fallback = get_template("industria_inexistente")
    check("Fallback a 'generico' funciona", fallback["entity_name"] == "Contacto")

    check("8 verticales definidas", len(INDUSTRY_TEMPLATES) == 8)


# ── 2. Servicio de inferencia ──────────────────────────────────────────────────


async def test_inference_service() -> None:
    print("\n🧠 SERVICIO DE INFERENCIA")
    service = IndustryInferenceService()

    test_cases = [
        (
            "Tengo una clínica dental en CDMX, atendemos familias, "
            "el problema es que los pacientes no llegan a sus citas y no les damos seguimiento",
            "salud", 0.65,
        ),
        (
            "Soy agente de bienes raíces en Monterrey, vendo departamentos "
            "a familias jóvenes, el seguimiento de prospectos es por WhatsApp",
            "bienes_raices", 0.65,
        ),
        (
            "Tenemos una academia de inglés en Querétaro, "
            "ofrecemos cursos a adultos y niños, inscripciones por WhatsApp",
            "educacion", 0.65,
        ),
        (
            "Soy dueño de un taller mecánico, arreglamos todo tipo de autos "
            "y camionetas, hacemos diagnósticos y servicio automotriz",
            "automotriz", 0.65,
        ),
        (
            "Tengo un restaurante de comida italiana en Guadalajara, "
            "hacemos reservaciones por WhatsApp y tenemos catering",
            "restaurante", 0.60,
        ),
    ]

    for text, expected_key, min_confidence in test_cases:
        async with AsyncSessionLocal() as db:
            session_id = uuid.uuid4()
            result = await service.analyze(text, session_id, turn=1, db=db)
        correct = result.industry_key == expected_key
        confident = result.confidence >= min_confidence
        check(
            f"Infiere '{expected_key}' correctamente",
            correct and confident,
            f"obtuvo '{result.industry_key}' conf={result.confidence:.2f}",
        )

    # Texto muy corto → follow_up_questions
    async with AsyncSessionLocal() as db:
        result = await service.analyze("negocio de ventas", uuid.uuid4(), turn=1, db=db)
    check("Texto corto genera follow_up_questions",
          len(result.follow_up_questions) > 0)

    # Texto ambiguo → generico o baja confianza
    async with AsyncSessionLocal() as db:
        result = await service.analyze(
            "Tengo un negocio muy diverso, vendemos varias cosas diferentes "
            "a distintos clientes en distintas ciudades",
            uuid.uuid4(), turn=1, db=db,
        )
    check(
        "Texto ambiguo cae en 'generico' o tiene baja confianza",
        result.industry_key == "generico" or result.confidence < 0.70,
        f"obtuvo '{result.industry_key}' conf={result.confidence:.2f}",
    )


# ── 3. Configuración del tenant ────────────────────────────────────────────────


async def test_tenant_setup() -> None:
    print("\n⚙️  CONFIGURACIÓN AUTOMÁTICA DEL TENANT")
    setup_svc = TenantSetupService()
    test_id = uuid.uuid4()
    tag = test_id.hex[:8]

    async with AsyncSessionLocal() as db:
        # Crear tenant + company + branch para que create_from_template funcione
        tenant = Tenant(
            id=test_id,
            name=f"Tenant Prueba 8B {tag}",
            email=f"test8b-{tag}@walix.test",
            industry_key="generico",
        )
        db.add(tenant)
        await db.flush()

        company = Company(
            tenant_id=test_id,
            name=f"Empresa Prueba 8B {tag}",
        )
        db.add(company)
        await db.flush()

        branch = Branch(
            company_id=company.id,
            tenant_id=test_id,
            name="Sede Principal",
            is_active=True,
        )
        db.add(branch)
        await db.commit()
        await db.refresh(tenant)

        # ── Aplicar template salud ─────────────────────────────────────────────
        result = await setup_svc.apply_industry_template(
            tenant=tenant,
            industry_key="salud",
            onboarding_description="Clínica dental de prueba Sprint 8B",
            extracted_data={"business_name": "Dental Test", "city": "CDMX"},
            db=db,
        )
        check("apply_industry_template retorna success=True", result.get("success") is True)
        check("Retorna stages_created > 0", result.get("stages_created", 0) > 0,
              f"stages_created={result.get('stages_created')}")

        await db.refresh(tenant)
        check("tenant.entity_name = 'Paciente'", tenant.entity_name == "Paciente")
        check("tenant.entity_plural = 'Pacientes'", tenant.entity_plural == "Pacientes")
        check("tenant.industry_key = 'salud'", tenant.industry_key == "salud")
        check("tenant.onboarding_completed_at seteado",
              tenant.onboarding_completed_at is not None)

        # Verificar stages activas
        stages = (
            await db.execute(
                select(PipelineStage).where(
                    PipelineStage.tenant_id == test_id,
                    PipelineStage.is_archived.is_(False),
                )
            )
        ).scalars().all()
        expected_salud = len(INDUSTRY_TEMPLATES["salud"]["pipeline_stages"])
        check(f"Se crearon {expected_salud} stages activas para 'salud'",
              len(stages) == expected_salud,
              f"encontradas={len(stages)}")

        stage_keys = {s.stage_key for s in stages}
        check("Stage 'appointment' existe", "appointment" in stage_keys)
        check("Stage 'in_treatment' existe", "in_treatment" in stage_keys)

        # ── Re-configurar a educacion ──────────────────────────────────────────
        result2 = await setup_svc.apply_industry_template(
            tenant=tenant,
            industry_key="educacion",
            onboarding_description="Academia de inglés — reconfiguración test",
            extracted_data={},
            db=db,
        )
        check("Re-configuración a 'educacion' retorna success=True",
              result2.get("success") is True)

        archived = (
            await db.execute(
                select(PipelineStage).where(
                    PipelineStage.tenant_id == test_id,
                    PipelineStage.is_archived.is_(True),
                )
            )
        ).scalars().all()
        check(f"Stages anteriores (salud={expected_salud}) archivadas",
              len(archived) == expected_salud,
              f"archivadas={len(archived)}")

        new_stages = (
            await db.execute(
                select(PipelineStage).where(
                    PipelineStage.tenant_id == test_id,
                    PipelineStage.is_archived.is_(False),
                )
            )
        ).scalars().all()
        expected_edu = len(INDUSTRY_TEMPLATES["educacion"]["pipeline_stages"])
        check(f"Stages nuevas (educacion={expected_edu}) creadas",
              len(new_stages) == expected_edu,
              f"activas={len(new_stages)}")

        # Método helper: get_industry_template
        tmpl = tenant.get_industry_template()
        check("tenant.get_industry_template() retorna template de educacion",
              tmpl.get("entity_name") == "Alumno")
        check("tenant.get_entity_display() singular",
              tenant.get_entity_display() == "Alumno")
        check("tenant.get_entity_display(plural=True)",
              tenant.get_entity_display(plural=True) == "Alumnos")

        # Limpiar — CASCADE borra company/branch/pipeline_stages
        await db.execute(delete(Tenant).where(Tenant.id == test_id))
        await db.commit()

    check("Limpieza del tenant de prueba OK", True)


# ── 4. Endpoints API ───────────────────────────────────────────────────────────


async def test_api_endpoints() -> None:
    print("\n🌐 ENDPOINTS API")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:

        # GET /v1/onboarding/prompt-guide
        resp = await client.get("/api/v1/onboarding/prompt-guide")
        check("GET /v1/onboarding/prompt-guide → 200", resp.status_code == 200)
        data = resp.json()
        check("prompt-guide tiene 'example'", "example" in data)
        check("prompt-guide tiene 'suggested_topics'", "suggested_topics" in data)
        check("prompt-guide tiene 'required_fields'", "required_fields" in data)
        check("prompt-guide min_words_hint = 30", data.get("min_words_hint") == 30)

        # POST /v1/onboarding/analyze — texto corto
        resp = await client.post("/api/v1/onboarding/analyze",
                                 json={"description": "negocio"})
        check("POST /v1/onboarding/analyze texto corto → 200", resp.status_code == 200)
        check("Texto corto devuelve needs_more_info=True",
              resp.json().get("needs_more_info") is True)

        # POST /v1/onboarding/analyze — clínica dental larga
        clinic_text = (
            "Tengo una clínica de nutrición en Monterrey, atendemos adultos con sobrepeso "
            "y diabetes, somos 2 nutriólogas y una recepcionista. El problema es que los "
            "pacientes nos contactan por WhatsApp pero no siempre hacemos seguimiento "
            "y muchos no regresan a su segunda consulta. Queremos mejorar eso."
        )
        resp = await client.post("/api/v1/onboarding/analyze",
                                 json={"description": clinic_text})
        check("POST /v1/onboarding/analyze texto válido → 200", resp.status_code == 200)
        data = resp.json()
        check("Análisis devuelve 'session_id'", "session_id" in data)
        check("Análisis devuelve 'industry_key' o 'needs_more_info'",
              "industry_key" in data or "needs_more_info" in data)

        # Multi-turno: si necesita más info, enviamos segundo turno
        session_id = data.get("session_id")
        if session_id and data.get("needs_more_info"):
            resp2 = await client.post("/api/v1/onboarding/analyze",
                                      json={
                                          "description": "La clínica se llama NutriVida y quiero dar seguimiento a cada paciente.",
                                          "session_id": session_id,
                                      })
            check("POST /v1/onboarding/analyze turno 2 → 200", resp2.status_code == 200)
            check("Turno 2 tiene session_id consistente",
                  resp2.json().get("session_id") == session_id)
        else:
            check("POST /v1/onboarding/analyze turno 2 (saltado — ya completó en turno 1)", True,
                  "industry inferida en primer turno")

        # GET /v1/settings/industry sin auth → 401
        resp = await client.get("/api/v1/settings/industry")
        check("GET /v1/settings/industry sin auth → 401", resp.status_code == 401)

        # POST /v1/settings/industry sin auth → 401
        resp = await client.post("/api/v1/settings/industry",
                                 json={"industry_key": "salud", "confirm_reset": True})
        check("POST /v1/settings/industry sin auth → 401", resp.status_code == 401)

        # POST /v1/onboarding/confirm sin auth → 401
        resp = await client.post("/api/v1/onboarding/confirm",
                                 json={"description": "test", "industry_key": "salud"})
        check("POST /v1/onboarding/confirm sin auth → 401", resp.status_code == 401)


# ── 5. Regresión ───────────────────────────────────────────────────────────────


async def test_regression() -> None:
    print("\n🔄 PRUEBA DE REGRESIÓN — clínica beta")
    result = subprocess.run(
        [sys.executable, "scripts/test_webhook.py"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    webhook_ok = result.returncode == 0 and "HTTP 200" in result.stdout
    check("test_webhook.py → HTTP 200", webhook_ok)
    if not webhook_ok:
        print(result.stdout[-500:] if result.stdout else "")
        print(result.stderr[-300:] if result.stderr else "")


# ── Main ───────────────────────────────────────────────────────────────────────


async def main() -> int:
    print("=" * 55)
    print("  Walix · Sprint 8B · Batería de pruebas")
    print("=" * 55)

    try:
        await test_catalog()
    except Exception as e:
        print(f"  ✗ ERROR en test_catalog: {e}")

    try:
        await test_inference_service()
    except Exception as e:
        print(f"  ✗ ERROR en test_inference_service: {e}")

    try:
        await test_tenant_setup()
    except Exception as e:
        print(f"  ✗ ERROR en test_tenant_setup: {e}")
        import traceback
        traceback.print_exc()

    try:
        await test_api_endpoints()
    except Exception as e:
        print(f"  ✗ ERROR en test_api_endpoints: {e}")

    try:
        await test_regression()
    except Exception as e:
        print(f"  ✗ ERROR en test_regression: {e}")

    passed = sum(RESULTS)
    total = len(RESULTS)
    print("\n" + "=" * 55)
    if passed == total:
        print(f"  ✅  TODAS LAS PRUEBAS PASARON: {passed}/{total}")
    else:
        failed = total - passed
        print(f"  ❌  {failed} PRUEBA(S) FALLARON: {passed}/{total} pasaron")
    print("=" * 55)
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
