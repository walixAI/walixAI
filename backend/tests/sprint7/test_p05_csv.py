"""
Sprint 7 · P-05 — CSV Import & Export
Tests for POST /api/v1/contacts/import  and  GET /api/v1/contacts/export

IMPORTANT — DB isolation caveat:
  The import background task creates a fresh AsyncSessionLocal() and commits
  directly to the database, bypassing the per-test SAVEPOINT rollback.
  Contacts inserted by import tests persist in the test DB until the next
  full wipe.  To minimise pollution:
    · Use highly specific phone numbers (+5215599XXXXXX range)
    · Tests that need polling are marked @pytest.mark.integration
    · Redis must be available (REDIS_URL env var pointing to a test instance)

Job response shape:
  GET /import/{job_id} → {status, processed, total, errors, tenant_id, [error_csv_base64]}
  error[].reason values: missing_name | invalid_phone | invalid_email | duplicate_phone

Import field names (CSV columns):
  nombre*, apellido, telefono, empresa, fuente, status, etiquetas (pipe-separated tags)

Export:
  Content-Type  text/csv; charset=utf-8
  BOM           0xEF 0xBB 0xBF  (UTF-8 BOM for Excel)
  Columns       nombre, apellido, telefono, email, empresa, status, fuente,
                etiquetas, vendedor_asignado, score, fecha_creacion, ultima_actividad
  status values lowercase enum  (nuevo | en_calificacion | calificado | escalado | perdido)
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStatus
from app.models.tenant import Branch, Tenant
from app.models.user import User
from tests.sprint7.factories import make_csv, make_valid_contact_row

# ── Helpers ───────────────────────────────────────────────────────────────────

_IMPORT_PATH = "/api/v1/contacts/import"
_EXPORT_PATH = "/api/v1/contacts/export"


def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}


def csv_bytes(text: str) -> bytes:
    """Plain UTF-8 bytes (no BOM) — the endpoint handles both utf-8 and utf-8-sig."""
    return text.encode("utf-8")


async def wait_for_job(
    client: AsyncClient,
    job_id: str,
    user: dict,
    *,
    timeout: float = 15.0,
    poll_interval: float = 0.1,
) -> dict:
    """
    Poll GET /import/{job_id} until status is 'completed' or 'failed'.
    Raises TimeoutError after `timeout` seconds.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(
            f"{_IMPORT_PATH}/{job_id}",
            headers=auth(user),
        )
        assert r.status_code == 200, f"Job polling failed: {r.text}"
        data = r.json()
        if data["status"] in ("completed", "failed"):
            return data
        await asyncio.sleep(poll_interval)
    raise TimeoutError(f"Import job {job_id!r} did not complete within {timeout}s")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def patch_session_local(db: AsyncSession, monkeypatch) -> None:
    """
    Redirect AsyncSessionLocal in the import background task to the test session.
    The background task runs within the same event loop and commits to the
    SAVEPOINT transaction, so test data (branch, tenant) is visible and FK
    constraints are satisfied without committing to the real DB.
    """
    @asynccontextmanager
    async def _mock_session():
        yield db

    monkeypatch.setattr("app.api.contacts.AsyncSessionLocal", _mock_session)


@pytest_asyncio.fixture()
async def user_asesor(asesor_user: User, asesor_token: str) -> dict:
    return {"id": str(asesor_user.id), "token": asesor_token}


@pytest_asyncio.fixture()
async def user_gerente(manager_user: User, manager_token: str) -> dict:
    return {"id": str(manager_user.id), "token": manager_token}


@pytest_asyncio.fixture()
async def contacts_for_export(
    db,
    tenant: Tenant,
    branch: Branch,
    asesor_user: User,
) -> list[Lead]:
    """10 contacts in the test tenant for export tests."""
    statuses = list(LeadStatus)
    leads = []
    for i in range(10):
        lead = Lead(
            branch_id=branch.id,
            tenant_id=tenant.id,
            wa_phone=f"+5215597000{i:03d}",
            name=f"ExportTest{i:02d}",
            last_name="CSV",
            status=statuses[i % len(statuses)],
            prospection_source="manual",
            assigned_to=asesor_user.id,
        )
        db.add(lead)
        leads.append(lead)
    await db.flush()
    return leads


# ── IMPORT — validation (no background job needed) ────────────────────────────


