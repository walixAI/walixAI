"""
Sprint 7 factory_boy factories with Mexican locale data.

Usage:
    from tests.sprint7.factories import ContactFactory, ActivityFactory, TagFactory, make_csv

    contact = ContactFactory(branch_id=branch.id, tenant_id=tenant.id)
    csv_bytes = make_csv([{"nombre": "Ana", "telefono": "+5215512345678"}])
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import factory
from factory.alchemy import SQLAlchemyModelFactory
from faker import Faker

from app.models.activity import Activity, ACTIVITY_TYPES
from app.models.lead import Lead, LeadStatus
from app.models.tag import Tag
from app.models.tenant import Branch, Company, Tenant
from app.models.user import User, UserRole

fake = Faker("es_MX")

# ── Base ──────────────────────────────────────────────────────────────────────


class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session_persistence = "flush"


# ── Tenant / Org ──────────────────────────────────────────────────────────────


class TenantFactory(BaseFactory):
    class Meta:
        model = Tenant

    name = factory.LazyFunction(lambda: fake.company())
    email = factory.LazyFunction(lambda: fake.company_email())
    plan = "pro"
    is_active = True


class CompanyFactory(BaseFactory):
    class Meta:
        model = Company

    tenant_id = factory.LazyFunction(uuid.uuid4)
    name = factory.LazyFunction(lambda: fake.company())


class BranchFactory(BaseFactory):
    class Meta:
        model = Branch

    company_id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.LazyFunction(uuid.uuid4)
    name = factory.LazyFunction(lambda: fake.city())
    is_active = True


# ── User ──────────────────────────────────────────────────────────────────────


class UserFactory(BaseFactory):
    class Meta:
        model = User

    tenant_id = factory.LazyFunction(uuid.uuid4)
    branch_id = factory.LazyFunction(uuid.uuid4)
    email = factory.LazyFunction(lambda: fake.email())
    name = factory.LazyFunction(lambda: fake.first_name())
    hashed_password = "$2b$12$testhash"  # not valid — don't use for auth tests
    role = UserRole.ASESOR
    is_active = True


# ── Contact (Lead) ────────────────────────────────────────────────────────────


def _mx_phone() -> str:
    """E.164 MX mobile number."""
    area = fake.numerify("##")
    number = fake.numerify("########")
    return f"+521{area}{number}"


class ContactFactory(BaseFactory):
    class Meta:
        model = Lead

    branch_id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.LazyFunction(uuid.uuid4)
    wa_phone = factory.LazyFunction(_mx_phone)
    name = factory.LazyFunction(lambda: fake.first_name())
    last_name = factory.LazyFunction(lambda: fake.last_name())
    company = factory.LazyFunction(lambda: fake.company())
    status = factory.Iterator(list(LeadStatus))
    prospection_source = "manual"


class ContactFactory_Nuevo(ContactFactory):
    """Factory pre-set to LeadStatus.NUEVO."""
    status = LeadStatus.NUEVO


class ContactFactory_Calificado(ContactFactory):
    status = LeadStatus.CALIFICADO


# ── Tag ───────────────────────────────────────────────────────────────────────

_TAG_COLORS = ["#7C3AED", "#0891B2", "#059669", "#D97706", "#DC2626", "#DB2777"]
_TAG_NAMES = ["VIP", "Recurrente", "Demo", "Frío", "Caliente", "Urgente", "Prospecto"]


class TagFactory(BaseFactory):
    class Meta:
        model = Tag

    tenant_id = factory.LazyFunction(uuid.uuid4)
    name = factory.Iterator(_TAG_NAMES)
    color = factory.Iterator(_TAG_COLORS)


# ── Activity ──────────────────────────────────────────────────────────────────


class ActivityFactory(BaseFactory):
    class Meta:
        model = Activity

    lead_id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.LazyFunction(uuid.uuid4)
    activity_type = factory.Iterator(list(ACTIVITY_TYPES))
    title = factory.LazyFunction(lambda: fake.sentence(nb_words=5))
    body = factory.LazyFunction(lambda: fake.paragraph(nb_sentences=2))
    created_by = factory.LazyFunction(uuid.uuid4)


class NoteFactory(ActivityFactory):
    activity_type = "note"
    title = factory.LazyFunction(lambda: f"Nota: {fake.sentence(nb_words=4)}")


class TaskFactory(ActivityFactory):
    activity_type = "task"
    title = factory.LazyFunction(lambda: f"Tarea: {fake.sentence(nb_words=4)}")
    due_date = factory.LazyFunction(
        lambda: datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    )


# ── CSV helper ────────────────────────────────────────────────────────────────

# Full set of columns accepted by the import endpoint
_IMPORT_COLUMNS = ["nombre", "apellido", "telefono", "empresa", "fuente", "status"]


def make_csv(
    rows: list[dict[str, str]],
    *,
    extra_columns: list[str] | None = None,
    encoding: str = "utf-8-sig",
) -> bytes:
    """
    Build a UTF-8 BOM CSV bytes object ready to POST as a file upload.

    Args:
        rows: List of dicts. Keys should match import column names.
        extra_columns: Additional column names appended after the standard ones.
        encoding: Default is UTF-8 with BOM (matches template download).

    Returns:
        Raw bytes of the CSV file.

    Examples:
        >>> make_csv([{"nombre": "Ana", "telefono": "+5215512345678"}])
    """
    columns = list(_IMPORT_COLUMNS)
    if extra_columns:
        columns += extra_columns

    buf = io.StringIO()
    writer = __import__("csv").DictWriter(
        buf,
        fieldnames=columns,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    return buf.getvalue().encode(encoding)


def make_valid_contact_row(
    *,
    nombre: str | None = None,
    telefono: str | None = None,
) -> dict[str, str]:
    """Return a dict with all required fields filled with valid MX data."""
    return {
        "nombre": nombre or fake.first_name(),
        "apellido": fake.last_name(),
        "telefono": telefono or _mx_phone(),
        "empresa": fake.company(),
        "fuente": "manual",
        "status": "nuevo",
    }
