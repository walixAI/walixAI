"""
Seed pipeline de oportunidades — Clínica Endocrinología Pediátrica
=================================================================
Crea contactos y oportunidades realistas para la sucursal Condesa CDMX.

Uso:
    cd backend
    .venv/bin/python scripts/seed_pipeline.py

Requiere backend corriendo en localhost:8000.
"""

import asyncio
import random
from datetime import date, timedelta

import httpx

# ── Config ────────────────────────────────────────────────────────────────────

BASE = "http://localhost:8000/api"

ASESOR_EMAIL = "asesor.con@clinica.com"
ASESOR_PWD   = "walix2026"
BRANCH_ID    = "0d9e1940-1b73-44d5-b25c-63175012775b"   # Condesa CDMX

TODAY = date.today()

# ── Datos realistas ───────────────────────────────────────────────────────────

CONTACTOS = [
    ("María",      "González Ruiz",       "+5215512345601"),
    ("Roberto",    "Hernández López",     "+5215512345602"),
    ("Laura",      "Martínez Soto",       "+5215512345603"),
    ("Carlos",     "Ramírez Torres",      "+5215512345604"),
    ("Ana",        "Jiménez Peña",        "+5215512345605"),
    ("Francisco",  "López Castro",        "+5215512345606"),
    ("Patricia",   "García Reyes",        "+5215512345607"),
    ("Alejandro",  "Morales Vega",        "+5215512345608"),
    ("Sofía",      "Díaz Mendoza",        "+5215512345609"),
    ("Jorge",      "Cruz Vargas",         "+5215512345610"),
    ("Verónica",   "Flores Sánchez",      "+5215512345611"),
    ("Eduardo",    "Romero Núñez",        "+5215512345612"),
    ("Daniela",    "Torres Ávila",        "+5215512345613"),
    ("Héctor",     "Gutiérrez Lima",      "+5215512345614"),
    ("Gabriela",   "Reyes Medina",        "+5215512345615"),
    ("Ricardo",    "Mendoza Fuentes",     "+5215512345616"),
    ("Claudia",    "Vega Ortega",         "+5215512345617"),
    ("Arturo",     "Sánchez Domínguez",   "+5215512345618"),
    ("Leticia",    "Castillo Ramos",      "+5215512345619"),
    ("Marco",      "Aguirre Paredes",     "+5215512345620"),
]