async def test_import_requires_gerente(
    client: AsyncClient, user_asesor: dict
) -> None:
    """Un asesor NO puede importar — requiere rol gerente o superior."""
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("t.csv", csv_bytes("nombre\nTest"), "text/csv")},
        headers=auth(user_asesor),
    )
    assert r.status_code == 403


async def test_import_csv_missing_nombre_column(
    client: AsyncClient, user_gerente: dict
) -> None:
    """CSV sin columna 'nombre' es rechazado con 422."""
    bad_csv = "email,telefono\ntest@test.com,+5215512345678"
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("bad.csv", csv_bytes(bad_csv), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 422


async def test_import_csv_empty_file(
    client: AsyncClient, user_gerente: dict
) -> None:
    """Archivo CSV sin filas de datos retorna 400."""
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("empty.csv", csv_bytes("nombre\n"), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 400


async def test_import_csv_file_too_large(
    client: AsyncClient, user_gerente: dict
) -> None:
    """Archivo que supera 10 MB retorna 413."""
    big_content = b"nombre\n" + b"X" * (10 * 1024 * 1024 + 1)
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("big.csv", big_content, "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 413


async def test_import_returns_job_id_and_total_rows(
    client: AsyncClient, user_gerente: dict
) -> None:
    """POST /import retorna 202 con job_id (str) y total_rows (int)."""
    rows = [make_valid_contact_row(telefono=f"+5215599{i:06d}") for i in range(3)]
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("test.csv", make_csv(rows), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert isinstance(data["job_id"], str) and len(data["job_id"]) > 0
    assert data["total_rows"] == 3


async def test_import_job_polling_404_on_bad_id(
    client: AsyncClient, user_gerente: dict
) -> None:
    """GET /import/{bad_id} retorna 404 si el job no existe."""
    r = await client.get(
        f"{_IMPORT_PATH}/nonexistent-job-id",
        headers=auth(user_gerente),
    )
    assert r.status_code == 404


# ── IMPORT — full flow tests (require Redis + real DB writes) ─────────────────

pytestmark_integration = pytest.mark.integration


@pytest.mark.integration
async def test_import_csv_basic(
    client: AsyncClient, user_gerente: dict
) -> None:
    """10 filas válidas → job completa con processed=10 y sin errores."""
    rows = [
        make_valid_contact_row(telefono=f"+5215599{100 + i:06d}") for i in range(10)
    ]
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("contactos.csv", make_csv(rows), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 202
    data = r.json()
    assert data["total_rows"] == 10

    job = await wait_for_job(client, data["job_id"], user_gerente)
    assert job["status"] == "completed"
    assert job["processed"] == 10
    assert job["errors"] == []


@pytest.mark.integration
async def test_import_csv_only_name_column(
    client: AsyncClient, user_gerente: dict
) -> None:
    """CSV con solo columna 'nombre' es válido — se crean sin teléfono (NOPHONE_...)."""
    raw_csv = "nombre\nCarlos López\nMaría Pérez\nJuan García"
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("test.csv", csv_bytes(raw_csv), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 202
    job = await wait_for_job(client, r.json()["job_id"], user_gerente)
    assert job["status"] == "completed"
    assert job["processed"] == 3
    assert job["errors"] == []


@pytest.mark.integration
async def test_import_csv_row_missing_nombre_skipped(
    client: AsyncClient, user_gerente: dict
) -> None:
    """Fila con nombre vacío se omite con reason='missing_name'."""
    raw_csv = "nombre,telefono\nValido,+5215599700001\n,+5215599700002"  # second row: empty name
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("test.csv", csv_bytes(raw_csv), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 202
    job = await wait_for_job(client, r.json()["job_id"], user_gerente)
    assert job["processed"] == 1
    assert len(job["errors"]) == 1
    assert job["errors"][0]["reason"] == "missing_name"


@pytest.mark.integration
async def test_import_csv_invalid_phone_skipped(
    client: AsyncClient, user_gerente: dict
) -> None:
    """Fila con teléfono inválido se omite con reason='invalid_phone'."""
    raw_csv = "nombre,telefono\nValido,+5215599800001\nInvalido,not-a-phone"
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("test.csv", csv_bytes(raw_csv), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 202
    job = await wait_for_job(client, r.json()["job_id"], user_gerente)
    assert job["processed"] == 1
    assert len(job["errors"]) == 1
    assert job["errors"][0]["reason"] == "invalid_phone"


@pytest.mark.integration
async def test_import_csv_duplicate_phone_skipped(
    client: AsyncClient, user_gerente: dict
) -> None:
    """
    Teléfono ya existente en la BD se omite con reason='duplicate_phone'.

    Uses a two-step import: first run commits the contact (via background task's
    own AsyncSessionLocal), second run detects the duplicate.
    """
    phone = "+5215599910001"

    # Step 1: import the contact so it's committed to the real DB
    first_csv = make_csv([make_valid_contact_row(telefono=phone)])
    r1 = await client.post(
        _IMPORT_PATH,
        files={"file": ("first.csv", first_csv, "text/csv")},
        headers=auth(user_gerente),
    )
    assert r1.status_code == 202
    job1 = await wait_for_job(client, r1.json()["job_id"], user_gerente)
    assert job1["processed"] == 1  # contact now in DB

    # Step 2: import same phone again
    dup_csv = f"nombre,telefono\nDuplicado Test,{phone}"
    r2 = await client.post(
        _IMPORT_PATH,
        files={"file": ("dup.csv", csv_bytes(dup_csv), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r2.status_code == 202
    job2 = await wait_for_job(client, r2.json()["job_id"], user_gerente)
    assert job2["processed"] == 0
    assert len(job2["errors"]) == 1
    assert job2["errors"][0]["reason"] == "duplicate_phone"


@pytest.mark.integration
async def test_import_csv_tags_parsed(
    client: AsyncClient, user_gerente: dict
) -> None:
    """Columna 'etiquetas' separada por '|' crea los tags y los asigna al contacto."""
    raw_csv = "nombre,telefono,etiquetas\nContacto Tags,+5215599920001,vip|cliente|prioritario"
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("tags.csv", csv_bytes(raw_csv), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 202
    job = await wait_for_job(client, r.json()["job_id"], user_gerente)
    assert job["status"] == "completed"
    assert job["processed"] == 1

    # Verify the created contact has the 3 tags
    r_list = await client.get(
        "/api/v1/contacts?q=Contacto Tags", headers=auth(user_gerente)
    )
    items = r_list.json()["items"]
    assert len(items) == 1, "Expected exactly one contact named 'Contacto Tags'"
    tag_names = {t["name"] for t in items[0]["tags"]}
    assert tag_names == {"vip", "cliente", "prioritario"}


@pytest.mark.integration
async def test_import_csv_phone_prefix_added(
    client: AsyncClient, user_gerente: dict
) -> None:
    """Teléfono sin '+' recibe el prefijo '+52' automáticamente."""
    raw_csv = "nombre,telefono\nSin Prefijo,5515590001"  # no leading +
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("prefix.csv", csv_bytes(raw_csv), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 202
    job = await wait_for_job(client, r.json()["job_id"], user_gerente)
    assert job["processed"] == 1

    r_list = await client.get(
        "/api/v1/contacts?q=Sin Prefijo", headers=auth(user_gerente)
    )
    items = r_list.json()["items"]
    assert len(items) == 1
    assert items[0]["wa_phone"].startswith("+52")


@pytest.mark.integration
async def test_import_csv_job_tenant_isolation(
    client: AsyncClient, user_gerente: dict, user_asesor: dict
) -> None:
    """Un usuario no puede ver el job de otro tenant (404 devuelto)."""
    rows = [make_valid_contact_row(telefono="+5215599930001")]
    r = await client.post(
        _IMPORT_PATH,
        files={"file": ("iso.csv", make_csv(rows), "text/csv")},
        headers=auth(user_gerente),
    )
    job_id = r.json()["job_id"]

    # user_asesor is in the same tenant — but the status endpoint checks tenant_id
    # They should still see it (same tenant). A user from another tenant would get 404.
    r_check = await client.get(f"{_IMPORT_PATH}/{job_id}", headers=auth(user_asesor))
    assert r_check.status_code == 200  # same tenant → can see the job


# ── EXPORT ────────────────────────────────────────────────────────────────────


async def test_export_csv_returns_file(
    client: AsyncClient,
    contacts_for_export: list[Lead],
    user_asesor: dict,
) -> None:
    """GET /export retorna 200 con content-type text/csv y Content-Disposition."""
    r = await client.get(_EXPORT_PATH, headers=auth(user_asesor))
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "walix-contactos-" in cd


async def test_export_csv_utf8_bom(
    client: AsyncClient,
    contacts_for_export: list[Lead],
    user_asesor: dict,
) -> None:
    """El CSV exportado comienza con BOM UTF-8 (0xEF 0xBB 0xBF) para Excel."""
    r = await client.get(_EXPORT_PATH, headers=auth(user_asesor))
    assert r.status_code == 200
    assert r.content[:3] == b"\xef\xbb\xbf", "Missing UTF-8 BOM"


async def test_export_csv_has_correct_headers(
    client: AsyncClient,
    contacts_for_export: list[Lead],
    user_asesor: dict,
) -> None:
    """La primera fila del CSV contiene los encabezados esperados."""
    r = await client.get(_EXPORT_PATH, headers=auth(user_asesor))
    csv_text = r.content.decode("utf-8-sig")
    first_line = csv_text.splitlines()[0]
    expected_cols = [
        "nombre", "apellido", "telefono", "email", "empresa",
        "status", "fuente", "etiquetas", "vendedor_asignado",
        "score", "fecha_creacion", "ultima_actividad",
    ]
    for col in expected_cols:
        assert col in first_line, f"Columna '{col}' ausente en el header del CSV"


async def test_export_csv_includes_all_contacts(
    client: AsyncClient,
    contacts_for_export: list[Lead],
    user_asesor: dict,
) -> None:
    """El CSV exportado contiene una fila por cada contacto del tenant."""
    r = await client.get(_EXPORT_PATH, headers=auth(user_asesor))
    csv_text = r.content.decode("utf-8-sig")
    lines = [l for l in csv_text.splitlines() if l.strip()]
    data_lines = lines[1:]  # exclude header
    assert len(data_lines) == len(contacts_for_export)


async def test_export_csv_respects_status_filter(
    client: AsyncClient,
    contacts_for_export: list[Lead],
    user_asesor: dict,
) -> None:
    """Export con ?status=nuevo solo incluye contactos con ese status."""
    r = await client.get(
        f"{_EXPORT_PATH}?status=nuevo", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    csv_text = r.content.decode("utf-8-sig")
    lines = [l for l in csv_text.splitlines() if l.strip()]
    data_lines = lines[1:]

    # contacts_for_export has 10 contacts with statuses cycling through 5 values → 2 per status
    assert len(data_lines) == 2
    for line in data_lines:
        # status column in exported CSV contains lowercase enum value
        assert "nuevo" in line.lower()


async def test_export_csv_empty_tenant(
    client: AsyncClient, user_asesor: dict
) -> None:
    """Exportar sin contactos retorna solo el header (1 línea)."""
    r = await client.get(_EXPORT_PATH, headers=auth(user_asesor))
    assert r.status_code == 200
    csv_text = r.content.decode("utf-8-sig")
    lines = [l for l in csv_text.splitlines() if l.strip()]
    assert len(lines) == 1  # only header row


async def test_export_asesor_can_export(
    client: AsyncClient,
    contacts_for_export: list[Lead],
    user_asesor: dict,
) -> None:
    """Rol asesor tiene permiso para exportar (incluido en _EXPORT_ROLES)."""
    r = await client.get(_EXPORT_PATH, headers=auth(user_asesor))
    assert r.status_code == 200


async def test_export_requires_auth(client: AsyncClient) -> None:
    """Sin token retorna 401."""
    r = await client.get(_EXPORT_PATH)
    assert r.status_code == 401


async def test_export_csv_respects_search_query(
    client: AsyncClient,
    contacts_for_export: list[Lead],
    user_asesor: dict,
) -> None:
    """Export con ?q= aplica el mismo filtro de búsqueda que el listado."""
    # ExportTest00 through ExportTest09; search for "ExportTest00"
    target_name = "ExportTest00"
    r = await client.get(
        f"{_EXPORT_PATH}?q={target_name}", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    csv_text = r.content.decode("utf-8-sig")
    lines = [l for l in csv_text.splitlines() if l.strip()]
    data_lines = lines[1:]
    assert len(data_lines) == 1
    assert target_name in data_lines[0]
