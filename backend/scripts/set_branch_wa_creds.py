"""Update a branch's WhatsApp credentials in the database.

Usage (run from backend/ directory):

    WA_PHONE_NUMBER_ID=<id> WA_TOKEN=<token> BRANCH_NAME=<name> \
        .venv/bin/python scripts/set_branch_wa_creds.py

On Railway, use the "Run command" option in the service shell, or set those
three variables as temporary env vars before running the script.

WA_PHONE_NUMBER_ID  — found in Meta for Developers → WhatsApp → API Setup
WA_TOKEN            — System User access token or temporary test token
BRANCH_NAME         — e.g. "Monterrey" (must match exactly what's in the DB)
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch

WA_PHONE_NUMBER_ID = os.environ["WA_PHONE_NUMBER_ID"]
WA_TOKEN = os.environ["WA_TOKEN"]
BRANCH_NAME = os.environ.get("BRANCH_NAME", "Monterrey")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Branch).where(Branch.name == BRANCH_NAME))
        branch = result.scalar_one_or_none()

        if branch is None:
            print(f"ERROR: branch '{BRANCH_NAME}' not found in DB.")
            sys.exit(1)

        old_id = branch.wa_phone_number_id
        branch.wa_phone_number_id = WA_PHONE_NUMBER_ID
        branch.wa_token = WA_TOKEN
        await db.commit()

        print(f"✓ Branch: {branch.name} (id={branch.id})")
        print(f"  wa_phone_number_id: {old_id!r} → {WA_PHONE_NUMBER_ID!r}")
        print(f"  wa_token:           ***set*** (length={len(WA_TOKEN)})")


if __name__ == "__main__":
    asyncio.run(main())