# (título, monto MXN, probabilidad %, días para cierre, notas)
OPPS_BY_STAGE: dict[str, list[tuple]] = {
    "nuevo": [
        ("Consulta inicial — Santiago (9 años)", 2_500, 20, 30,
         "Mamá refiere que el niño está muy bajo de talla. Contactó por WhatsApp."),
        ("Evaluación talla-peso — Valeria (7 años)", 2_500, 20, 25,
         "Preocupación por sobrepeso desde los 5 años. Papá preguntó precios."),
        ("Consulta nueva — Mateo (11 años)", 2_500, 20, 20,
         "Derivado por pediatra. Sospecha pubertad precoz."),
        ("Consulta hormonal — Camila (8 años)", 2_500, 20, 35,
         "Búsqueda en Google. Quieren segunda opinión sobre hipotiroidismo."),
        ("Primera visita — Diego (10 años)", 2_500, 20, 28,
         "Captado en feria de salud escolar Pedregal. Interés genuino."),
    ],
    "contacto": [
        ("Cita 1ª consulta — Renata (6 años)", 3_200, 40, 18,
         "Ya habló con recepción. Pendiente confirmar horario del miércoles."),
        ("Seguimiento WhatsApp — Emilio (9 años)", 3_200, 45, 15,
         "Enviaron resultados de glucosa. Esperando agenda de endocrinología."),
        ("Consulta presupuestada — Lucía (12 años)", 3_200, 40, 21,
         "Padres recibieron cotización. Preguntan si hay plan de pagos."),
        ("Paciente referido — Andrés (7 años)", 3_200, 50, 12,
         "Referido por Dr. Muñoz del IMSS. Alta probabilidad de conversión."),
        ("Comparando opciones — Mariana (10 años)", 3_200, 35, 20,
         "Mamá comparando con Hospital Ángeles. El precio es el freno principal."),
    ],
    "cita": [
        ("Cita confirmada — Isabella (8 años)", 3_800, 65, 7,
         "Cita el jueves 10am. Solicitar estudios previos: T3, T4, TSH."),
        ("Consulta agendada — Sebastián (11 años)", 3_800, 65, 5,
         "Cita mañana martes 4pm. Talla baja familiar vs. déficit GH."),
        ("Primera visita mañana — Valentina (7 años)", 3_800, 70, 3,
         "Confirmó asistencia por WhatsApp. Viene con abuela. Pago en efectivo."),
        ("Cita Dra. López — Nicolás (9 años)", 3_800, 60, 10,
         "Agenda Dra. López el lunes. Recordatorio enviado hoy."),
        ("Adolescente consulta — Regina (13 años)", 4_200, 65, 8,
         "Problemas menstruales + sospecha SOP. Cita con Dra. López."),
    ],
    "tratamiento": [
        ("Tratamiento hormona crecimiento — Tomás (10)", 48_000, 80, 90,
         "Inició GH hace 3 semanas. Control mensual. Buena adherencia."),
        ("Terapia hipotiroidismo — Andrea (8 años)", 24_000, 85, 60,
         "Levotiroxina ajustada la semana pasada. TSH bajando bien."),
        ("Plan nutricional metabólico — Sofía (11 años)", 18_000, 80, 45,
         "Obesidad infantil con resistencia a insulina. Dieta + metformina."),
        ("Protocolo pubertad precoz — Ximena (6 años)", 36_000, 85, 180,
         "Análogo GnRH mensual. Padres muy comprometidos con el protocolo."),
        ("Protocolo talla baja — Mateo (9 años)", 42_000, 80, 120,
         "Mes 2 de GH. Gana 0.8 cm/mes. Familia muy motivada. Control en 4 semanas."),
        ("Seguimiento diabetes tipo 1 — Pablo (12 años)", 30_000, 90, 90,
         "DM1 diagnosticada hace 6 meses. Excelente control glucémico."),
    ],
    "seguimiento": [
        ("Control TSH post-consulta — Daniela (9 años)", 8_500, 70, 20,
         "Primera consulta hace 3 semanas. TSH en 6.2. Ajustar dosis."),
        ("Revisión 1 mes GH — Lucas (10 años)", 8_500, 75, 15,
         "Bien tolerado. Padres preguntan por IGF-1 adicional."),
        ("Seguimiento nutricional — Fernanda (8 años)", 8_500, 70, 22,
         "Perdió 1.5 kg en el primer mes. Familia coopera. Próxima cita en 30 días."),
        ("Post-tratamiento — Ximena (7 años)", 8_500, 72, 18,
         "Trayectoria de talla mejorando. Reporte escolar muy positivo."),
    ],
    "ganado": [
        ("Alta médica — Camila (9 años)", 52_000, 100, 0,
         "Completó 18 meses de tratamiento GH. Alcanzó percentil 25. ¡Éxito total!"),
        ("Alta endocrinología — Bruno (12 años)", 28_000, 100, 0,
         "Hipotiroidismo compensado. Alta con levotiroxina crónica. Derivado a pediatra."),
        ("Caso cerrado — Isabella R. (10 años)", 15_000, 100, 0,
         "Pubertad precoz controlada. Suspensión análogo GnRH. Evolución normal."),
    ],
    "perdido": [
        ("No regresó — paciente sin nombre", 0, 0, 0,
         "Cita confirmada. No se presentó. 3 intentos de contacto sin respuesta."),
        ("Precio fuera de alcance — familia de Emilio", 0, 0, 0,
         "Eligió clínica de seguro médico. Precio fue el factor determinante."),
        ("Se fue con otro médico — Rodrigo (11 años)", 0, 0, 0,
         "Optó por consulta privada en Hospital Ángeles. Competencia directa."),
    ],
}

