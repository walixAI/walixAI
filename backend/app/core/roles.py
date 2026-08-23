"""Constantes de roles compartidas entre módulos.

Única fuente de verdad para roles con acceso cross-branch — resuelve el
hallazgo #1 de docs/PERMISSIONS_DRIFT_BACKLOG.md (leads.py, pipeline.py,
pipelines.py y users.py redefinían esto localmente sin PLATFORM_OWNER,
mientras metrics.py sí lo incluía).
"""
from __future__ import annotations

from app.models.user import UserRole

MULTI_BRANCH_ROLES = frozenset({UserRole.OWNER, UserRole.IT, UserRole.PLATFORM_OWNER})