# Oportunidades estancadas (sin actividad +14 días)
OPPS_STALE = [
    ("Sin seguimiento — Rodrigo (8 años)", 4_500, 35, "contacto",
     "Vino a consulta hace 3 semanas. Nadie le ha dado seguimiento.", 20),
    ("Presupuesto enviado — familia Torres", 3_800, 30, "contacto",
     "Cotización enviada hace 45 días. Sin respuesta.", 45),
    ("Cita reprogramada 2 veces — Kevin (9)", 3_800, 40, "cita",
     "Ha cancelado dos citas consecutivas. Alta probabilidad de pérdida.", 16),
]

SOURCES = ["whatsapp_inbound", "form", "referral", "manual"]

LOST_REASONS = {
    "precio":       "El precio superó el presupuesto de la familia",
    "competitor":   "Eligió otra clínica o médico particular",
    "no_response":  "No contestó después de 3 intentos de contacto",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def future_date(days: int) -> str | None:
    return (TODAY + timedelta(days=days)).isoformat() if days > 0 else None


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as client:

        # Login
        r = await client.post(f"{BASE}/auth/login",
                              json={"email": ASESOR_EMAIL, "password": ASESOR_PWD})
        r.raise_for_status()
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        print(f"✓ Login como {ASESOR_EMAIL}")

        # Resolver etapas reales desde la API
        board = (await client.get(f"{BASE}/opportunities/board", headers=h)).json()
        stages_raw = board.get("stages", [])
        by_index = sorted(stages_raw, key=lambda s: s["order_index"])

        # Mapear alias → id real por posición y flags won/lost
        open_stages = [s for s in by_index if not s["is_won"] and not s["is_lost"]]
        won_stage  = next((s for s in by_index if s["is_won"]), None)
        lost_stage = next((s for s in by_index if s["is_lost"]), None)

        slug_map: dict[str, str | None] = {
            "nuevo":       open_stages[0]["id"] if len(open_stages) > 0 else None,
            "contacto":    open_stages[1]["id"] if len(open_stages) > 1 else None,
            "cita":        open_stages[2]["id"] if len(open_stages) > 2 else None,
            "tratamiento": open_stages[3]["id"] if len(open_stages) > 3 else None,
            "seguimiento": open_stages[4]["id"] if len(open_stages) > 4 else None,
            "ganado":      won_stage["id"]  if won_stage  else None,
            "perdido":     lost_stage["id"] if lost_stage else None,
        }
        print(f"✓ {len(stages_raw)} etapas encontradas:")
        for s in by_index:
            flag = "(won)" if s["is_won"] else "(lost)" if s["is_lost"] else ""
            key = next((k for k, v in slug_map.items() if v == s["id"]), "?")
            print(f"    [{key:12}] {s['name']}")

        # ── Crear contactos ──────────────────────────────────────────────────
        print(f"\n── Creando {len(CONTACTOS)} contactos ─────────────────────")
        lead_ids: list[str] = []
        for nombre, apellido, tel in CONTACTOS:
            r = await client.post(
                f"{BASE}/v1/contacts",
                headers=h,
                json={
                    "name": nombre,
                    "last_name": apellido,
                    "wa_phone": tel,
                    "prospection_source": random.choice(SOURCES),
                },
            )
            if r.status_code in (200, 201):
                lead_ids.append(r.json()["id"])
                print(f"  + {nombre} {apellido}")
            elif r.status_code == 409:
                # Contacto duplicado — reusar el existente
                existing = (await client.get(
                    f"{BASE}/v1/contacts?search={tel}&limit=1", headers=h
                )).json()
                items = existing.get("items", [])
                if items:
                    lead_ids.append(items[0]["id"])
                    print(f"  ~ {nombre} {apellido} (ya existe)")
                else:
                    print(f"  ✗ {nombre} {apellido} — {r.status_code} {r.text[:60]}")
            else:
                print(f"  ✗ {nombre} {apellido} — {r.status_code} {r.text[:80]}")

        print(f"✓ {len(lead_ids)} contactos disponibles")

        # ── Crear oportunidades por etapa ────────────────────────────────────
        print("\n── Creando oportunidades ────────────────────────────────────")
        opp_count = 0
        lead_cursor = 0

        for stage_key, opps in OPPS_BY_STAGE.items():
            stage_id = slug_map.get(stage_key)
            if not stage_id:
                print(f"  ⚠  Etapa '{stage_key}' no disponible, omitiendo {len(opps)} opps")
                continue

            is_won  = stage_key == "ganado"
            is_lost = stage_key == "perdido"

            for title, amount, prob, close_days, notes in opps:
                lead_id = lead_ids[lead_cursor % len(lead_ids)] if lead_ids else None
                lead_cursor += 1

                payload: dict = {
                    "title":     title,
                    "branch_id": BRANCH_ID,
                    "stage_id":  stage_id,
                    "currency":  "MXN",
                    "notes":     notes,
                    "source":    random.choice(SOURCES),
                }
                if amount:
                    payload["amount"] = str(amount)
                if prob and not is_won and not is_lost:
                    payload["probability"] = prob
                if close_days and not is_won and not is_lost:
                    payload["close_date"] = future_date(close_days)
                if lead_id:
                    payload["lead_id"] = lead_id

                r = await client.post(f"{BASE}/opportunities", headers=h, json=payload)
                if r.status_code not in (200, 201):
                    print(f"  ✗ {title[:45]} — {r.status_code} {r.text[:80]}")
                    continue

                opp_id = r.json()["id"]
                opp_count += 1

                # Marcar como perdida
                if is_lost and amount == 0:
                    rc = random.choice(list(LOST_REASONS.keys()))
                    await client.post(
                        f"{BASE}/opportunities/{opp_id}/lost",
                        headers=h,
                        json={"lost_reason": LOST_REASONS[rc], "reason_code": rc},
                    )

                print(f"  + [{stage_key:12}] {title[:52]}")

        # ── Oportunidades estancadas ──────────────────────────────────────────
        print("\n── Oportunidades estancadas (sin actividad reciente) ─────────")
        for title, amount, prob, stage_key, notes, _ in OPPS_STALE:
            stage_id = slug_map.get(stage_key)
            if not stage_id:
                continue
            lead_id = lead_ids[lead_cursor % len(lead_ids)] if lead_ids else None
            lead_cursor += 1

            payload = {
                "title":       title,
                "branch_id":   BRANCH_ID,
                "stage_id":    stage_id,
                "amount":      str(amount),
                "currency":    "MXN",
                "probability": prob,
                "notes":       notes,
                "source":      random.choice(SOURCES),
                "close_date":  future_date(10),
            }
            if lead_id:
                payload["lead_id"] = lead_id

            r = await client.post(f"{BASE}/opportunities", headers=h, json=payload)
            if r.status_code in (200, 201):
                opp_count += 1
                print(f"  + [estancada    ] {title[:52]}")
            else:
                print(f"  ✗ {title[:45]} — {r.status_code} {r.text[:80]}")

        # ── Resumen ──────────────────────────────────────────────────────────
        board2 = (await client.get(f"{BASE}/opportunities/board", headers=h)).json()
        print("\n── Pipeline final ───────────────────────────────────────────")
        total_opps = 0
        total_mxn  = 0.0
        for s in sorted(board2["stages"], key=lambda x: x["order_index"]):
            n   = s["total"]
            amt = float(s.get("total_amount") or 0)
            total_opps += n
            total_mxn  += amt
            bar  = "█" * min(n, 15)
            flag = " (won)" if s["is_won"] else " (lost)" if s["is_lost"] else ""
            print(f"  {s['name']:28}{bar:15} {n:>3} opps   ${amt:>10,.0f} MXN{flag}")

        print(f"\n  TOTAL: {total_opps} oportunidades  /  ${total_mxn:,.0f} MXN en pipeline")
        print("\n✅ Seed completado")


if __name__ == "__main__":
    asyncio.run(main())
